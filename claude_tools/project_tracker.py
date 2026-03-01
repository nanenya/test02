#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_tracker.py - PROJECT_ANALYSIS.md 정적 섹션 → SQLite DB 관리

관리 테이블:
  requirements  — 요구사항 전체 (섹션 0.1/0.2/0.3 통합, status로 구분)
                  status: 'DONE' | 'IN_PROGRESS' | 'PENDING'
  change_log    — 변경 이력 (섹션 0.4)
  deleted_files — 삭제된 파일 이력 (섹션 5.1)
  test_status   — 테스트 현황 (섹션 6)

이슈 (섹션 10)는 orchestrator/issue_tracker.py 의 issues 테이블을 그대로 사용.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ─────────────────────────────────────────────
# DB 경로
# ─────────────────────────────────────────────

def get_db_path() -> str:
    """프로젝트 루트 기준 DB 경로를 반환합니다."""
    # claude_tools/ 의 부모 = test02/ (프로젝트 루트)
    project_root = Path(__file__).parent.parent
    return str(project_root / "history" / "conversations.db")


# ─────────────────────────────────────────────
# DB 연결 헬퍼
# ─────────────────────────────────────────────

@contextmanager
def _get_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ─────────────────────────────────────────────
# 테이블 초기화
# ─────────────────────────────────────────────

def _ensure_issue_id_column(conn) -> None:
    """requirements 테이블에 issue_id 컬럼이 없으면 추가합니다."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(requirements)").fetchall()]
    if "issue_id" not in cols:
        conn.execute(
            "ALTER TABLE requirements ADD COLUMN issue_id INTEGER DEFAULT NULL"
        )


def init_tables(db_path: Optional[str] = None) -> None:
    """4개 테이블을 생성합니다 (이미 있으면 무시). requirements에 issue_id 컬럼 보장."""
    if db_path is None:
        db_path = get_db_path()

    with _get_db(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS requirements (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                number        INTEGER NOT NULL,
                title         TEXT    NOT NULL,
                applied_files TEXT    NOT NULL DEFAULT '',
                status        TEXT    NOT NULL DEFAULT 'DONE',
                note          TEXT    NOT NULL DEFAULT '',
                completed_at  TEXT    NOT NULL,
                issue_id      INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS change_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT    NOT NULL,
                description   TEXT    NOT NULL,
                changed_files TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deleted_files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT    NOT NULL,
                level       TEXT    NOT NULL DEFAULT '',
                note        TEXT    NOT NULL DEFAULT '',
                deleted_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS test_status (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                test_file     TEXT    NOT NULL UNIQUE,
                target_module TEXT    NOT NULL DEFAULT '',
                note          TEXT    NOT NULL DEFAULT '',
                test_count    INTEGER NOT NULL DEFAULT 0,
                checked_at    TEXT    NOT NULL
            );
        """)
        # 기존 테이블에 issue_id 컬럼이 없으면 추가 (스키마 마이그레이션)
        _ensure_issue_id_column(conn)


# ─────────────────────────────────────────────
# requirements 테이블
# ─────────────────────────────────────────────

