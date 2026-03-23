#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from .models import AgentRequest, AgentResponse, ExecutionGroup, WisdomEntry, PlanValidation
from .llm_client import (
    generate_execution_plan,
    generate_parallel_plan,
    generate_final_answer,
    generate_title_for_conversation,
    extract_keywords,
    detect_topic_split,
    classify_intent,
    classify_intent_full,
    classify_intent_and_category,
    extract_wisdom,
    validate_execution_plan,
    classify_task_category,
    summarize_history,
    _get_model_for_category,
)
from .constants import (
    PLAN_VALIDATION_MIN_SCORE,
    HISTORY_AUTO_SUMMARIZE_THRESHOLD,
    HISTORY_KEEP_RECENT,
    HISTORY_SUMMARY_MARKER,
    USER_REQUEST_PREFIX,
    TOOL_RESULT_TRUNCATED_SUFFIX,
)

from . import tool_registry
from . import history_manager
from . import graph_manager
from . import agent_config_manager
from . import mcp_db_manager
from . import pipeline_db
from . import pipeline_manager
import asyncio
import inspect
import logging
import os
import re
import time
from datetime import datetime
from fastapi.responses import JSONResponse
from . import issue_tracker
from . import token_tracker


from .constants import (
    RECENT_HISTORY_ITEMS, RESULT_HISTORY_ITEMS,
)
from ._api_helpers import (
    _resp,
    _apply_category_preference,
    _validate_and_replan,
    _resolve_persona,
    _format_wisdom,
    _maybe_auto_summarize,
    _validate_requirement_path,
    _prune_history,
    _extract_first_query,
    _validate_tool_arguments,
    _execute_single_task,
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    graph_manager.init_db()
    agent_config_manager.init_db()
    issue_tracker.init_db()
    pipeline_db.init_db()          # 4층 파이프라인 테이블 초기화
    await tool_registry.initialize()
    yield
    await tool_registry.shutdown()

app = FastAPI(title="Multi-Provider Agent Orchestrator", lifespan=lifespan)

from .web_router import router as web_router  # noqa: E402
app.include_router(web_router)


@app.exception_handler(Exception)
async def _global_exception_handler(request, exc: Exception):
    import traceback as _tb
    issue_tracker.capture(
        error_message=str(exc),
        error_type=type(exc).__name__,
        traceback=_tb.format_exc(),
        context=f"{request.method} {request.url.path}",
        source="api_server",
        severity="error",
    )
    return JSONResponse(status_code=500, content={"detail": f"내부 서버 오류: {type(exc).__name__}"})

from ._agent_handlers import _handle_new_query, _handle_replan

@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    """
    ReAct 루프의 핵심.
    1. 사용자 입력(신규/수정)이 있으면: '첫 번째' 계획 그룹을 생성합니다.
    2. 사용자 입력이 없으면(STEP_EXECUTED 후): History를 기반으로 '다음' 계획 그룹을 생성합니다.
    3. Planner가 '[]'를 반환하면: 'FINAL_ANSWER'를 생성합니다.
    """
    token_tracker.begin_tracking()

    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else request.history
    convo_id = data.get("id", request.conversation_id) if data else request.conversation_id

    # 페르소나 해석
    effective_system_prompts, effective_allowed_skills = _resolve_persona(
        request.system_prompts or [],
        request.allowed_skills,
        request.user_input or "",
        request.persona,
    )

    if request.user_input or not history:
        return await _handle_new_query(
            request, convo_id, history, effective_system_prompts, effective_allowed_skills
        )
    else:
        return await _handle_replan(
            request, convo_id, history, data or {}, effective_system_prompts, effective_allowed_skills
        )


@app.post("/agent/execute_group", response_model=AgentResponse)
async def execute_group(request: AgentRequest):
    """
    저장된 그룹을 실행합니다. can_parallel=True 그룹은 병렬 실행 [A].
    완료 후 'STEP_EXECUTED'를 반환하여 Re-plan을 트리거합니다.
    """
    token_tracker.begin_tracking()

    data = history_manager.load_conversation(request.conversation_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"대화 ID '{request.conversation_id}'를 찾을 수 없습니다. "
                   "새 대화를 시작하려면 /agent/decide_and_act에 user_input을 전달하세요.",
        )

    history = data.get("history", [])
    plan_dicts = data.get("plan", [])
    convo_id = data.get("id", request.conversation_id)

    if not plan_dicts:
        raise HTTPException(status_code=400, detail="실행할 계획이 없습니다.")

    plan_list = [ExecutionGroup(**group) for group in plan_dicts]

    async def _run_single_group(grp: ExecutionGroup) -> tuple:
        """단일 그룹의 모든 태스크를 실행합니다. (success: bool, exc: Exception|None) 반환."""
        sess_id = None
        try:
            sess_id = mcp_db_manager.start_session(
                conversation_id=convo_id, group_id=grp.group_id
            )
        except Exception as e:
            logging.warning(f"mcp_db_manager.start_session 실패: {e}")

        history.append(f"그룹 실행 시작: [{grp.group_id}] {grp.description}")
        for task in grp.tasks:
            history.append(f"  - 도구 실행: {task.tool_name} (인자: {task.arguments})")

        try:
            # P3-A: 그룹 내 태스크를 asyncio.gather로 병렬 실행
            results = await asyncio.gather(
                *[_execute_single_task(task, sess_id) for task in grp.tasks],
                return_exceptions=True,
            )
            first_exc = None
            for r in results:
                if isinstance(r, Exception):
                    # return_exceptions=True 시 Exception 객체 직접 반환 (#52/#53)
                    first_exc = r
                    history.append(f"  - 실행 오류 (unknown): {r}")
                else:
                    tool_name, result_str, exc = r
                    if exc is not None:
                        first_exc = exc
                        history.append(f"  - 실행 오류 ({tool_name}): {exc}")
                    else:
                        history.append(f"  - 실행 결과 ({tool_name}): {result_str}")

            if first_exc is not None:
                try:
                    if sess_id:
                        mcp_db_manager.end_session(sess_id, overall_success=False)
                except Exception:
                    pass
                return False, first_exc

            history.append(f"그룹 실행 완료: [{grp.group_id}]")
            try:
                if sess_id:
                    mcp_db_manager.end_session(sess_id, overall_success=True)
            except Exception as end_err:
                logging.warning(f"mcp_db_manager.end_session 실패: {end_err}")
            return True, None

        except Exception as e:
            try:
                if sess_id:
                    mcp_db_manager.end_session(sess_id, overall_success=False)
            except Exception:
                pass
            return False, e

    # [A] 병렬/직렬 그룹 분리
    parallel_groups = [g for g in plan_list if g.can_parallel]
    serial_groups = [g for g in plan_list if not g.can_parallel]

    overall_error = None
    failed_group_id = None

    # 병렬 그룹 동시 실행
    if parallel_groups:
        par_results = await asyncio.gather(
            *[_run_single_group(g) for g in parallel_groups],
            return_exceptions=True,
        )
        for i, r in enumerate(par_results):
            if isinstance(r, Exception):
                logging.error(f"[A-Parallel] group {parallel_groups[i].group_id} 실패: {r}")
            elif isinstance(r, tuple) and not r[0]:
                logging.warning(f"[A-Parallel] group {parallel_groups[i].group_id} 실패: {r[1]}")

    # 직렬 그룹 순차 실행
    for grp in serial_groups:
        success, exc = await _run_single_group(grp)
        if not success:
            overall_error = exc
            failed_group_id = grp.group_id
            break

    if overall_error is not None:
        is_validation_err = isinstance(overall_error, ValueError)
        if is_validation_err:
            logging.warning(f"execute_group 검증 오류 [{failed_group_id}]: {overall_error}")
        else:
            issue_tracker.capture_exception(
                overall_error, context=f"execute_group group_id={failed_group_id}", source="tool"
            )
        history.append(f"그룹 실행 중 오류 발생: {overall_error}")
        history_manager.save_conversation(convo_id, history, "실행 오류", plan_dicts, 0, is_final=False)
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{failed_group_id}' 실행 중 오류: {overall_error}",
        )

    history_manager.save_conversation(
        convo_id, history, data.get("title", "실행 중"), [], 0, is_final=False
    )

    # [B] 실행 결과에서 지식 추출 (백그라운드식, 실패 무시)
    try:
        result_lines = [h for h in history[-RESULT_HISTORY_ITEMS:] if "실행 결과" in h]
        ctx = history[0] if history else ""
        wisdom = await extract_wisdom(result_lines, ctx)
        if wisdom:
            graph_manager.save_wisdom(convo_id, wisdom)
            executed_ids = [g.group_id for g in plan_list]
            logging.info(f"[B-Wisdom] {len(wisdom)}개 지식 저장 (그룹: {executed_ids})")
    except Exception as we:
        logging.debug(f"[B-Wisdom] 추출 실패 (무시): {we}")

    executed_count = len(parallel_groups) + len(serial_groups)
    return _resp(
        conversation_id=convo_id,
        status="STEP_EXECUTED",
        history=history,
        message=f"그룹 실행 완료 ({executed_count}개 그룹)"
    )


