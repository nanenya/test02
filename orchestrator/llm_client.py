#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/llm_client.py
# 프로바이더 라우터: 호출 시점에 활성 프로바이더를 읽어 적절한 클라이언트 모듈로 위임
# P2-B: 프로바이더 폴백 체인 지원 (model_config.json의 fallback_chain 순서대로 재시도)

import logging
import json
import re
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from . import agent_config_manager as _acm
from ._llm_utils import _extract_json_block
from .models import WisdomEntry, PlanValidation
from .constants import (
    RECENT_HISTORY_ITEMS, MAX_TOOLS_IN_PROMPT, HISTORY_EXCERPT_MAX_CHARS,
)
from ._circuit_breaker import (  # noqa: F401
    _call_with_fallback,
    _get_fallback_chain,
    _get_client_module,
    _get_active_client_module,
    _is_tripped,
    _trip,
    _detect_circuit_trip,
    get_provider_status,
    _VALID_PROVIDERS,
    _circuit_breaker,
)

logger = logging.getLogger(__name__)

ModelPreference = Literal["auto", "standard", "high"]


# ── 이하 프로바이더 라우터 함수 ──────────────────────────────────────────────

async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> list:
    """실행 계획 그룹 목록을 생성합니다. On error: raises (폴백 체인 소진 시)."""
    return await _call_with_fallback(
        "generate_execution_plan",
        user_query=user_query,
        requirements_content=requirements_content,
        history=history,
        model_preference=model_preference,
        system_prompts=system_prompts,
        allowed_skills=allowed_skills,
    )


async def generate_parallel_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
):
    """병렬 플래닝 모드: 독립 태스크를 여러 그룹으로 한 번에 계획합니다.

    react_planner_parallel_note를 system_prompts 앞에 주입하여
    can_parallel=True 그룹을 여러 개 반환하도록 유도합니다.
    """
    try:
        parallel_note = _acm.get_prompt("react_planner_parallel_note")
    except KeyError:
        parallel_note = ""
    augmented_prompts = ([parallel_note] if parallel_note else []) + (system_prompts or [])
    return await _call_with_fallback(
        "generate_execution_plan",
        user_query=user_query,
        requirements_content=requirements_content,
        history=history,
        model_preference=model_preference,
        system_prompts=augmented_prompts,
        allowed_skills=allowed_skills,
    )


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto",
) -> str:
    try:
        return await _call_with_fallback(
            "generate_final_answer",
            history=history,
            model_preference=model_preference,
        )
    except Exception as e:
        # 모든 프로바이더 실패 시 최후 폴백 메시지 반환
        logger.error(f"[generate_final_answer] 모든 프로바이더 실패: {e}", exc_info=True)
        last_result = next(
            (item for item in reversed(history) if isinstance(item, str) and item.startswith("  - 실행 결과:")),
            None,
        )
        if last_result:
            return f"최종 요약 생성에 실패했습니다 (서버 로그 참조). 마지막 실행 결과입니다:\n{last_result}"
        return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다. 서버 로그를 확인해주세요."


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
    prompt = _acm.render_prompt("clarifying_questions_user", user_query=user_query)
    result = await _call_with_parse_fallback(
        "USER_REQUEST", prompt, model_preference, "Prometheus", _parse_json_arr
    )
    if result is not None:
        return result
    logger.warning("[Prometheus] 모든 provider 실패")
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
    excerpt = "\n".join(str(h) for h in history)[:HISTORY_EXCERPT_MAX_CHARS]
    prompt_history = [_acm.render_prompt("summarize_history_user", excerpt=excerpt)]
    try:
        return await _call_with_fallback(
            "generate_final_answer",
            history=prompt_history,
            model_preference=model_preference,
        )
    except Exception:
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
    prompt = _acm.render_prompt("classify_intent_user", user_query=user_query)
    def _parse(raw):
        return "chat" if "chat" in raw.strip().lower()[:20] else "task"
    result = await _call_with_parse_fallback(
        "INTENT_CLASSIFY", prompt, model_preference, "IntentGate", _parse
    )
    return result if result is not None else "task"


