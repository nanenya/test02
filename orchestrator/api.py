#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from .models import AgentRequest, AgentResponse, ExecutionGroup
from .llm_client import (
    generate_execution_plan,
    generate_final_answer,
    generate_title_for_conversation,
    extract_keywords,
    detect_topic_split,
    classify_intent,
)

# P3-B: 역할별 시스템 프롬프트
_ROLE_PROMPTS = {
    "planner": (
        "당신은 계획 수립 전문가(Planner)입니다. "
        "주어진 작업을 명확하고 실행 가능한 단계별 계획으로 분해하세요. "
        "병렬 실행 가능한 단계는 같은 그룹에 배치하고, "
        "각 그룹은 독립적으로 완료될 수 있어야 합니다."
    ),
    "reviewer": (
        "당신은 결과 검토 전문가(Reviewer)입니다. "
        "이전 실행 결과를 면밀히 검토하고, 작업이 완전히 완료되었는지 확인하세요. "
        "미완료 항목이 있으면 다음 실행 단계를 계획하고, "
        "모든 작업이 완료되었으면 반드시 빈 계획([])을 반환하세요."
    ),
}
from . import tool_registry
from . import history_manager
from . import graph_manager
from . import agent_config_manager
from . import mcp_db_manager
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


from .constants import MAX_HISTORY_ENTRIES, MAX_TOOL_RESULT_LENGTH, MAX_REQUIREMENT_FILE_SIZE


def _resp(**kwargs) -> AgentResponse:
    """token_usage를 자동으로 포함한 AgentResponse를 생성합니다."""
    kwargs.setdefault("token_usage", token_tracker.get_accumulated())
    return AgentResponse(**kwargs)


def _validate_requirement_path(path: str) -> str:
    """요구사항 파일 경로를 검증합니다.

    심볼릭 링크를 해소하고, 일반 파일 여부와 1MB 크기 제한을 확인합니다.
    Returns:
        실제 경로(realpath) 문자열
    Raises:
        ValueError: 파일이 존재하지 않거나 일반 파일이 아니거나 너무 큰 경우
    """
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise ValueError(f"요구사항 경로가 일반 파일이 아닙니다: {path}")
    if os.path.getsize(real) > MAX_REQUIREMENT_FILE_SIZE:
        raise ValueError(f"요구사항 파일이 너무 큽니다 (최대 1MB): {path}")
    return real


def _prune_history(history: list) -> list:
    """대화 이력이 MAX_HISTORY_ENTRIES를 초과하면 오래된 항목을 제거합니다."""
    if len(history) > MAX_HISTORY_ENTRIES:
        logging.info(
            f"대화 이력이 {MAX_HISTORY_ENTRIES}개를 초과하여 오래된 항목을 제거합니다. "
            f"(현재: {len(history)}개)"
        )
        return history[-MAX_HISTORY_ENTRIES:]
    return history


def _extract_first_query(history: list) -> str:
    """대화 이력에서 첫 번째 사용자 요청을 추출합니다.

    '사용자 요청: ' 접두어로 시작하는 첫 번째 항목에서 내용을 반환합니다.
    찾지 못하면 기본 문자열을 반환합니다.
    """
    prefix = "사용자 요청:"
    for entry in history:
        if isinstance(entry, str) and entry.startswith(prefix):
            return entry[len(prefix):].strip()
    return "이전 작업을 계속하세요."


