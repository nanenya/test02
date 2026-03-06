#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_mcp_code_ops.py — MCP 함수 코드 등록/테스트/캐시/마이그레이션
"""MCP 함수 코드 등록, 실행 테스트, 캐시 모듈 생성, 파일 마이그레이션."""

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
from .constants import utcnow
from . import config as _config

_BASE_DIR = Path(__file__).parent.parent
MCP_CACHE_DIR = _BASE_DIR / "mcp_cache"

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

    if test_code.strip():
        _run_and_activate(func_name, new_version, run_tests, result, db_path)
    else:
        _activate_function(func_name, new_version, db_path)
        result["activated"] = True

    return result


def add_function(
    func_name: str,
    module_group: str,
    code: str,
    description: str = "",
    source_type: str = "auto_generated",
    source_desc: str = "",
    db_path=DB_PATH,
) -> int:
    """함수를 즉시 활성화하여 DB에 등록하고 row ID를 반환합니다.

    test_code 없이 register_function(run_tests=False)을 호출하므로
    is_active=1로 즉시 활성화됩니다.
    """
    register_function(
        func_name=func_name,
        module_group=module_group,
        code=code,
        test_code="",
        description=description,
        source_type=source_type,
        source_desc=source_desc,
        run_tests=False,
        db_path=db_path,
    )
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM mcp_functions WHERE func_name = ? AND is_active = 1",
            (func_name,),
        ).fetchone()
    if not row:
        raise RuntimeError(f"add_function: 활성화된 행을 찾을 수 없습니다: {func_name}")
    return row[0]


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


def _run_and_activate(
    func_name: str, version: int, run_tests: bool, result: dict, db_path
) -> None:
    """테스트 실행 후 합격 시 활성화. result dict 인플레이스 업데이트."""
    if not run_tests:
        _activate_function(func_name, version, db_path)
        result["activated"] = True
        return
    test_result = run_function_tests(func_name, version, db_path)
    result["test_status"] = test_result["test_status"]
    result["test_output"] = test_result.get("test_output", "")
    if test_result["test_status"] == "passed":
        _activate_function(func_name, version, db_path)
        result["activated"] = True
    else:
        result["activated"] = False


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

    # __file__을 주입하여 preamble에서 Path(__file__).parent 등 경로 계산이 가능하게 함
    namespace: dict = {
        "__file__": str(_BASE_DIR / _config.MCP_DIRECTORY / f"{module_group}.py"),
        "__name__": module_group,
    }
    exec("\n\n".join(parts), namespace)  # noqa: S102

    target_names = {row[0] for row in funcs}
    return {k: v for k, v in namespace.items()
            if callable(v) and k in target_names}



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
    _run_and_activate(func_name, version, run_tests, result, db_path)
    return result


def activate_function(func_name: str, version: int, db_path=DB_PATH) -> None:
    """특정 버전을 수동으로 활성화합니다."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM mcp_functions WHERE func_name=? AND version=?",
            (func_name, version),
        ).fetchone()
    if not row:
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
