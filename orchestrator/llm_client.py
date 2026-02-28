#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/llm_client.py
# 프로바이더 라우터: 호출 시점에 활성 프로바이더를 읽어 적절한 클라이언트 모듈로 위임
# P2-B: 프로바이더 폴백 체인 지원 (model_config.json의 fallback_chain 순서대로 재시도)

import logging
from typing import Dict, Any, List, Literal, Optional

logger = logging.getLogger(__name__)

ModelPreference = Literal["auto", "standard", "high"]


def _get_client_module(provider: str):
    """프로바이더 이름으로 클라이언트 모듈을 반환."""
    if provider == "claude":
        from . import claude_client
        return claude_client
    if provider == "ollama":
        from . import ollama_client
        return ollama_client
    from . import gemini_client
    return gemini_client


def _get_active_client_module():
    """현재 활성 프로바이더에 맞는 클라이언트 모듈을 반환."""
    from .model_manager import load_config, get_active_model
    provider, _ = get_active_model(load_config())
    return _get_client_module(provider)


def _get_fallback_chain() -> List[str]:
    """model_config.json의 fallback_chain을 반환. 없으면 active_provider만."""
    from .model_manager import load_config, get_active_model
    config = load_config()
    chain = config.get("fallback_chain", [])
    if not chain:
        provider, _ = get_active_model(config)
        return [provider]
    return chain


async def _call_with_fallback(fn_name: str, **kwargs):
    """폴백 체인 순서대로 provider를 시도해 첫 성공 결과를 반환.

    모든 provider가 실패하면 마지막 예외를 re-raise 합니다.
    """
    chain = _get_fallback_chain()
    last_exc: Exception = RuntimeError("폴백 체인이 비어 있습니다.")

    for provider in chain:
        try:
            module = _get_client_module(provider)
            fn = getattr(module, fn_name)
            return await fn(**kwargs)
        except Exception as exc:
            logger.warning(f"[폴백] provider={provider} fn={fn_name} 실패: {exc}")
            last_exc = exc

    raise last_exc


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
):
    return await _call_with_fallback(
        "generate_execution_plan",
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
    return await _call_with_fallback(
        "generate_final_answer",
        history=history,
        model_preference=model_preference,
    )


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    return await _call_with_fallback(
        "extract_keywords",
        history=history,
        model_preference=model_preference,
    )


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    return await _call_with_fallback(
        "detect_topic_split",
        history=history,
        model_preference=model_preference,
    )


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    return await _call_with_fallback(
        "generate_title_for_conversation",
        history=history,
        model_preference=model_preference,
    )


# P2-C: Prometheus 모드 — 실행 전 요구사항 명확화 질문 생성
async def generate_clarifying_questions(
    user_query: str,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """사용자 쿼리를 분석해 실행 전 확인이 필요한 질문 목록을 반환합니다.

    폴백 체인을 사용합니다. 모든 provider 실패 시 빈 리스트 반환.
    """
    from .model_manager import load_config, get_active_model
    chain = _get_fallback_chain()
    last_exc: Exception = RuntimeError("no provider")

    prompt = (
        f"사용자가 다음 작업을 요청했습니다:\n\n\"{user_query}\"\n\n"
        "실행하기 전에 범위, 모호한 부분, 전제 조건을 명확히 하기 위해 "
        "사용자에게 물어봐야 할 핵심 질문 3~5개를 JSON 배열 형식으로만 반환하세요.\n"
        "예시: [\"질문1\", \"질문2\", \"질문3\"]\n"
        "질문이 불필요하면 빈 배열 []을 반환하세요."
    )

    for provider in chain:
        try:
            import json, re
            module = _get_client_module(provider)
            # generate_final_answer를 재사용해 단순 텍스트 응답 획득
            raw = await module.generate_final_answer(
                history=[f"USER_REQUEST: {prompt}"],
                model_preference=model_preference,
            )
            # JSON 배열 추출
            match = re.search(r"\[.*?\]", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return []
        except Exception as exc:
            logger.warning(f"[Prometheus] provider={provider} 실패: {exc}")
            last_exc = exc

    logger.warning(f"[Prometheus] 모든 provider 실패: {last_exc}")
    return []


# P2-D: 히스토리 요약 압축
async def summarize_history(
    history: list,
    model_preference: ModelPreference = "standard",
) -> str:
    """긴 히스토리를 핵심 내용 위주로 요약한 문자열을 반환합니다.

    폴백 체인을 사용합니다. 실패 시 빈 문자열 반환.
    """
    if not history:
        return ""

    excerpt = "\n".join(str(h) for h in history)[:8000]
    prompt_history = [
        f"다음은 AI 에이전트와의 대화 이력입니다. 핵심 작업 내용, 완료된 항목, "
        f"미완료 항목, 중요한 결정 사항만 3~5문장으로 간결하게 요약하세요:\n\n{excerpt}"
    ]

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            return await module.generate_final_answer(
                history=prompt_history,
                model_preference=model_preference,
            )
        except Exception as exc:
            logger.warning(f"[요약] provider={provider} 실패: {exc}")

    return ""


# P3-C: IntentGate — 도구 실행 필요 여부 사전 분류
async def classify_intent(
    user_query: str,
    model_preference: ModelPreference = "standard",
) -> str:
    """사용자 쿼리를 'chat' 또는 'task'로 분류합니다.

    'chat': 단순 질문/대화 (도구 사용 불필요, 직접 답변 가능)
    'task': 파일 생성/수정/실행 등 도구가 필요한 작업
    실패 시 'task'를 반환합니다 (보수적 기본값).
    """
    prompt = (
        f"사용자 요청: \"{user_query}\"\n\n"
        "위 요청이 단순 질문/대화('chat')인지, 파일·코드·시스템 도구 사용이 필요한 작업('task')인지 "
        "한 단어로만 답하세요: chat 또는 task"
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"INTENT_CLASSIFY: {prompt}"],
                model_preference=model_preference,
            )
            if "chat" in raw.strip().lower()[:20]:
                return "chat"
            return "task"
        except Exception as exc:
            logger.warning(f"[IntentGate] provider={provider} 실패: {exc}")

    return "task"  # 보수적 기본값
