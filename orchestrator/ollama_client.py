#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/ollama_client.py
"""Ollama 로컬 LLM 클라이언트.

8GB RAM 환경 기준 모델:
  HIGH    : qwen2.5-coder:7b  (~4.5GB, 코딩 고성능)
  STANDARD: qwen2.5-coder:3b  (~2.0GB, 코딩 경량/균형)

Gemini/Claude 클라이언트와 동일한 함수 인터페이스를 제공합니다.
"""

import logging
import os
from typing import Any, Dict, List, Literal, Optional

import httpx
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


async def _call_ollama(system: str, user: str, model: str, json_mode: bool = False) -> str:
    """_llm_utils 통합 시그니처 어댑터 — system+user를 단일 프롬프트로 합쳐 전달."""
    combined = f"{system}\n\n{user}" if system and system.strip() else user
    try:
        return await _ollama_chat(model=model, prompt=combined, json_format=json_mode)
    except httpx.ConnectError:
        raise RuntimeError(
            f"Ollama 서버에 연결할 수 없습니다 ({OLLAMA_BASE_URL}). "
            "'ollama serve' 명령으로 서버를 먼저 실행해주세요."
        )


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
    return await generate_execution_plan_with_caller(
        _call_ollama, user_query, requirements_content, history,
        model_name, system_prompts, allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    """작업 완료 후 최종 답변을 생성합니다."""
    model_name = _get_model_name(model_preference, default_type="standard")
    return await generate_final_answer_with_caller(_call_ollama, history, model_name)


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """대화에서 핵심 키워드 5~10개를 추출합니다. 실패 시 [] 반환."""
    return await extract_keywords_with_caller(
        _call_ollama, history, _get_model_name(model_preference, default_type="standard")
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    """대화에서 주제 전환 지점을 감지합니다. 실패 시 None 반환."""
    return await detect_topic_split_with_caller(
        _call_ollama, history, _get_model_name(model_preference, default_type="standard")
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    """대화 내용을 요약한 5단어 이내 제목을 생성합니다."""
    return await generate_title_with_caller(
        _call_ollama, history, _get_model_name(model_preference, default_type="standard")
    )
