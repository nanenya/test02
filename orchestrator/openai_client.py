#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/openai_client.py

import httpx
import os
import json
import logging
from dotenv import load_dotenv
from .tool_registry import get_filtered_tool_descriptions
from .models import ExecutionGroup
from .constants import HISTORY_MAX_CHARS, truncate_history as _truncate_history
from . import agent_config_manager as _acm
from ._llm_utils import (
    _extract_json_block,
    extract_keywords_with_caller,
    detect_topic_split_with_caller,
    generate_title_with_caller,
)
from typing import Dict, Any, List, Literal, Optional

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    logging.warning("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. OpenAI API 호출 시 오류가 발생합니다.")

HIGH_PERF_MODEL_NAME = os.getenv("OPENAI_HIGH_PERF_MODEL", "gpt-4o")
STANDARD_MODEL_NAME = os.getenv("OPENAI_STANDARD_MODEL", "gpt-4o-mini")

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


async def _call_openai(
    prompt: str,
    system_prompt: str,
    model: str,
    json_format: bool = False,
) -> str:
    """OpenAI Chat Completions API 호출 내부 헬퍼."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 설정해주세요.")

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if json_format:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    # 토큰 사용량 기록
    try:
        from . import token_tracker
        _usage = data.get("usage", {})
        token_tracker.record(
            provider="openai",
            model=model,
            input_tokens=_usage.get("prompt_tokens", 0) or 0,
            output_tokens=_usage.get("completion_tokens", 0) or 0,
        )
    except Exception:
        pass

    choices = data.get("choices", [])
    if not choices:
        raise ValueError("OpenAI API가 빈 choices를 반환했습니다.")

    text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise ValueError("OpenAI API가 빈 텍스트를 반환했습니다.")

    return text


async def _call_unified(system: str, user: str, model: str, json_mode: bool = False) -> str:
    """_llm_utils 통합 시그니처용 어댑터."""
    return await _call_openai(prompt=user, system_prompt=system, model=model, json_format=json_mode)


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> List[ExecutionGroup]:
    model_name = _get_model_name(model_preference, default_type="high")
    tool_descriptions = get_filtered_tool_descriptions(allowed_skills)
    formatted_history = _truncate_history(history)
    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."
    system = custom_system_prompt + "\n\n" + _acm.get_prompt("react_planner_system")

    user = _acm.render_prompt(
        "react_planner_instruction",
        user_query=user_query,
        requirements_content=requirements_content if requirements_content else "없음",
        tool_descriptions=tool_descriptions,
        formatted_history=formatted_history,
    )

    try:
        text = await _call_openai(prompt=user, system_prompt=system, model=model_name, json_format=True)
        text = _extract_json_block(text)
        parsed_json = json.loads(text)

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan[:1]

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"JSON 파싱 오류: {e}\n받은 응답: {text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        print(f"Planner 모델 호출 오류: {e}")
        raise e


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    model_name = _get_model_name(model_preference, default_type="standard")
    system = _acm.get_prompt("final_answer_system")
    history_str = _truncate_history(history)
    user = _acm.render_prompt("final_answer_user", history_str=history_str)

    try:
        text = await _call_openai(prompt=user, system_prompt=system, model=model_name, json_format=False)
        return text.strip()
    except Exception as e:
        logging.error(f"generate_final_answer 오류: {e}", exc_info=True)
        last_result = next((item for item in reversed(history) if item.startswith("  - 실행 결과:")), None)
        if last_result:
            return f"최종 요약 생성에 실패했습니다 (서버 로그 참조). 마지막 실행 결과입니다:\n{last_result}"
        else:
            return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다. 서버 로그를 확인해주세요."


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    if not os.getenv("OPENAI_API_KEY"):
        return []
    return await extract_keywords_with_caller(
        _call_unified, history, _get_model_name(model_preference, default_type="standard")
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return await detect_topic_split_with_caller(
        _call_unified, history, _get_model_name(model_preference, default_type="standard")
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return "Untitled_Conversation"
    return await generate_title_with_caller(
        _call_unified, history, _get_model_name(model_preference, default_type="standard")
    )
