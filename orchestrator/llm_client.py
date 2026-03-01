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


# ── 4층 파이프라인 전용 LLM 함수 ─────────────────────────────────────────────


async def generate_design(
    user_query: str,
    persona_prompt: str = "",
    history: list = None,
    model_preference: ModelPreference = "high",
) -> Dict[str, Any]:
    """사용자 쿼리를 분석해 고수준 설계를 생성합니다 (Design Phase).

    반환 형식:
      {
        "goal": "최종 목표 한 줄 요약",
        "approach": "접근 방법 (2-3문장)",
        "constraints": ["제약사항1", ...],
        "expected_outputs": ["결과물1", ...],
        "complexity": "simple|medium|complex"
      }
    실패 시 기본 구조를 반환합니다.
    """
    import json, re
    system_ctx = persona_prompt + "\n\n" if persona_prompt else ""
    history_ctx = ""
    if history:
        recent = history[-6:]  # 최근 6항목만 (토큰 절약)
        history_ctx = "\n".join(str(h) for h in recent) + "\n\n"

    prompt = (
        f"{system_ctx}{history_ctx}"
        f"사용자 요청:\n\"{user_query}\"\n\n"
        "위 요청을 분석하여 아래 JSON 형식으로 설계를 반환하세요. "
        "반드시 JSON만 반환하고 다른 텍스트는 포함하지 마세요.\n\n"
        "{\n"
        '  "goal": "최종 목표 한 줄 요약",\n'
        '  "approach": "접근 방법 2-3문장",\n'
        '  "constraints": ["제약사항1", "제약사항2"],\n'
        '  "expected_outputs": ["결과물1", "결과물2"],\n'
        '  "complexity": "simple 또는 medium 또는 complex"\n'
        "}"
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"DESIGN_GENERATE: {prompt}"],
                model_preference=model_preference,
            )
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as exc:
            logger.warning(f"[Design] provider={provider} 실패: {exc}")

    # 실패 시 기본 구조
    return {
        "goal": user_query[:100],
        "approach": "단계적으로 요청을 처리합니다.",
        "constraints": [],
        "expected_outputs": ["작업 완료"],
        "complexity": "medium",
    }


async def decompose_tasks(
    design: Dict[str, Any],
    user_query: str,
    model_preference: ModelPreference = "standard",
) -> List[Dict[str, str]]:
    """설계를 실행 가능한 태스크 목록으로 분해합니다 (Task Decomposition Phase).

    반환 형식: [{"title": "태스크 제목", "description": "상세 설명"}, ...]
    최대 10개 태스크.
    실패 시 단일 태스크 목록을 반환합니다.
    """
    import json, re
    design_text = (
        f"목표: {design.get('goal', '')}\n"
        f"접근법: {design.get('approach', '')}\n"
        f"결과물: {', '.join(design.get('expected_outputs', []))}"
    )
    prompt = (
        f"설계 내용:\n{design_text}\n\n"
        f"사용자 원래 요청: \"{user_query}\"\n\n"
        "위 설계를 독립적으로 실행 가능한 태스크로 분해하세요. "
        "최대 10개, JSON 배열만 반환하세요.\n\n"
        '[{"title": "태스크 제목", "description": "무엇을 해야 하는지 구체적 설명"}, ...]'
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"TASK_DECOMPOSE: {prompt}"],
                model_preference=model_preference,
            )
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                tasks = json.loads(match.group())
                # 형식 보정
                valid = [
                    {"title": t.get("title", "태스크"), "description": t.get("description", "")}
                    for t in tasks if isinstance(t, dict)
                ]
                if valid:
                    return valid[:10]
        except Exception as exc:
            logger.warning(f"[TaskDecompose] provider={provider} 실패: {exc}")

    # 실패 시 단일 태스크
    return [{"title": user_query[:80], "description": design.get("approach", "")}]


async def map_plans(
    task: Dict[str, str],
    available_tools: List[str],
    model_preference: ModelPreference = "standard",
) -> List[Dict[str, Any]]:
    """태스크를 순서 있는 계획 단계(Plan Steps)로 매핑합니다 (Plan Mapping Phase).

    반환 형식:
      [{"action": "수행 동작 설명", "tool_hints": ["예상도구1", "예상도구2"]}, ...]
    실패 시 단일 단계를 반환합니다.
    """
    import json, re
    tools_str = ", ".join(available_tools[:30]) if available_tools else "없음"
    prompt = (
        f"태스크: {task.get('title', '')}\n"
        f"설명: {task.get('description', '')}\n\n"
        f"사용 가능한 도구 목록: {tools_str}\n\n"
        "위 태스크를 실행 순서대로 분해하세요. "
        "각 단계는 하나의 도구 호출로 처리 가능해야 합니다. "
        "최대 8단계, JSON 배열만 반환하세요.\n\n"
        '[{"action": "무엇을 할 것인지 설명", "tool_hints": ["도구명1", "도구명2"]}, ...]'
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"PLAN_MAP: {prompt}"],
                model_preference=model_preference,
            )
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                plans = json.loads(match.group())
                valid = [
                    {
                        "action": p.get("action", "실행"),
                        "tool_hints": p.get("tool_hints", [])[:5],
                    }
                    for p in plans if isinstance(p, dict)
                ]
                if valid:
                    return valid[:8]
        except Exception as exc:
            logger.warning(f"[PlanMap] provider={provider} 실패: {exc}")

    # 실패 시 단일 단계
    return [{"action": task.get("title", "실행"), "tool_hints": []}]


