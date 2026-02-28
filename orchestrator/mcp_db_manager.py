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


# ── 등록/활성화 ───────────────────────────────────────────────────

def register_function(
    func_name: str,
    module_group: str,
    code: str,
    test_code: str = "",
    description: str = "",
    source_type: str = "internal",
    source_url: str = "",
    source_author: str = "",
    source_license: str = "",
    source_desc: str = "",
    run_tests: bool = True,
    db_path=DB_PATH,
) -> Dict:
    """함수를 DB에 새 버전으로 등록합니다.

    테스트 코드가 있으면 자동 실행 후 통과 시 활성화합니다.
    테스트 코드가 없으면 즉시 활성화합니다.
    """
    now = utcnow()
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(version) FROM mcp_functions WHERE func_name = ?",
            (func_name,),
        ).fetchone()
        new_version = (row[0] or 0) + 1

        conn.execute(
            """INSERT INTO mcp_functions
               (func_name, module_group, version, is_active, code, test_code,
                test_status, description, source_type, source_url, source_author,
                source_license, source_desc, created_at)
               VALUES (?, ?, ?, 0, ?, ?, 'untested', ?, ?, ?, ?, ?, ?, ?)""",
            (
                func_name, module_group, new_version, code, test_code,
                description, source_type, source_url, source_author,
                source_license, source_desc, now,
            ),
        )

    result: Dict = {"func_name": func_name, "version": new_version, "test_status": "untested"}

    if run_tests and test_code.strip():
        test_result = run_function_tests(func_name, new_version, db_path)
        result["test_status"] = test_result["test_status"]
        result["test_output"] = test_result.get("test_output", "")
        if test_result["test_status"] == "passed":
            _activate_function(func_name, new_version, db_path)
            result["activated"] = True
        else:
            result["activated"] = False
    else:
        # 테스트 코드 없음 → 즉시 활성화
        _activate_function(func_name, new_version, db_path)
        result["activated"] = True

    return result


def _activate_function(func_name: str, version: int, db_path=DB_PATH) -> None:
    """특정 버전을 활성화합니다 (동일 func_name의 기존 active는 모두 비활성화)."""
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE mcp_functions SET is_active = 0 WHERE func_name = ?",
            (func_name,),
        )
        conn.execute(
            "UPDATE mcp_functions SET is_active = 1, activated_at = ? "
            "WHERE func_name = ? AND version = ?",
            (now, func_name, version),
        )
    _invalidate_cache_for_function(func_name, db_path)


def _invalidate_cache_for_function(func_name: str, db_path=DB_PATH) -> None:
    """함수가 속한 모듈 그룹의 캐시 파일을 삭제합니다."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT module_group FROM mcp_functions WHERE func_name = ? AND is_active = 1",
            (func_name,),
        ).fetchone()
    if row:
        cache_file = MCP_CACHE_DIR / f"{row[0]}.py"
        if cache_file.exists():
            cache_file.unlink()


# ── 테스트 실행 ───────────────────────────────────────────────────

def run_function_tests(func_name: str, version: int, db_path=DB_PATH) -> Dict:
    """pytest를 subprocess로 실행하여 함수 테스트를 수행합니다."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT f.code, f.test_code, f.module_group, c.preamble_code "
            "FROM mcp_functions f "
            "LEFT JOIN mcp_module_contexts c ON f.module_group = c.module_group "
            "WHERE f.func_name = ? AND f.version = ?",
            (func_name, version),
        ).fetchone()

    if not row:
        return {"test_status": "failed", "test_output": "함수를 찾을 수 없습니다."}

    func_code, test_code, module_group, preamble = (
        row[0], row[1], row[2], row[3] or ""
    )

    if not test_code.strip():
        return {"test_status": "untested", "test_output": "테스트 코드가 없습니다."}

    MCP_CACHE_DIR.mkdir(exist_ok=True)
    test_file = MCP_CACHE_DIR / f"_test_{func_name}_v{version}.py"
    try:
        test_content = f"{preamble}\n\n{func_code}\n\n{test_code}\n"
        test_file.write_text(test_content, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=str(_BASE_DIR),
            timeout=60,
        )
        test_output = proc.stdout + proc.stderr
        test_status = "passed" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        test_output = "테스트 타임아웃 (60초)"
        test_status = "failed"
    except Exception as e:
        test_output = str(e)
        test_status = "failed"
    finally:
        if test_file.exists():
            test_file.unlink()

    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE mcp_functions SET test_status = ?, test_output = ? "
            "WHERE func_name = ? AND version = ?",
            (test_status, test_output, func_name, version),
        )

    return {"test_status": test_status, "test_output": test_output}


# ── 캐시 파일 생성 ────────────────────────────────────────────────

