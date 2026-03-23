#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/issue_tracker.py
"""런타임 이슈 자동 저장 모듈."""

import logging
import traceback as _traceback
from typing import Dict, List, Optional

from .constants import utcnow
from .graph_manager import DB_PATH, get_db


_ISSUE_COLS = (
    "id, title, error_type, error_message, traceback, "
    "context, source, severity, status, created_at, resolved_at, resolution_note"
)
_ISSUE_KEYS = [
    "id", "title", "error_type", "error_message", "traceback",
    "context", "source", "severity", "status",
    "created_at", "resolved_at", "resolution_note",
]


# ── DB 초기화 ──────────────────────────────────────────────────────

def init_db(path=DB_PATH) -> None:
    """issues 테이블을 생성합니다."""
    with get_db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS issues (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                title            TEXT    NOT NULL DEFAULT '',
                error_type       TEXT    NOT NULL DEFAULT '',
                error_message    TEXT    NOT NULL,
                traceback        TEXT    NOT NULL DEFAULT '',
                context          TEXT    NOT NULL DEFAULT '',
                source           TEXT    NOT NULL DEFAULT '',
                severity         TEXT    NOT NULL DEFAULT 'error',
                status           TEXT    NOT NULL DEFAULT 'open',
                created_at       TEXT    NOT NULL,
                resolved_at      TEXT,
                resolution_note  TEXT    NOT NULL DEFAULT ''
            );
        """)


# ── 핵심 함수 ──────────────────────────────────────────────────────

def capture(
    error_message: str,
    error_type: str = "",
    traceback: str = "",
    context: str = "",
    source: str = "",
    severity: str = "error",
    title: str = "",
    db_path=DB_PATH,
) -> Optional[int]:
    """이슈를 DB에 저장합니다. 예외는 절대 re-raise 하지 않습니다."""
    try:
        if not title:
            title = f"[{error_type}] {error_message[:80]}"
        now = utcnow()
        with get_db(db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO issues
                    (title, error_type, error_message, traceback, context,
                     source, severity, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (title, error_type, error_message, traceback, context,
                 source, severity, now),
            )
            return cur.lastrowid
    except Exception as inner:
        logging.warning(f"issue_tracker.capture 실패: {inner}")
        return None


def capture_exception(
    exc: Exception,
    context: str = "",
    source: str = "",
    severity: str = "error",
    db_path=DB_PATH,
) -> Optional[int]:
    """except 블록 안에서 호출하면 traceback을 자동 캡처합니다."""
    tb = _traceback.format_exc()
    return capture(
        error_message=str(exc),
        error_type=type(exc).__name__,
        traceback=tb,
        context=context,
        source=source,
        severity=severity,
        db_path=db_path,
    )


def list_issues(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    db_path=DB_PATH,
) -> List[Dict]:
    """이슈 목록을 반환합니다. ORDER BY created_at DESC."""
    try:
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if source:
            conditions.append("source = ?")
            params.append(source)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        with get_db(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT {_ISSUE_COLS}
                FROM issues
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(zip(_ISSUE_KEYS, row)) for row in rows]
    except Exception as e:
        logging.warning(f"issue_tracker.list_issues 실패: {e}")
        return []


def get_issue(issue_id: int, db_path=DB_PATH) -> Optional[Dict]:
    """단일 이슈를 반환합니다. 없으면 None."""
    try:
        with get_db(db_path) as conn:
            row = conn.execute(
                f"SELECT {_ISSUE_COLS} FROM issues WHERE id = ?",
                (issue_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(zip(_ISSUE_KEYS, row))
    except Exception as e:
        logging.warning(f"issue_tracker.get_issue 실패: {e}")
        return None


def update_status(
    issue_id: int,
    status: str,
    resolution_note: str = "",
    db_path=DB_PATH,
) -> bool:
    """이슈 상태를 갱신합니다. 성공 시 True 반환."""
    try:
        now = utcnow()
        resolved_at = now if status in ("resolved", "ignored") else None
        with get_db(db_path) as conn:
            cur = conn.execute(
                """
                UPDATE issues
                SET status = ?, resolved_at = ?, resolution_note = ?
                WHERE id = ?
                """,
                (status, resolved_at, resolution_note, issue_id),
            )
            return cur.rowcount > 0
    except Exception as e:
        logging.warning(f"issue_tracker.update_status 실패: {e}")
        return False


# ── 모듈 로드 시 자동 초기화 ───────────────────────────────────────
init_db()
