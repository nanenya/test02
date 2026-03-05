#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/ollama_client.py
"""Ollama 로컬 LLM 클라이언트.

8GB RAM 환경 기준 모델:
  HIGH    : qwen2.5-coder:7b  (~4.5GB, 코딩 고성능)
  STANDARD: qwen2.5-coder:3b  (~2.0GB, 코딩 경량/균형)

Gemini/Claude 클라이언트와 동일한 함수 인터페이스를 제공합니다.
"""

import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

import httpx
from dotenv import load_dotenv

from .models import ExecutionGroup
from .tool_registry import get_filtered_tool_descriptions
from .constants import HISTORY_MAX_CHARS, truncate_history as _truncate_history
from . import agent_config_manager as _acm

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
HIGH_PERF_MODEL_NAME = os.getenv("OLLAMA_HIGH_PERF_MODEL", "qwen2.5-coder:7b")
STANDARD_MODEL_NAME = os.getenv("OLLAMA_STANDARD_MODEL", "qwen2.5-coder:3b")

# 로컬 추론은 네트워크 지연 없이 모델 처리 시간만 소요 → 여유있게 설정
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

ModelPreference = Literal["auto", "standard", "high"]


def _get_model_name(
    model_preference: ModelPreference = "auto",
    default_type: Literal["high", "standard"] = "standard",
) -> str:
    if model_preference == "high":
        return HIGH_PERF_MODEL_NAME
    if model_preference == "standard":
        return STANDARD_MODEL_NAME
    if default_type == "high":
        return HIGH_PERF_MODEL_NAME
    return STANDARD_MODEL_NAME


async def _ollama_chat(
    model: str,
    prompt: str,
    json_format: bool = False,
) -> str:
    """Ollama /api/chat 엔드포인트 호출 (단일 user 메시지)."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if json_format:
        payload["format"] = "json"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    # 토큰 사용량 기록 (로컬/무료, 비용 없음)
    try:
        from . import token_tracker
        token_tracker.record(
            provider="ollama",
            model=model,
            input_tokens=data.get("prompt_eval_count", 0) or 0,
            output_tokens=data.get("eval_count", 0) or 0,
        )
    except Exception:
        pass

    return data["message"]["content"]


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> List[ExecutionGroup]:
    """ReAct 플래너: 다음 1개 실행 그룹을 생성합니다. 완료 시 [] 반환."""
    model_name = _get_model_name(model_preference, default_type="high")

    tool_descriptions = get_filtered_tool_descriptions(allowed_skills)
    formatted_history = _truncate_history(history)
    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."
    react_system = _acm.get_prompt("react_planner_system")
    instruction = _acm.render_prompt(
        "react_planner_instruction",
        user_query=user_query,
        requirements_content=requirements_content if requirements_content else "없음",
        tool_descriptions=tool_descriptions,
        formatted_history=formatted_history,
    )
    prompt = f"{custom_system_prompt}\n\n{react_system}\n\n{instruction}"
    response_text = ""
    try:
        response_text = await _ollama_chat(model_name, prompt, json_format=True)
        parsed_json = json.loads(response_text)

        # Case 1: {"ExecutionGroup": [...]} 또는 {"plan": [...]} 등 리스트 래핑
        if isinstance(parsed_json, dict):
            # Case 1a: {"tasks": [...]} → ExecutionGroup 구조로 자동 변환
            if "tasks" in parsed_json and isinstance(parsed_json["tasks"], list):
                parsed_json = [{
                    "group_id": "group_1",
                    "description": "자동 생성된 실행 그룹",
                    "tasks": parsed_json["tasks"],
                }]
            else:
                # Case 1b: 값 중 첫 번째 리스트를 꺼냄
                for v in parsed_json.values():
                    if isinstance(v, list):
                        parsed_json = v
                        break
                else:
                    raise ValueError("응답 dict에서 실행 계획 리스트를 찾을 수 없습니다.")

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan[:1]

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logging.error(f"JSON 파싱 오류: {e}\n받은 응답: {response_text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except httpx.ConnectError:
        raise RuntimeError(
            f"Ollama 서버에 연결할 수 없습니다 ({OLLAMA_BASE_URL}). "
            "'ollama serve' 명령으로 서버를 먼저 실행해주세요."
        )
    except Exception as e:
        logging.error(f"Planner 모델 호출 오류: {e}")
        raise


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    """작업 완료 후 최종 답변을 생성합니다."""
    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)
    prompt = _acm.render_prompt("final_answer_user", history_str=history_str)
    try:
        result = await _ollama_chat(model_name, prompt, json_format=False)
        return result.strip()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Ollama 서버에 연결할 수 없습니다 ({OLLAMA_BASE_URL}). "
            "'ollama serve' 명령으로 서버를 먼저 실행해주세요."
        )


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """대화에서 핵심 키워드 5~10개를 추출합니다. 실패 시 [] 반환."""
    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)
    prompt = _acm.render_prompt("extract_keywords_user", history_str=history_str)
    try:
        result = await _ollama_chat(model_name, prompt, json_format=True)
        parsed = json.loads(result)
        # 모델이 {"keywords": [...]} 형태로 반환할 수도 있으므로 유연하게 처리
        if isinstance(parsed, list):
            return [str(k) for k in parsed if isinstance(k, str)]
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return [str(k) for k in v if isinstance(k, str)]
        return []
    except Exception as e:
        logging.warning(f"키워드 추출 실패: {e}")
        return []


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    """대화에서 주제 전환 지점을 감지합니다. 실패 시 None 반환."""
    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)
    prompt = _acm.render_prompt("detect_topic_split_user", history_str=history_str)
    try:
        result = await _ollama_chat(model_name, prompt, json_format=True)
        parsed = json.loads(result)
        if isinstance(parsed, dict) and "detected" in parsed:
            return parsed
        return None
    except Exception as e:
        logging.warning(f"주제 분리 감지 실패: {e}")
        return None


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    """대화 내용을 요약한 5단어 이내 제목을 생성합니다."""
    model_name = _get_model_name(model_preference, default_type="standard")

    if len(history) < 2:
        return "새로운_대화"

    prompt = _acm.render_prompt(
        "generate_title_user",
        msg0=history[0],
        msg1=history[1] if len(history) > 1 else "",
    )
    try:
        result = await _ollama_chat(model_name, prompt, json_format=False)
        return result.strip().replace("*", "").replace("`", "").replace('"', "")
    except Exception:
        return "Untitled_Conversation"
