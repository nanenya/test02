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
from .constants import HISTORY_MAX_CHARS

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
HIGH_PERF_MODEL_NAME = os.getenv("OLLAMA_HIGH_PERF_MODEL", "qwen2.5-coder:7b")
STANDARD_MODEL_NAME = os.getenv("OLLAMA_STANDARD_MODEL", "qwen2.5-coder:3b")

# 로컬 추론은 네트워크 지연 없이 모델 처리 시간만 소요 → 여유있게 설정
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)

ModelPreference = Literal["auto", "standard", "high"]

DEFAULT_HISTORY_MAX_CHARS = HISTORY_MAX_CHARS  # constants.py에서 중앙 관리


def _truncate_history(history: list, max_chars: int = DEFAULT_HISTORY_MAX_CHARS) -> str:
    """최근 대화 우선 보존하는 캐릭터 예산 기반 히스토리 truncation."""
    if not history:
        return ""

    selected = []
    total = 0
    for item in reversed(history):
        item_len = len(item)
        if total + item_len > max_chars and selected:
            break
        selected.append(item)
        total += item_len

    selected.reverse()

    if len(selected) < len(history):
        return "... (이전 기록 생략) ...\n" + "\n".join(selected)
    return "\n".join(selected)


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

    prompt = f"""
    {custom_system_prompt}

    당신은 사용자의 목표를 달성하기 위해, '이전 대화'를 분석하여 '다음 1단계'의 계획을 수립하는 'ReAct 플래너'입니다.

    ## 최종 목표 (사용자 최초 요청):
    {user_query}

    ## 사용자가 제공한 추가 요구사항 및 컨텍스트:
    {requirements_content if requirements_content else "없음"}

    ## 사용 가능한 도구 목록:
    {tool_descriptions}

    ## 이전 대화 요약 (매우 중요!):
    {formatted_history}

    ## 지시사항 (필독!):
    1. '최종 목표'와 '이전 대화 요약'을 면밀히 분석합니다.
    2. '이전 대화 요약'에 "실행 결과"가 있다면, 그 결과를 **입력으로 사용**하여 **다음에 실행할 논리적인 1개의 '실행 그룹(ExecutionGroup)'**을 만드세요.
       (예: "실행 결과: ['a.txt']"가 있다면, 다음 그룹은 'read_file(path="a.txt")' 태스크를 포함해야 합니다.)
    3. 만약 '이전 대화 요약'을 분석했을 때 모든 '최종 목표'가 완료되었다고 판단되면, 반드시 빈 리스트( `[]` )를 반환하세요.
    4. 만약 '이전 대화 요약'이 비어있거나 "실행 결과"가 없다면(첫 단계), '최종 목표' 달성을 위한 **첫 번째 1개의 '실행 그룹'**을 만드세요.
    5. 각 'task' 객체 내에 'model_preference' 필드를 포함해야 합니다 ('high', 'standard', 'auto').

    ## 출력 형식:
    반드시 'ExecutionGroup' 객체의 리스트(배열) 형식으로만 응답해야 합니다.
    **다음 1개 그룹만** 포함하거나, **완료 시 빈 리스트 `[]`**를 반환해야 합니다.

    # 예시 1: 다음 단계가 남은 경우 (1개 그룹만 포함)
    [
      {{
        "group_id": "group_N",
        "description": "다음에 실행할 단일 그룹에 대한 설명",
        "tasks": [
          {{
            "tool_name": "도구_이름",
            "arguments": {{"이전_결과_활용": "값"}},
            "model_preference": "standard"
          }}
        ]
      }}
    ]

    # 예시 2: 모든 작업 완료 시
    []

    ## 다음 실행 계획 (JSON):
    """

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

    prompt = f"""
    다음은 AI 에이전트와 사용자의 작업 기록 요약입니다.
    모든 작업이 완료되었습니다.
    전체 '실행 결과'와 '사용자 목표'를 바탕으로 사용자에게 제공할 최종적이고 종합적인 답변을 한국어로 생성해주세요.

    --- 작업 기록 요약 ---
    {history_str}
    ---

    최종 답변:
    """
    try:
        result = await _ollama_chat(model_name, prompt, json_format=False)
        return result.strip()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Ollama 서버에 연결할 수 없습니다 ({OLLAMA_BASE_URL}). "
            "'ollama serve' 명령으로 서버를 먼저 실행해주세요."
        )
    except Exception as e:
        logging.error(f"generate_final_answer 오류: {e}", exc_info=True)
        last_result = next(
            (item for item in reversed(history) if item.startswith("  - 실행 결과:")), None
        )
        if last_result:
            return f"최종 요약 생성에 실패했습니다. 마지막 실행 결과입니다:\n{last_result}"
        return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다."


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """대화에서 핵심 키워드 5~10개를 추출합니다. 실패 시 [] 반환."""
    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    prompt = f"""
다음 대화에서 핵심 키워드를 5~10개 추출해주세요.
명사 위주로, 한국어/영어 혼용 가능합니다.

--- 대화 내용 ---
{history_str}
---

JSON 배열로만 응답하세요. 예: ["FastAPI", "SQLite", "ReAct", "Python"]
"""
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

    prompt = f"""
다음 대화에서 주제가 크게 전환된 지점이 있는지 분석해주세요.

--- 대화 내용 (인덱스 포함) ---
{history_str}
---

JSON 형식으로만 응답하세요:
{{
  "detected": true또는false,
  "split_index": 정수(주제 전환이 시작되는 메시지 인덱스),
  "reason": "전환 이유 설명",
  "topic_a": "첫 번째 주제 이름",
  "topic_b": "두 번째 주제 이름"
}}
주제 전환이 없으면 detected를 false로 응답하세요.
"""
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

    prompt = f"""
    다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 '요약'을 한국어로 만들어줘.

    --- 대화 내용 (초반 2개) ---
    {history[0]}
    {history[1] if len(history) > 1 else ""}
    ---

    요약:
    """
    try:
        result = await _ollama_chat(model_name, prompt, json_format=False)
        return result.strip().replace("*", "").replace("`", "").replace('"', "")
    except Exception:
        return "Untitled_Conversation"
