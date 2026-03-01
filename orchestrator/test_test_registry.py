#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_test_registry.py

import sqlite3
from pathlib import Path

import pytest

from orchestrator.test_registry import (
    get_test,
    import_all,
    import_test_file,
    init_db,
    list_tests,
    run_test,
)


@pytest.fixture
def db(tmp_path):
    """각 테스트마다 격리된 임시 DB."""
    db_path = tmp_path / "test_registry.db"
    init_db(db_path)
    return db_path


# ── TestInitDb ────────────────────────────────────────────────────

class TestInitDb:
    def test_table_exists(self, db):
        conn = sqlite3.connect(str(db))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "orchestrator_tests" in tables

    def test_idempotent(self, db):
        """두 번 호출해도 오류 없이 동일 테이블."""
        init_db(db)
        conn = sqlite3.connect(str(db))
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='orchestrator_tests'"
        ).fetchone()[0]
        conn.close()
        assert count == 1


# ── TestImportTestFile ────────────────────────────────────────────

class TestImportTestFile:
    def test_new_import(self, db, tmp_path):
        """신규 파일 임포트 시 created=True."""
        f = tmp_path / "test_sample.py"
        f.write_text("def test_pass(): pass\n", encoding="utf-8")
        result = import_test_file(f, db_path=db)
        assert result["name"] == "test_sample"
        assert result["created"] is True

    def test_reimport_updates(self, db, tmp_path):
        """재임포트 시 created=False, 코드가 갱신됨."""
        f = tmp_path / "test_sample.py"
        f.write_text("def test_pass(): pass\n", encoding="utf-8")
        import_test_file(f, db_path=db)

        f.write_text("def test_pass(): assert 1 == 1\n", encoding="utf-8")
        result = import_test_file(f, db_path=db)
        assert result["created"] is False

        test = get_test("test_sample", db_path=db)
        assert "assert 1 == 1" in test["code"]

    def test_missing_file_raises(self, db, tmp_path):
        """존재하지 않는 파일은 FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            import_test_file(tmp_path / "test_nonexistent.py", db_path=db)


# ── TestImportAll ─────────────────────────────────────────────────

class TestImportAll:
    def test_import_multiple_files(self, db, tmp_path):
        """test_*.py 파일 2개가 있으면 2개 임포트."""
        (tmp_path / "test_alpha.py").write_text("def test_a(): pass\n", encoding="utf-8")
        (tmp_path / "test_beta.py").write_text("def test_b(): pass\n", encoding="utf-8")
        results = import_all(directory=tmp_path, db_path=db)
        assert len(results) == 2

    def test_import_all_result_names(self, db, tmp_path):
        """임포트된 이름이 파일 stem과 일치."""
        (tmp_path / "test_foo.py").write_text("def test_foo(): pass\n", encoding="utf-8")
        results = import_all(directory=tmp_path, db_path=db)
        names = [r["name"] for r in results]
        assert "test_foo" in names


# ── TestListTests ─────────────────────────────────────────────────

class TestListTests:
    def test_empty_list(self, db):
        """임포트 전에는 빈 목록."""
        tests = list_tests(db_path=db)
        assert tests == []

    def test_list_after_import(self, db, tmp_path):
        """임포트 후 목록에 포함됨."""
        f = tmp_path / "test_xyz.py"
        f.write_text("def test_x(): pass\n", encoding="utf-8")
        import_test_file(f, db_path=db)
        tests = list_tests(db_path=db)
        assert len(tests) == 1
        assert tests[0]["name"] == "test_xyz"


# ── TestGetTest ───────────────────────────────────────────────────

class TestGetTest:
    def test_get_existing(self, db, tmp_path):
        """존재하는 이름으로 조회 시 dict 반환."""
        f = tmp_path / "test_abc.py"
        f.write_text("def test_a(): pass\n", encoding="utf-8")
        import_test_file(f, db_path=db)
        result = get_test("test_abc", db_path=db)
        assert result is not None
        assert result["name"] == "test_abc"

    def test_get_nonexistent_returns_none(self, db):
        """존재하지 않는 이름은 None 반환."""
        result = get_test("test_nonexistent", db_path=db)
        assert result is None


# ── TestRunTest ───────────────────────────────────────────────────

class TestRunTest:
    def test_run_passing_test(self, db, tmp_path):
        """간단한 통과 테스트 코드를 저장하고 실행."""
        f = tmp_path / "test_simple_pass.py"
        f.write_text("def test_always_passes():\n    assert 1 == 1\n", encoding="utf-8")
        import_test_file(f, db_path=db)
        result = run_test("test_simple_pass", db_path=db)
        assert result["status"] == "passed"
        assert "name" in result

    def test_run_failing_test(self, db, tmp_path):
        """실패하는 테스트 코드를 저장하고 실행."""
        f = tmp_path / "test_simple_fail.py"
        f.write_text("def test_always_fails():\n    assert False\n", encoding="utf-8")
        import_test_file(f, db_path=db)
        result = run_test("test_simple_fail", db_path=db)
        assert result["status"] == "failed"

    def test_run_nonexistent_returns_error(self, db):
        """존재하지 않는 이름은 error 키 반환."""
        result = run_test("test_does_not_exist", db_path=db)
        assert "error" in result
