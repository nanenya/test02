#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

from google import genai
from google.genai import types
import os
import logging
from dotenv import load_dotenv
from .models import ExecutionGroup
from .constants import HISTORY_MAX_CHARS, truncate_history as _truncate_history
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

_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if _api_key:
    client = genai.Client(api_key=_api_key)
else:
    logging.warning("GEMINI_API_KEY 환경변수가 설정되지 않았습니다. Gemini API 호출 시 오류가 발생합니다.")
    client = None

ModelPreference = Literal["auto", "standard", "high"]

JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
)


def _record_usage(response, model_name: str) -> None:
    """Gemini 응답의 usage_metadata를 token_tracker에 기록합니다. 실패는 무시."""
    try:
        from . import token_tracker
        um = response.usage_metadata
        token_tracker.record(
            provider="gemini",
            model=model_name,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
        )
    except Exception:
        pass


def _get_model_name(
    model_preference: ModelPreference = "auto",
    default_type: Literal["high", "standard"] = "standard",
) -> str:
    from .model_manager import load_config
    config = load_config()
    gemini_cfg = config.get("providers", {}).get("gemini", {})
    if model_preference == "high":
        return gemini_cfg.get("high_model") or config.get("active_model", "")
    if model_preference == "standard":
        return gemini_cfg.get("standard_model") or config.get("active_model", "")
    active = config.get("active_model", "")
    if active:
        return active
    if default_type == "high":
        return gemini_cfg.get("high_model", "")
    return gemini_cfg.get("standard_model", "")


async def _call_gemini(system: str, user: str, model: str, json_mode: bool = False) -> str:
    """Gemini API 호출 — _llm_utils 통합 시그니처 어댑터.

    system + user를 단일 프롬프트로 합쳐서 Gemini API에 전달합니다.
    """
    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 설정해주세요.")
    combined = f"{system}\n\n{user}" if system and system.strip() else user
    config = JSON_CONFIG if json_mode else None
    response = await client.aio.models.generate_content(
        model=model,
        contents=combined,
        config=config,
    )
    _record_usage(response, model)
    if not response.text:
        raise ValueError("모델이 빈 응답을 반환했습니다 (내용 필터링 가능성).")
    return response.text


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
    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 설정해주세요.")
    model_name = _get_model_name(model_preference, default_type="high")
    return await generate_execution_plan_with_caller(
        _call_gemini, user_query, requirements_content, history,
        model_name, system_prompts, allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    model_name = _get_model_name(model_preference, default_type="standard")
    return await generate_final_answer_with_caller(_call_gemini, history, model_name)


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """Gemini로 키워드 5~10개 추출. 실패 시 [] 반환."""
    if not client:
        return []
    model_name = _get_model_name(model_preference, default_type="standard")
    return await extract_keywords_with_caller(_call_gemini, history, model_name)


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    """Gemini로 주제 전환 지점 감지. 실패 시 None 반환."""
    if not client:
        return None
    model_name = _get_model_name(model_preference, default_type="standard")
    return await detect_topic_split_with_caller(_call_gemini, history, model_name)


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    if not client:
        return "Untitled_Conversation"
    model_name = _get_model_name(model_preference, default_type="standard")
    return await generate_title_with_caller(_call_gemini, history, model_name)
