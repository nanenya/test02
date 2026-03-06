#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/claude_client.py

import httpx
import os
import json
import logging
from dotenv import load_dotenv
from .models import ExecutionGroup
from .constants import HISTORY_MAX_CHARS
from . import agent_config_manager as _acm
from ._llm_utils import (
    _extract_json_block,
    generate_execution_plan_with_caller,
    generate_final_answer_with_caller,
    extract_keywords_with_caller,
    detect_topic_split_with_caller,
    generate_title_with_caller,
)
from typing import Dict, Any, List, Literal, Optional

load_dotenv()

_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    logging.warning("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. Claude API 호출 시 오류가 발생합니다.")

HIGH_PERF_MODEL_NAME = os.getenv("CLAUDE_HIGH_PERF_MODEL", "claude-sonnet-4-6")
STANDARD_MODEL_NAME = os.getenv("CLAUDE_STANDARD_MODEL", "claude-haiku-4-5-20251001")

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


async def _call_claude(
    system: str,
    user: str,
    model: str,
    json_mode: bool = False,
) -> str:
    """Claude Messages API 호출 내부 헬퍼."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일에 ANTHROPIC_API_KEY를 설정해주세요.")

    if not user or not user.strip():
        raise ValueError("Claude API 호출 실패: user 메시지가 비어 있습니다.")

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": user}],
    }
    # system이 빈 문자열이면 Anthropic API가 400을 반환하므로 제외
    if system and system.strip():
        payload["system"] = system

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            logging.error(
                f"Claude API 오류 [{resp.status_code}] model={model}: {resp.text}"
            )
        resp.raise_for_status()
        data = resp.json()

    try:
        from . import token_tracker
        _usage = data.get("usage", {})
        def _to_int(v):
            try:
                return int(v)
            except Exception:
                return None
        token_tracker.record(
            provider="claude",
            model=model,
            input_tokens=_usage.get("input_tokens", 0) or 0,
            output_tokens=_usage.get("output_tokens", 0) or 0,
            rate_limit_limit=_to_int(resp.headers.get("anthropic-ratelimit-tokens-limit")),
            rate_limit_remaining=_to_int(resp.headers.get("anthropic-ratelimit-tokens-remaining")),
        )
    except Exception:
        pass

    content_blocks = data.get("content", [])
    if not content_blocks:
        raise ValueError("Claude API가 빈 content를 반환했습니다.")

    text = content_blocks[0].get("text", "")
    if not text:
        raise ValueError("Claude API가 빈 텍스트를 반환했습니다.")

    return text


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> List[ExecutionGroup]:
    """ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다.
    목표가 완료되면 빈 리스트 []를 반환합니다.
    """
    model_name = _get_model_name(model_preference, default_type="high")
    return await generate_execution_plan_with_caller(
        _call_claude, user_query, requirements_content, history,
        model_name, system_prompts, allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    model_name = _get_model_name(model_preference, default_type="standard")
    return await generate_final_answer_with_caller(_call_claude, history, model_name)


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """Claude로 키워드 5~10개 추출. 실패 시 [] 반환."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return []
    return await extract_keywords_with_caller(
        _call_claude, history, _get_model_name(model_preference, default_type="standard")
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    """Claude로 주제 전환 지점 감지. 실패 시 None 반환."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    return await detect_topic_split_with_caller(
        _call_claude, history, _get_model_name(model_preference, default_type="standard")
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "Untitled_Conversation"
    return await generate_title_with_caller(
        _call_claude, history, _get_model_name(model_preference, default_type="standard")
    )
