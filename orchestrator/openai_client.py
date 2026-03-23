#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/openai_client.py

import httpx
import os
import logging
from dotenv import load_dotenv
from .models import ExecutionGroup
from .constants import HISTORY_MAX_CHARS
from ._llm_utils import (
    generate_execution_plan_with_caller,
    generate_final_answer_with_caller,
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
    system: str,
    user: str,
    model: str,
    json_mode: bool = False,
) -> str:
    """OpenAI Chat Completions API 호출 내부 헬퍼."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 설정해주세요.")

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
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


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> List[ExecutionGroup]:
    model_name = _get_model_name(model_preference, default_type="high")
    return await generate_execution_plan_with_caller(
        _call_openai, user_query, requirements_content, history,
        model_name, system_prompts, allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    model_name = _get_model_name(model_preference, default_type="standard")
    return await generate_final_answer_with_caller(_call_openai, history, model_name)


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    if not os.getenv("OPENAI_API_KEY"):
        return []
    return await extract_keywords_with_caller(
        _call_openai, history, _get_model_name(model_preference, default_type="standard")
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return await detect_topic_split_with_caller(
        _call_openai, history, _get_model_name(model_preference, default_type="standard")
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return "Untitled_Conversation"
    return await generate_title_with_caller(
        _call_openai, history, _get_model_name(model_preference, default_type="standard")
    )
