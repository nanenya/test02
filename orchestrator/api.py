#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from fastapi import FastAPI, HTTPException
from .models import AgentRequest, AgentResponse, GeminiToolCall, ExecutionGroup
from .gemini_client import (
    generate_execution_plan, 
    generate_final_answer, 
    generate_title_for_conversation
)
from . import tool_registry
from . import history_manager
import inspect
import os

app = FastAPI(title="Gemini Agent Orchestrator")

@app.on_event("startup")
async def startup_event():
    tool_registry.load_tools()

@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    """
    사용자 입력(신규 또는 수정)에 따라 'Planner' 모델을 호출하여 실행 계획을 수립합니다.
    입력이 없으면 기존 계획을 계속 진행할지 확인합니다.
    """
    
    # DB에서 최신 대화 상태 로드
    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else request.history
    plan_dicts = data.get("plan", []) if data else []
    current_group_index = data.get("current_group_index", 0) if data else 0

    # 1. 사용자 입력이 있는 경우 (신규 작업 또는 계획 수정)
    if request.user_input:
        query = request.user_input
        history.append(f"사용자 요청: {query}")
        
        # 2. (요청사항 3) 요구사항 파일 읽기
        requirements_content = ""
        if request.requirement_paths:
            history.append(f"요구사항 파일 참조: {', '.join(request.requirement_paths)}")
            for path in request.requirement_paths:
                try:
                    # 'history' 디렉토리와 같은 위치 또는 상대 경로에서 파일 읽기 시도
                    # 실제 환경에서는 안정적인 경로 처리가 필요
                    with open(path, 'r', encoding='utf-8') as f:
                        requirements_content += f"--- {os.path.basename(path)} ---\n"
                        requirements_content += f.read()
                        requirements_content += "\n-----------------------------------\n\n"
                except Exception as e:
                    history.append(f"경고: 요구사항 파일 '{path}' 읽기 실패: {e}")
                    
        try:
            # 3. (요청사항 1) 'Planner' 모델로 전체 실행 계획 생성
            plan_list = await generate_execution_plan(query, requirements_content, history)
            
            if not plan_list:
                raise HTTPException(status_code=500, detail="계획 생성에 실패했습니다 (빈 계획 반환).")
            
            # Pydantic 모델을 JSON 저장을 위해 dict 리스트로 변환
            plan_dicts = [group.model_dump() for group in plan_list]
            current_group_index = 0
            title = f"계획 수립: {plan_list[0].description[:20]}..."
            
            # 새 계획을 DB에 저장
            history_manager.save_conversation(
                request.conversation_id, history, title, plan_dicts, current_group_index
            )
            
            # 4. (요청사항 2) 첫 번째 '그룹'을 사용자에게 확인 요청
            first_group = plan_list[0]
            return AgentResponse(
                conversation_id=request.conversation_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"[{first_group.group_id}] {first_group.description}",
                execution_group=first_group
            )

        except Exception as e:
            history.append(f"계획 수립 오류: {e}")
            history_manager.save_conversation(request.conversation_id, history, "계획 실패")
            return AgentResponse(
                conversation_id=request.conversation_id,
                status="ERROR",
                history=history,
                message=f"계획 수립 중 오류 발생: {e}",
            )

    # 5. 사용자 입력이 없는 경우 (기존 계획 계속)
    else:
        if not plan_dicts or current_group_index >= len(plan_dicts):
            return AgentResponse(
                conversation_id=request.conversation_id,
                status="FINAL_ANSWER",
                history=history,
                message="모든 계획이 완료되었습니다. 새 작업을 시작하려면 --query 옵션을 사용하세요."
            )
            
        # Pydantic 모델로 다시 변환
        plan_list = [ExecutionGroup(**group) for group in plan_dicts]
        next_group = plan_list[current_group_index]
        
        # 다음 그룹을 확인
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"저장된 다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )


@app.post("/agent/execute_group", response_model=AgentResponse)
async def execute_group(request: AgentRequest):
    """
    (요청사항 2) 사용자가 승인한 'ExecutionGroup'을 실행합니다.
    """
    # DB에서 최신 상태 로드
    data = history_manager.load_conversation(request.conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="대화 ID를 찾을 수 없습니다.")

    history = data.get("history", [])
    plan_dicts = data.get("plan", [])
    current_group_index = data.get("current_group_index", 0)

    if not plan_dicts or current_group_index >= len(plan_dicts):
        raise HTTPException(status_code=400, detail="실행할 계획이 없습니다.")

    plan_list = [ExecutionGroup(**group) for group in plan_dicts]
    group_to_execute = plan_list[current_group_index]
    
    history.append(f"✅ 그룹 실행 시작: [{group_to_execute.group_id}] {group_to_execute.description}")

    try:
        # 그룹 내의 모든 태스크(도구)를 순차적으로 실행
        for task in group_to_execute.tasks:
            tool_function = tool_registry.get_tool(task.tool_name)
            if not tool_function:
                raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")
            
            history.append(f"  - 도구 실행: {task.tool_name} (인자: {task.arguments})")
            
            if inspect.iscoroutinefunction(tool_function):
                result = await tool_function(**task.arguments)
            else:
                result = tool_function(**task.arguments)
            
            # 결과가 너무 길 경우 잘라서 저장
            result_str = str(result)
            if len(result_str) > 1000:
                result_str = result_str[:1000] + "... (결과가 너무 길어 잘림)"
            
            history.append(f"  - 실행 결과: {result_str}")
        
        history.append(f"🏁 그룹 실행 완료: [{group_to_execute.group_id}]")
        current_group_index += 1
        
        # 실행 완료 후 상태 저장
        history_manager.save_conversation(
            request.conversation_id, history, data.get("title", "실행 중"), plan_dicts, current_group_index
        )

    except Exception as e:
        history.append(f"❌ 그룹 실행 중 오류 발생: {e}")
        # 오류 발생 시에도 상태 저장
        history_manager.save_conversation(
            request.conversation_id, history, "실행 오류", plan_dicts, current_group_index
        )
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류: {e}",
        )

    # 7. 다음 계획 확인 또는 최종 답변
    if current_group_index < len(plan_list):
        # 다음 그룹 실행 확인
        next_group = plan_list[current_group_index]
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )
    else:
        # (요청사항 1) 'Executor' 모델로 최종 답변 생성
        final_answer = await generate_final_answer(history)
        history.append(f"💡 최종 답변: {final_answer}")
        
        # (요청사항 1) 'Executor' 모델로 제목 생성
        title = await generate_title_for_conversation(history)
        
        # 최종 상태 저장
        history_manager.save_conversation(
            request.conversation_id, history, title, plan_dicts, current_group_index
        )
        
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="FINAL_ANSWER",
            history=history,
            message=final_answer
        )
