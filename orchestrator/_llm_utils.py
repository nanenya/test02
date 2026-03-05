#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_llm_utils.py
"""LLM 클라이언트 공통 유틸리티.

claude_client / openai_client / grok_client 에서 동일하게 사용하는
헬퍼 함수를 한 곳에 정의합니다.

call_fn 통합 시그니처: async (system, user, model, json_mode) -> str
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .constants import truncate_history as _truncate_history
from . import agent_config_manager as _acm


def _extract_json_block(text: str) -> str:
    """```json...``` 블록에서 JSON 문자열을 추출합니다."""
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            return m.group(1).strip()
    return text.strip()


async def extract_keywords_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> List[str]:
    """공통 키워드 추출 로직. call_fn만 프로바이더별로 다름."""
    history_str = _truncate_history(history)
    system = _acm.get_prompt("extract_keywords_system")
    user = _acm.render_prompt("extract_keywords_user", history_str=history_str)
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=True)
        parsed = json.loads(_extract_json_block(text))
        if isinstance(parsed, list):
            return [str(k) for k in parsed if isinstance(k, str)]
        return []
    except Exception as e:
        logging.warning(f"키워드 추출 실패: {e}")
        return []


async def detect_topic_split_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> Optional[Dict[str, Any]]:
    """공통 주제 분리 감지 로직. call_fn만 프로바이더별로 다름."""
    history_str = _truncate_history(history)
    system = _acm.get_prompt("detect_topic_split_system")
    user = _acm.render_prompt("detect_topic_split_user", history_str=history_str)
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=True)
        parsed = json.loads(_extract_json_block(text))
        if isinstance(parsed, dict) and "detected" in parsed:
            return parsed
        return None
    except Exception as e:
        logging.warning(f"주제 분리 감지 실패: {e}")
        return None


async def generate_title_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> str:
    """공통 대화 제목 생성 로직. call_fn만 프로바이더별로 다름."""
    if len(history) < 2:
        return "새로운_대화"
    system = _acm.get_prompt("generate_title_system")
    user = _acm.render_prompt(
        "generate_title_user",
        msg0=history[0],
        msg1=history[1] if len(history) > 1 else "",
    )
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=False)
        return text.strip().replace("*", "").replace("`", "").replace('"', "")
    except Exception:
        return "Untitled_Conversation"
