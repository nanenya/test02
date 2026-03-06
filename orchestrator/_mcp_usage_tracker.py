#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_mcp_usage_tracker.py — MCP 세션·사용 추적
"""MCP 함수 사용 통계 및 세션 관리."""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .graph_manager import DB_PATH, get_db
from .constants import MAX_FUNC_NAMES_PER_SESSION, utcnow

# ── 사용 추적 ─────────────────────────────────────────────────────

def start_session(
    conversation_id: Optional[str] = None,
    group_id: str = "",
    db_path=DB_PATH,
) -> str:
    """실행 세션을 시작하고 session_id(UUID)를 반환합니다."""
    session_id = str(uuid.uuid4())
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO mcp_session_log "
            "(id, conversation_id, group_id, started_at, func_names) "
            "VALUES (?, ?, ?, ?, '[]')",
            (session_id, conversation_id, group_id, now),
        )
    return session_id


def end_session(
    session_id: str,
    overall_success: bool = True,
    db_path=DB_PATH,
) -> None:
    """실행 세션을 종료합니다."""
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE mcp_session_log SET ended_at = ?, overall_success = ? WHERE id = ?",
            (now, 1 if overall_success else 0, session_id),
        )


def log_usage(
    func_name: str,
    success: bool,
    session_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error_message: str = "",
    args_summary: str = "",
    db_path=DB_PATH,
) -> None:
    """함수 실행 로그를 기록합니다."""
    now = utcnow()
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT version, module_group FROM mcp_functions "
            "WHERE func_name = ? AND is_active = 1",
            (func_name,),
        ).fetchone()
        func_version = row[0] if row else 0
        module_group = row[1] if row else ""

        conn.execute(
            """INSERT INTO mcp_usage_log
               (session_id, func_name, func_version, module_group, called_at,
                duration_ms, success, error_message, args_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, func_name, func_version, module_group, now,
                duration_ms, 1 if success else 0, error_message, args_summary,
            ),
        )

        if session_id:
            sess_row = conn.execute(
                "SELECT func_names FROM mcp_session_log WHERE id = ?",
                (session_id,),
            ).fetchone()
            if sess_row:
                func_names = json.loads(sess_row[0])
                if func_name not in func_names:
                    if len(func_names) >= MAX_FUNC_NAMES_PER_SESSION:
                        logging.warning(
                            f"세션 '{session_id}'의 func_names가 {MAX_FUNC_NAMES_PER_SESSION}개 "
                            f"한도에 도달했습니다. '{func_name}'을 추가하지 않습니다."
                        )
                    else:
                        func_names.append(func_name)
                conn.execute(
                    "UPDATE mcp_session_log SET func_names = ? WHERE id = ?",
                    (json.dumps(func_names), session_id),
                )


def get_usage_stats(
    func_name: Optional[str] = None,
    module_group: Optional[str] = None,
    db_path=DB_PATH,
) -> Dict:
    """사용 통계를 집계합니다."""
    query = "SELECT func_name, module_group, success, duration_ms FROM mcp_usage_log WHERE 1=1"
    params: List = []
    if func_name:
        query += " AND func_name = ?"
        params.append(func_name)
    if module_group:
        query += " AND module_group = ?"
        params.append(module_group)

    with get_db(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return {"total_calls": 0, "success_rate": 0.0, "avg_duration_ms": 0.0, "by_function": {}}

    by_func: Dict[str, Dict] = {}
    for row in rows:
        fn = row[0]
        if fn not in by_func:
            by_func[fn] = {"total": 0, "success": 0, "durations": []}
        by_func[fn]["total"] += 1
        if row[2]:
            by_func[fn]["success"] += 1
        if row[3] is not None:
            by_func[fn]["durations"].append(row[3])

    total_calls = len(rows)
    total_success = sum(r[2] for r in rows)
    durations = [r[3] for r in rows if r[3] is not None]

    result_by_func = {}
    for fn, stats in by_func.items():
        avg_dur = (
            sum(stats["durations"]) / len(stats["durations"])
            if stats["durations"] else 0.0
        )
        result_by_func[fn] = {
            "total_calls": stats["total"],
            "success_rate": stats["success"] / stats["total"] if stats["total"] else 0.0,
            "avg_duration_ms": avg_dur,
        }

    return {
        "total_calls": total_calls,
        "success_rate": total_success / total_calls if total_calls else 0.0,
        "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
        "by_function": result_by_func,
    }


