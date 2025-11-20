#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from fastapi import FastAPI, HTTPException
from .models import AgentRequest, AgentResponse, GeminiToolCall, ExecutionGroup
from .gemini_client import (
    generate_execution_plan, 
    generate_final_answer, 
    generate_title_for_conversation,
    generate_new_mcp_code
)
from . import tool_registry
from . import history_manager
import inspect
import os
import re
from datetime import datetime
import nest_asyncio # (수정) 추가: 중첩 이벤트 루프 허용 라이브러리

# (수정) 실행 중인 이벤트 루프에서 asyncio.run() 호출 시 발생하는 오류 방지
nest_asyncio.apply()

app = FastAPI(title="Gemini Agent Orchestrator")

# 위험하다고 간주할 도구 목록
DANGEROUS_TOOLS = ["execute_shell_command", "execute_python_code"]

@app.on_event("startup")
async def startup_event():
    tool_registry.load_tools()

@app.post("/agent/reload_tools", response_model=AgentResponse)
async def reload_tools(request: AgentRequest):
    """새로 생성된 MCP 파일을 읽어 도구 목록을 다시 로드합니다."""
    try:
        tool_registry.load_tools()
        history = request.history or []
        history.append("시스템: 새 도구를 성공적으로 리로드했습니다.")
        
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message="새 도구를 리로드했습니다. 다음 계획을 진행합니다.",
        )
    except Exception as e:
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="ERROR",
            history=request.history,
            message=f"도구 리로드 중 오류 발생: {e}",
        )