def generate_temp_module(module_group: str, db_path=DB_PATH) -> Path:
    """활성 함수들을 조합하여 mcp_cache/{module_group}.py 를 생성합니다."""
    MCP_CACHE_DIR.mkdir(exist_ok=True)
    cache_file = MCP_CACHE_DIR / f"{module_group}.py"

    with get_db(db_path) as conn:
        ctx_row = conn.execute(
            "SELECT preamble_code FROM mcp_module_contexts WHERE module_group = ?",
            (module_group,),
        ).fetchone()
        preamble = ctx_row[0] if ctx_row else ""

        funcs = conn.execute(
            "SELECT func_name, code FROM mcp_functions "
            "WHERE module_group = ? AND is_active = 1 "
            "ORDER BY func_name",
            (module_group,),
        ).fetchall()

    lines = [
        "# Auto-generated by mcp_db_manager — DO NOT EDIT",
        f"# module_group: {module_group}",
        f"# generated_at: {datetime.now().isoformat()}",
        "",
    ]
    if preamble:
        lines.append(preamble)
        lines.append("")
    for row in funcs:
        lines.append(row[1])
        lines.append("")

    cache_file.write_text("\n".join(lines), encoding="utf-8")
    return cache_file


# ── 인메모리 로드 ─────────────────────────────────────────────────