async def build_execution_group_for_step(
    plan_step: Dict[str, Any],
    task: Dict[str, str],
    design: Dict[str, Any],
    available_tools: List[str],
    history: list = None,
    model_preference: ModelPreference = "standard",
) -> Dict[str, Any]:
    """계획 단계 1개에 대한 ExecutionGroup을 생성합니다.

    기존 generate_execution_plan과 달리 단일 단계에 집중하여
    컨텍스트를 최소화하고 토큰을 절약합니다.

    반환 형식: ExecutionGroup.model_dump() 호환 dict
    """
    import json, re

    tools_desc = "\n".join(f"- {t}" for t in available_tools[:20])
    history_ctx = ""
    if history:
        recent = "\n".join(str(h) for h in history[-4:])
        history_ctx = f"최근 대화:\n{recent}\n\n"

    prompt = (
        f"{history_ctx}"
        f"전체 목표: {design.get('goal', '')}\n"
        f"현재 태스크: {task.get('title', '')}\n"
        f"현재 단계: {plan_step.get('action', '')}\n"
        f"예상 도구 힌트: {plan_step.get('tool_hints', [])}\n\n"
        f"사용 가능한 도구:\n{tools_desc}\n\n"
        "위 단계를 실행하기 위한 도구 호출을 JSON으로 반환하세요. "
        "반드시 아래 형식만 반환하고, 도구가 필요 없으면 tasks를 빈 배열로 하세요.\n\n"
        "{\n"
        '  "group_id": "group_1",\n'
        '  "description": "이 단계에서 하는 일 설명",\n'
        '  "tasks": [\n'
        '    {"tool_name": "도구이름", "arguments": {"인자명": "값"}, "model_preference": "standard"}\n'
        "  ]\n"
        "}"
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"EXEC_GROUP_BUILD: {prompt}"],
                model_preference=model_preference,
            )
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                group = json.loads(match.group())
                # 최소 형식 검증
                if "group_id" in group and "tasks" in group:
                    group.setdefault("description", plan_step.get("action", ""))
                    return group
        except Exception as exc:
            logger.warning(f"[ExecGroupBuild] provider={provider} 실패: {exc}")

    # 실패 시 빈 그룹 반환 (실행은 되지 않지만 파이프라인 진행 가능)
    return {
        "group_id": "group_fallback",
        "description": plan_step.get("action", "실행"),
        "tasks": [],
    }


# ── Phase 2: 템플릿 인자 적응 ─────────────────────────────────────────────────

async def adapt_template_arguments(
    template_group: Dict[str, Any],
    plan_step: Dict[str, Any],
    task: Dict[str, str],
    design: Dict[str, Any],
    history: list = None,
    model_preference: ModelPreference = "standard",
) -> Dict[str, Any]:
    """기존 템플릿의 구조를 유지하면서 arguments만 현재 컨텍스트에 맞게 교체합니다.

    - tool_name은 절대 변경하지 않습니다.
    - 변경 범위: arguments 내의 경로·파일명·쿼리 파라미터·값 등
    - 실패 시 원본 template_group을 그대로 반환합니다.
    - standard 티어 이하로 처리 (비용 최소화).
    """
    import json, re

    template_json = json.dumps(template_group, ensure_ascii=False, indent=2)
    history_ctx = ""
    if history:
        history_ctx = "최근 대화:\n" + "\n".join(str(h) for h in history) + "\n\n"

    prompt = (
        f"{history_ctx}"
        f"현재 목표: {design.get('goal', '')}\n"
        f"현재 태스크: {task.get('title', '')}\n"
        f"현재 단계: {plan_step.get('action', '')}\n\n"
        f"아래는 이전에 성공한 실행 템플릿입니다:\n{template_json}\n\n"
        "위 템플릿의 arguments 값만 현재 컨텍스트에 맞게 수정하세요.\n"
        "반드시 지켜야 할 규칙:\n"
        "  1. tool_name은 절대 변경하지 마세요.\n"
        "  2. tasks 배열의 길이와 순서를 유지하세요.\n"
        "  3. arguments의 키(key)는 변경하지 마세요, 값(value)만 수정하세요.\n"
        "  4. 수정이 불필요한 arguments는 그대로 유지하세요.\n"
        "수정된 전체 JSON만 반환하세요 (설명 없이)."
    )

    for provider in _get_fallback_chain():
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"TEMPLATE_ADAPT: {prompt}"],
                model_preference=model_preference,
            )
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                adapted = json.loads(match.group())
                if "group_id" in adapted and "tasks" in adapted:
                    return adapted
        except Exception as exc:
            logger.warning(f"[TemplateAdapt] provider={provider} 실패: {exc}")

    return template_group  # 실패 시 원본 반환
