#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/pipeline_db.py
"""4층 파이프라인 DB 관리 모듈.

테이블:
  - designs           : 설계 결과 (사용자 확인 포함)
  - tasks             : 태스크 분해 결과
  - task_plans        : 태스크별 계획 단계
  - execution_templates : 실행 그룹 템플릿 (재사용 핵심)
  - task_plan_cache   : 태스크 → 계획 단계 매핑 캐시 (map_plans LLM 절약)
  - tool_gap_log      : 도구 부재 → 발견/구현 이력
  - pipeline_cursors  : 대화별 파이프라인 현재 위치 커서
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .graph_manager import DB_PATH, get_db
from .constants import utcnow

logger = logging.getLogger(__name__)


# ── DB 초기화 ─────────────────────────────────────────────────────────────────

def init_db(path=DB_PATH) -> None:
    """파이프라인 관련 테이블을 IF NOT EXISTS로 생성하고 마이그레이션합니다."""
    with get_db(path) as conn:
        # is_active 컬럼 하위 호환 마이그레이션 (이미 존재하면 무시)
        try:
            conn.execute(
                "ALTER TABLE execution_templates ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )
        except Exception:
            pass  # 이미 존재하는 컬럼
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS designs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT    NOT NULL,
            query_hash      TEXT    NOT NULL DEFAULT '',
            query_text      TEXT    NOT NULL,
            design_text     TEXT    NOT NULL,
            approach        TEXT    NOT NULL DEFAULT '',
            complexity      TEXT    NOT NULL DEFAULT 'medium',
            persona_used    TEXT    NOT NULL DEFAULT '',
            status          TEXT    NOT NULL DEFAULT 'pending_confirm',
            created_at      TEXT    NOT NULL,
            confirmed_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_designs_conversation ON designs(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_designs_query_hash ON designs(query_hash);

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            design_id   INTEGER NOT NULL REFERENCES designs(id),
            task_index  INTEGER NOT NULL DEFAULT 0,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_design ON tasks(design_id, status);

        CREATE TABLE IF NOT EXISTS task_plans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER NOT NULL REFERENCES tasks(id),
            step_index  INTEGER NOT NULL DEFAULT 0,
            action      TEXT    NOT NULL,
            tool_hints  TEXT    NOT NULL DEFAULT '[]',
            template_id INTEGER,
            status      TEXT    NOT NULL DEFAULT 'pending',
            result      TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_task_plans_task ON task_plans(task_id, status);

        CREATE TABLE IF NOT EXISTS execution_templates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL UNIQUE,
            description     TEXT    NOT NULL DEFAULT '',
            keywords        TEXT    NOT NULL DEFAULT '[]',
            execution_group TEXT    NOT NULL,
            success_count   INTEGER NOT NULL DEFAULT 0,
            fail_count      INTEGER NOT NULL DEFAULT 0,
            is_active       INTEGER NOT NULL DEFAULT 1,
            last_used_at    TEXT,
            created_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_plan_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_signature  TEXT    NOT NULL UNIQUE,
            keywords        TEXT    NOT NULL DEFAULT '[]',
            plans           TEXT    NOT NULL,
            use_count       INTEGER NOT NULL DEFAULT 1,
            last_used_at    TEXT    NOT NULL,
            created_at      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_task_plan_cache_sig ON task_plan_cache(task_signature);

        CREATE TABLE IF NOT EXISTS tool_gap_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            required_tool   TEXT    NOT NULL,
            resolution_type TEXT    NOT NULL DEFAULT 'not_found',
            mcp_server_name TEXT    NOT NULL DEFAULT '',
            func_id         INTEGER,
            note            TEXT    NOT NULL DEFAULT '',
            created_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pipeline_cursors (
            conversation_id TEXT    PRIMARY KEY,
            design_id       INTEGER,
            task_id         INTEGER,
            plan_id         INTEGER,
            phase           TEXT    NOT NULL DEFAULT 'idle',
            updated_at      TEXT    NOT NULL
        );
        """)


# ── 설계(Design) ──────────────────────────────────────────────────────────────

