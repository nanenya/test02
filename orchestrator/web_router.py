#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/web_router.py
"""웹 UI용 REST API 라우터 — /api/v1 prefix."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import graph_manager
from . import mcp_db_manager
from . import agent_config_manager

router = APIRouter(prefix="/api/v1", tags=["web"])


# ── 요청 바디 모델 ────────────────────────────────────────────────

class SystemPromptCreate(BaseModel):
    name: str
    content: str
    description: str = ""
    is_default: bool = False


class SystemPromptUpdate(BaseModel):
    content: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


class PersonaCreate(BaseModel):
    name: str
    system_prompt: str
    display_name: str = ""
    description: str = ""
    allowed_skills: list = []
    keywords: list = []
    is_default: bool = False


class PersonaUpdate(BaseModel):
    system_prompt: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    allowed_skills: Optional[list] = None
    keywords: Optional[list] = None
    is_default: Optional[bool] = None


class SkillToggle(BaseModel):
    active: bool


# ── 대화 관리 ─────────────────────────────────────────────────────

@router.get("/conversations")
def list_conversations(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    group_id: Optional[int] = None,
):
    try:
        return graph_manager.list_conversations(
            keyword=keyword, status=status, group_id=group_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{convo_id}")
def get_conversation(convo_id: str):
    try:
        data = graph_manager.load_conversation(convo_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return data


@router.delete("/conversations/{convo_id}")
def delete_conversation(convo_id: str):
    try:
        deleted = graph_manager.delete_conversation(convo_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/groups")
def list_groups():
    try:
        return graph_manager.list_groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── MCP 함수 (읽기 전용) ──────────────────────────────────────────

@router.get("/functions/stats")
def get_function_stats():
    try:
        return mcp_db_manager.get_usage_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/functions")
def list_functions(
    module_group: Optional[str] = None,
    active_only: bool = True,
):
    try:
        return mcp_db_manager.list_functions(
            module_group=module_group, active_only=active_only
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/functions/{func_name}/versions")
def get_function_versions(func_name: str):
    try:
        versions = mcp_db_manager.get_function_versions(func_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not versions:
        raise HTTPException(status_code=404, detail="함수를 찾을 수 없습니다.")
    return versions


@router.get("/functions/{func_name}")
def get_function(func_name: str):
    try:
        data = mcp_db_manager.get_active_function(func_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="함수를 찾을 수 없습니다.")
    return data


# ── 설정 — 시스템 프롬프트 ───────────────────────────────────────

@router.get("/settings/prompts")
def list_prompts():
    try:
        return agent_config_manager.list_system_prompts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/prompts", status_code=201)
def create_prompt(body: SystemPromptCreate):
    try:
        new_id = agent_config_manager.create_system_prompt(
            name=body.name,
            content=body.content,
            description=body.description,
            is_default=body.is_default,
        )
        return {"id": new_id, "name": body.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/prompts/{name}")
def update_prompt(name: str, body: SystemPromptUpdate):
    try:
        updated = agent_config_manager.update_system_prompt(
            name=name,
            content=body.content,
            description=body.description,
            is_default=body.is_default,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/settings/prompts/{name}")
def delete_prompt(name: str):
    try:
        deleted = agent_config_manager.delete_system_prompt(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다.")
    return {"ok": True}


# ── 설정 — 스킬 ──────────────────────────────────────────────────

@router.get("/settings/skills")
def list_skills():
    try:
        return agent_config_manager.list_skills(active_only=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/skills/{name}/toggle")
def toggle_skill(name: str, body: SkillToggle):
    try:
        updated = agent_config_manager.set_skill_active(name, body.active)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="스킬을 찾을 수 없습니다.")
    return {"ok": True, "active": body.active}


# ── 설정 — 페르소나 ──────────────────────────────────────────────

@router.get("/settings/personas")
def list_personas():
    try:
        return agent_config_manager.list_personas()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/personas", status_code=201)
def create_persona(body: PersonaCreate):
    try:
        new_id = agent_config_manager.create_persona(
            name=body.name,
            system_prompt=body.system_prompt,
            display_name=body.display_name,
            description=body.description,
            allowed_skills=body.allowed_skills,
            keywords=body.keywords,
            is_default=body.is_default,
        )
        return {"id": new_id, "name": body.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/personas/{name}")
def update_persona(name: str, body: PersonaUpdate):
    try:
        updated = agent_config_manager.update_persona(
            name=name,
            system_prompt=body.system_prompt,
            display_name=body.display_name,
            description=body.description,
            allowed_skills=body.allowed_skills,
            keywords=body.keywords,
            is_default=body.is_default,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/settings/personas/{name}")
def delete_persona(name: str):
    try:
        deleted = agent_config_manager.delete_persona(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    return {"ok": True}


# ── 설정 — 매크로 / 워크플로우 (읽기 전용) ───────────────────────

@router.get("/settings/macros")
def list_macros():
    try:
        return agent_config_manager.list_macros()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/workflows")
def list_workflows():
    try:
        return agent_config_manager.list_workflows()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
