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
import re # (요청사항 3)
from datetime import datetime # (요청사항 3)

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
    # (요청사항 3) ID가 파일명일 수 있으므로 load_conversation이 처리
    data = history_manager.load_conversation(request.conversation_id)
    history = data.get("history", []) if data else request.history
    plan_dicts = data.get("plan", []) if data else []
    current_group_index = data.get("current_group_index", 0) if data else 0
    
    # (요청사항 3) ID가 파일명으로 변경되었을 수 있으니, data의 id를 사용
    convo_id = data.get("id", request.conversation_id) if data else request.conversation_id


    # 1. 사용자 입력이 있는 경우 (신규 작업 또는 계획 수정)
    if request.user_input:
        query = request.user_input
        history.append(f"사용자 요청: {query}")
        
        # 2. 요구사항 파일 읽기
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
            # 3. 'Planner' 모델로 전체 실행 계획 생성
            # (요청사항 1, 4) 모델 선호도와 시스템 프롬프트 전달
            plan_list = await generate_execution_plan(
                user_query=query, 
                requirements_content=requirements_content, 
                history=history,
                model_preference=request.model_preference,
                system_prompts=request.system_prompts or []
            )
            
            if not plan_list:
                raise HTTPException(status_code=500, detail="계획 생성에 실패했습니다 (빈 계획 반환).")
            
            # Pydantic 모델을 JSON 저장을 위해 dict 리스트로 변환
            plan_dicts = [group.model_dump() for group in plan_list]
            current_group_index = 0
            title = f"계획 수립: {plan_list[0].description[:20]}..."
            
            # 새 계획을 DB에 저장 (임시 저장, is_final=False)
            history_manager.save_conversation(
                convo_id, history, title, plan_dicts, current_group_index, is_final=False
            )
            
            # 4. (요청사항 2) 전체 계획을 사용자에게 확인 요청
            return AgentResponse(
                conversation_id=convo_id,
                status="PLAN_CONFIRMATION",
                history=history,
                message=f"전체 계획이 수립되었습니다. {len(plan_list)}개 그룹.",
                plan=[group.model_dump() for group in plan_list] # Pydantic 객체 리스트 전달
            )

        except Exception as e:
            history.append(f"계획 수립 오류: {e}")
            history_manager.save_conversation(convo_id, history, "계획 실패", is_final=False)
            return AgentResponse(
                conversation_id=convo_id,
                status="ERROR",
                history=history,
                message=f"계획 수립 중 오류 발생: {e}",
            )

    # 5. 사용자 입력이 없는 경우 (기존 계획 계속)
    else:
        if not plan_dicts or current_group_index >= len(plan_dicts):
            return AgentResponse(
                conversation_id=convo_id,
                status="FINAL_ANSWER",
                history=history,
                message="모든 계획이 완료되었습니다. 새 작업을 시작하려면 --query 옵션을 사용하세요."
            )
            
        # Pydantic 모델로 다시 변환
        plan_list = [ExecutionGroup(**group) for group in plan_dicts]
        next_group = plan_list[current_group_index]
        
        # 다음 그룹을 확인
        return AgentResponse(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"저장된 다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group # 다음 그룹 1개만 전달
        )


