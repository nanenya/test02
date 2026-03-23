#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/pipeline_manager.py
"""4층 파이프라인 오케스트레이터.

흐름:
  1. [DESIGN]   사용자 쿼리 → LLM(high) → 설계 생성 → DESIGN_CONFIRMATION
  2. [TASKS]    설계 확인 → LLM(standard) → 태스크 분해
  3. [PLANS]    각 태스크 → LLM(standard) → 계획 단계 매핑
  4. [EXEC]     계획 단계 → LLM(standard)/템플릿 → ExecutionGroup → PLAN_CONFIRMATION
     [ADVANCE]  실행 결과 → 다음 단계/태스크/완료 판단
  5. [FINAL]    모든 태스크 완료 → LLM → 최종 답변 → FINAL_ANSWER

LLM 티어 전략:
  - 설계 생성     : high   (창의적 판단 필요)
  - 태스크 분해   : standard
  - 계획 매핑     : standard (템플릿 미스 시)
  - 실행 그룹 빌드: standard (단일 단계, 컨텍스트 최소)
  - 최종 답변     : standard
  - 단순 분류     : standard → local (IntentGate에서 처리)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .models import AgentResponse, ExecutionGroup, ToolCall
from . import pipeline_db
from . import template_engine
from . import llm_router
from .graph_manager import get_db
from . import tool_registry
from . import history_manager
from . import token_tracker
from .llm_client import (
    generate_design,
    decompose_tasks,
    map_plans,
    build_execution_group_for_step,
    generate_final_answer,
    generate_title_for_conversation,
    extract_keywords,
)
from .constants import RECENT_HISTORY_ITEMS

logger = logging.getLogger(__name__)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_query_hash(query: str) -> str:
    """쿼리 텍스트의 SHA-256 앞 16자리를 반환합니다."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _make_task_signature(title: str, description: str) -> str:
    """태스크 제목+설명을 정규화해 SHA-256 앞 24자리 시그니처를 반환합니다."""
    import re as _re
    normalized = _re.sub(r"\s+", " ", (title + " " + description).lower().strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


async def _map_plans_with_cache(
    task: Dict[str, Any],
    available_tools: List[str],
    model_preference: str,
) -> List[Dict[str, Any]]:
    """task_plan_cache 조회 → 캐시 히트 시 LLM 없이 반환, 미스 시 LLM + 캐시 저장."""
    sig = _make_task_signature(task.get("title", ""), task.get("description", ""))
    cached_plans = pipeline_db.get_task_plan_cache(sig)
    if cached_plans:
        logger.info(f"[PlanCache] 히트: sig={sig[:8]}... task={task.get('title','')!r}")
        return cached_plans

    # 캐시 미스 → LLM 호출
    plans = await map_plans(
        task={"title": task.get("title", ""), "description": task.get("description", "")},
        available_tools=available_tools,
        model_preference=model_preference,
    )
    # 캐시 저장
    keywords = task.get("title", "").split()[:8]
    pipeline_db.save_task_plan_cache(sig, keywords, plans)
    logger.info(f"[PlanCache] 저장: sig={sig[:8]}... steps={len(plans)}")
    return plans


def _get_available_tools() -> List[str]:
    """현재 등록된 모든 도구 이름을 반환합니다 (로컬 + MCP)."""
    tools = list(tool_registry.TOOLS.keys())
    tools += list(tool_registry._mcp_tools.keys())
    return tools


def _resp(**kwargs) -> AgentResponse:
    kwargs.setdefault("token_usage", token_tracker.get_accumulated())
    return AgentResponse(**kwargs)


def _build_execution_group_obj(group_dict: Dict[str, Any]) -> Optional[ExecutionGroup]:
    """dict → ExecutionGroup 객체 변환. 실패 시 None."""
    try:
        tasks = [
            ToolCall(
                tool_name=t["tool_name"],
                arguments=t.get("arguments", {}),
                model_preference=t.get("model_preference", "standard"),
            )
            for t in group_dict.get("tasks", [])
        ]
        return ExecutionGroup(
            group_id=group_dict.get("group_id", "group_1"),
            description=group_dict.get("description", ""),
            tasks=tasks,
        )
    except Exception as e:
        logger.warning(f"ExecutionGroup 변환 실패: {e}")
        return None


def _format_design_message(design: Dict[str, Any], design_id: int) -> str:
    """설계 내용을 사용자에게 보여줄 텍스트로 포맷합니다."""
    constraints = "\n".join(f"  - {c}" for c in design.get("constraints", [])) or "  없음"
    outputs = "\n".join(f"  - {o}" for o in design.get("expected_outputs", [])) or "  미정"
    return (
        f"[설계 ID: {design_id}] 복잡도: {design.get('complexity', '?')}\n\n"
        f"목표: {design.get('goal', '')}\n\n"
        f"접근법: {design.get('approach', '')}\n\n"
        f"제약사항:\n{constraints}\n\n"
        f"예상 결과물:\n{outputs}\n\n"
        "─── 위 설계로 진행하려면 확인(confirm)하세요. "
        "수정이 필요하면 새로운 지시를 입력하세요. ───"
    )


# ── Phase 1: 설계 생성 ─────────────────────────────────────────────────────────

async def start_design_phase(
    conversation_id: str,
    query: str,
    history: List[str],
    persona_prompt: str = "",
    model_preference: str = "high",
) -> AgentResponse:
    """사용자 쿼리로부터 설계를 생성하고 DESIGN_CONFIRMATION을 반환합니다."""

    history.append(f"사용자 요청: {query}")

    # Phase 4: 설계는 항상 high (복잡도 추정 전이므로 쿼리 기반)
    inferred_complexity = llm_router.infer_complexity_from_query(query)
    design_tier = llm_router.route("design_generation", complexity=inferred_complexity,
                                   force=model_preference if model_preference != "auto" else None)
    try:
        design = await generate_design(
            user_query=query,
            persona_prompt=persona_prompt,
            history=history,
            model_preference=design_tier,
        )
    except Exception as e:
        logger.error(f"설계 생성 실패: {e}")
        design = {
            "goal": query[:100],
            "approach": "단계적으로 처리합니다.",
            "constraints": [],
            "expected_outputs": ["완료"],
            "complexity": "medium",
        }

    design_id = pipeline_db.create_design(
        conversation_id=conversation_id,
        query_text=query,
        design_text=json.dumps(design, ensure_ascii=False),
        approach=design.get("approach", ""),
        complexity=design.get("complexity", "medium"),
        persona_used=persona_prompt[:200] if persona_prompt else "",
        query_hash=_make_query_hash(query),
    )

    pipeline_db.set_cursor(
        conversation_id=conversation_id,
        phase="design_pending",
        design_id=design_id,
    )

    history_manager.save_conversation(
        conversation_id, history,
        f"설계: {design.get('goal', query[:30])}",
        plan=[], current_group_index=0, is_final=False,
    )

    return _resp(
        conversation_id=conversation_id,
        status="DESIGN_CONFIRMATION",
        history=history,
        message=_format_design_message(design, design_id),
        pipeline_state={"design_id": design_id, "phase": "design_pending"},
    )


# ── Phase 2~4: 설계 확인 후 태스크/계획/실행그룹 빌드 ─────────────────────────

async def proceed_after_design_confirm(
    conversation_id: str,
    design_id: int,
    history: List[str],
    model_preference: str = "standard",
) -> AgentResponse:
    """설계 확인 후 태스크 분해 → 첫 번째 실행 그룹을 반환합니다."""

    # 설계 확인 처리
    pipeline_db.confirm_design(design_id)
    design_row = pipeline_db.get_design(design_id)
    if not design_row:
        return _resp(
            conversation_id=conversation_id,
            status="ERROR",
            history=history,
            message="설계 정보를 찾을 수 없습니다.",
        )

    design = json.loads(design_row["design_text"])
    query = design_row["query_text"]
    history.append(f"설계 확인됨: {design.get('goal', '')}")

    # Phase 4: 태스크 분해 티어 라우팅
    complexity = llm_router.infer_complexity_from_design(design)
    task_tier = llm_router.route("task_decomposition", complexity=complexity)

    # 태스크 분해
    try:
        tasks_raw = await decompose_tasks(
            design=design,
            user_query=query,
            model_preference=task_tier,
        )
    except Exception as e:
        logger.error(f"태스크 분해 실패: {e}")
        tasks_raw = [{"title": query[:80], "description": design.get("approach", "")}]

    task_ids = pipeline_db.create_tasks(design_id, tasks_raw)
    if not task_ids:
        return _resp(
            conversation_id=conversation_id,
            status="ERROR",
            history=history,
            message="태스크 분해 결과가 없습니다.",
        )

    history.append(f"태스크 {len(task_ids)}개 분해 완료: " + ", ".join(t["title"] for t in tasks_raw[:3]))

    # 첫 번째 태스크 → 계획 매핑
    first_task = pipeline_db.get_next_pending_task(design_id)
    if not first_task:
        return _resp(
            conversation_id=conversation_id,
            status="ERROR",
            history=history,
            message="실행할 태스크가 없습니다.",
        )

    pipeline_db.update_task_status(first_task["id"], "in_progress")
    available_tools = _get_available_tools()

    try:
        plans_raw = await _map_plans_with_cache(first_task, available_tools, model_preference)
    except Exception as e:
        logger.error(f"계획 매핑 실패: {e}")
        plans_raw = [{"action": first_task["title"], "tool_hints": []}]

    pipeline_db.create_task_plans(first_task["id"], plans_raw)
    history.append(
        f"태스크 '{first_task['title']}' 계획 {len(plans_raw)}단계 수립"
    )

    # 첫 번째 계획 단계 → 실행 그룹 빌드
    first_plan = pipeline_db.get_next_pending_plan(first_task["id"])
    if not first_plan:
        return _resp(
            conversation_id=conversation_id,
            status="ERROR",
            history=history,
            message="계획 단계가 없습니다.",
        )

    return await _build_and_return_step(
        conversation_id=conversation_id,
        design=design,
        task=first_task,
        plan_step=first_plan,
        history=history,
        available_tools=available_tools,
        model_preference=model_preference,
    )


# ── Phase 4 Advance: 실행 후 다음 단계 결정 ───────────────────────────────────

async def advance_after_execution(
    conversation_id: str,
    execution_result: str,
    history: List[str],
    model_preference: str = "standard",
) -> AgentResponse:
    """현재 계획 단계 완료 처리 후 다음 단계/태스크/완료를 반환합니다."""

    cursor = pipeline_db.get_cursor(conversation_id)
    if not cursor or cursor["phase"] not in ("executing",):
        # 파이프라인 상태 없음 → 기존 방식으로 처리
        return None  # caller에서 기존 decide_and_act로 fallback

    design_id = cursor["design_id"]
    task_id = cursor["task_id"]
    plan_id = cursor["plan_id"]

    design_row = pipeline_db.get_design(design_id)
    if not design_row:
        return None
    design = json.loads(design_row["design_text"])

    # 현재 단계 완료 처리
    pipeline_db.update_plan_status(plan_id, "done", result=execution_result[:500])
    history.append(f"단계 실행 완료: {execution_result[:200]}")

    # 현재 태스크에 다음 계획 단계 있는지 확인
    next_plan = pipeline_db.get_next_pending_plan(task_id)
    if next_plan:
        # 다음 계획 단계 실행
        task_row = pipeline_db.get_tasks(design_id)
        current_task = next((t for t in task_row if t["id"] == task_id), {})
        available_tools = _get_available_tools()
        return await _build_and_return_step(
            conversation_id=conversation_id,
            design=design,
            task=current_task,
            plan_step=next_plan,
            history=history,
            available_tools=available_tools,
            model_preference=model_preference,
        )

    # 현재 태스크 완료 → 다음 태스크 확인
    pipeline_db.update_task_status(task_id, "done")
    next_task = pipeline_db.get_next_pending_task(design_id)

    if next_task:
        # 다음 태스크 시작
        pipeline_db.update_task_status(next_task["id"], "in_progress")
        available_tools = _get_available_tools()
        history.append(f"다음 태스크 시작: {next_task['title']}")

        try:
            plans_raw = await _map_plans_with_cache(next_task, available_tools, model_preference)
        except Exception as e:
            logger.warning(f"계획 매핑 실패: {e}")
            plans_raw = [{"action": next_task["title"], "tool_hints": []}]

        pipeline_db.create_task_plans(next_task["id"], plans_raw)

        next_plan_step = pipeline_db.get_next_pending_plan(next_task["id"])
        if not next_plan_step:
            return await _finish_pipeline(conversation_id, design_id, history, model_preference)

        return await _build_and_return_step(
            conversation_id=conversation_id,
            design=design,
            task=next_task,
            plan_step=next_plan_step,
            history=history,
            available_tools=available_tools,
            model_preference=model_preference,
        )

    # 모든 태스크 완료 → 최종 답변
    return await _finish_pipeline(conversation_id, design_id, history, model_preference)


# ── 내부 헬퍼: 실행 그룹 빌드 → PLAN_CONFIRMATION 반환 ────────────────────────

async def _try_template_match(plan_step, task, design, history, model_preference):
    """template_engine으로 매칭 시도. 실패 시 (None, None)."""
    try:
        group_dict, template_id = await template_engine.find_and_adapt(
            plan_step=plan_step,
            task={"title": task.get("title", ""), "description": task.get("description", "")},
            design=design, history=history, model_preference=model_preference,
        )
        if group_dict:
            history.append(f"[캐시] 실행 템플릿 적용 (id={template_id})")
            return group_dict, template_id
    except Exception as e:
        logger.warning(f"[Pipeline] template_engine 실패: {e}")
    return None, None


async def _build_group_with_llm(plan_step, task, design, available_tools, history, model_preference):
    """LLM으로 실행 그룹 빌드. 실패 시 빈 그룹 반환."""
    try:
        return await build_execution_group_for_step(
            plan_step=plan_step,
            task={"title": task.get("title", ""), "description": task.get("description", "")},
            design=design, available_tools=available_tools,
            history=history[-RECENT_HISTORY_ITEMS:], model_preference=model_preference,
        )
    except Exception as e:
        logger.error(f"실행 그룹 빌드 실패: {e}")
        return {"group_id": f"group_{plan_step['id']}", "description": plan_step.get("action", "실행"), "tasks": []}


def _filter_available_tools(group_dict: dict, available_tools: list, plan_step: dict) -> list:
    """이용 불가 도구를 필터링하고 tool_gap을 로깅합니다."""
    available_set = set(available_tools)
    filtered = []
    for t in group_dict.get("tasks", []):
        tool_name = t.get("tool_name", "")
        if tool_name in available_set:
            filtered.append(t)
        else:
            logger.warning(f"[Pipeline] 도구 없음: {tool_name}")
            pipeline_db.log_tool_gap(
                required_tool=tool_name, resolution_type="not_found",
                note=f"plan_step_id={plan_step['id']}",
            )
    return filtered


async def _build_and_return_step(
    conversation_id: str,
    design: Dict[str, Any],
    task: Dict[str, Any],
    plan_step: Dict[str, Any],
    history: List[str],
    available_tools: List[str],
    model_preference: str = "standard",
) -> AgentResponse:
    """단일 계획 단계에 대한 ExecutionGroup을 빌드하고 PLAN_CONFIRMATION을 반환합니다.

    템플릿 엔진(향상된 스코어링 + 인자 적응) → LLM 순서로 시도합니다.
    """
    # ① template_engine: 향상된 스코어링 + 인자 적응 (Phase 2 핵심)
    group_dict, template_id = await _try_template_match(
        plan_step, task, design, history, model_preference
    )

    # ② 템플릿 미스 시 LLM으로 실행 그룹 빌드
    if not group_dict:
        group_dict = await _build_group_with_llm(
            plan_step, task, design, available_tools, history, model_preference
        )

    # 존재하지 않는 도구 필터링 + tool_gap_log 기록
    group_dict["tasks"] = _filter_available_tools(group_dict, available_tools, plan_step)

    # ExecutionGroup 객체 변환
    exec_group = _build_execution_group_obj(group_dict)

    # 커서 업데이트
    pipeline_db.update_plan_status(plan_step["id"], "in_progress", template_id=template_id)
    pipeline_db.set_cursor(
        conversation_id=conversation_id,
        phase="executing",
        design_id=_get_design_id_for_task(task["id"]),
        task_id=task["id"],
        plan_id=plan_step["id"],
    )

    # 대화 저장
    task_summary = task.get("title", "")
    step_summary = plan_step.get("action", "")
    title = f"[{task_summary}] {step_summary}"[:60]
    history_manager.save_conversation(
        conversation_id, history, title,
        plan=[group_dict], current_group_index=0, is_final=False,
    )

    message = (
        f"[태스크: {task_summary}]\n"
        f"[단계: {step_summary}]\n"
        f"{group_dict.get('description', '')}"
    )
    if template_id:
        message += "\n(캐시 템플릿 적용됨)"

    return _resp(
        conversation_id=conversation_id,
        status="PLAN_CONFIRMATION",
        history=history,
        message=message,
        execution_group=exec_group,
        pipeline_state={
            "design_id": _get_design_id_for_task(task["id"]),
            "task_id": task["id"],
            "plan_id": plan_step["id"],
            "phase": "executing",
        },
    )


def _get_design_id_for_task(task_id: int) -> Optional[int]:
    """task_id로 design_id를 역조회합니다."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT design_id FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        return row["design_id"] if row else None


# ── Phase 5: 파이프라인 완료 ──────────────────────────────────────────────────

async def _finish_pipeline(
    conversation_id: str,
    design_id: int,
    history: List[str],
    model_preference: str = "standard",
) -> AgentResponse:
    """모든 태스크 완료 후 최종 답변을 생성합니다."""

    pipeline_db.clear_cursor(conversation_id)

    try:
        final_answer = await generate_final_answer(history, model_preference)
    except Exception as e:
        logger.error(f"최종 답변 생성 실패: {e}")
        final_answer = "모든 작업이 완료되었습니다."

    history.append(f"최종 답변: {final_answer}")

    try:
        title = await generate_title_for_conversation(history, model_preference)
    except Exception:
        title = "완료된 작업"

    history_manager.save_conversation(
        conversation_id, history, title, plan=[], current_group_index=0, is_final=True
    )

    try:
        keywords = await extract_keywords(history, model_preference)
        if keywords:
            from . import graph_manager
            graph_manager.assign_keywords_to_conversation(conversation_id, keywords)
    except Exception:
        pass

    return _resp(
        conversation_id=conversation_id,
        status="FINAL_ANSWER",
        history=history,
        message=final_answer,
        pipeline_state={"design_id": design_id, "phase": "done"},
    )


# ── 실행 템플릿 학습 (성공 후 호출) ─────────────────────────────────────────────

def record_execution_success(
    plan_id: int,
    execution_group_dict: Dict[str, Any],
) -> None:
    """실행 성공 후 템플릿을 저장/업데이트합니다.

    Phase 2 핵심: 성공 패턴이 쌓일수록 LLM 호출 감소.
    예외는 절대 발생시키지 않습니다.
    """
    try:
        with get_db() as conn:
            plan_row = conn.execute(
                "SELECT tp.*, t.title, t.design_id FROM task_plans tp "
                "JOIN tasks t ON tp.task_id = t.id WHERE tp.id=?",
                (plan_id,),
            ).fetchone()
            if not plan_row:
                return

        tool_names = [
            t.get("tool_name", "") for t in execution_group_dict.get("tasks", [])
        ]
        action = plan_row["action"]
        task_title = plan_row["title"]
        keywords = tool_names + action.split()[:5] + task_title.split()[:3]
        keywords = list(dict.fromkeys(k for k in keywords if k))  # 중복 제거

        template_name = f"{task_title[:30]}:{action[:30]}"
        pipeline_db.save_execution_template(
            name=template_name,
            description=f"{task_title} - {action}",
            keywords=keywords,
            execution_group=execution_group_dict,
        )
        logger.info(f"[Pipeline] 실행 템플릿 저장: {template_name}")
    except Exception as e:
        logger.warning(f"템플릿 저장 실패 (무시): {e}")