def add_requirement(
    number: int,
    title: str,
    applied_files: str = "",
    status: str = "DONE",
    note: str = "",
    completed_at: Optional[str] = None,
    issue_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    """요구사항을 DB에 추가합니다.

    completed_at 규칙:
      - status='DONE' 이고 completed_at=None → 현재 시각 자동 설정
      - status가 DONE이 아닌 경우 completed_at=None → '' (빈 문자열, 미결정)
      - 명시적으로 전달하면 그 값 사용

    issue_id: 이슈 기반 요구사항일 경우 연결할 이슈 ID
    """
    if db_path is None:
        db_path = get_db_path()
    if completed_at is None:
        completed_at = _now() if status == "DONE" else ""
    with _get_db(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO requirements
               (number, title, applied_files, status, note, completed_at, issue_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (number, title, applied_files, status, note, completed_at, issue_id),
        )
        return cur.lastrowid


def update_requirement_status(
    number: int,
    new_status: str,
    note: str = "",
    applied_files: str = "",
    db_path: Optional[str] = None,
) -> bool:
    """요구사항 상태를 변경합니다 (PENDING→IN_PROGRESS→DONE 등).

    new_status가 'DONE'이면:
      - completed_at을 현재 시각으로 갱신
      - issue_id가 연결된 이슈가 있으면 동일 시그니처의 open 이슈 전부 resolved 처리
    """
    if db_path is None:
        db_path = get_db_path()
    completed_at = _now() if new_status == "DONE" else ""
    with _get_db(db_path) as conn:
        params = [new_status, completed_at]
        set_clauses = "status = ?, completed_at = ?"
        if note:
            set_clauses += ", note = ?"
            params.append(note)
        if applied_files:
            set_clauses += ", applied_files = ?"
            params.append(applied_files)
        params.append(number)
        cur = conn.execute(
            f"UPDATE requirements SET {set_clauses} WHERE number = ?",
            params,
        )
        ok = cur.rowcount > 0

    # DONE 전환 시 연결 이슈 자동 resolved
    if ok and new_status == "DONE":
        resolved = auto_resolve_issues(db_path=db_path)
        if resolved:
            print(f"  [이슈 자동 해결] {resolved}개 이슈 resolved 처리")

    return ok


def list_requirements(
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict]:
    """요구사항 목록을 반환합니다.

    status=None  → 전체
    status='DONE'       → 완료된 항목
    status='IN_PROGRESS' → 진행 중인 항목
    status='PENDING'    → 미구현/예정 항목
    """
    if db_path is None:
        db_path = get_db_path()
    where = "WHERE status = ?" if status else ""
    params = [status] if status else []
    with _get_db(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM requirements {where} ORDER BY number",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 이슈 ↔ 요구사항 자동화
# ─────────────────────────────────────────────

def _issue_sig(error_type: str, error_message: str) -> str:
    """중복 방지용 이슈 시그니처 (error_type + 메시지 앞 120자)."""
    return f"{error_type}::{error_message[:120]}"


def get_next_req_number(db_path: Optional[str] = None) -> int:
    """requirements 테이블의 현재 최대 number + 1을 반환합니다."""
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        row = conn.execute("SELECT MAX(number) FROM requirements").fetchone()
    return (row[0] or 0) + 1


def auto_create_from_issues(
    db_path: Optional[str] = None,
    severity_filter: Optional[List[str]] = None,
    dry_run: bool = False,
) -> List[Dict]:
    """open 이슈를 스캔해 아직 요구사항이 없는 그룹마다 PENDING 요구사항을 자동 생성합니다.

    중복 방지:
      - (error_type, error_message[:120]) 시그니처 기준으로 그룹핑
      - 그룹당 요구사항 1개 (이미 issue_id로 연결된 requirements가 있으면 스킵)

    severity_filter: 처리할 심각도 목록 (기본: ['error', 'warning', 'critical'])
    dry_run: True이면 실제 삽입 없이 생성 예정 목록만 반환

    반환: 새로 생성된(또는 생성 예정인) 요구사항 Dict 목록
    """
    if db_path is None:
        db_path = get_db_path()
    if severity_filter is None:
        severity_filter = ["error", "warning", "critical"]

    init_tables(db_path)

    with _get_db(db_path) as conn:
        # issues 테이블 존재 확인
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()
        if not exists:
            return []

        # open 이슈 중 해당 severity만 가져오기
        placeholders = ",".join("?" * len(severity_filter))
        open_issues = conn.execute(
            f"""SELECT id, error_type, error_message, source, created_at
                FROM issues
                WHERE status = 'open' AND severity IN ({placeholders})
                ORDER BY id""",
            severity_filter,
        ).fetchall()

        # 이미 issue_id로 연결된 요구사항의 issue_id 집합
        linked_ids = {
            r[0]
            for r in conn.execute(
                "SELECT issue_id FROM requirements WHERE issue_id IS NOT NULL"
            ).fetchall()
        }

        # 시그니처 → (대표 이슈 row) 그룹핑 (첫 번째 = 최소 id)
        groups: Dict[str, object] = {}
        sig_to_count: Dict[str, int] = {}
        for row in open_issues:
            sig = _issue_sig(row[1], row[2])
            sig_to_count[sig] = sig_to_count.get(sig, 0) + 1
            if sig not in groups:
                groups[sig] = row  # 최소 id (첫 등장)

        created: List[Dict] = []
        next_num = get_next_req_number(db_path)

        for sig, rep in groups.items():
            issue_id = rep[0]
            # 해당 그룹의 어떤 이슈도 이미 연결되어 있으면 스킵
            # (같은 시그니처 이슈 id 전체를 확인)
            same_sig_ids = {
                r[0]
                for r in conn.execute(
                    "SELECT id FROM issues WHERE status='open' AND error_type=? AND SUBSTR(error_message,1,120)=?",
                    (rep[1], rep[2][:120]),
                ).fetchall()
            }
            if same_sig_ids & linked_ids:
                continue  # 이미 요구사항 존재

            count = sig_to_count[sig]
            title = f"[버그수정] {rep[1]}: {rep[2][:60]}{'...' if len(rep[2]) > 60 else ''}"
            note = f"이슈 그룹 {count}건 | 대표 이슈 #{issue_id} | 소스: {rep[3] or '(없음)'}"

            entry = {
                "number": next_num,
                "title": title,
                "status": "PENDING",
                "note": note,
                "issue_id": issue_id,
                "issue_count": count,
            }
            created.append(entry)

            if not dry_run:
                conn.execute(
                    """INSERT INTO requirements
                       (number, title, applied_files, status, note, completed_at, issue_id)
                       VALUES (?, ?, '', 'PENDING', ?, '', ?)""",
                    (next_num, title, note, issue_id),
                )
                linked_ids.add(issue_id)

            next_num += 1

    return created


def auto_resolve_issues(db_path: Optional[str] = None) -> int:
    """DONE 처리된 이슈 기반 요구사항의 연결 이슈를 모두 resolved 처리합니다.

    동작:
      1. requirements에서 status='DONE' AND issue_id IS NOT NULL인 항목 조회
      2. 각 항목의 issue_id로 이슈의 (error_type, error_message[:120]) 시그니처 확인
      3. 같은 시그니처의 open 이슈를 모두 resolved 처리

    반환: resolved된 이슈 수
    """
    if db_path is None:
        db_path = get_db_path()

    with _get_db(db_path) as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()
        if not exists:
            return 0

        # DONE 처리된 이슈 기반 요구사항 조회
        done_reqs = conn.execute(
            """SELECT r.issue_id, i.error_type, i.error_message
               FROM requirements r
               JOIN issues i ON i.id = r.issue_id
               WHERE r.status = 'DONE' AND r.issue_id IS NOT NULL""",
        ).fetchall()

        if not done_reqs:
            return 0

        resolved_count = 0
        now = _now()
        for issue_id, error_type, error_message in done_reqs:
            # 같은 시그니처의 open 이슈 전부 resolved 처리
            cur = conn.execute(
                """UPDATE issues
                   SET status = 'resolved',
                       resolved_at = ?,
                       resolution_note = '요구사항 DONE 처리로 자동 해결'
                   WHERE status = 'open'
                     AND error_type = ?
                     AND SUBSTR(error_message, 1, 120) = ?""",
                (now, error_type, error_message[:120]),
            )
            resolved_count += cur.rowcount

    return resolved_count


def sync_issues(
    db_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict:
    """이슈 → 요구사항 동기화를 실행합니다 (create + resolve).

    반환: {"created": [...], "resolved": int}
    """
    if db_path is None:
        db_path = get_db_path()
    created = auto_create_from_issues(db_path=db_path, dry_run=dry_run)
    resolved = 0 if dry_run else auto_resolve_issues(db_path=db_path)
    return {"created": created, "resolved": resolved}


def get_issue_detail(issue_id: int, db_path: Optional[str] = None) -> Optional[Dict]:
    """단일 이슈의 전체 상세 정보를 반환합니다 (traceback, context 포함)."""
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()
        if not exists:
            return None
        row = conn.execute(
            """SELECT id, title, error_type, error_message, traceback,
                      context, source, severity, status,
                      created_at, resolved_at, resolution_note
               FROM issues WHERE id = ?""",
            (issue_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def list_bug_requirements(db_path: Optional[str] = None) -> List[Dict]:
    """이슈 기반(issue_id 있는) 요구사항 중 미완료 항목을 이슈 상세 포함하여 반환합니다."""
    if db_path is None:
        db_path = get_db_path()
    init_tables(db_path)
    with _get_db(db_path) as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            """SELECT r.id, r.number, r.title, r.status, r.note, r.issue_id,
                      i.error_type, i.error_message, i.traceback,
                      i.context, i.source, i.severity,
                      (SELECT COUNT(*) FROM issues i2
                       WHERE i2.status = 'open'
                         AND i2.error_type = i.error_type
                         AND SUBSTR(i2.error_message,1,120) = SUBSTR(i.error_message,1,120)
                      ) AS open_count
               FROM requirements r
               JOIN issues i ON i.id = r.issue_id
               WHERE r.status IN ('PENDING', 'IN_PROGRESS')
               ORDER BY r.status DESC, r.number""",
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# change_log 테이블
# ─────────────────────────────────────────────

def add_change(
    date: str,
    description: str,
    changed_files: str = "",
    db_path: Optional[str] = None,
) -> int:
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO change_log (date, description, changed_files, created_at)
               VALUES (?, ?, ?, ?)""",
            (date, description, changed_files, _now()),
        )
        return cur.lastrowid


def list_changes(
    limit: int = 20,
    db_path: Optional[str] = None,
) -> List[Dict]:
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM change_log ORDER BY date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# deleted_files 테이블
# ─────────────────────────────────────────────

def add_deleted_file(
    module_name: str,
    level: str = "",
    note: str = "",
    deleted_at: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    if db_path is None:
        db_path = get_db_path()
    if deleted_at is None:
        deleted_at = _now()
    with _get_db(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO deleted_files (module_name, level, note, deleted_at)
               VALUES (?, ?, ?, ?)""",
            (module_name, level, note, deleted_at),
        )
        return cur.lastrowid


def list_deleted_files(db_path: Optional[str] = None) -> List[Dict]:
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM deleted_files ORDER BY id",
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# test_status 테이블
# ─────────────────────────────────────────────

def upsert_test_status(
    test_file: str,
    target_module: str = "",
    note: str = "",
    test_count: int = 0,
    db_path: Optional[str] = None,
) -> None:
    if db_path is None:
        db_path = get_db_path()
    now = _now()
    with _get_db(db_path) as conn:
        conn.execute(
            """INSERT INTO test_status (test_file, target_module, note, test_count, checked_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(test_file) DO UPDATE SET
                   target_module = excluded.target_module,
                   note          = excluded.note,
                   test_count    = excluded.test_count,
                   checked_at    = excluded.checked_at""",
            (test_file, target_module, note, test_count, now),
        )


def list_test_status(db_path: Optional[str] = None) -> List[Dict]:
    if db_path is None:
        db_path = get_db_path()
    with _get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM test_status ORDER BY test_file",
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 마이그레이션 (PROJECT_ANALYSIS.md → DB, 1회성)
# ─────────────────────────────────────────────

def _already_migrated(db_path: str) -> bool:
    """마이그레이션 완료 여부 확인 (requirements 테이블에 데이터 있으면 완료)."""
    with _get_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    return count > 0


def migrate_from_md(db_path: Optional[str] = None, force: bool = False) -> None:
    """PROJECT_ANALYSIS.md 5개 섹션 데이터를 DB로 마이그레이션합니다 (1회성)."""
    if db_path is None:
        db_path = get_db_path()

    init_tables(db_path)

    if not force and _already_migrated(db_path):
        print("이미 마이그레이션 완료. --force 옵션으로 재실행 가능.")
        return

    # ── 섹션 0.1: 완료된 요구사항 (37~43번) ──────────────────────────
    requirements_data = [
        (37, "Ollama LLM 프로바이더 추가",
         "test_ollama_client.py(신규), test_model_manager.py, main.py",
         "DONE",
         "5개 함수 테스트(18개), model_manager ollama fixture 추가(3개), model set 도움말 수정, 전체 246개 통과",
         "2026-02-26"),
        (38, "보안 취약점 4건(심각도 상) 수정",
         "mcp_db_manager.py, config.py, api.py, test_mcp_db_manager.py, test_config.py(신규), test_api.py",
         "DONE",
         "exec() 구문검증, MCP command 화이트리스트, 요구사항 파일 경로검증+1MB제한, tool 인자 서명검증; 전체 271개 통과",
         "2026-02-26"),
        (39, "보안 취약점 6건(심각도 중) 수정",
         "constants.py(신규), models.py, api.py, mcp_db_manager.py, gemini/claude/ollama_client.py, test_models.py(신규), test_api.py, test_mcp_db_manager.py",
         "DONE",
         "필드 길이/개수 검증, 히스토리 200개 제한, HISTORY_MAX_CHARS 중앙화, func_names 1000개 제한, 잘림 경고 로그, 쿼리 추출 함수화; 전체 295개 통과",
         "2026-02-26"),
        (40, "보안 취약점 3건(심각도 하) 수정",
         "constants.py, graph_manager.py, agent_config_manager.py, mcp_db_manager.py, test_graph_manager.py, test_agent_config_manager.py",
         "DONE",
         "키워드 SQL 중복 제거(_fetch_keywords), UTC 타임스탬프 통일(utcnow()), sync_skills 로깅 추가; 전체 303개 통과",
         "2026-02-26"),
        (41, "PROJECT_ANALYSIS.md mcp_modules 불일치 수정",
         "PROJECT_ANALYSIS.md",
         "DONE",
         "섹션 2/4.1/4.5/5/6/8/10/11 갱신 — mcp_modules/ 빈 디렉토리 반영, 삭제된 파일 목록 이력 표시, 보안 설계 현행화, 테스트 수 303개 반영",
         "2026-02-26"),
        (42, "PROJECT_ANALYSIS.md 불일치 수정 + validate 자동검증 추가",
         "PROJECT_ANALYSIS.md, claude_tools/report_validator.py(신규), claude_tools/__main__.py",
         "DONE",
         "7개 범주 불일치 수정(섹션 1~7), 4개 누락 모듈 기술 추가(4.8~4.18), 테스트 수 303→324, pytest-asyncio 추가; report_validator.py(신규) + validate 명령 추가",
         "2026-02-26"),
        (43, "project02 개선 패턴 이식 (코드 품질 개선)",
         "constants.py, models.py, api.py, config.py, requirements.txt, pytest.ini, gemini_client.py, test_api.py, test_models.py, PROJECT_ANALYSIS.md",
         "DONE",
         "Final[int] 타입, 신규 상수 4개, GeminiToolCall→ToolCall(alias 하위호환), DB init lifespan, 앱 제목, config lazy accessor, asyncio_mode=auto; 324개 통과",
         "2026-02-27"),
    ]

    with _get_db(db_path) as conn:
        if force:
            conn.execute("DELETE FROM requirements")
        for number, title, applied_files, status, note, completed_at in requirements_data:
            conn.execute(
                """INSERT INTO requirements
                   (number, title, applied_files, status, note, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (number, title, applied_files, status, note, completed_at),
            )
    print(f"  requirements: {len(requirements_data)}개 삽입")

    # ── 섹션 0.4: 변경 이력 (7개) ────────────────────────────────────
    change_log_data = [
        ("2026-02-26",
         "Ollama 프로바이더 추가(#37): test_ollama_client.py(신규, 18개 테스트), test_model_manager.py(ollama fixture+3개 테스트), main.py(model set 도움말), 전체 246개 통과",
         "test_ollama_client.py(신규), test_model_manager.py, main.py"),
        ("2026-02-26",
         "보안 취약점 4건 수정(#38): exec() ast 구문검증, MCP command 화이트리스트, 요구사항 파일 경로검증+1MB, tool 인자 서명검증; test_config.py(신규), 전체 271개 통과",
         "mcp_db_manager.py, config.py, api.py, test_config.py(신규), test_mcp_db_manager.py, test_api.py"),
        ("2026-02-26",
         "보안 취약점 6건 수정(#39): 필드 길이검증(models.py), 히스토리 200개 제한+_prune_history, HISTORY_MAX_CHARS 중앙화(constants.py), func_names 1000개 제한, 잘림 경고 로그, _extract_first_query 함수화; test_models.py(신규), 전체 295개 통과",
         "constants.py(신규), models.py, api.py, mcp_db_manager.py, gemini/claude/ollama_client.py, test_models.py(신규), test_api.py, test_mcp_db_manager.py"),
        ("2026-02-26",
         "보안 취약점 3건 수정(#40): _fetch_keywords() 헬퍼(SQL중복제거), utcnow() UTC통일(3개 파일), sync_skills 로깅 추가(added/updated/total); 전체 303개 통과",
         "constants.py, graph_manager.py, agent_config_manager.py, mcp_db_manager.py, test_graph_manager.py, test_agent_config_manager.py"),
        ("2026-02-26",
         "PROJECT_ANALYSIS.md mcp_modules 불일치 수정(#41): 섹션 2/4.1/4.5/5/6/8/10/11 현행화, 삭제된 10개 파일 이력 표시, 보안 설계 현행화, 테스트 수 226→303 갱신",
         "PROJECT_ANALYSIS.md"),
        ("2026-02-26",
         "PROJECT_ANALYSIS.md 불일치 수정+validate 추가(#42): 섹션 1(LLM 백엔드), 섹션 2(디렉토리+orchestrator 파일), 섹션 3(llm_client 라우팅), 섹션 4.3(히스토리 예산 기반), 4.4(web_router), 4.6(어댑터 구조), 4.8~4.18(누락 모듈 11개), 섹션 6(테스트 303→324, 파일 4개 추가), 섹션 7(pytest-asyncio); report_validator.py(신규) + validate 명령",
         "PROJECT_ANALYSIS.md, claude_tools/report_validator.py(신규), claude_tools/__main__.py"),
        ("2026-02-27",
         "project02 개선 패턴 이식(#43): Final[int] 타입+4개 신규 상수(MAX_TOOL_RESULT_LENGTH 등), GeminiToolCall→ToolCall rename+alias, lifespan DB init 3개, 앱 제목, import json 모듈레벨, Optional[str], config lazy accessor, asyncio_mode=auto, requirements.txt 재구성(6개 패키지 추가)",
         "constants.py, models.py, api.py, config.py, requirements.txt, pytest.ini, gemini_client.py, test_api.py, test_models.py, PROJECT_ANALYSIS.md"),
    ]

    with _get_db(db_path) as conn:
        if force:
            conn.execute("DELETE FROM change_log")
        for date, description, changed_files in change_log_data:
            conn.execute(
                """INSERT INTO change_log (date, description, changed_files, created_at)
                   VALUES (?, ?, ?, ?)""",
                (date, description, changed_files, _now()),
            )
    print(f"  change_log: {len(change_log_data)}개 삽입")

    # ── 섹션 5.1: 삭제된 파일 이력 (10개) ───────────────────────────
    deleted_files_data = [
        ("code_execution_atomic.py", "Atomic", "DB mcp_functions 테이블로 이전"),
        ("code_execution_composite.py", "Composite", "동일"),
        ("user_interaction_atomic.py", "Atomic", "동일"),
        ("user_interaction_composite.py", "Composite", "동일"),
        ("file_management.py", "Atomic", "동일 (이전에 YAML 스펙만 존재하다가 #29에서 구현됨)"),
        ("file_content_operations.py", "Atomic", "동일"),
        ("file_attributes.py", "Atomic", "동일"),
        ("file_system_composite.py", "Composite", "동일"),
        ("git_version_control.py", "Composite", "동일"),
        ("web_network_atomic.py", "Atomic", "동일"),
    ]

    deleted_at = "2026-02-25T00:00:00"  # #34 작업일
    with _get_db(db_path) as conn:
        if force:
            conn.execute("DELETE FROM deleted_files")
        for module_name, level, note in deleted_files_data:
            conn.execute(
                """INSERT INTO deleted_files (module_name, level, note, deleted_at)
                   VALUES (?, ?, ?, ?)""",
                (module_name, level, note, deleted_at),
            )
    print(f"  deleted_files: {len(deleted_files_data)}개 삽입")

    # ── 섹션 6: 테스트 현황 (15개) ───────────────────────────────────
    test_status_data = [
        ("test_api.py", "api.py",
         "FastAPI 엔드포인트, 경로 검증, 인자 검증, 히스토리 정리, 결과 잘림 경고"),
        ("test_config.py", "config.py",
         "MCP 서버 command 화이트리스트 검증"),
        ("test_gemini_client.py", "gemini_client.py",
         "실행 계획/최종 답변/키워드/주제 분리/제목 생성"),
        ("test_graph_manager.py", "graph_manager.py",
         "대화/그룹/토픽/키워드 CRUD, UTC 타임스탬프"),
        ("test_agent_config_manager.py", "agent_config_manager.py",
         "시스템 프롬프트/스킬/매크로/워크플로우/페르소나 CRUD, 스킬 동기화 로깅"),
        ("test_mcp_db_manager.py", "mcp_db_manager.py",
         "함수 등록/버전/테스트/세션/사용 통계, 구문 검증, func_names 한도"),
        ("test_mcp_manager.py", "mcp_manager.py",
         "MCP 서버 레지스트리 CRUD, 활성화/비활성화"),
        ("test_model_manager.py", "model_manager.py",
         "설정 I/O, 프로바이더 목록, 모델 fetch (Gemini/Claude/OpenAI/Grok/Ollama)"),
        ("test_models.py", "models.py",
         "Pydantic 필드 길이·개수 검증"),
        ("test_ollama_client.py", "ollama_client.py",
         "실행 계획/최종 답변/키워드/주제 분리/제목 생성"),
        ("test_issue_tracker.py", "issue_tracker.py",
         "이슈 캡처/조회/상태 변경"),
        ("test_test_registry.py", "test_registry.py",
         "테스트 파일 DB 저장/실행"),
        ("test_registry.py", "test_registry.py",
         "테스트 파일 스캔/파싱 기능"),
        ("test_tool_registry.py", "tool_registry.py",
         "로컬/MCP 도구 로드 및 조회"),
        ("test_web_router.py", "web_router.py",
         "/api/v1 엔드포인트"),
    ]

    checked_at = "2026-02-26T00:00:00"
    with _get_db(db_path) as conn:
        if force:
            conn.execute("DELETE FROM test_status")
        for test_file, target_module, note in test_status_data:
            conn.execute(
                """INSERT INTO test_status (test_file, target_module, note, test_count, checked_at)
                   VALUES (?, ?, ?, 0, ?)
                   ON CONFLICT(test_file) DO UPDATE SET
                       target_module = excluded.target_module,
                       note = excluded.note,
                       checked_at = excluded.checked_at""",
                (test_file, target_module, note, checked_at),
            )
    print(f"  test_status: {len(test_status_data)}개 삽입")

    # ── 섹션 10: 알려진 이슈 (2개) — issue_tracker.capture() 사용 ───
    # issue_tracker는 orchestrator 패키지 소속이므로 직접 sqlite3 사용
    issues_data = [
        ("스펙만 존재하는 모듈 6개 Python 구현체 없음",
         "KnownIssue",
         "스펙만 존재하는 모듈 6개 Python 구현체 없음",
         "", "PROJECT_ANALYSIS.md", "info",
         "resolved", "2026-02-18T00:00:00",
         "#29: 6개 모듈 Python 구현 완료"),
        ("mcp_modules/ 내 Python 파일 전체 삭제됨 (DB 마이그레이션 #34)",
         "KnownIssue",
         "mcp_modules/ 내 Python 파일 전체 삭제됨 (DB 마이그레이션 #34)",
         "", "PROJECT_ANALYSIS.md", "info",
         "resolved", "2026-02-25T00:00:00",
         "tool_registry.py는 DB 우선 로드, 파일 폴백 실패 시 ERROR 로그 (정상 동작). DB에 함수 등록 필요"),
    ]

    inserted_issues = 0
    with _get_db(db_path) as conn:
        # issues 테이블 존재 여부 확인
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()
        if exists:
            if force:
                conn.execute("DELETE FROM issues WHERE source='PROJECT_ANALYSIS.md'")
            for (title, error_type, error_message, traceback,
                 source, severity, status, resolved_at, resolution_note) in issues_data:
                created_at = "2026-02-26T00:00:00"
                conn.execute(
                    """INSERT INTO issues
                       (title, error_type, error_message, traceback, context,
                        source, severity, status, created_at, resolved_at, resolution_note)
                       VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)""",
                    (title, error_type, error_message, traceback,
                     source, severity, status, created_at, resolved_at, resolution_note),
                )
                inserted_issues += 1
        else:
            print("  issues 테이블 없음 (issue_tracker 초기화 필요). 이슈 삽입 건너뜀.")

    if inserted_issues:
        print(f"  issues: {inserted_issues}개 삽입")

    print("\n마이그레이션 완료.")