_INTENT_CATEGORIES = frozenset({
    "dialogue", "code_write", "file_ops", "web_search", "analysis"
})
_COMPLEXITY_CATEGORIES = frozenset({"quick", "deep", "ultrabrain", "visual"})


async def classify_intent_full(
    user_query: str,
    model_preference: ModelPreference = "standard",
) -> str:
    """사용자 쿼리를 5-카테고리로 분류합니다.

    카테고리: dialogue / code_write / file_ops / web_search / analysis
    실패 시 'analysis' 반환 (보수적 기본값).
    """
    prompt = _acm.render_prompt("classify_intent_full_user", user_query=user_query)
    def _parse(raw):
        cat = raw.strip().lower().split()[0] if raw.strip() else ""
        return cat if cat in _INTENT_CATEGORIES else None
    try:
        result = await _call_with_parse_fallback(
            "INTENT_FULL", prompt, model_preference, "IntentGateFull", _parse
        )
    except Exception as exc:
        logger.warning(f"[IntentGateFull] 예외 발생, analysis로 폴백: {exc}")
        return "analysis"
    return result if result is not None else "analysis"


async def classify_intent_and_category(
    user_query: str,
    model_preference: ModelPreference = "standard",
) -> tuple:
    """의도(5-카테고리) + 복잡도(4-카테고리)를 단일 LLM 호출로 분류합니다.

    Returns:
        (intent, complexity) 튜플
        intent: "dialogue"|"code_write"|"file_ops"|"web_search"|"analysis"
        complexity: "quick"|"deep"|"ultrabrain"|"visual"
    실패 시 ("analysis", "deep") 반환 (보수적 기본값).
    """
    prompt = _acm.render_prompt("classify_intent_and_category_user", user_query=user_query)

    def _parse(raw: str):
        intent = None
        complexity = None
        for line in raw.strip().splitlines():
            line = line.strip().lower()
            if line.startswith("intent:"):
                val = line.split(":", 1)[1].strip().split()[0] if ":" in line else ""
                if val in _INTENT_CATEGORIES:
                    intent = val
            elif line.startswith("complexity:"):
                val = line.split(":", 1)[1].strip().split()[0] if ":" in line else ""
                if val in _COMPLEXITY_CATEGORIES:
                    complexity = val
        if intent and complexity:
            return (intent, complexity)
        return None

    try:
        result = await _call_with_parse_fallback(
            "INTENT_CATEGORY", prompt, model_preference, "IntentAndCategory", _parse
        )
    except Exception as exc:
        logger.warning(f"[IntentAndCategory] 예외 발생, 기본값 사용: {exc}")
        return ("analysis", "deep")
    return result if result is not None else ("analysis", "deep")


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
    system_ctx = persona_prompt + "\n\n" if persona_prompt else ""
    history_ctx = ""
    if history:
        recent = history[-RECENT_HISTORY_ITEMS:]
        history_ctx = "\n".join(str(h) for h in recent) + "\n\n"
    prompt = _acm.render_prompt(
        "design_user",
        system_ctx=system_ctx,
        history_ctx=history_ctx,
        user_query=user_query,
    )
    result = await _call_with_parse_fallback(
        "DESIGN_GENERATE", prompt, model_preference, "Design", _parse_json_obj
    )
    if result:
        return result
    return {
        "goal": user_query[:100],
        "approach": "단계적으로 처리합니다.",
        "constraints": [],
        "expected_outputs": ["완료"],
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
    design_text = (
        f"목표: {design.get('goal', '')}\n"
        f"접근법: {design.get('approach', '')}\n"
        f"결과물: {', '.join(design.get('expected_outputs', []))}"
    )
    prompt = _acm.render_prompt(
        "decompose_tasks_user",
        design_text=design_text,
        user_query=user_query,
    )
    def _parse(raw):
        arr = _parse_json_arr(raw)
        if not arr:
            return None
        valid = [{"title": t.get("title", "태스크"), "description": t.get("description", "")}
                 for t in arr if isinstance(t, dict)]
        return valid[:10] if valid else None
    result = await _call_with_parse_fallback(
        "TASK_DECOMPOSE", prompt, model_preference, "TaskDecompose", _parse
    )
    return result or [{"title": user_query[:80], "description": design.get("approach", "")}]


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
    tools_str = ", ".join(available_tools[:MAX_TOOLS_IN_PROMPT]) if available_tools else "없음"
    prompt = _acm.render_prompt(
        "map_plans_user",
        task_title=task.get("title", ""),
        task_description=task.get("description", ""),
        tools_str=tools_str,
    )
    def _parse(raw):
        arr = _parse_json_arr(raw)
        if not arr:
            return None
        valid = [{"action": p.get("action", "실행"), "tool_hints": p.get("tool_hints", [])[:5]}
                 for p in arr if isinstance(p, dict)]
        return valid[:8] if valid else None
    result = await _call_with_parse_fallback(
        "PLAN_MAP", prompt, model_preference, "PlanMap", _parse
    )
    return result or [{"action": task.get("title", "실행"), "tool_hints": []}]


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
    tools_desc = "\n".join(f"- {t}" for t in available_tools[:MAX_TOOLS_IN_PROMPT])
    history_ctx = ""
    if history:
        recent = "\n".join(str(h) for h in history[-RECENT_HISTORY_ITEMS:])
        history_ctx = f"최근 대화:\n{recent}\n\n"
    prompt = _acm.render_prompt(
        "build_execution_group_user",
        history_ctx=history_ctx,
        goal=design.get("goal", ""),
        task_title=task.get("title", ""),
        step_action=plan_step.get("action", ""),
        tool_hints=str(plan_step.get("tool_hints", [])),
        tools_desc=tools_desc,
    )
    def _parse(raw):
        group = _parse_json_obj(raw)
        if group and "group_id" in group and "tasks" in group:
            group.setdefault("description", plan_step.get("action", ""))
            return group
        return None
    result = await _call_with_parse_fallback(
        "EXEC_GROUP_BUILD", prompt, model_preference, "ExecGroupBuild", _parse
    )
    return result or {
        "group_id": "group_fallback",
        "description": plan_step.get("action", "실행"),
        "tasks": [],
    }


# ── Phase 2: 템플릿 인자 적응 ─────────────────────────────────────────────────


def _parse_json_obj(text: str) -> Optional[dict]:
    """raw 텍스트에서 JSON 객체({})를 추출합니다. 실패 시 None."""
    clean = _extract_json_block(text)
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _parse_json_arr(text: str) -> Optional[list]:
    """raw 텍스트에서 JSON 배열([])을 추출합니다. 실패 시 None."""
    clean = _extract_json_block(text)
    m = re.search(r"\[.*\]", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


async def _call_with_parse_fallback(
    prefix: str,
    prompt: str,
    model_preference: str,
    warn_prefix: str,
    parser_fn,
) -> Optional[Any]:
    """폴백 체인 순서대로 provider를 시도.
    parser_fn(raw)이 None이 아닌 결과를 반환하면 즉시 중단.
    모두 실패하면 None 반환. Circuit Breaker 적용.
    """
    for provider in _get_fallback_chain():
        tripped, trip_reason = _is_tripped(provider)
        if tripped:
            logger.info(f"[CircuitBreaker] ⏭ {provider} 스킵 ({warn_prefix}): {trip_reason}")
            continue
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"{prefix}: {prompt}"],
                model_preference=model_preference,
            )
            result = parser_fn(raw)
            if result is not None:
                return result
        except Exception as exc:
            trip = _detect_circuit_trip(exc, provider)
            if trip:
                duration, reason = trip
                _trip(provider, duration, reason)
            logger.warning(f"[{warn_prefix}] provider={provider} 실패: {exc}", exc_info=True)
    return None


