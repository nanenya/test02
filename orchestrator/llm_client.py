#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/llm_client.py
# 프로바이더 라우터: 호출 시점에 활성 프로바이더를 읽어 적절한 클라이언트 모듈로 위임

from typing import Dict, Any, List, Literal, Optional


def _get_active_client_module():
    """현재 활성 프로바이더에 맞는 클라이언트 모듈을 반환."""
    from .model_manager import load_config, get_active_model
    provider, _ = get_active_model(load_config())
    if provider == "claude":
        from . import claude_client
        return claude_client
    if provider == "ollama":
        from . import ollama_client
        return ollama_client
    from . import gemini_client
    return gemini_client


ModelPreference = Literal["auto", "standard", "high"]


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
):
    return await _get_active_client_module().generate_execution_plan(
        user_query=user_query,
        requirements_content=requirements_content,
        history=history,
        model_preference=model_preference,
        system_prompts=system_prompts,
        allowed_skills=allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    return await _get_active_client_module().generate_final_answer(
        history=history,
        model_preference=model_preference,
    )


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    return await _get_active_client_module().extract_keywords(
        history=history,
        model_preference=model_preference,
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    return await _get_active_client_module().detect_topic_split(
        history=history,
        model_preference=model_preference,
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    return await _get_active_client_module().generate_title_for_conversation(
        history=history,
        model_preference=model_preference,
    )
