#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/web_router.py
"""웹 UI용 REST API 라우터 — /api/v1 prefix."""

from typing import Callable, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import graph_manager
from . import mcp_db_manager
from . import agent_config_manager
from . import tool_registry

router = APIRouter(prefix="/api/v1", tags=["web"])


def _list_safe(list_fn: Callable) -> list:
    """예외를 HTTP 500으로 변환하여 목록을 반환합니다."""
    try:
        return list_fn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _delete_resource(
    delete_fn: Callable[[str], bool],
    name: str,
    not_found_msg: str,
) -> dict:
    """삭제 실행 후 미존재 시 404, 예외 시 500."""
    try:
        deleted = delete_fn(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=not_found_msg)
    return {"ok": True}


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


class MacroCreate(BaseModel):
    name: str
    template: str
    description: str = ""
    variables: Optional[List[str]] = None


class MacroUpdate(BaseModel):
    template: Optional[str] = None
    description: Optional[str] = None
    variables: Optional[List[str]] = None


class WorkflowCreate(BaseModel):
    name: str
    steps: List[Dict]
    description: str = ""


class WorkflowUpdate(BaseModel):
    steps: Optional[List[Dict]] = None
    description: Optional[str] = None


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
    return _list_safe(agent_config_manager.list_system_prompts)


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
    return _delete_resource(agent_config_manager.delete_system_prompt, name, "프롬프트를 찾을 수 없습니다.")


# ── 설정 — 스킬 ──────────────────────────────────────────────────

@router.get("/settings/skills")
def list_skills():
    return _list_safe(lambda: agent_config_manager.list_skills(active_only=False))


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
    return _delete_resource(agent_config_manager.delete_persona, name, "페르소나를 찾을 수 없습니다.")


# ── 설정 — 매크로 CRUD ────────────────────────────────────────────

@router.get("/settings/macros")
def list_macros():
    return _list_safe(agent_config_manager.list_macros)


@router.post("/settings/macros", status_code=201)
def create_macro(body: MacroCreate):
    try:
        new_id = agent_config_manager.create_macro(
            name=body.name,
            template=body.template,
            description=body.description,
            variables=body.variables,
        )
        return {"id": new_id, "name": body.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/macros/{name}")
def update_macro(name: str, body: MacroUpdate):
    try:
        updated = agent_config_manager.update_macro(
            name=name,
            template=body.template,
            description=body.description,
            variables=body.variables,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="매크로를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/settings/macros/{name}")
def delete_macro(name: str):
    return _delete_resource(agent_config_manager.delete_macro, name, "매크로를 찾을 수 없습니다.")


# ── 설정 — 워크플로우 CRUD ────────────────────────────────────────

@router.get("/settings/workflows")
def list_workflows():
    return _list_safe(agent_config_manager.list_workflows)


@router.post("/settings/workflows", status_code=201)
def create_workflow(body: WorkflowCreate):
    try:
        new_id = agent_config_manager.create_workflow(
            name=body.name,
            steps=body.steps,
            description=body.description,
        )
        return {"id": new_id, "name": body.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/workflows/{name}")
def update_workflow(name: str, body: WorkflowUpdate):
    try:
        updated = agent_config_manager.update_workflow(
            name=name,
            steps=body.steps,
            description=body.description,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/settings/workflows/{name}")
def delete_workflow(name: str):
    return _delete_resource(agent_config_manager.delete_workflow, name, "워크플로우를 찾을 수 없습니다.")


@router.get("/tools/status")
def get_tools_status():
    """현재 로드된 도구의 실제 상태를 반환합니다."""
    try:
        return tool_registry.get_tool_load_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers/status")
def get_providers_status():
    """LLM 프로바이더 Circuit Breaker 상태를 반환합니다.

    quota/크레딧 소진으로 차단된 프로바이더와 재시도 예정 시각을 확인합니다.
    """
    try:
        from . import llm_client
        return llm_client.get_provider_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
