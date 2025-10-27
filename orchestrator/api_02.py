#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/api.py

from fastapi import FastAPI, HTTPException
from .models import AgentRequest, AgentResponse, GeminiToolCall
from .gemini_client import get_next_action_with_history, generate_title_for_conversation
from . import tool_registry
from . import history_manager
import inspect

app = FastAPI(title="Gemini Agent Orchestrator")

@app.on_event("startup")
async def startup_event():
    tool_registry.load_tools()

@app.post("/agent/decide_and_act", response_model=AgentResponse)
async def decide_and_act(request: AgentRequest):
    history = request.history
    if request.user_input:
        history.append(f"사용자 입력: {request.user_input}")

    # 1. Gemini에게 다음 행동 결정 요청
    decision = get_next_action_with_history(history[0], history) # 첫번째 메시지를 목표로 전달

    # 2. Gemini가 최종 답변을 한 경우
    if isinstance(decision, str):
        history.append(f"최종 답변: {decision}")
        title = generate_title_for_conversation(history)
        history_manager.save_conversation(request.conversation_id, history, title)
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="FINAL_ANSWER",
            history=history,
            message=decision
        )

    # 3. Gemini가 도구 사용을 결정한 경우 (사용자 확인 단계)
    if isinstance(decision, GeminiToolCall):
        history.append(f"계획: {decision.tool_name} 도구를 {decision.arguments} 인자와 함께 사용.")
        # 실행하지 않고 사용자에게 확인을 요청
        return AgentResponse(
            conversation_id=request.conversation_id,
            status="TOOL_CONFIRMATION",
            history=history,
            message=f"도구 '{decision.tool_name}'을(를) 다음 인자로 실행할까요?: {decision.arguments}",
            tool_call=decision
        )

    raise HTTPException(status_code=400, detail="Invalid decision format from Gemini.")

@app.post("/agent/execute_tool", response_model=AgentResponse)
async def execute_tool(request: AgentRequest):
    """사용자가 승인한 도구를 실행하고, 그 결과를 history에 추가합니다."""
    # history의 마지막은 "계획: ..." 이어야 함
    # 이 계획을 실행하고 그 결과를 다시 history에 추가한 뒤, 다시 decide_and_act를 호출하는 흐름
    last_plan_str = next((item for item in reversed(request.history) if item.startswith("계획:")), None)
    if not last_plan_str:
        raise HTTPException(status_code=400, detail="No tool execution plan found in history.")

    # 문자열에서 ToolCall 정보 재구성 (실제로는 더 정교한 파싱 필요)
    try:
        tool_name = last_plan_str.split(" 도구를 ")[0].split("계획: ")[1]
        args_str = last_plan_str.split(" 인자와 함께 사용.")[0].split("{")[1].replace("}", "")
        args = eval("{" + args_str + "}") # eval은 보안상 위험하므로 실제 프로젝트에서는 json.loads 추천
        tool_call = GeminiToolCall(tool_name=tool_name, arguments=args)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse tool call from history.")

    tool_function = tool_registry.get_tool(tool_call.tool_name)
    if not tool_function:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_call.tool_name}' not found.")

    try:
        if inspect.iscoroutinefunction(tool_function):
            result = await tool_function(**tool_call.arguments)
        else:
            result = tool_function(**tool_call.arguments)
        
        request.history.append(f"실행 결과: {result}")
        # 실행 후 다음 행동을 결정하기 위해 다시 decide_and_act 호출과 같은 로직 수행
        return await decide_and_act(AgentRequest(
            conversation_id=request.conversation_id,
            history=request.history
        ))
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error executing tool '{tool_call.tool_name}': {e}")
