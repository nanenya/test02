#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/models.py

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Literal

class AgentRequest(BaseModel):
    """CLI가 서버로 보내는 요청 모델"""
    conversation_id: str
    history: List[str]
    user_input: str | None = None # 사용자의 추가 입력 (예: 새 쿼리, 수정 지시)
    requirement_paths: List[str] | None = None # (요청사항 3) 참조할 요구사항 파일 경로

class GeminiToolCall(BaseModel):
    """단일 도구 호출(MCP)을 정의하는 모델"""
    tool_name: str
    arguments: Dict[str, Any]

class ExecutionGroup(BaseModel):
    """(요청사항 2) 여러 태스크를 묶는 실행 그룹 모델"""
    group_id: str = Field(..., description="그룹의 고유 ID (예: 'group_1')")
    description: str = Field(..., description="사용자에게 보여줄 그룹에 대한 설명")
    tasks: List[GeminiToolCall] = Field(..., description="이 그룹에서 실행할 도구 호출 목록")

class AgentResponse(BaseModel):
    """서버가 CLI로 보내는 응답 모델"""
    conversation_id: str
    status: Literal["PLAN_CONFIRMATION", "FINAL_ANSWER", "ERROR"] # (요청사항 2) 'TOOL_CONFIRMATION'을 'PLAN_CONFIRMATION'으로 변경
    history: List[str]
    message: str # 사용자에게 보여줄 메시지 (최종 답변 또는 확인 질문)
    execution_group: ExecutionGroup | None = None # (요청사항 2) 확인이 필요한 실행 '그룹'