@app.post("/agent/pipeline", response_model=AgentResponse)
async def pipeline_endpoint(request: AgentRequest):
    """4층 파이프라인 통합 엔드포인트.

    상태 흐름:
      1. user_input 있음 + pipeline_cursor 없음  → 설계 생성 (DESIGN_CONFIRMATION)
      2. pipeline_action="confirm_design"        → 태스크 분해 → 첫 실행 그룹 (PLAN_CONFIRMATION)
      3. pipeline_action="reject_design"         → 설계 거부 후 재설계 (DESIGN_CONFIRMATION)
      4. pipeline_cursor.phase="executing"       → 다음 단계 계산 (PLAN_CONFIRMATION or FINAL_ANSWER)
    """
    token_tracker.begin_tracking()

    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else list(request.history)
    convo_id = data.get("id", request.conversation_id) if data else request.conversation_id

    # 페르소나 해석
    _prompts, effective_allowed_skills = _resolve_persona(
        list(request.system_prompts) if request.system_prompts else [],
        request.allowed_skills,
        request.user_input or "",
        request.persona,
    )
    persona_prompt = "\n".join(_prompts) if _prompts else ""

    try:
        cursor = pipeline_db.get_cursor(convo_id)

        # ── 설계 확인/거부 처리 ─────────────────────────────────────
        if request.pipeline_action == "reject_design":
            design_id = (cursor or {}).get("design_id") or (
                (request.pipeline_state or {}).get("design_id")
            )
            if design_id:
                pipeline_db.reject_design(design_id)
                history.append("설계 거부됨. 재설계 진행.")
            # 새 설계 생성 (user_input 없으면 원래 쿼리 재사용)
            query = request.user_input or _extract_first_query(history)
            return await pipeline_manager.start_design_phase(
                conversation_id=convo_id,
                query=query,
                history=history,
                persona_prompt=persona_prompt,
                model_preference="high",
            )

        if request.pipeline_action == "confirm_design":
            design_id = (cursor or {}).get("design_id") or (
                (request.pipeline_state or {}).get("design_id")
            )
            if not design_id:
                raise HTTPException(status_code=400, detail="확인할 설계 ID가 없습니다.")
            return await pipeline_manager.proceed_after_design_confirm(
                conversation_id=convo_id,
                design_id=design_id,
                history=history,
                model_preference=request.model_preference,
            )

        # ── 실행 후 다음 단계 진행 (user_input 없음 + executing 상태) ──
        if not request.user_input and cursor and cursor.get("phase") == "executing":
            # execute_group에서 실행이 완료된 후 호출됨
            execution_result = history[-1] if history else ""
            result = await pipeline_manager.advance_after_execution(
                conversation_id=convo_id,
                execution_result=execution_result,
                history=history,
                model_preference=request.model_preference,
            )
            if result is not None:
                return result
            # None이면 파이프라인 상태 없음 → fallback to decide_and_act 로직

        # ── 신규 쿼리 → 설계 생성 ──────────────────────────────────────
        if request.user_input:
            # IntentGate: chat이면 즉시 답변 (토큰 절약)
            try:
                intent = await classify_intent(request.user_input, "standard")
                if intent == "chat":
                    history.append(f"사용자 요청: {request.user_input}")
                    direct = await generate_final_answer(history, request.model_preference)
                    history.append(f"최종 답변: {direct}")
                    title = await generate_title_for_conversation(history, request.model_preference)
                    history_manager.save_conversation(
                        convo_id, history, title, [], 0, is_final=True
                    )
                    return _resp(
                        conversation_id=convo_id,
                        status="FINAL_ANSWER",
                        history=history,
                        message=direct,
                    )
            except Exception as e:
                logging.warning(f"IntentGate 실패: {e}")

            return await pipeline_manager.start_design_phase(
                conversation_id=convo_id,
                query=request.user_input,
                history=history,
                persona_prompt=persona_prompt,
                model_preference="high",
            )

        # ── 아무 상태도 없으면 안내 ────────────────────────────────────
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message="처리할 입력이 없습니다. user_input 또는 pipeline_action을 지정하세요.",
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        issue_tracker.capture(
            error_message=str(e),
            error_type=type(e).__name__,
            traceback=_tb.format_exc(),
            context=f"pipeline_endpoint convo_id={convo_id}",
            source="pipeline",
        )
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"파이프라인 오류: {type(e).__name__}: {e}",
        )