async def extract_wisdom(
    tool_results: List[str],
    context: str = "",
) -> List[dict]:
    """도구 실행 결과에서 재사용 가능한 학습 사항을 추출합니다.

    standard 모델 사용 (비용 절약). 실패 시 [] 반환.
    Returns: [{category, content, source_tool}, ...]
    """
    if not tool_results:
        return []

    # 최근 10개 결과만 처리 (토큰 절약)
    results_text = "\n".join(str(r) for r in tool_results[-10:])
    prompt = _acm.render_prompt(
        "extract_wisdom_user",
        tool_results=results_text,
        context=context[:500],
    )

    def _parse(raw):
        arr = _parse_json_arr(raw)
        if not isinstance(arr, list):
            return None
        items = [{"category": e.get("category", "misc"), "content": e.get("content", ""),
                  "source_tool": e.get("source_tool", "")}
                 for e in arr if isinstance(e, dict) and e.get("content")]
        return items if items else None
    result = await _call_with_parse_fallback(
        "WISDOM_EXTRACT", prompt, "standard", "Wisdom", _parse
    )
    return result or []


async def validate_execution_plan(
    plan_list,
    available_tools: List[str],
) -> PlanValidation:
    """실행 계획의 도구 유효성·인자 충실도·완료 조건을 검증합니다.

    standard 모델 사용. 실패 시 PlanValidation(valid=True, score=1.0) 반환 (보수적 통과).
    """
    if not plan_list:
        return PlanValidation(valid=True, score=1.0)

    try:
        plan_json = json.dumps(
            [g.model_dump() if hasattr(g, "model_dump") else g for g in plan_list],
            ensure_ascii=False,
        )
    except Exception:
        return PlanValidation(valid=True, score=1.0)

    tools_str = ", ".join(available_tools[:50]) if available_tools else "없음"
    prompt = _acm.render_prompt(
        "validate_plan_user",
        available_tools=tools_str,
        plan_json=plan_json[:3000],
    )

    def _parse(raw):
        data = _parse_json_obj(raw)
        if data:
            return PlanValidation(
                valid=bool(data.get("valid", True)),
                score=float(data.get("score", 1.0)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
            )
        return None
    result = await _call_with_parse_fallback(
        "PLAN_VALIDATE", prompt, "standard", "PlanValidate", _parse
    )
    return result or PlanValidation(valid=True, score=1.0)


async def classify_task_category(user_query: str) -> str:
    """사용자 쿼리를 태스크 카테고리로 분류합니다 (LLM 없이 휴리스틱).

    Returns: "quick" | "deep" | "ultrabrain" | "visual"
    키워드 검사 우선, 단어 수는 fallback.
    """
    q = user_query.lower().strip()
    words = q.split()

    # 아키텍처/설계/전체/리팩터 키워드 → ultrabrain (키워드 우선)
    ultrabrain_kw = [
        "아키텍처", "설계", "전체", "리팩터", "리팩토링", "refactor",
        "architecture", "전반", "시스템 구조", "분석해줘", "분석 해줘",
        "전체적으로", "처음부터",
    ]
    if any(kw in q for kw in ultrabrain_kw):
        return "ultrabrain"

    # ui/css/화면/디자인/레이아웃 키워드 → visual
    visual_kw = [
        "ui", "css", "화면", "디자인", "레이아웃", "layout", "design",
        "스타일", "style", "색상", "color", "이미지", "image",
    ]
    if any(kw in q for kw in visual_kw):
        return "visual"

    # 단어 5개 이하 → quick (경량)
    if len(words) <= 5:
        return "quick"

    return "deep"


def _get_model_for_category(category: Optional[str]) -> str:
    """카테고리에 맞는 model_preference 문자열을 반환합니다."""
    from .constants import CATEGORY_MODEL_MAP
    return CATEGORY_MODEL_MAP.get(category or "", "auto")


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
    template_json = json.dumps(template_group, ensure_ascii=False, indent=2)
    history_ctx = ""
    if history:
        history_ctx = "최근 대화:\n" + "\n".join(str(h) for h in history) + "\n\n"
    prompt = _acm.render_prompt(
        "adapt_template_user",
        history_ctx=history_ctx,
        goal=design.get("goal", ""),
        task_title=task.get("title", ""),
        step_action=plan_step.get("action", ""),
        template_json=template_json,
    )
    def _parse(raw):
        adapted = _parse_json_obj(raw)
        if adapted and "group_id" in adapted and "tasks" in adapted:
            return adapted
        return None
    result = await _call_with_parse_fallback(
        "TEMPLATE_ADAPT", prompt, model_preference, "TemplateAdapt", _parse
    )
    return result or template_group