@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    """
    사용자 입력(신규 또는 수정)에 따라 'Planner' 모델을 호출하여 실행 계획을 수립합니다.
    """
    
    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else request.history
    plan_dicts = data.get("plan", []) if data else []
    current_group_index = data.get("current_group_index", 0) if data else 0
    convo_id = data.get("id", request.conversation_id) if data else request.conversation_id

    # 사용자가 '새 MCP 생성'을 선택한 경우
    if request.user_decision == "create_mcp" and request.user_input:
        try:
            mcp_code = await generate_new_mcp_code(
                user_instruction=request.user_input,
                history=history,
                model_preference=request.model_preference
            )
            
            history.append(f"사용자 요청: {request.user_input}")
            history.append(f"AI 응답 (신규 MCP 코드 제안):\n```python\n{mcp_code}\n```")
            
            user_query = "방금 제안된 MCP 코드를 'mcp_modules/mcp_custom_tool.py' 파일로 저장하고, 도구를 리로드한 뒤, 원래 목표를 이 새 도구로 다시 시도하는 계획을 수립해줘."
            
            request.user_input = user_query 

        except Exception as e:
            history.append(f"MCP 코드 생성 중 오류: {e}")
            return AgentResponse(
                conversation_id=convo_id, status="ERROR", history=history,
                message=f"새 MCP 생성 AI 호출 중 오류 발생: {e}"
            )

    # 1. 사용자 입력이 있는 경우 (신규 작업 또는 계획 수정)
    if request.user_input:
        query = request.user_input
        if not query.startswith("사용자 요청:"):
            history.append(f"사용자 요청: {query}")
        
        requirements_content = ""
        if request.requirement_paths:
            pass
            
        try:
            plan_list = await generate_execution_plan(
                user_query=query, 
                requirements_content=requirements_content, 
                history=history,
                model_preference=request.model_preference,
                system_prompts=request.system_prompts or []
            )
            
            if not plan_list:
                raise HTTPException(status_code=500, detail="계획 생성에 실패했습니다 (빈 계획 반환).")
            
            plan_dicts = [group.model_dump() for group in plan_list]
            current_group_index = 0
            title = f"계획 수립: {plan_list[0].description[:20]}..."
            
            history_manager.save_conversation(
                convo_id, history, title, plan_dicts, current_group_index, is_final=False
            )
            
            return AgentResponse(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"전체 계획이 수립되었습니다. {len(plan_list)}개 그룹.",
                plan=[group.model_dump() for group in plan_list]
            )

        except Exception as e:
            history.append(f"계획 수립 오류: {e}")
            history_manager.save_conversation(convo_id, history, "계획 실패", is_final=False)
            return AgentResponse(
                conversation_id=convo_id, status="ERROR", history=history,
                message=f"계획 수립 중 오류 발생: {e}"
            )

    # 5. 사용자 입력이 없는 경우 (기존 계획 계속)
    else:
        if not plan_dicts or current_group_index >= len(plan_dicts):
            return AgentResponse(
                conversation_id=convo_id, status="FINAL_ANSWER", history=history,
                message="모든 계획이 완료되었습니다."
            )
            
        plan_list = [ExecutionGroup(**group) for group in plan_dicts]
        next_group = plan_list[current_group_index]
        
        return AgentResponse(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"저장된 다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )


@app.post("/agent/execute_group", response_model=AgentResponse)
async def execute_group(request: AgentRequest):
    """
    사용자가 승인한 'ExecutionGroup'을 실행합니다.
    """
    data = history_manager.load_conversation(request.conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="대화 ID를 찾을 수 없습니다.")

    history = data.get("history", [])
    plan_dicts = data.get("plan", [])
    current_group_index = data.get("current_group_index", 0)
    convo_id = data.get("id", request.conversation_id)

    if not plan_dicts or current_group_index >= len(plan_dicts):
        raise HTTPException(status_code=400, detail="실행할 계획이 없습니다.")

    plan_list = [ExecutionGroup(**group) for group in plan_dicts]
    group_to_execute = plan_list[current_group_index]
    
    # 1. 이전 실행 결과 수집
    previous_results = []
    for item in history:
        if item.startswith("  - 실행 결과: "):
            result_content = item.split(": ", 1)[1]
            previous_results.append(result_content)
    merged_results = "\n\n".join(previous_results)
    last_result = previous_results[-1] if previous_results else ""
    
    history.append(f"그룹 실행 시작: [{group_to_execute.group_id}] {group_to_execute.description}")

    try:
        # 그룹 내의 모든 태스크(도구)를 순차적으로 실행
        for task in group_to_execute.tasks:
            
            # 위험 작업 감지
            if task.tool_name in DANGEROUS_TOOLS and request.user_decision != "proceed":
                history.append(f"  - 위험 작업 감지: {task.tool_name}. 사용자 확인 필요.")
                history_manager.save_conversation(
                    convo_id, history, data.get("title", "위험 작업 대기"), 
                    plan_dicts, current_group_index, is_final=False
                )
                return AgentResponse(
                    conversation_id=convo_id,
                    status="DANGEROUS_TASK_CONFIRMATION",
                    history=history,
                    message=f"'{task.tool_name}'은(는) 위험한 작업입니다. 실행 코드를 확인하세요.",
                    dangerous_task_details={
                        "tool_name": task.tool_name,
                        "arguments": task.arguments
                    }
                )

            # 'reload_tools'는 MCP가 아니므로 특별 처리
            if task.tool_name == "reload_tools":
                history.append("  - 특수 명령 실행: reload_tools")
                tool_registry.load_tools()
                history.append("  - 실행 결과: 도구 리로드 완료")
                continue

            tool_function = tool_registry.get_tool(task.tool_name)
            if not tool_function:
                raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")
            
            # 2. 인자 치환 (ARGUMENT SUBSTITUTION)
            substituted_args = {}
            for key, value in task.arguments.items():
                if isinstance(value, str):
                    if value == "$MERGED_RESULTS":
                        substituted_args[key] = merged_results
                    elif value == "$LAST_RESULT":
                        substituted_args[key] = last_result
                    else:
                        substituted_args[key] = value
                else:
                    substituted_args[key] = value
            
            history.append(f"  - 도구 실행: {task.tool_name} (인자: {substituted_args})")
            
            if inspect.iscoroutinefunction(tool_function):
                result = await tool_function(**substituted_args)
            else:
                result = tool_function(**substituted_args)
            
            result_str = str(result)
            history.append(f"  - 실행 결과: {result_str}")

        history.append(f"그룹 실행 완료: [{group_to_execute.group_id}]")
        current_group_index += 1
        
        history_manager.save_conversation(
            convo_id, history, data.get("title", "실행 중"), plan_dicts, current_group_index,
            is_final=False
        )

    except Exception as e:
        history.append(f"그룹 실행 중 오류 발생: {e}")
        history_manager.save_conversation(
            convo_id, history, "실행 오류", plan_dicts, current_group_index,
            is_final=False
        )
        return AgentResponse(
            conversation_id=convo_id,
            status="EXECUTION_ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류: {e}",
        )

    # 7. 다음 계획 확인 또는 최종 답변
    if current_group_index < len(plan_list):
        next_group = plan_list[current_group_index]
        return AgentResponse(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )
    else:
        final_answer = await generate_final_answer(
            history, model_preference=request.model_preference
        )
        history.append(f"최종 답변: {final_answer}")
        
        title_summary = await generate_title_for_conversation(
            history, model_preference=request.model_preference
        )
        
        history_manager.save_conversation(
            convo_id, history, title_summary, plan_dicts, current_group_index,
            is_final=True
        )
        
        final_data = history_manager.load_conversation(convo_id)
        final_id = final_data.get("id", convo_id) if final_data else convo_id

        return AgentResponse(
            conversation_id=final_id, 
            status="FINAL_ANSWER",
            history=history,
            message=final_answer
        )
