#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/models.py

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Literal, Optional

class AgentRequest(BaseModel):
    """CLI가 서버로 보내는 요청 모델"""
    conversation_id: str
    history: List[str]
    user_input: str | None = None
    requirement_paths: List[str] | None = None
    model_preference: str = "auto"
    system_prompts: List[str] | None = None
    persona: str | None = None
    allowed_skills: List[str] | None = None

class GeminiToolCall(BaseModel):
    """단일 도구 호출(MCP)을 정의하는 모델"""
    tool_name: str
    arguments: Dict[str, Any]
    model_preference: str = Field(
        default="auto", 
        description="이 태스크에 사용할 모델 (standard, high, auto)"
    )


class ExecutionGroup(BaseModel):
    """여러 태스크를 묶는 실행 그룹 모델"""
    group_id: str = Field(..., description="그룹의 고유 ID (예: 'group_1')")
    description: str = Field(..., description="사용자에게 보여줄 그룹에 대한 설명")
    tasks: List[GeminiToolCall] = Field(..., description="이 그룹에서 실행할 도구 호출 목록")

class AgentResponse(BaseModel):
    """서버가 CLI로 보내는 응답 모델"""
    conversation_id: str
    # (수정) STEP_EXECUTED 상태 추가
    status: Literal["PLAN_CONFIRMATION", "FINAL_ANSWER", "ERROR", "STEP_EXECUTED"]
    history: List[str]
    message: str
    execution_group: ExecutionGroup | None = None # 다음 1개 그룹 확인용
    topic_split_info: Optional[Dict[str, Any]] = None  # 주제 분리 감지 결과
