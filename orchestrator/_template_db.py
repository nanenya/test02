#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_template_db.py — 실행 템플릿 / 태스크 계획 캐시 / 도구 부재 로그 CRUD
"""파이프라인 실행 템플릿, 계획 캐시, 도구 부재(gap) 로그 관리."""

import json
import logging
from typing import Any, Dict, List, Optional

from .graph_manager import DB_PATH, get_db
from .constants import utcnow

logger = logging.getLogger(__name__)

# ── 실행 템플릿(Execution Template) ──────────────────────────────────────────

def save_execution_template(
    name: str,
    description: str,
    keywords: List[str],
    execution_group: Dict[str, Any],
    path=DB_PATH,
) -> int:
    """실행 그룹 템플릿을 저장하고 template_id를 반환합니다.

    동일 name이 있으면 execution_group을 업데이트하고 success_count를 증가시킵니다.
    """
    now = utcnow()
    keywords_json = json.dumps(keywords, ensure_ascii=False)
    group_json = json.dumps(execution_group, ensure_ascii=False)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT id FROM execution_templates WHERE name=?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE execution_templates
                   SET execution_group=?, success_count=success_count+1, last_used_at=?
                   WHERE id=?""",
                (group_json, now, existing["id"]),
            )
            return existing["id"]
        cur = conn.execute(
            """
            INSERT INTO execution_templates
                (name, description, keywords, execution_group, success_count, last_used_at, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (name, description, keywords_json, group_json, now, now),
        )
        return cur.lastrowid


def find_best_template(keywords: List[str], path=DB_PATH) -> Optional[Dict[str, Any]]:
    """키워드 중복 수로 가장 유사한 활성 템플릿을 반환합니다 (기본 조회용).

    향상된 스코어링은 template_engine.TemplateEngine.find_and_adapt()를 사용하세요.
    3개 이상 겹치지 않으면 None을 반환합니다 (품질 임계값).
    """
    if not keywords:
        return None
    with get_db(path) as conn:
        rows = conn.execute(
            "SELECT * FROM execution_templates WHERE success_count > 0 AND is_active=1"
        ).fetchall()

    best_score = 0
    best_template = None
    kw_set = set(k.lower() for k in keywords)

    for row in rows:
        t = dict(row)
        t_keywords = set(k.lower() for k in json.loads(t.get("keywords") or "[]"))
        score = len(kw_set & t_keywords)
        if score > best_score:
            best_score = score
            best_template = t

    if best_score < 3:
        return None

    if best_template:
        best_template["execution_group"] = json.loads(
            best_template.get("execution_group") or "{}"
        )
    return best_template


def list_templates(
    active_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    path=DB_PATH,
) -> List[Dict[str, Any]]:
    """템플릿 목록을 반환합니다 (success_count 내림차순)."""
    where = "WHERE is_active=1" if active_only else ""
    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT id, name, description, success_count, fail_count, is_active, "
            f"last_used_at, created_at FROM execution_templates "
            f"{where} ORDER BY success_count DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_template(template_id: int, path=DB_PATH) -> Optional[Dict[str, Any]]:
    """단일 템플릿 전체 정보를 반환합니다."""
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT * FROM execution_templates WHERE id=?", (template_id,)
        ).fetchone()
    if not row:
        return None
    t = dict(row)
    t["execution_group"] = json.loads(t.get("execution_group") or "{}")
    t["keywords"] = json.loads(t.get("keywords") or "[]")
    return t


def disable_template(template_id: int, path=DB_PATH) -> None:
    """템플릿을 비활성화합니다."""
    with get_db(path) as conn:
        conn.execute("UPDATE execution_templates SET is_active=0 WHERE id=?", (template_id,))


def enable_template(template_id: int, path=DB_PATH) -> None:
    """템플릿을 활성화합니다."""
    with get_db(path) as conn:
        conn.execute("UPDATE execution_templates SET is_active=1 WHERE id=?", (template_id,))


def delete_template(template_id: int, path=DB_PATH) -> None:
    """템플릿을 삭제합니다."""
    with get_db(path) as conn:
        conn.execute("DELETE FROM execution_templates WHERE id=?", (template_id,))