def _validate_tool_arguments(tool_function, tool_name: str, arguments: dict) -> None:
    """LLM이 생성한 tool 인자를 함수 서명과 대조하여 검증합니다.

    허용되지 않은 인자가 있으면 ValueError를 발생시킵니다.
    **kwargs를 받는 함수나 서명 조회가 불가능한 경우에는 검증을 생략합니다.
    """
    try:
        sig = inspect.signature(tool_function)
    except (ValueError, TypeError):
        return
    # **kwargs 파라미터가 있으면 모든 keyword 인자를 허용
    if any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    ):
        return
    allowed = set(sig.parameters.keys())
    unknown = set(arguments.keys()) - allowed
    if unknown:
        raise ValueError(
            f"도구 '{tool_name}'에 허용되지 않은 인자: {unknown}. 허용된 인자: {allowed}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph_manager.init_db()
    agent_config_manager.init_db()
    issue_tracker.init_db()
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

@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    """
    (수정) ReAct 루프의 핵심.
    1. 사용자 입력(신규/수정)이 있으면: '첫 번째' 계획 그룹을 생성합니다.
    2. 사용자 입력이 없으면(STEP_EXECUTED 후): History를 기반으로 '다음' 계획 그룹을 생성합니다.
    3. Planner가 '[]'를 반환하면: 'FINAL_ANSWER'를 생성합니다.
    """
    token_tracker.begin_tracking()

    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else request.history
    convo_id = data.get("id", request.conversation_id) if data else request.conversation_id

    # 페르소나 해석
    effective_system_prompts = request.system_prompts or []
    effective_allowed_skills = request.allowed_skills  # None = 필터 없음

    if not effective_system_prompts:
        persona = agent_config_manager.get_effective_persona(
            query=request.user_input or "",
            explicit_name=request.persona,
        )
        if persona:
            effective_system_prompts = [persona["system_prompt"]]
            if effective_allowed_skills is None and persona.get("allowed_skills"):
                effective_allowed_skills = persona["allowed_skills"]

    if request.user_input or not history:
        query = request.user_input or "무엇을 할까요?"

        if request.user_input:
            history.append(f"사용자 요청: {query}")

        # P3-C: IntentGate — chat/task 분류 후 chat이면 즉시 최종 답변 반환
        try:
            intent = await classify_intent(query, request.model_preference)
            if intent == "chat":
                direct_answer = await generate_final_answer(history, request.model_preference)
                history.append(f"최종 답변: {direct_answer}")
                title_summary = await generate_title_for_conversation(history, request.model_preference)
                history_manager.save_conversation(
                    convo_id, history, title_summary, [], 0, is_final=True
                )
                return _resp(
                    conversation_id=convo_id,
                    status="FINAL_ANSWER",
                    history=history,
                    message=direct_answer,
                )
        except Exception as intent_err:
            logging.warning(f"IntentGate 실패, task로 진행: {intent_err}")

        # P3-B: Planner 역할 프롬프트 주입
        planner_prompts = [_ROLE_PROMPTS["planner"]] + effective_system_prompts

        requirements_content = ""
        if request.requirement_paths:
            history.append(f"요구사항 파일 참조: {', '.join(request.requirement_paths)}")
            for path in request.requirement_paths:
                try:
                    real_path = _validate_requirement_path(path)
                    with open(real_path, 'r', encoding='utf-8') as f:
                        requirements_content += f"--- {os.path.basename(real_path)} ---\n"
                        requirements_content += f.read()
                        requirements_content += "\n-----------------------------------\n\n"
                except Exception as e:
                    history.append(f"경고: 요구사항 파일 '{path}' 읽기 실패: {e}")

        try:
            plan_list = await generate_execution_plan(
                user_query=query,
                requirements_content=requirements_content,
                history=history,
                model_preference=request.model_preference,
                system_prompts=planner_prompts,
                allowed_skills=effective_allowed_skills,
            )
            
            if not plan_list:
                 return _resp(
                    conversation_id=convo_id,
                    status="FINAL_ANSWER",
                    history=history,
                    message="요청하신 작업에 대해 실행할 단계가 없습니다. (작업 완료)"
                )
            
            history = _prune_history(history)
            plan_dicts = [group.model_dump() for group in plan_list]
            history_manager.save_conversation(
                convo_id, history, f"계획: {plan_list[0].description[:20]}...", plan_dicts, 0, is_final=False
            )

            first_group = plan_list[0]
            return _resp(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"[{first_group.group_id}] {first_group.description}",
                execution_group=first_group
            )

        except Exception as e:
            issue_tracker.capture_exception(
                e, context=f"generate_execution_plan convo_id={convo_id}", source="agent"
            )
            history.append(f"계획 수립 오류: {e}")
            # (수정 2) 누락된 인자 plan=[], current_group_index=0 추가
            history_manager.save_conversation(
                convo_id, history, "계획 실패", plan=[], current_group_index=0, is_final=False
            )
            return _resp(
                conversation_id=convo_id,
                status="ERROR",
                history=history,
                message=f"계획 수립 중 오류 발생: {e}",
            )

    else:
        try:
            first_query = _extract_first_query(history)

            # P3-B: Reviewer 역할 프롬프트 주입 (재계획 단계)
            reviewer_prompts = [_ROLE_PROMPTS["reviewer"]] + effective_system_prompts

            plan_list = await generate_execution_plan(
                user_query=first_query,
                requirements_content="",
                history=history,
                model_preference=request.model_preference,
                system_prompts=reviewer_prompts,
                allowed_skills=effective_allowed_skills,
            )
            
            if not plan_list:
                final_answer = await generate_final_answer(history, request.model_preference)
                history.append(f"최종 답변: {final_answer}")

                title_summary = await generate_title_for_conversation(history, request.model_preference)

                history_manager.save_conversation(
                    convo_id, history, title_summary, [], 0,
                    is_final=True
                )

                # 키워드 추출 (실패 무시)
                try:
                    keywords = await extract_keywords(history, request.model_preference)
                    if keywords:
                        graph_manager.assign_keywords_to_conversation(convo_id, keywords)
                except Exception as e:
                    logging.warning(f"키워드 추출 실패: {e}")

                # 주제 분리 감지 (실패 무시)
                topic_split_info = None
                try:
                    topic_split_info = await detect_topic_split(history, request.model_preference)
                except Exception as e:
                    logging.warning(f"주제 분리 감지 실패: {e}")

                return _resp(
                    conversation_id=convo_id,
                    status="FINAL_ANSWER",
                    history=history,
                    message=final_answer,
                    topic_split_info=topic_split_info,
                )
            
            history = _prune_history(history)
            plan_dicts = [group.model_dump() for group in plan_list]
            history_manager.save_conversation(
                convo_id, history, data.get("title", "진행 중"), plan_dicts, 0, is_final=False
            )
            
            next_group = plan_list[0]
            return _resp(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"[{next_group.group_id}] {next_group.description}",
                execution_group=next_group
            )
        
        except Exception as e:
             issue_tracker.capture_exception(
                 e, context=f"re-plan convo_id={convo_id}", source="agent"
             )
             history.append(f"다음 단계 계획 중 오류: {e}")
             # (수정 2) 누락된 인자 plan=[], current_group_index=0 추가
             history_manager.save_conversation(
                 convo_id, history, "계획 오류", plan=[], current_group_index=0, is_final=False
             )
             return _resp(
                 conversation_id=convo_id,
                 status="ERROR",
                 history=history,
                 message=f"다음 단계 계획 중 오류 발생: {e}",
             )


@app.post("/agent/execute_group", response_model=AgentResponse)
async def execute_group(request: AgentRequest):
    """
    (수정) 저장된 '단일' 그룹을 실행합니다.
    (수정) 완료 후 'STEP_EXECUTED'를 반환하여 Re-plan을 트리거합니다.
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

    plan_list = [ExecutionGroup(**group) for group in plan_dicts]
    group_to_execute = plan_list[0] 
    
    history.append(f"그룹 실행 시작: [{group_to_execute.group_id}] {group_to_execute.description}")

    session_id = None
    overall_success = True
    try:
        session_id = mcp_db_manager.start_session(
            conversation_id=convo_id,
            group_id=group_to_execute.group_id,
        )
    except Exception as e:
        logging.warning(f"mcp_db_manager.start_session 실패: {e}")

    async def _execute_single_task(task) -> tuple:
        """단일 태스크를 실행하고 (tool_name, result_str, exc | None) 튜플을 반환."""
        # P3-D: on-demand MCP 서버 지연 연결
        await tool_registry.ensure_tool_server_connected(task.tool_name)

        tool_function = tool_registry.get_tool(task.tool_name)
        if not tool_function:
            raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")

        providers = tool_registry.get_tool_providers(task.tool_name)
        if len(providers) >= 2:
            server_names = [p["server"] for p in providers]
            logging.info(f"Tool '{task.tool_name}' has multiple providers: {server_names}")

        _validate_tool_arguments(tool_function, task.tool_name, task.arguments)

        t_start = time.monotonic()
        try:
            if inspect.iscoroutinefunction(tool_function):
                result = await tool_function(**task.arguments)
            else:
                result = tool_function(**task.arguments)
            duration_ms = int((time.monotonic() - t_start) * 1000)
            try:
                mcp_db_manager.log_usage(
                    task.tool_name, success=True, session_id=session_id,
                    duration_ms=duration_ms, args_summary=",".join(task.arguments.keys()),
                )
            except Exception as log_err:
                logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
            result_str = str(result)
            if len(result_str) > MAX_TOOL_RESULT_LENGTH:
                logging.warning(
                    f"도구 '{task.tool_name}' 결과가 {MAX_TOOL_RESULT_LENGTH}자를 초과하여 잘렸습니다. "
                    f"(원래 길이: {len(result_str)}자)"
                )
                result_str = result_str[:MAX_TOOL_RESULT_LENGTH] + "... (결과가 너무 길어 잘림)"
            return task.tool_name, result_str, None
        except Exception as tool_err:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            try:
                mcp_db_manager.log_usage(
                    task.tool_name, success=False, session_id=session_id,
                    duration_ms=duration_ms, error_message=str(tool_err),
                    args_summary=",".join(task.arguments.keys()),
                )
            except Exception as log_err:
                logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
            return task.tool_name, "", tool_err

    try:
        # P3-A: 그룹 내 태스크를 asyncio.gather로 병렬 실행
        tasks = group_to_execute.tasks
        for task in tasks:
            history.append(f"  - 도구 실행: {task.tool_name} (인자: {task.arguments})")

        results = await asyncio.gather(
            *[_execute_single_task(task) for task in tasks],
            return_exceptions=True,
        )

        first_exc = None
        for tool_name, result_str, exc in results:
            if isinstance(exc, Exception) or (isinstance(exc, BaseException) and exc is not None):
                first_exc = exc
                history.append(f"  - 실행 오류 ({tool_name}): {exc}")
            elif exc is not None:
                first_exc = exc
                history.append(f"  - 실행 오류 ({tool_name}): {exc}")
            else:
                history.append(f"  - 실행 결과 ({tool_name}): {result_str}")

        if first_exc is not None:
            raise first_exc

        history.append(f"그룹 실행 완료: [{group_to_execute.group_id}]")

        history_manager.save_conversation(
            convo_id, history, data.get("title", "실행 중"), [], 0,
            is_final=False
        )

    except ValueError as e:
        # ValueError는 _validate_tool_arguments / 도구 미발견 등 의도된 검증 실패.
        # 클라이언트에 ERROR 응답을 반환하는 정상 흐름이므로 issue_tracker에 기록하지 않음.
        logging.warning(f"execute_group 검증 오류 [{group_to_execute.group_id}]: {e}")
        overall_success = False
        history.append(f"그룹 실행 중 오류 발생: {e}")
        history_manager.save_conversation(
            convo_id, history, "실행 오류", plan_dicts, 0,
            is_final=False
        )
        try:
            if session_id:
                mcp_db_manager.end_session(session_id, overall_success=False)
        except Exception as end_err:
            logging.warning(f"mcp_db_manager.end_session 실패: {end_err}")
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류: {e}",
        )
    except Exception as e:
        # 예기치 않은 도구 실행 오류만 issue_tracker에 기록
        issue_tracker.capture_exception(
            e, context=f"execute_group group_id={group_to_execute.group_id}", source="tool"
        )
        overall_success = False
        history.append(f"그룹 실행 중 오류 발생: {e}")
        history_manager.save_conversation(
            convo_id, history, "실행 오류", plan_dicts, 0,
            is_final=False
        )
        try:
            if session_id:
                mcp_db_manager.end_session(session_id, overall_success=False)
        except Exception as end_err:
            logging.warning(f"mcp_db_manager.end_session 실패: {end_err}")
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류: {e}",
        )

    try:
        if session_id:
            mcp_db_manager.end_session(session_id, overall_success=True)
    except Exception as end_err:
        logging.warning(f"mcp_db_manager.end_session 실패: {end_err}")

    return _resp(
        conversation_id=convo_id,
        status="STEP_EXECUTED",
        history=history,
        message=f"그룹 [{group_to_execute.group_id}] 실행 완료"
    )


# StaticFiles는 반드시 마지막에 마운트 (라우팅 우선순위)
import os as _os
_static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