@app.post("/agent/execute_group", response_model=AgentResponse)
async def execute_group(request: AgentRequest):
    """
    사용자가 승인한 'ExecutionGroup'을 실행합니다.
    """
    # DB에서 최신 상태 로드
    data = history_manager.load_conversation(request.conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="대화 ID를 찾을 수 없습니다.")

    history = data.get("history", [])
    plan_dicts = data.get("plan", [])
    current_group_index = data.get("current_group_index", 0)
    convo_id = data.get("id", request.conversation_id) # (요청사항 3)

    if not plan_dicts or current_group_index >= len(plan_dicts):
        raise HTTPException(status_code=400, detail="실행할 계획이 없습니다.")

    plan_list = [ExecutionGroup(**group) for group in plan_dicts]
    group_to_execute = plan_list[current_group_index]
    
    # -----------------------------------------------------------------
    # ✨ 1. 이전 실행 결과 수집 (NEW)
    # -----------------------------------------------------------------
    # history에서 이전 실행 결과('  - 실행 결과: ...')를 모두 수집합니다.
    previous_results = []
    for item in history:
        if item.startswith("  - 실행 결과: "):
            # '  - 실행 결과: ' 접두사 제거
            result_content = item.split(": ", 1)[1]
            previous_results.append(result_content)

    # 여러 결과를 합쳐야 할 때를 대비해 MERGED_RESULTS를 만듭니다.
    # 사용자의 요청(파일 코드 모두 담기)에 적합하게 줄바꿈 2개로 결합합니다.
    merged_results = "\n\n".join(previous_results)
    last_result = previous_results[-1] if previous_results else ""
    # -----------------------------------------------------------------
    
    history.append(f"그룹 실행 시작: [{group_to_execute.group_id}] {group_to_execute.description}")

    try:
        # 그룹 내의 모든 태스크(도구)를 순차적으로 실행
        for task in group_to_execute.tasks:
            tool_function = tool_registry.get_tool(task.tool_name)
            if not tool_function:
                raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")
            
            # (요청사항 2) 태스크에 지정된 모델 선호도 (현재는 로컬 툴 실행뿐이라 미사용)
            # model_pref_for_task = task.model_preference 
            
            # -----------------------------------------------------------------
            # ✨ 2. 인자 치환 (ARGUMENT SUBSTITUTION) (MODIFIED)
            # -----------------------------------------------------------------
            substituted_args = {}
            for key, value in task.arguments.items():
                if isinstance(value, str):
                    if value == "$MERGED_RESULTS":
                        substituted_args[key] = merged_results
                    elif value == "$LAST_RESULT":
                        substituted_args[key] = last_result
                    # (필요시 "$PREVIOUS_RESULTS[0]" 등 더 복잡한 치환 로직 추가 가능)
                    else:
                        substituted_args[key] = value
                else:
                    substituted_args[key] = value
            # -----------------------------------------------------------------
            
            history.append(f"  - 도구 실행: {task.tool_name} (인자: {substituted_args})")
            
            if inspect.iscoroutinefunction(tool_function):
                result = await tool_function(**substituted_args) # 수정됨
            else:
                result = tool_function(**substituted_args) # 수정됨
            
            result_str = str(result)
            
            # -----------------------------------------------------------------
            # ✨ 3. 결과 잘림(TRUNCATION) 제거 (MODIFIED)
            # -----------------------------------------------------------------
            # 원본:
            # if len(result_str) > 1000:
            #     result_str = result_str[:1000] + "... (결과가 너무 길어 잘림)"
            
            # history에 '전체' 결과 저장
            history.append(f"  - 실행 결과: {result_str}")
            # -----------------------------------------------------------------
        
        history.append(f"그룹 실행 완료: [{group_to_execute.group_id}]")
        current_group_index += 1
        
        # 실행 완료 후 상태 저장 (임시)
        history_manager.save_conversation(
            convo_id, history, data.get("title", "실행 중"), plan_dicts, current_group_index,
            is_final=False
        )

    except Exception as e:
        history.append(f"그룹 실행 중 오류 발생: {e}")
        # 오류 발생 시에도 상태 저장 (임시)
        history_manager.save_conversation(
            convo_id, history, "실행 오류", plan_dicts, current_group_index,
            is_final=False
        )
        return AgentResponse(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"그룹 '{group_to_execute.group_id}' 실행 중 오류: {e}",
        )

    # 7. 다음 계획 확인 또는 최종 답변
    if current_group_index < len(plan_list):
        # 다음 그룹 실행 확인
        next_group = plan_list[current_group_index]
        return AgentResponse(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"다음 계획: [{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )
    else:
        # 'Executor' 모델로 최종 답변 생성
        # (요청사항 1) 모델 선호도 전달
        final_answer = await generate_final_answer(
            history, model_preference=request.model_preference
        )
        history.append(f"최종 답변: {final_answer}")
        
        # 'Executor' 모델로 요약 (제목용) 생성
        # (요청사항 1) 모델 선호도 전달
        title_summary = await generate_title_for_conversation(
            history, model_preference=request.model_preference
        )
        
        # (요청사항 3) 파일명 형식에 맞게 제목 포맷팅
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # history_manager의 _sanitize_title과 동일한 로직 사용
        safe_summary = re.sub(r'[^\w\s가-힣-]', '', title_summary).replace(' ', '_')[:20]
        final_title = f"{timestamp}-{safe_summary}"
        
        # (요청사항 3) 최종 상태 저장 (is_final=True)
        # convo_id는 아직 UUID일 수 있음. save_conversation이 파일명 변경 처리
        history_manager.save_conversation(
            convo_id, history, title_summary, plan_dicts, current_group_index,
            is_final=True
        )
        
        # (요청사항 3) 반환되는 ID는 새 파일명 (이 루프에서는 마지막이라 사용되진 않음)
        return AgentResponse(
            conversation_id=final_title, 
            status="FINAL_ANSWER",
            history=history,
            message=final_answer
        )
