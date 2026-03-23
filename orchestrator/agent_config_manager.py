#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/agent_config_manager.py — 에이전트 설정 관리 파사드
"""에이전트 설정 관리 모듈 — 시스템 프롬프트, 스킬, 매크로, 워크플로우, 페르소나."""

import logging
from pathlib import Path
from typing import Dict, Optional

from .graph_manager import DB_PATH
from ._config_store import (  # noqa: F401
    init_db,
    _seed_default_prompts,
    _apply_update,
    _MACRO_VAR_RE,
    create_system_prompt,
    get_system_prompt,
    get_default_system_prompt,
    list_system_prompts,
    update_system_prompt,
    delete_system_prompt,
    migrate_prompts_from_files,
    sync_skills_from_registry,
    list_skills,
    get_skill,
    set_skill_active,
    create_macro,
    get_macro,
    list_macros,
    update_macro,
    delete_macro,
    render_macro,
    create_workflow,
    get_workflow,
    list_workflows,
    update_workflow,
    delete_workflow,
    create_persona,
    get_persona,
    list_personas,
    update_persona,
    delete_persona,
    get_effective_persona,
)


# ── 인메모리 프롬프트 캐시 ────────────────────────────────────────
_PROMPT_CACHE: dict[str, str] = {}


def get_prompt(name: str, db_path: Path = DB_PATH) -> str:
    """캐시 우선으로 프롬프트 내용을 반환합니다. 없으면 KeyError 발생."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    row = get_system_prompt(name, db_path)
    if row is None:
        raise KeyError(f"프롬프트 '{name}'을 찾을 수 없습니다.")
    _PROMPT_CACHE[name] = row["content"]
    return row["content"]


def render_prompt(name: str, db_path: Path = DB_PATH, **kwargs) -> str:
    """프롬프트 템플릿을 로드하여 변수를 치환합니다 (format_map 사용)."""
    content = get_prompt(name, db_path)
    return content.format_map(kwargs)


# ── 자동 초기화 ──────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    logging.warning(f"agent_config_manager DB 자동 초기화 실패: {_e}")

try:
    _seed_default_prompts()
except Exception as _e:
    logging.warning(f"agent_config_manager 프롬프트 시드 실패: {_e}")