def create_design(
    conversation_id: str,
    query_text: str,
    design_text: str,
    approach: str = "",
    complexity: str = "medium",
    persona_used: str = "",
    query_hash: str = "",
    path=DB_PATH,
) -> int:
    """설계를 DB에 저장하고 design_id를 반환합니다."""
    now = utcnow()
    with get_db(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO designs
                (conversation_id, query_hash, query_text, design_text, approach,
                 complexity, persona_used, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_confirm', ?)
            """,
            (conversation_id, query_hash, query_text, design_text, approach,
             complexity, persona_used, now),
        )
        return cur.lastrowid


def confirm_design(design_id: int, path=DB_PATH) -> None:
    """설계를 confirmed 상태로 변경합니다."""
    now = utcnow()
    with get_db(path) as conn:
        conn.execute(
            "UPDATE designs SET status='confirmed', confirmed_at=? WHERE id=?",
            (now, design_id),
        )


def reject_design(design_id: int, path=DB_PATH) -> None:
    """설계를 rejected 상태로 변경합니다."""
    with get_db(path) as conn:
        conn.execute(
            "UPDATE designs SET status='rejected' WHERE id=?",
            (design_id,),
        )


def get_design(design_id: int, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """design_id로 설계를 조회합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT * FROM designs WHERE id=?", (design_id,)
        ).fetchone()
        return dict(row) if row else None


def get_active_design(conversation_id: str, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """대화의 현재 활성 설계(pending_confirm 또는 confirmed)를 반환합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            """SELECT * FROM designs
               WHERE conversation_id=? AND status IN ('pending_confirm','confirmed')
               ORDER BY id DESC LIMIT 1""",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None


# ── 태스크(Task) ──────────────────────────────────────────────────────────────

def create_tasks(design_id: int, tasks: List[Dict[str, str]], path=DB_PATH) -> List[int]:
    """태스크 목록을 DB에 저장하고 task_id 리스트를 반환합니다."""
    now = utcnow()
    ids = []
    with get_db(path) as conn:
        for idx, task in enumerate(tasks):
            cur = conn.execute(
                """
                INSERT INTO tasks (design_id, task_index, title, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (design_id, idx, task.get("title", ""), task.get("description", ""), now),
            )
            ids.append(cur.lastrowid)
    return ids


def get_tasks(design_id: int, path=DB_PATH) -> List[Dict[str, Any]]:
    """design_id에 속한 모든 태스크를 반환합니다."""
    with get_db(path) as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE design_id=? ORDER BY task_index",
            (design_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_next_pending_task(design_id: int, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """다음 실행 대기 중인 태스크를 반환합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            """SELECT * FROM tasks
               WHERE design_id=? AND status='pending'
               ORDER BY task_index LIMIT 1""",
            (design_id,),
        ).fetchone()
        return dict(row) if row else None


def update_task_status(task_id: int, status: str, path=DB_PATH) -> None:
    with get_db(path) as conn:
        conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))


# ── 계획(Plan) ────────────────────────────────────────────────────────────────

def create_task_plans(task_id: int, plans: List[Dict[str, Any]], path=DB_PATH) -> List[int]:
    """계획 단계 목록을 DB에 저장하고 plan_id 리스트를 반환합니다."""
    now = utcnow()
    ids = []
    with get_db(path) as conn:
        for idx, step in enumerate(plans):
            tool_hints_json = json.dumps(step.get("tool_hints", []), ensure_ascii=False)
            cur = conn.execute(
                """
                INSERT INTO task_plans
                    (task_id, step_index, action, tool_hints, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, idx, step.get("action", ""), tool_hints_json, now),
            )
            ids.append(cur.lastrowid)
    return ids


def get_task_plans(task_id: int, path=DB_PATH) -> List[Dict[str, Any]]:
    """task_id에 속한 모든 계획 단계를 반환합니다."""
    with get_db(path) as conn:
        rows = conn.execute(
            "SELECT * FROM task_plans WHERE task_id=? ORDER BY step_index",
            (task_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tool_hints"] = json.loads(d.get("tool_hints") or "[]")
            result.append(d)
        return result


def get_next_pending_plan(task_id: int, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """다음 실행 대기 중인 계획 단계를 반환합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            """SELECT * FROM task_plans
               WHERE task_id=? AND status='pending'
               ORDER BY step_index LIMIT 1""",
            (task_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tool_hints"] = json.loads(d.get("tool_hints") or "[]")
        return d


def update_plan_status(
    plan_id: int,
    status: str,
    result: str = "",
    template_id: Optional[int] = None,
    path=DB_PATH,
) -> None:
    with get_db(path) as conn:
        if template_id is not None:
            conn.execute(
                "UPDATE task_plans SET status=?, result=?, template_id=? WHERE id=?",
                (status, result, template_id, plan_id),
            )
        else:
            conn.execute(
                "UPDATE task_plans SET status=?, result=? WHERE id=?",
                (status, result, plan_id),
            )


# ── 파이프라인 커서(Pipeline Cursor) ─────────────────────────────────────────

def set_cursor(
    conversation_id: str,
    phase: str,
    design_id: Optional[int] = None,
    task_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    path=DB_PATH,
) -> None:
    """현재 파이프라인 위치를 저장합니다 (UPSERT)."""
    now = utcnow()
    with get_db(path) as conn:
        conn.execute(
            """
            INSERT INTO pipeline_cursors
                (conversation_id, design_id, task_id, plan_id, phase, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                design_id=excluded.design_id,
                task_id=excluded.task_id,
                plan_id=excluded.plan_id,
                phase=excluded.phase,
                updated_at=excluded.updated_at
            """,
            (conversation_id, design_id, task_id, plan_id, phase, now),
        )


def get_cursor(conversation_id: str, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """대화의 현재 파이프라인 커서를 반환합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT * FROM pipeline_cursors WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None


def clear_cursor(conversation_id: str, path=DB_PATH) -> None:
    """파이프라인 커서를 idle 상태로 초기화합니다."""
    set_cursor(conversation_id, phase="idle", path=path)

# ── 하위 모듈 위임 (하위 호환 re-export) ─────────────────────────
from ._template_db import (  # noqa: F401
    save_execution_template,
    find_best_template,
    list_templates,
    get_template,
    disable_template,
    enable_template,
    delete_template,
    get_template_stats,
    auto_disable_failing_templates,
    increment_template_fail,
    get_task_plan_cache,
    save_task_plan_cache,
    log_tool_gap,
)
