#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_registry.py
"""orchestrator 테스트 파일 DB 저장 및 실행 모듈."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .graph_manager import DB_PATH, get_db

_BASE_DIR = Path(__file__).parent.parent


# ── DB 초기화 ──────────────────────────────────────────────────────

def init_db(path=DB_PATH) -> None:
    """orchestrator_tests 테이블을 생성합니다."""
    with get_db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orchestrator_tests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL UNIQUE,
                file_path    TEXT    NOT NULL DEFAULT '',
                code         TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'untested',
                last_output  TEXT    NOT NULL DEFAULT '',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            );
        """)


init_db()


# ── 핵심 함수 ──────────────────────────────────────────────────────

def import_test_file(file_path, db_path=DB_PATH) -> Dict:
    """파일을 읽어 DB에 upsert합니다."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    name = p.stem
    code = p.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM orchestrator_tests WHERE name = ?", (name,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE orchestrator_tests SET code = ?, file_path = ?, updated_at = ? WHERE name = ?",
                (code, str(p), now, name),
            )
            created = False
        else:
            conn.execute(
                "INSERT INTO orchestrator_tests (name, file_path, code, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, str(p), code, now, now),
            )
            created = True

    return {"name": name, "file_path": str(p), "created": created}


def import_all(directory=None, db_path=DB_PATH) -> List[Dict]:
    """orchestrator/ 디렉토리의 test_*.py 파일을 모두 임포트합니다."""
    base = Path(directory) if directory else Path(__file__).parent
    results = []
    for fp in sorted(base.glob("test_*.py")):
        if fp.name == "test_test_registry.py":
            continue
        try:
            result = import_test_file(fp, db_path=db_path)
            results.append(result)
        except Exception as e:
            results.append({"name": fp.stem, "file_path": str(fp), "error": str(e)})
    return results


def list_tests(db_path=DB_PATH) -> List[Dict]:
    """저장된 테스트 목록을 반환합니다."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, file_path, code, status, last_output, created_at, updated_at "
            "FROM orchestrator_tests ORDER BY name ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_test(name, db_path=DB_PATH) -> Optional[Dict]:
    """이름으로 테스트를 조회합니다."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, file_path, code, status, last_output, created_at, updated_at "
            "FROM orchestrator_tests WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def run_test(name, db_path=DB_PATH) -> Dict:
    """DB에서 코드를 꺼내 임시 파일로 pytest를 실행합니다."""
    test = get_test(name, db_path=db_path)
    if not test:
        return {"error": "not found"}

    tmp_file = _BASE_DIR / f"_test_tmp_{name}.py"
    try:
        tmp_file.write_text(test["code"], encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(tmp_file), "--tb=short", "-v"],
            capture_output=True,
            text=True,
            cwd=str(_BASE_DIR),
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        status = "passed" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        output = "테스트 타임아웃 (120초)"
        status = "failed"
    except Exception as e:
        output = str(e)
        status = "failed"
    finally:
        if tmp_file.exists():
            tmp_file.unlink()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE orchestrator_tests SET status = ?, last_output = ?, updated_at = ? WHERE name = ?",
            (status, output, now, name),
        )

    return {"name": name, "status": status, "output": output}


def run_all(db_path=DB_PATH) -> List[Dict]:
    """저장된 모든 테스트를 순차 실행합니다."""
    tests = list_tests(db_path=db_path)
    return [run_test(t["name"], db_path=db_path) for t in tests]
