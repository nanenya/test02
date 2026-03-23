#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/mcp_db_manager.py
"""SQLite DB 기반 MCP 함수 관리 모듈."""

import ast
import json
import logging
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .graph_manager import DB_PATH, get_db
from .constants import MAX_FUNC_NAMES_PER_SESSION, utcnow
from . import config as _config

_BASE_DIR = Path(__file__).parent.parent
MCP_CACHE_DIR = _BASE_DIR / "mcp_cache"


# ── DB 초기화 ──────────────────────────────────────────────────────

def init_db(path=DB_PATH) -> None:
    """MCP 관련 테이블 4개를 생성합니다."""
    with get_db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS mcp_functions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                func_name     TEXT    NOT NULL,
                module_group  TEXT    NOT NULL,
                version       INTEGER NOT NULL DEFAULT 1,
                is_active     INTEGER NOT NULL DEFAULT 0,
                code          TEXT    NOT NULL,
                test_code     TEXT    NOT NULL DEFAULT '',
                test_status   TEXT    NOT NULL DEFAULT 'untested',
                test_output   TEXT    NOT NULL DEFAULT '',
                description   TEXT    NOT NULL DEFAULT '',
                source_type   TEXT    NOT NULL DEFAULT 'internal',
                source_url    TEXT    NOT NULL DEFAULT '',
                source_author TEXT    NOT NULL DEFAULT '',
                source_license TEXT   NOT NULL DEFAULT '',
                source_desc   TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL,
                activated_at  TEXT,
                UNIQUE(func_name, version)
            );

            CREATE TABLE IF NOT EXISTS mcp_module_contexts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                module_group TEXT    NOT NULL UNIQUE,
                preamble_code TEXT   NOT NULL DEFAULT '',
                description  TEXT    NOT NULL DEFAULT '',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mcp_usage_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT,
                func_name     TEXT    NOT NULL,
                func_version  INTEGER NOT NULL DEFAULT 0,
                module_group  TEXT    NOT NULL DEFAULT '',
                called_at     TEXT    NOT NULL,
                duration_ms   INTEGER,
                success       INTEGER NOT NULL DEFAULT 1,
                error_message TEXT    NOT NULL DEFAULT '',
                args_summary  TEXT    NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS mcp_session_log (
                id              TEXT    PRIMARY KEY,
                conversation_id TEXT,
                group_id        TEXT    NOT NULL DEFAULT '',
                started_at      TEXT    NOT NULL,
                ended_at        TEXT,
                overall_success INTEGER NOT NULL DEFAULT 1,
                func_names      TEXT    NOT NULL DEFAULT '[]'
            );
        """)


# 모듈 로드 시 자동 초기화
try:
    init_db()
    MCP_CACHE_DIR.mkdir(exist_ok=True)
except Exception as _e:
    logging.warning(f"mcp_db_manager init_db 실패: {_e}")


# ── 조회 ──────────────────────────────────────────────────────────

def get_active_function(func_name: str, db_path=DB_PATH) -> Optional[Dict]:
    """활성 버전의 함수 정보를 반환합니다."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM mcp_functions WHERE func_name = ? AND is_active = 1",
            (func_name,),
        ).fetchone()
    return dict(row) if row else None


def list_functions(
    module_group: Optional[str] = None,
    active_only: bool = True,
    db_path=DB_PATH,
) -> List[Dict]:
    """함수 목록을 반환합니다."""
    query = "SELECT * FROM mcp_functions WHERE 1=1"
    params: List = []
    if active_only:
        query += " AND is_active = 1"
    if module_group:
        query += " AND module_group = ?"
        params.append(module_group)
    query += " ORDER BY module_group, func_name"
    with get_db(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_function_versions(func_name: str, db_path=DB_PATH) -> List[Dict]:
    """함수의 모든 버전 이력을 반환합니다."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_functions WHERE func_name = ? ORDER BY version DESC",
            (func_name,),
        ).fetchall()
    return [dict(r) for r in rows]



# ── 하위 모듈 위임 (하위 호환 re-export) ─────────────────────────
from ._mcp_code_ops import (  # noqa: F401
    register_function,
    add_function,
    _activate_function,
    _run_and_activate,
    _invalidate_cache_for_function,
    run_function_tests,
    generate_temp_module,
    _validate_code_syntax,
    load_module_in_memory,
    import_from_file,
    _extract_preamble,
    _extract_test_map,
    update_function_test_code,
    activate_function,
    set_module_preamble,
)
from ._mcp_usage_tracker import (  # noqa: F401
    start_session,
    end_session,
    log_usage,
    get_usage_stats,
)
