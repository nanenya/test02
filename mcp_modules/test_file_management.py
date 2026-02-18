#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_file_management.py: file_management 모듈에 대한 단위 테스트
"""

import pytest
from pathlib import Path

from . import file_management as mcp


@pytest.fixture(autouse=True)
def patch_allowed_base(tmp_path, monkeypatch):
    """ALLOWED_BASE_PATH를 tmp_path로 교체하여 실제 파일시스템 격리"""
    monkeypatch.setattr("mcp_modules.file_management.ALLOWED_BASE_PATH", tmp_path)


class TestCreateDirectory:
    def test_success(self, tmp_path):
        new_dir = tmp_path / "new_dir"
        assert mcp.create_directory(str(new_dir)) is True
        assert new_dir.is_dir()

    def test_success_nested(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        assert mcp.create_directory(str(nested)) is True
        assert nested.is_dir()

    def test_success_exist_ok(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        # exist_ok=True이면 예외 없음
        assert mcp.create_directory(str(existing), exist_ok=True) is True

    def test_failure_path_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.create_directory("/etc/evil_dir")


class TestListDirectory:
    def test_success(self, tmp_path):
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        entries = mcp.list_directory(str(tmp_path))
        assert "file1.txt" in entries
        assert "file2.txt" in entries

    def test_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert mcp.list_directory(str(empty_dir)) == []

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.list_directory(str(tmp_path / "nonexistent"))

    def test_failure_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            mcp.list_directory(str(f))

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.list_directory("/etc")


class TestRename:
    def test_success_file(self, tmp_path):
        f = tmp_path / "old.txt"
        f.write_text("content")
        new_path = mcp.rename(str(f), "new.txt")
        assert Path(new_path).name == "new.txt"
        assert Path(new_path).exists()
        assert not f.exists()

    def test_failure_separator_in_name(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError):
            mcp.rename(str(f), "subdir/file.txt")

    def test_failure_backslash_in_name(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError):
            mcp.rename(str(f), "sub\\file.txt")

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.rename(str(tmp_path / "nonexistent.txt"), "new.txt")


class TestDeleteFile:
    def test_success(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("x")
        assert mcp.delete_file(str(f)) is True
        assert not f.exists()

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.delete_file(str(tmp_path / "nonexistent.txt"))

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "a_dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.delete_file(str(d))

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.delete_file("/etc/passwd")


class TestDeleteEmptyDirectory:
    def test_success(self, tmp_path):
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        assert mcp.delete_empty_directory(str(empty)) is True
        assert not empty.exists()

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.delete_empty_directory(str(tmp_path / "nonexistent"))

    def test_failure_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            mcp.delete_empty_directory(str(f))

    def test_failure_not_empty(self, tmp_path):
        d = tmp_path / "non_empty"
        d.mkdir()
        (d / "file.txt").write_text("x")
        with pytest.raises(OSError):
            mcp.delete_empty_directory(str(d))
