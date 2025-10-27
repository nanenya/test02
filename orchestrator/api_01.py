#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException
from .models import AgentExecutionRequest, AgentExecutionResponse, GeminiToolCall
# 수정한 함수를 import 합니다.
from .gemini_client import get_next_action_with_history
from . import tool_registry
import inspect

app = FastAPI(title="Gemini Agent Orchestrator")

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 MCP를 로드합니다."""
    tool_registry.load_tools()

@app.post("/agent/execute", response_model=AgentExecutionResponse)
async def execute_agent(request: AgentExecutionRequest):
    """에이전트의 핵심 실행 로직 (실행 루프 포함)"""
    print(f"📥 Received query: {request.query}")

    conversation_history = [f"사용자 목표: {request.query}"]
    max_turns = 100 # 무한 루프를 방지하기 위한 최대 실행 횟수

    for turn in range(max_turns):
        print(f"\n--- 턴 {turn + 1} 시작 ---")

        # 1. Gemini에게 다음 행동 결정 요청 (이제 history를 함께 전달)
        decision = get_next_action_with_history(request.query, conversation_history)

        # 2. Gemini가 최종 답변을 한 경우, 루프 종료
        if isinstance(decision, str):
            print(f"✅ Gemini provided final answer.")
            conversation_history.append(f"최종 답변: {decision}")
            return AgentExecutionResponse(
                input=request.query,
                final_answer=decision
            )

        # 3. Gemini가 도구 사용을 결정한 경우
        if isinstance(decision, GeminiToolCall):
            print(f"🛠️ Gemini decided to use tool: {decision.tool_name} with args: {decision.arguments}")
            conversation_history.append(f"계획: {decision.tool_name} 도구를 {decision.arguments} 인자와 함께 사용.")

            tool_function = tool_registry.get_tool(decision.tool_name)
            if not tool_function:
                error_message = f"오류: '{decision.tool_name}' 도구를 찾을 수 없습니다."
                conversation_history.append(error_message)
                continue # 루프의 다음 턴으로 넘어가서 오류를 해결하도록 유도

            # 4. MCP(도구) 실행
            try:
                if inspect.iscoroutinefunction(tool_function):
                    result = await tool_function(**decision.arguments)
                else:
                    result = tool_function(**decision.arguments)

                print(f"📄 Tool result: {result}")
                # 실행 결과를 history에 추가
                conversation_history.append(f"실행 결과: {result}")

            except Exception as e:
                error_message = f"오류: '{decision.tool_name}' 실행 중 에러 발생: {e}"
                print(f"❌ {error_message}")
                conversation_history.append(error_message)
                continue # 오류 발생 시에도 루프를 계속하여 자가 수정을 유도

    # 최대 턴에 도달한 경우
    final_message = "최대 작업 횟수에 도달했지만 목표를 완료하지 못했습니다."
    return AgentExecutionResponse(input=request.query, final_answer=final_message)
