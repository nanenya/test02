#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from .models import AgentRequest, AgentResponse, GeminiToolCall, ExecutionGroup
from .gemini_client import (
    generate_execution_plan,
    generate_final_answer,
    generate_title_for_conversation,
    extract_keywords,
    detect_topic_split,
)
from . import tool_registry
from . import history_manager
from . import graph_manager
from . import agent_config_manager
from . import mcp_db_manager
import inspect
import logging
import os
import re
import time
from datetime import datetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    await tool_registry.initialize()
    yield
    await tool_registry.shutdown()

app = FastAPI(title="Gemini Agent Orchestrator", lifespan=lifespan)

@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    """
    (수정) ReAct 루프의 핵심.
    1. 사용자 입력(신규/수정)이 있으면: '첫 번째' 계획 그룹을 생성합니다.
    2. 사용자 입력이 없으면(STEP_EXECUTED 후): History를 기반으로 '다음' 계획 그룹을 생성합니다.
    3. Planner가 '[]'를 반환하면: 'FINAL_ANSWER'를 생성합니다.
    """
    
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
        
        requirements_content = ""
        if request.requirement_paths:
            history.append(f"요구사항 파일 참조: {', '.join(request.requirement_paths)}")
            for path in request.requirement_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        requirements_content += f"--- {os.path.basename(path)} ---\n"
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
                system_prompts=effective_system_prompts,
                allowed_skills=effective_allowed_skills,
            )
            
            if not plan_list:
                 return AgentResponse(
                    conversation_id=convo_id,
                    status="FINAL_ANSWER",
                    history=history,
                    message="요청하신 작업에 대해 실행할 단계가 없습니다. (작업 완료)"
                )
            
            plan_dicts = [group.model_dump() for group in plan_list]
            history_manager.save_conversation(
                convo_id, history, f"계획: {plan_list[0].description[:20]}...", plan_dicts, 0, is_final=False
            )
            
            first_group = plan_list[0]
            return AgentResponse(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"[{first_group.group_id}] {first_group.description}",
                execution_group=first_group
            )

        except Exception as e:
            history.append(f"계획 수립 오류: {e}")
            # (수정 2) 누락된 인자 plan=[], current_group_index=0 추가
            history_manager.save_conversation(
                convo_id, history, "계획 실패", plan=[], current_group_index=0, is_final=False
            )
            return AgentResponse(
                conversation_id=convo_id,
                status="ERROR",
                history=history,
                message=f"계획 수립 중 오류 발생: {e}",
            )

    else:
        try:
            first_query = next((h.split(":", 1)[1].strip() for h in history if h.startswith("사용자 요청:")), "이전 작업을 계속하세요.")
            
            plan_list = await generate_execution_plan(
                user_query=first_query,
                requirements_content="",
                history=history,
                model_preference=request.model_preference,
                system_prompts=effective_system_prompts,
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

                return AgentResponse(
                    conversation_id=convo_id,
                    status="FINAL_ANSWER",
                    history=history,
                    message=final_answer,
                    topic_split_info=topic_split_info,
                )
            
            plan_dicts = [group.model_dump() for group in plan_list]
            history_manager.save_conversation(
                convo_id, history, data.get("title", "진행 중"), plan_dicts, 0, is_final=False
            )
            
            next_group = plan_list[0]
            return AgentResponse(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"[{next_group.group_id}] {next_group.description}",
                execution_group=next_group
            )
        
        except Exception as e:
             history.append(f"다음 단계 계획 중 오류: {e}")
             # (수정 2) 누락된 인자 plan=[], current_group_index=0 추가
             history_manager.save_conversation(
                 convo_id, history, "계획 오류", plan=[], current_group_index=0, is_final=False
             )
             return AgentResponse(
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

    try:
        for task in group_to_execute.tasks:
            tool_function = tool_registry.get_tool(task.tool_name)
            if not tool_function:
                raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")

            providers = tool_registry.get_tool_providers(task.tool_name)
            if len(providers) >= 2:
                server_names = [p["server"] for p in providers]
                logging.info(
                    f"Tool '{task.tool_name}' has multiple providers: {server_names}"
                )

            history.append(f"  - 도구 실행: {task.tool_name} (인자: {task.arguments})")

            t_start = time.monotonic()
            try:
                if inspect.iscoroutinefunction(tool_function):
                    result = await tool_function(**task.arguments)
                else:
                    result = tool_function(**task.arguments)

                duration_ms = int((time.monotonic() - t_start) * 1000)
                args_summary = ",".join(task.arguments.keys())
                try:
                    mcp_db_manager.log_usage(
                        task.tool_name,
                        success=True,
                        session_id=session_id,
                        duration_ms=duration_ms,
                        args_summary=args_summary,
                    )
                except Exception as log_err:
                    logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
            except Exception as tool_err:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                try:
                    mcp_db_manager.log_usage(
                        task.tool_name,
                        success=False,
                        session_id=session_id,
                        duration_ms=duration_ms,
                        error_message=str(tool_err),
                        args_summary=",".join(task.arguments.keys()),
                    )
                except Exception as log_err:
                    logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
                raise tool_err

            result_str = str(result)
            if len(result_str) > 1000:
                result_str = result_str[:1000] + "... (결과가 너무 길어 잘림)"

            history.append(f"  - 실행 결과: {result_str}")

        history.append(f"그룹 실행 완료: [{group_to_execute.group_id}]")

        history_manager.save_conversation(
            convo_id, history, data.get("title", "실행 중"), [], 0,
            is_final=False
        )

    except Exception as e:
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
        return AgentResponse(
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

    return AgentResponse(
        conversation_id=convo_id,
        status="STEP_EXECUTED",
        history=history,
        message=f"그룹 [{group_to_execute.group_id}] 실행 완료"
    )
