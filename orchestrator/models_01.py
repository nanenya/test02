#!/usr/bin/env python3

from pydantic import BaseModel, Field
from typing import Dict, Any

class AgentExecutionRequest(BaseModel):
    """사용자가 CLI를 통해 전달하는 요청 모델"""
    query: str = Field(..., description="사용자의 원본 명령어")

class GeminiToolCall(BaseModel):
    """Gemini가 반환하는 도구 호출 JSON 구조 모델"""
    tool_name: str = Field(..., description="실행할 MCP(도구)의 이름")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="MCP에 전달할 인자들")

class AgentExecutionResponse(BaseModel):
    """에이전트 실행 결과를 담는 응답 모델"""
    input: str
    tool_call: GeminiToolCall | None = None
    tool_result: str | None = None
    final_answer: str
