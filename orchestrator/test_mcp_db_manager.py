#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_mcp_db_manager.py

import json
import sqlite3
from pathlib import Path

import pytest

from orchestrator.mcp_db_manager import (
    MCP_CACHE_DIR,
    _extract_preamble,
    _extract_test_map,
    activate_function,
    end_session,
    generate_temp_module,
    get_active_function,
    get_function_versions,
    get_usage_stats,
    import_from_file,
    init_db,
    list_functions,
    log_usage,
    register_function,
    run_function_tests,
    update_function_test_code,
    set_module_preamble,
    start_session,
)
import ast


@pytest.fixture
def db(tmp_path):
    """각 테스트마다 격리된 임시 DB."""
    db_path = tmp_path / "test_mcp.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """격리된 임시 캐시 디렉토리."""
    cache = tmp_path / "mcp_cache"
    cache.mkdir()
    monkeypatch.setattr("orchestrator.mcp_db_manager.MCP_CACHE_DIR", cache)
    return cache


# ── TestInitDb ────────────────────────────────────────────────────

class TestInitDb:
    def test_all_tables_exist(self, db):
        conn = sqlite3.connect(str(db))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "mcp_functions",
            "mcp_module_contexts",
            "mcp_usage_log",
            "mcp_session_log",
        }
        assert expected.issubset(tables)

    def test_idempotent(self, db):
        """두 번 호출해도 오류 없음."""
        init_db(db)
        init_db(db)


# ── TestRegisterFunction ──────────────────────────────────────────

class TestRegisterFunction:
    def test_basic_register(self, db):
        result = register_function(
            func_name="hello",
            module_group="test_group",
            code="def hello():\n    return 'hi'",
            db_path=db,
        )
        assert result["func_name"] == "hello"
        assert result["version"] == 1
        assert result["activated"] is True

    def test_version_increments(self, db):
        register_function("foo", "grp", "def foo(): pass", db_path=db)
        result2 = register_function("foo", "grp", "def foo(): return 1", db_path=db)
        assert result2["version"] == 2

    def test_active_flag_switches_to_latest(self, db):
        register_function("bar", "grp", "def bar(): pass", db_path=db)
        register_function("bar", "grp", "def bar(): return 99", db_path=db)

        funcs = list_functions(module_group="grp", db_path=db)
        active = [f for f in funcs if f["func_name"] == "bar"]
        assert len(active) == 1
        assert active[0]["version"] == 2

    def test_test_code_passes(self, db):
        code = "def add(a, b):\n    return a + b"
        test_code = (
            "class TestAdd:\n"
            "    def test_basic(self):\n"
            "        assert add(1, 2) == 3\n"
        )
        result = register_function(
            "add", "math_group", code, test_code=test_code, run_tests=True, db_path=db
        )
        assert result["test_status"] == "passed"
        assert result["activated"] is True

    def test_test_code_fails_no_activation(self, db):
        code = "def broken(): return 1"
        test_code = (
            "class TestBroken:\n"
            "    def test_fail(self):\n"
            "        assert broken() == 999\n"
        )
        result = register_function(
            "broken", "grp", code, test_code=test_code, run_tests=True, db_path=db
        )
        assert result["test_status"] == "failed"
        assert result["activated"] is False

    def test_no_test_code_activates_immediately(self, db):
        result = register_function("noop", "grp", "def noop(): pass", db_path=db)
        assert result["activated"] is True


# ── TestListFunctions ─────────────────────────────────────────────

class TestListFunctions:
    def test_active_only_default(self, db):
        register_function("f1", "g1", "def f1(): pass", db_path=db)
        register_function("f2", "g2", "def f2(): pass", db_path=db)
        funcs = list_functions(db_path=db)
        names = [f["func_name"] for f in funcs]
        assert "f1" in names and "f2" in names

    def test_filter_by_group(self, db):
        register_function("fa", "groupA", "def fa(): pass", db_path=db)
        register_function("fb", "groupB", "def fb(): pass", db_path=db)
        result = list_functions(module_group="groupA", db_path=db)
        assert all(f["module_group"] == "groupA" for f in result)

    def test_all_versions(self, db):
        register_function("v_func", "grp", "def v_func(): return 1", db_path=db)
        register_function("v_func", "grp", "def v_func(): return 2", db_path=db)
        all_vers = list_functions(active_only=False, db_path=db)
        v_versions = [f for f in all_vers if f["func_name"] == "v_func"]
        assert len(v_versions) == 2


# ── TestGetFunctionVersions ───────────────────────────────────────

class TestGetFunctionVersions:
    def test_returns_all_versions_descending(self, db):
        register_function("myfunc", "g", "def myfunc(): return 1", db_path=db)
        register_function("myfunc", "g", "def myfunc(): return 2", db_path=db)
        versions = get_function_versions("myfunc", db_path=db)
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_empty_for_unknown_func(self, db):
        assert get_function_versions("nonexistent", db_path=db) == []


# ── TestGetActiveFunction ─────────────────────────────────────────

class TestGetActiveFunction:
    def test_returns_active_version(self, db):
        register_function("actf", "g", "def actf(): return 1", db_path=db)
        register_function("actf", "g", "def actf(): return 2", db_path=db)
        active = get_active_function("actf", db_path=db)
        assert active is not None
        assert active["version"] == 2
        assert active["is_active"] == 1

    def test_returns_none_for_unknown(self, db):
        assert get_active_function("unknown", db_path=db) is None


# ── TestGenerateTempModule ────────────────────────────────────────

class TestGenerateTempModule:
    def test_file_created(self, db, tmp_path, monkeypatch):
        cache = tmp_path / "mcp_cache"
        cache.mkdir()
        monkeypatch.setattr("orchestrator.mcp_db_manager.MCP_CACHE_DIR", cache)

        register_function("fn1", "mymod", "def fn1():\n    return 1", db_path=db)
        path = generate_temp_module("mymod", db_path=db)
        assert path.exists()

    def test_file_contains_auto_header(self, db, tmp_path, monkeypatch):
        cache = tmp_path / "mcp_cache"
        cache.mkdir()
        monkeypatch.setattr("orchestrator.mcp_db_manager.MCP_CACHE_DIR", cache)

        register_function("fn2", "mod2", "def fn2():\n    pass", db_path=db)
        path = generate_temp_module("mod2", db_path=db)
        content = path.read_text()
        assert "Auto-generated by mcp_db_manager" in content
        assert "def fn2" in content

    def test_includes_preamble(self, db, tmp_path, monkeypatch):
        cache = tmp_path / "mcp_cache"
        cache.mkdir()
        monkeypatch.setattr("orchestrator.mcp_db_manager.MCP_CACHE_DIR", cache)

        set_module_preamble("pmod", "import os\nX = 42", db_path=db)
        register_function("pf", "pmod", "def pf():\n    return X", db_path=db)
        path = generate_temp_module("pmod", db_path=db)
        content = path.read_text()
        assert "import os" in content
        assert "X = 42" in content


# ── TestSessionLogging ────────────────────────────────────────────

class TestSessionLogging:
    def test_start_and_end_session(self, db):
        sid = start_session(conversation_id="conv123", group_id="grp1", db_path=db)
        assert len(sid) == 36  # UUID 형식
        end_session(sid, overall_success=True, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT ended_at, overall_success FROM mcp_session_log WHERE id = ?",
            (sid,),
        ).fetchone()
        conn.close()
        assert row[0] is not None
        assert row[1] == 1

    def test_session_failure(self, db):
        sid = start_session(db_path=db)
        end_session(sid, overall_success=False, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT overall_success FROM mcp_session_log WHERE id = ?",
            (sid,),
        ).fetchone()
        conn.close()
        assert row[0] == 0


# ── TestLogUsage ──────────────────────────────────────────────────

class TestLogUsage:
    def test_log_recorded(self, db):
        register_function("logfunc", "g", "def logfunc(): pass", db_path=db)
        log_usage("logfunc", success=True, duration_ms=50, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT success, duration_ms FROM mcp_usage_log WHERE func_name = 'logfunc'"
        ).fetchone()
        conn.close()
        assert row[0] == 1
        assert row[1] == 50

    def test_session_func_names_updated(self, db):
        register_function("sfunc", "g", "def sfunc(): pass", db_path=db)
        sid = start_session(db_path=db)
        log_usage("sfunc", success=True, session_id=sid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT func_names FROM mcp_session_log WHERE id = ?", (sid,)
        ).fetchone()
        conn.close()
        func_names = json.loads(row[0])
        assert "sfunc" in func_names

    def test_no_duplicate_in_func_names(self, db):
        register_function("dupfunc", "g", "def dupfunc(): pass", db_path=db)
        sid = start_session(db_path=db)
        log_usage("dupfunc", success=True, session_id=sid, db_path=db)
        log_usage("dupfunc", success=True, session_id=sid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT func_names FROM mcp_session_log WHERE id = ?", (sid,)
        ).fetchone()
        conn.close()
        func_names = json.loads(row[0])
        assert func_names.count("dupfunc") == 1


# ── TestGetUsageStats ─────────────────────────────────────────────

class TestGetUsageStats:
    def test_empty_stats(self, db):
        stats = get_usage_stats(db_path=db)
        assert stats["total_calls"] == 0

    def test_basic_stats(self, db):
        register_function("statf", "sg", "def statf(): pass", db_path=db)
        log_usage("statf", success=True, duration_ms=10, db_path=db)
        log_usage("statf", success=True, duration_ms=20, db_path=db)
        log_usage("statf", success=False, duration_ms=5, db_path=db)

        stats = get_usage_stats(func_name="statf", db_path=db)
        assert stats["total_calls"] == 3
        assert abs(stats["success_rate"] - 2/3) < 0.01
        assert stats["avg_duration_ms"] == pytest.approx(35/3, rel=0.01)

    def test_filter_by_module_group(self, db):
        register_function("gf1", "modA", "def gf1(): pass", db_path=db)
        register_function("gf2", "modB", "def gf2(): pass", db_path=db)
        log_usage("gf1", success=True, db_path=db)
        log_usage("gf2", success=True, db_path=db)

        stats = get_usage_stats(module_group="modA", db_path=db)
        assert stats["total_calls"] == 1
        assert "gf1" in stats["by_function"]


# ── TestExtractPreamble ───────────────────────────────────────────

class TestExtractPreamble:
    def test_extracts_imports(self):
        source = "import os\nimport sys\n\ndef my_func():\n    return 1\n"
        tree = ast.parse(source)
        preamble = _extract_preamble(source, tree)
        assert "import os" in preamble
        assert "import sys" in preamble
        assert "def my_func" not in preamble

    def test_excludes_public_functions(self):
        source = "X = 10\n\ndef pub(): pass\n\ndef _priv(): pass\n"
        tree = ast.parse(source)
        preamble = _extract_preamble(source, tree)
        assert "X = 10" in preamble
        assert "def pub" not in preamble
        assert "def _priv" in preamble  # private 함수는 preamble에 포함

    def test_empty_source(self):
        source = ""
        tree = ast.parse(source)
        preamble = _extract_preamble(source, tree)
        assert preamble == ""


# ── TestExtractTestMap ────────────────────────────────────────────

class TestExtractTestMap:
    def test_camel_to_snake(self):
        test_source = (
            "class TestCreateDirectory:\n"
            "    def test_basic(self):\n"
            "        pass\n"
        )
        result = _extract_test_map(test_source)
        assert "create_directory" in result

    def test_fixture_included(self):
        test_source = (
            "import pytest\n\n"
            "@pytest.fixture\n"
            "def tmp(tmp_path):\n"
            "    return tmp_path\n\n"
            "class TestReadFile:\n"
            "    def test_ok(self, tmp):\n"
            "        pass\n"
        )
        result = _extract_test_map(test_source)
        assert "read_file" in result
        assert "@pytest.fixture" in result["read_file"]

    def test_non_test_class_ignored(self):
        test_source = (
            "class Helper:\n"
            "    pass\n\n"
            "class TestFoo:\n"
            "    def test_it(self):\n"
            "        pass\n"
        )
        result = _extract_test_map(test_source)
        assert "foo" in result
        assert "helper" not in result


# ── TestImportFromFile ────────────────────────────────────────────

class TestImportFromFile:
    def test_basic_import(self, db, tmp_path):
        py_file = tmp_path / "my_module.py"
        py_file.write_text(
            "import os\n\n"
            "CONST = 42\n\n"
            "def greet(name):\n"
            "    '''인사 함수'''\n"
            "    return f'Hello {name}'\n\n"
            "def _helper():\n"
            "    pass\n",
            encoding="utf-8",
        )
        result = import_from_file(str(py_file), db_path=db)
        assert result["imported_functions"] == 1  # greet만 (공개 함수)
        assert result["failed"] == []

    def test_file_not_found(self, db):
        result = import_from_file("/nonexistent/file.py", db_path=db)
        assert result["imported_functions"] == 0
        assert len(result["failed"]) > 0

    def test_module_group_inferred_from_filename(self, db, tmp_path):
        py_file = tmp_path / "custom_tools.py"
        py_file.write_text("def tool_a():\n    pass\n", encoding="utf-8")
        import_from_file(str(py_file), db_path=db)
        funcs = list_functions(module_group="custom_tools", db_path=db)
        assert len(funcs) == 1

    def test_preamble_saved(self, db, tmp_path):
        py_file = tmp_path / "preamble_test.py"
        py_file.write_text(
            "import json\n\nDEFAULT = 'x'\n\ndef do_it(): pass\n",
            encoding="utf-8",
        )
        import_from_file(str(py_file), db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT preamble_code FROM mcp_module_contexts WHERE module_group = 'preamble_test'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert "import json" in row[0]


# ── TestUpdateFunctionTestCode ────────────────────────────────────

class TestUpdateFunctionTestCode:
    def test_update_and_pass(self, db):
        register_function("mul", "math", "def mul(a, b):\n    return a * b", db_path=db)
        test_code = "class TestMul:\n    def test_basic(self):\n        assert mul(3, 4) == 12\n"
        result = update_function_test_code("mul", test_code, run_tests=True, db_path=db)
        assert result["test_status"] == "passed"
        assert result["activated"] is True

    def test_update_and_fail(self, db):
        register_function("sub", "math", "def sub(a, b):\n    return a - b", db_path=db)
        test_code = "class TestSub:\n    def test_wrong(self):\n        assert sub(1, 2) == 999\n"
        result = update_function_test_code("sub", test_code, run_tests=True, db_path=db)
        assert result["test_status"] == "failed"
        assert result["activated"] is False

    def test_update_without_run(self, db):
        register_function("div", "math", "def div(a, b):\n    return a / b", db_path=db)
        test_code = "class TestDiv:\n    def test_basic(self):\n        assert div(6, 2) == 3.0\n"
        result = update_function_test_code("div", test_code, run_tests=False, db_path=db)
        assert "test_status" not in result

        # DB에 test_code가 저장되었는지 확인
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT test_code, test_status FROM mcp_functions WHERE func_name = 'div' AND is_active = 1"
        ).fetchone()
        conn.close()
        assert "TestDiv" in row[0]
        assert row[1] == "untested"

    def test_error_on_unknown_func(self, db):
        result = update_function_test_code("nonexistent", "class Test: pass", db_path=db)
        assert "error" in result

    def test_specific_version(self, db):
        r1 = register_function("inc", "math", "def inc(x):\n    return x + 1", db_path=db)
        register_function("inc", "math", "def inc(x):\n    return x + 10", db_path=db)

        test_code = "class TestInc:\n    def test_v1(self):\n        assert inc(5) == 6\n"
        result = update_function_test_code("inc", test_code, version=r1["version"], run_tests=True, db_path=db)
        assert result["test_status"] == "passed"
        assert result["activated"] is True
        # v1이 활성화됨
        active = get_active_function("inc", db_path=db)
        assert active["version"] == r1["version"]

    def test_error_on_unknown_version(self, db):
        register_function("foo", "g", "def foo(): pass", db_path=db)
        result = update_function_test_code("foo", "class T: pass", version=999, db_path=db)
        assert "error" in result


# ── TestActivateFunction ──────────────────────────────────────────

class TestActivateFunction:
    def test_activate_older_version(self, db):
        r1 = register_function("ver_func", "g", "def ver_func(): return 1", db_path=db)
        register_function("ver_func", "g", "def ver_func(): return 2", db_path=db)

        # v2가 현재 active
        assert get_active_function("ver_func", db_path=db)["version"] == 2

        # v1으로 rollback
        activate_function("ver_func", r1["version"], db_path=db)
        assert get_active_function("ver_func", db_path=db)["version"] == 1

    def test_activate_unknown_version_raises(self, db):
        register_function("only_v1", "g", "def only_v1(): pass", db_path=db)
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            activate_function("only_v1", 99, db_path=db)