def get_template_stats(path=DB_PATH) -> Dict[str, Any]:
    """템플릿 전체 통계를 반환합니다."""
    with get_db(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM execution_templates").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM execution_templates WHERE is_active=1"
        ).fetchone()[0]
        total_success = conn.execute(
            "SELECT COALESCE(SUM(success_count),0) FROM execution_templates"
        ).fetchone()[0]
        total_fail = conn.execute(
            "SELECT COALESCE(SUM(fail_count),0) FROM execution_templates"
        ).fetchone()[0]
        cache_total = conn.execute("SELECT COUNT(*) FROM task_plan_cache").fetchone()[0]
        cache_hits = conn.execute(
            "SELECT COALESCE(SUM(use_count)-COUNT(*),0) FROM task_plan_cache"
        ).fetchone()[0]
    return {
        "total_templates": total,
        "active_templates": active,
        "disabled_templates": total - active,
        "total_success_executions": int(total_success),
        "total_fail_executions": int(total_fail),
        "success_rate": round(
            total_success / (total_success + total_fail), 3
        ) if (total_success + total_fail) > 0 else 0.0,
        "plan_cache_entries": cache_total,
        "plan_cache_hits": int(cache_hits),
    }


def auto_disable_failing_templates(
    fail_rate_threshold: float = 0.6,
    min_uses: int = 3,
    path=DB_PATH,
) -> List[int]:
    """실패율이 임계값을 초과한 템플릿을 자동 비활성화합니다.

    조건: fail_count / (success_count + fail_count) >= fail_rate_threshold
          AND (success_count + fail_count) >= min_uses
    반환: 비활성화된 template_id 목록
    """
    disabled_ids = []
    with get_db(path) as conn:
        rows = conn.execute(
            "SELECT id, success_count, fail_count FROM execution_templates WHERE is_active=1"
        ).fetchall()
        for row in rows:
            total = row["success_count"] + row["fail_count"]
            if total < min_uses:
                continue
            if row["fail_count"] / total >= fail_rate_threshold:
                conn.execute(
                    "UPDATE execution_templates SET is_active=0 WHERE id=?", (row["id"],)
                )
                disabled_ids.append(row["id"])
                logger.info(
                    f"[Template] 자동 비활성화: id={row['id']} "
                    f"fail_rate={row['fail_count']/total:.1%}"
                )
    return disabled_ids


def increment_template_fail(template_id: int, path=DB_PATH) -> None:
    with get_db(path) as conn:
        conn.execute(
            "UPDATE execution_templates SET fail_count=fail_count+1 WHERE id=?",
            (template_id,),
        )
    auto_disable_failing_templates(path=path)


# ── 태스크 계획 캐시(Task Plan Cache) ─────────────────────────────────────────

def get_task_plan_cache(task_signature: str, path=DB_PATH) -> Optional[List[Dict[str, Any]]]:
    """태스크 시그니처로 캐시된 계획 단계를 반환하고 use_count를 증가시킵니다."""
    now = utcnow()
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT * FROM task_plan_cache WHERE task_signature=?", (task_signature,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE task_plan_cache SET use_count=use_count+1, last_used_at=? WHERE task_signature=?",
            (now, task_signature),
        )
    plans = json.loads(row["plans"])
    return plans


def save_task_plan_cache(
    task_signature: str,
    keywords: List[str],
    plans: List[Dict[str, Any]],
    path=DB_PATH,
) -> None:
    """태스크 계획 매핑 결과를 캐시에 저장합니다 (UPSERT)."""
    now = utcnow()
    plans_json = json.dumps(plans, ensure_ascii=False)
    kw_json = json.dumps(keywords, ensure_ascii=False)
    with get_db(path) as conn:
        conn.execute(
            """
            INSERT INTO task_plan_cache (task_signature, keywords, plans, use_count, last_used_at, created_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(task_signature) DO UPDATE SET
                plans=excluded.plans,
                use_count=use_count+1,
                last_used_at=excluded.last_used_at
            """,
            (task_signature, kw_json, plans_json, now, now),
        )


# ── 도구 부재 로그(Tool Gap Log) ──────────────────────────────────────────────

def log_tool_gap(
    required_tool: str,
    resolution_type: str = "not_found",
    mcp_server_name: str = "",
    func_id: Optional[int] = None,
    note: str = "",
    path=DB_PATH,
) -> None:
    """도구 부재 이벤트를 기록합니다. 예외는 절대 발생시키지 않습니다."""
    try:
        now = utcnow()
        with get_db(path) as conn:
            conn.execute(
                """INSERT INTO tool_gap_log
                       (required_tool, resolution_type, mcp_server_name, func_id, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (required_tool, resolution_type, mcp_server_name, func_id, note, now),
            )
    except Exception as e:
        logger.warning(f"tool_gap_log 기록 실패: {e}")


