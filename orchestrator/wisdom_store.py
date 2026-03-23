#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/wisdom_store.py — 누적 지식(Wisdom) + 스케줄 태스크 CRUD

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .constants import utcnow
from .graph_manager import DB_PATH, get_db


# ── 누적 지식(Wisdom) CRUD ────────────────────────────────────────

def save_wisdom(
    convo_id: str,
    entries: List[dict],
    db_path: Path = DB_PATH,
) -> None:
    """실행 결과에서 추출한 지식 항목을 저장합니다.

    entries: [{category, content, source_tool}, ...]
    WISDOM_MAX_ENTRIES 초과 시 오래된 항목 삭제.
    """
    from .constants import WISDOM_MAX_ENTRIES

    if not entries:
        return

    now = utcnow()
    with get_db(db_path) as conn:
        for entry in entries:
            conn.execute(
                """
                INSERT INTO session_wisdom
                    (conversation_id, category, content, source_tool, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    convo_id,
                    entry.get("category", "misc"),
                    entry.get("content", ""),
                    entry.get("source_tool", ""),
                    now,
                ),
            )
        count = conn.execute(
            "SELECT COUNT(*) FROM session_wisdom WHERE conversation_id=?",
            (convo_id,),
        ).fetchone()[0]
        if count > WISDOM_MAX_ENTRIES:
            excess = count - WISDOM_MAX_ENTRIES
            conn.execute(
                """
                DELETE FROM session_wisdom WHERE id IN (
                    SELECT id FROM session_wisdom
                    WHERE conversation_id=?
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (convo_id, excess),
            )


def load_wisdom(
    convo_id: str,
    limit: int = 50,
    query: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> List[dict]:
    """대화에 저장된 지식 항목을 반환합니다 (최신순)."""
    if query:
        return search_wisdom_fts(query, convo_id=convo_id, limit=limit, db_path=db_path)

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT category, content, source_tool, created_at
            FROM session_wisdom
            WHERE conversation_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (convo_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def search_wisdom_fts(
    query: str,
    convo_id: Optional[str] = None,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> List[dict]:
    """FTS5로 wisdom 전문 검색."""
    with get_db(db_path) as conn:
        try:
            if convo_id:
                rows = conn.execute(
                    """
                    SELECT sw.conversation_id, sw.category, sw.content,
                           sw.source_tool, sw.created_at
                    FROM session_wisdom_fts fts
                    JOIN session_wisdom sw ON sw.id = fts.rowid
                    WHERE fts.session_wisdom_fts MATCH ?
                      AND sw.conversation_id = ?
                    ORDER BY sw.created_at DESC
                    LIMIT ?
                    """,
                    (query, convo_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT sw.conversation_id, sw.category, sw.content,
                           sw.source_tool, sw.created_at
                    FROM session_wisdom_fts fts
                    JOIN session_wisdom sw ON sw.id = fts.rowid
                    WHERE fts.session_wisdom_fts MATCH ?
                    ORDER BY sw.created_at DESC
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logging.warning(f"FTS 검색 실패, 일반 검색으로 폴백: {e}")
            pattern = f"%{query}%"
            if convo_id:
                rows = conn.execute(
                    """
                    SELECT conversation_id, category, content, source_tool, created_at
                    FROM session_wisdom
                    WHERE (content LIKE ? OR category LIKE ?)
                      AND conversation_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (pattern, pattern, convo_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT conversation_id, category, content, source_tool, created_at
                    FROM session_wisdom
                    WHERE content LIKE ? OR category LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (pattern, pattern, limit),
                ).fetchall()
            return [dict(r) for r in rows]


# ── 스케줄 태스크 CRUD ────────────────────────────────────────────

def add_scheduled_task(
    name: str,
    query: str,
    cron_expr: str,
    convo_id: str = "",
    db_path: Path = DB_PATH,
) -> int:
    """스케줄 태스크를 추가하고 id를 반환."""
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO scheduled_tasks
                (name, query, cron_expr, convo_id, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (name, query, cron_expr, convo_id, now),
        )
        return cur.lastrowid


def list_scheduled_tasks(db_path: Path = DB_PATH) -> List[dict]:
    """모든 스케줄 태스크 목록 반환."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_scheduled_task(task_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    """ID로 스케줄 태스크 조회."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)
        ).fetchone()
        return dict(row) if row else None


def remove_scheduled_task(task_id: int, db_path: Path = DB_PATH) -> bool:
    """스케줄 태스크 삭제. 성공 여부 반환."""
    with get_db(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM scheduled_tasks WHERE id=?", (task_id,)
        )
        return cur.rowcount > 0


def toggle_scheduled_task(task_id: int, enabled: bool, db_path: Path = DB_PATH) -> bool:
    """스케줄 태스크 활성화/비활성화. 성공 여부 반환."""
    with get_db(db_path) as conn:
        cur = conn.execute(
            "UPDATE scheduled_tasks SET enabled=? WHERE id=?",
            (1 if enabled else 0, task_id),
        )
        return cur.rowcount > 0


def update_scheduled_task_run(
    task_id: int,
    next_run_at: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """태스크 실행 후 last_run_at/run_count/next_run_at 갱신."""
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET last_run_at=?, run_count=run_count+1, next_run_at=?
            WHERE id=?
            """,
            (now, next_run_at, task_id),
        )
