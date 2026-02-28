#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/models.py

import json
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, List, Literal, Optional

class AgentRequest(BaseModel):
    """CLI가 서버로 보내는 요청 모델"""
    conversation_id: str = Field(..., description="대화 세션 식별자")
    history: List[str] = Field(default_factory=list, description="이전 대화 이력")
    user_input: Optional[str] = None
    requirement_paths: Optional[List[str]] = None
    model_preference: str = Field(default="auto", description="사용할 모델 등급 (standard, high, auto)")
    system_prompts: Optional[List[str]] = None
    persona: Optional[str] = None
    allowed_skills: Optional[List[str]] = None

class ToolCall(BaseModel):
    """단일 도구 호출(MCP)을 정의하는 모델"""
    tool_name: str = Field(..., max_length=100, description="도구 이름")
    arguments: Dict[str, Any]
    model_preference: str = Field(
        default="auto",
        description="이 태스크에 사용할 모델 (standard, high, auto)"
    )

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        """도구 이름에 위험 문자가 없는지 검증합니다."""
        if not v or not v.strip():
            raise ValueError("tool_name은 비어 있을 수 없습니다.")
        return v

    @field_validator("arguments")
    @classmethod
    def validate_arguments_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """arguments 직렬화 크기를 10KB로 제한합니다."""
        if len(json.dumps(v, ensure_ascii=False)) > 10_240:
            raise ValueError("arguments 크기가 10KB를 초과합니다.")
        return v


# 하위 호환 alias
GeminiToolCall = ToolCall


class ExecutionGroup(BaseModel):
    """여러 태스크를 묶는 실행 그룹 모델"""
    group_id: str = Field(..., max_length=100, description="그룹의 고유 ID (예: 'group_1')")
    description: str = Field(..., max_length=500, description="사용자에게 보여줄 그룹에 대한 설명")
    tasks: List[ToolCall] = Field(..., description="이 그룹에서 실행할 도구 호출 목록")

    @field_validator("tasks")
    @classmethod
    def validate_tasks_count(cls, v: List[ToolCall]) -> List[ToolCall]:
        """태스크 수를 50개로 제한합니다."""
        if len(v) > 50:
            raise ValueError(f"태스크 수가 50개를 초과합니다: {len(v)}개")
        return v

class AgentResponse(BaseModel):
    """서버가 CLI로 보내는 응답 모델"""
    conversation_id: str
    # (수정) STEP_EXECUTED 상태 추가
    status: Literal["PLAN_CONFIRMATION", "FINAL_ANSWER", "ERROR", "STEP_EXECUTED"]
    history: List[str]
    message: str
    execution_group: Optional[ExecutionGroup] = None  # 다음 1개 그룹 확인용
    topic_split_info: Optional[Dict[str, Any]] = None  # 주제 분리 감지 결과
    token_usage: Optional[Dict[str, Any]] = None  # LLM 토큰 사용량 (provider/model/input/output/cost)
