#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/models.py

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Literal

class AgentRequest(BaseModel):
    """CLI가 서버로 보내는 요청 모델"""
    conversation_id: str
    history: List[str]
    user_input: str | None = None # 사용자의 추가 입력 (예: 승인, 수정)

class GeminiToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

class AgentResponse(BaseModel):
    """서버가 CLI로 보내는 응답 모델"""
    conversation_id: str
    status: Literal["TOOL_CONFIRMATION", "FINAL_ANSWER", "ERROR"]
    history: List[str]
    message: str # 사용자에게 보여줄 메시지 (최종 답변 또는 확인 질문)
    tool_call: GeminiToolCall | None = None # 확인이 필요한 도구 호출 정보