def _validate_code_syntax(code: str, label: str = "") -> None:
    """코드 구문 유효성 검사. SyntaxError 발생 시 ValueError를 발생시킵니다."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        suffix = f" ({label})" if label else ""
        raise ValueError(f"코드 구문 오류{suffix}: {e}") from e


def load_module_in_memory(module_group: str, db_path=DB_PATH) -> dict:
    """DB 활성 함수들을 exec()으로 메모리에 로드. {func_name: callable} 반환."""
    with get_db(db_path) as conn:
        ctx_row = conn.execute(
            "SELECT preamble_code FROM mcp_module_contexts WHERE module_group = ?",
            (module_group,),
        ).fetchone()
        preamble = ctx_row[0] if ctx_row else ""
        funcs = conn.execute(
            "SELECT func_name, code FROM mcp_functions "
            "WHERE module_group = ? AND is_active = 1 ORDER BY func_name",
            (module_group,),
        ).fetchall()

    if not funcs:
        return {}

    parts = []
    if preamble:
        _validate_code_syntax(preamble, "preamble")
        parts.append(preamble)
    for func_name, code in funcs:
        _validate_code_syntax(code, func_name)
        parts.append(code)

    namespace: dict = {}
    exec("\n\n".join(parts), namespace)  # noqa: S102

    target_names = {row[0] for row in funcs}
    return {k: v for k, v in namespace.items()
            if callable(v) and k in target_names}


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


# ── 마이그레이션 ──────────────────────────────────────────────────

def import_from_file(
    file_path: str,
    module_group: Optional[str] = None,
    test_file_path: Optional[str] = None,
    run_tests: bool = True,
    db_path=DB_PATH,
) -> Dict:
    """기존 Python 파일에서 공개 함수를 DB로 임포트합니다."""
    fp = Path(file_path)
    if not fp.exists():
        return {"imported_functions": 0, "failed": [f"파일 없음: {file_path}"]}

    if module_group is None:
        module_group = fp.stem

    source = fp.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"imported_functions": 0, "failed": [f"SyntaxError: {e}"]}

    preamble = _extract_preamble(source, tree)
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO mcp_module_contexts
               (module_group, preamble_code, created_at, updated_at)
               VALUES (?, ?,
                 COALESCE((SELECT created_at FROM mcp_module_contexts WHERE module_group = ?), ?),
                 ?)""",
            (module_group, preamble, module_group, now, now),
        )

    test_map: Dict[str, str] = {}
    if test_file_path:
        tf = Path(test_file_path)
        if tf.exists():
            test_source = tf.read_text(encoding="utf-8")
            test_map = _extract_test_map(test_source)

    source_lines = source.splitlines()
    imported = 0
    failed: List[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.col_offset != 0:
            continue
        if node.name.startswith("_"):
            continue

        start = node.lineno - 1
        end = node.end_lineno
        func_code = "\n".join(source_lines[start:end])
        description = ast.get_docstring(node) or ""
        test_code = test_map.get(node.name, "")

        try:
            result = register_function(
                func_name=node.name,
                module_group=module_group,
                code=func_code,
                test_code=test_code,
                description=description,
                run_tests=run_tests and bool(test_code),
                db_path=db_path,
            )
            imported += 1
            logging.info(f"Imported function: {node.name} (v{result['version']})")
        except Exception as e:
            failed.append(f"{node.name}: {e}")
            logging.error(f"Failed to import {node.name}: {e}")

    return {"imported_functions": imported, "failed": failed}


def _extract_preamble(source: str, tree: ast.Module) -> str:
    """공개 함수 블록을 제외한 모듈 레벨 코드(imports, 상수 등)를 반환합니다."""
    source_lines = source.splitlines()
    func_ranges: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0 and not node.name.startswith("_"):
                for i in range(node.lineno - 1, node.end_lineno):
                    func_ranges.add(i)
    preamble_lines = [
        line for i, line in enumerate(source_lines)
        if i not in func_ranges
    ]
    return "\n".join(preamble_lines).strip()


def _extract_test_map(test_source: str) -> Dict[str, str]:
    """테스트 파일에서 TestXxx 클래스를 파싱해 func_name → test_code 매핑을 반환합니다."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return {}

    test_lines = test_source.splitlines()

    # @pytest.fixture 함수 수집
    fixtures: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.col_offset == 0:
            for deco in node.decorator_list:
                try:
                    deco_str = ast.unparse(deco)
                except AttributeError:
                    deco_str = ""
                if "fixture" in deco_str:
                    # decorator 라인부터 포함 (node.lineno는 def 키워드 라인)
                    start = (node.decorator_list[0].lineno - 1) if node.decorator_list else (node.lineno - 1)
                    end = node.end_lineno
                    fixtures.append("\n".join(test_lines[start:end]))
                    break
    fixture_code = "\n\n".join(fixtures)

    result: Dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not node.name.startswith("Test"):
            continue

        # CamelCase → snake_case (TestCreateDirectory → create_directory)
        class_body = node.name[4:]  # "Test" 제거
        func_name = re.sub(r"(?<!^)(?=[A-Z])", "_", class_body).lower()

        start = node.lineno - 1
        end = node.end_lineno
        class_code = "\n".join(test_lines[start:end])
        result[func_name] = f"{fixture_code}\n\n{class_code}" if fixture_code else class_code

    return result


# ── 테스트 코드 업데이트 / 수동 활성화 ──────────────────────────────

def update_function_test_code(
    func_name: str,
    test_code: str,
    version: Optional[int] = None,
    run_tests: bool = True,
    db_path=DB_PATH,
) -> Dict:
    """기존 버전의 test_code를 업데이트하고 선택적으로 테스트를 실행합니다.

    새 버전을 생성하지 않고 기존 버전의 테스트 코드만 교체합니다.
    run_tests=True 이고 테스트 통과 시 해당 버전을 활성화합니다.
    """
    with get_db(db_path) as conn:
        if version is None:
            row = conn.execute(
                "SELECT version FROM mcp_functions WHERE func_name = ? AND is_active = 1",
                (func_name,),
            ).fetchone()
            if not row:
                return {"error": f"활성 버전을 찾을 수 없습니다: {func_name}"}
            version = row[0]
        else:
            row = conn.execute(
                "SELECT version FROM mcp_functions WHERE func_name = ? AND version = ?",
                (func_name, version),
            ).fetchone()
            if not row:
                return {"error": f"버전 {version}을 찾을 수 없습니다: {func_name}"}

        conn.execute(
            "UPDATE mcp_functions SET test_code = ?, test_status = 'untested' "
            "WHERE func_name = ? AND version = ?",
            (test_code, func_name, version),
        )

    result: Dict = {"func_name": func_name, "version": version}
    if run_tests:
        test_result = run_function_tests(func_name, version, db_path)
        result.update(test_result)
        if test_result["test_status"] == "passed":
            _activate_function(func_name, version, db_path)
            result["activated"] = True
        else:
            result["activated"] = False
    return result


def activate_function(func_name: str, version: int, db_path=DB_PATH) -> None:
    """특정 버전을 수동으로 활성화합니다."""
    versions = get_function_versions(func_name, db_path)
    if not any(v["version"] == version for v in versions):
        raise ValueError(f"'{func_name}' v{version}을 찾을 수 없습니다.")
    _activate_function(func_name, version, db_path)


# ── 모듈 컨텍스트 직접 설정 ───────────────────────────────────────

def set_module_preamble(
    module_group: str,
    preamble_code: str,
    description: str = "",
    db_path=DB_PATH,
) -> None:
    """모듈 그룹의 preamble 코드를 직접 설정합니다."""
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO mcp_module_contexts
               (module_group, preamble_code, description, created_at, updated_at)
               VALUES (?, ?, ?,
                 COALESCE((SELECT created_at FROM mcp_module_contexts WHERE module_group = ?), ?),
                 ?)""",
            (module_group, preamble_code, description, module_group, now, now),
        )
    cache_file = MCP_CACHE_DIR / f"{module_group}.py"
    if cache_file.exists():
        cache_file.unlink()