@app.post("/agent/pipeline/execute", response_model=AgentResponse)
async def pipeline_execute(request: AgentRequest):
    """파이프라인 전용 그룹 실행 엔드포인트.

    기존 /agent/execute_group과 동일하게 그룹을 실행하되,
    실행 성공 시 pipeline_manager.record_execution_success()를 호출하여
    템플릿 학습을 수행합니다.
    """
    token_tracker.begin_tracking()

    data = history_manager.load_conversation(request.conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="대화 ID를 찾을 수 없습니다.")

    history = data.get("history", [])
    plan_dicts = data.get("plan", [])
    convo_id = data.get("id", request.conversation_id)

    if not plan_dicts:
        raise HTTPException(status_code=400, detail="실행할 계획이 없습니다.")

    group_dict = plan_dicts[0]
    group_to_execute = ExecutionGroup(**group_dict)
    history.append(f"그룹 실행 시작: [{group_to_execute.group_id}] {group_to_execute.description}")

    session_id = None
    try:
        session_id = mcp_db_manager.start_session(convo_id, group_to_execute.group_id)
    except Exception as e:
        logging.warning(f"start_session 실패: {e}")

    raw_results = await asyncio.gather(
        *[_execute_single_task(task, session_id) for task in group_to_execute.tasks],
        return_exceptions=True,
    )
    results = []
    overall_success = True
    for r in raw_results:
        if isinstance(r, Exception):
            results.append(("unknown", "", r))
            overall_success = False
        else:
            tool_name, result_str, exc = r
            results.append((tool_name, result_str, exc))
            if exc is not None:
                overall_success = False

    has_error = False
    for tool_name, result_str, exc in results:
        if exc is not None:
            has_error = True
            history.append(f"  - 실행 오류 ({tool_name}): {exc}")
            # 파이프라인 템플릿 실패 카운트
            cursor = pipeline_db.get_cursor(convo_id)
            if cursor and cursor.get("plan_id"):
                with pipeline_db.get_db() as conn:
                    row = conn.execute(
                        "SELECT template_id FROM task_plans WHERE id=?",
                        (cursor["plan_id"],)
                    ).fetchone()
                    if row and row["template_id"]:
                        pipeline_db.increment_template_fail(row["template_id"])
        else:
            history.append(f"  - 실행 결과 ({tool_name}): {result_str}")

    try:
        if session_id:
            mcp_db_manager.end_session(session_id, overall_success=overall_success)
    except Exception as e:
        logging.warning(f"end_session 실패: {e}")

    if has_error:
        history_manager.save_conversation(convo_id, history, "실행 오류", plan_dicts, 0, is_final=False)
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류 발생",
        )

    # 성공 → 템플릿 학습
    cursor = pipeline_db.get_cursor(convo_id)
    if cursor and cursor.get("plan_id"):
        pipeline_manager.record_execution_success(cursor["plan_id"], group_dict)

    history.append(f"그룹 실행 완료: [{group_to_execute.group_id}]")
    history_manager.save_conversation(convo_id, history, data.get("title", "실행 중"), [], 0, is_final=False)

    return _resp(
        conversation_id=convo_id,
        status="STEP_EXECUTED",
        history=history,
        message=f"그룹 [{group_to_execute.group_id}] 실행 완료",
        pipeline_state=cursor,
    )


# StaticFiles는 반드시 마지막에 마운트 (라우팅 우선순위)
import os as _os
_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
