#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_issue_tracker.py

import sqlite3
from pathlib import Path

import pytest

from orchestrator.issue_tracker import (
    capture,
    capture_exception,
    get_issue,
    init_db,
    list_issues,
    update_status,
)


@pytest.fixture
def db(tmp_path):
    """각 테스트마다 격리된 임시 DB."""
    db_path = tmp_path / "test_issues.db"
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
        assert "issues" in tables

    def test_idempotent(self, db):
        """두 번 호출해도 오류 없이 동일 테이블."""
        init_db(db)
        conn = sqlite3.connect(str(db))
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='issues'"
        ).fetchone()[0]
        conn.close()
        assert count == 1


# ── TestCapture ───────────────────────────────────────────────────

class TestCapture:
    def test_basic_capture(self, db):
        issue_id = capture(error_message="test error", db_path=db)
        assert issue_id is not None
        assert isinstance(issue_id, int)
        assert issue_id >= 1

    def test_all_fields_stored(self, db):
        capture(
            error_message="full error",
            error_type="ValueError",
            traceback="Traceback ...",
            context="test context",
            source="tool",
            severity="warning",
            title="custom title",
            db_path=db,
        )
        issue = get_issue(1, db_path=db)
        assert issue is not None
        assert issue["error_message"] == "full error"
        assert issue["error_type"] == "ValueError"
        assert issue["traceback"] == "Traceback ..."
        assert issue["context"] == "test context"
        assert issue["source"] == "tool"
        assert issue["severity"] == "warning"
        assert issue["title"] == "custom title"
        assert issue["status"] == "open"

    def test_db_failure_returns_none(self, tmp_path):
        bad_path = tmp_path / "nonexistent_dir" / "bad.db"
        result = capture(error_message="msg", db_path=bad_path)
        assert result is None

    def test_capture_exception_includes_traceback(self, db):
        try:
            raise RuntimeError("boom")
        except RuntimeError as e:
            issue_id = capture_exception(e, context="test", source="agent", db_path=db)

        assert issue_id is not None
        issue = get_issue(issue_id, db_path=db)
        assert issue is not None
        assert issue["error_type"] == "RuntimeError"
        assert issue["error_message"] == "boom"
        assert "RuntimeError" in issue["traceback"]


# ── TestListIssues ────────────────────────────────────────────────

class TestListIssues:
    def test_empty_list(self, db):
        result = list_issues(db_path=db)
        assert result == []

    def test_source_filter(self, db):
        capture(error_message="a", source="agent", db_path=db)
        capture(error_message="b", source="tool", db_path=db)
        capture(error_message="c", source="agent", db_path=db)

        agent_issues = list_issues(source="agent", db_path=db)
        assert len(agent_issues) == 2
        assert all(i["source"] == "agent" for i in agent_issues)

    def test_limit(self, db):
        for i in range(10):
            capture(error_message=f"err {i}", db_path=db)

        result = list_issues(limit=3, db_path=db)
        assert len(result) == 3

    def test_status_filter_after_update(self, db):
        capture(error_message="issue1", db_path=db)
        capture(error_message="issue2", db_path=db)
        update_status(1, "resolved", db_path=db)

        open_issues = list_issues(status="open", db_path=db)
        assert len(open_issues) == 1
        assert open_issues[0]["id"] == 2

        resolved_issues = list_issues(status="resolved", db_path=db)
        assert len(resolved_issues) == 1
        assert resolved_issues[0]["id"] == 1


# ── TestGetIssue ──────────────────────────────────────────────────

class TestGetIssue:
    def test_get_existing_issue(self, db):
        capture(error_message="hello", error_type="TestError", db_path=db)
        issue = get_issue(1, db_path=db)
        assert issue is not None
        assert issue["id"] == 1
        assert issue["error_message"] == "hello"
        assert issue["error_type"] == "TestError"

    def test_get_nonexistent_returns_none(self, db):
        result = get_issue(9999, db_path=db)
        assert result is None


# ── TestUpdateStatus ──────────────────────────────────────────────

class TestUpdateStatus:
    def test_resolve_with_note(self, db):
        capture(error_message="fixme", db_path=db)
        ok = update_status(1, "resolved", resolution_note="수정 완료", db_path=db)
        assert ok is True
        issue = get_issue(1, db_path=db)
        assert issue["status"] == "resolved"
        assert issue["resolution_note"] == "수정 완료"
        assert issue["resolved_at"] is not None

    def test_ignore(self, db):
        capture(error_message="skip", db_path=db)
        ok = update_status(1, "ignored", db_path=db)
        assert ok is True
        issue = get_issue(1, db_path=db)
        assert issue["status"] == "ignored"
        assert issue["resolved_at"] is not None

    def test_nonexistent_id_returns_false(self, db):
        ok = update_status(9999, "resolved", db_path=db)
        assert ok is False

    def test_in_progress_resolved_at_is_none(self, db):
        capture(error_message="wip", db_path=db)
        ok = update_status(1, "in_progress", db_path=db)
        assert ok is True
        issue = get_issue(1, db_path=db)
        assert issue["status"] == "in_progress"
        assert issue["resolved_at"] is None
