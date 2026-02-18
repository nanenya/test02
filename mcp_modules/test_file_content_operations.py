#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_file_content_operations.py: file_content_operations 모듈에 대한 단위 테스트
"""

import pytest
from pathlib import Path

from . import file_content_operations as mcp


@pytest.fixture(autouse=True)
def patch_allowed_base(tmp_path, monkeypatch):
    """ALLOWED_BASE_PATH를 tmp_path로 교체"""
    monkeypatch.setattr("mcp_modules.file_content_operations.ALLOWED_BASE_PATH", tmp_path)


class TestReadFile:
    def test_success(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        assert mcp.read_file(str(f)) == "hello world"

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.read_file(str(tmp_path / "nonexistent.txt"))

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "a_dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.read_file(str(d))

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.read_file("/etc/passwd")


class TestReadBinaryFile:
    def test_success(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        data = mcp.read_binary_file(str(f))
        assert data == b"\x00\x01\x02\x03"
        assert isinstance(data, bytes)

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.read_binary_file(str(tmp_path / "nonexistent.bin"))

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.read_binary_file(str(d))


class TestWriteFile:
    def test_success_create(self, tmp_path):
        f = tmp_path / "new_file.txt"
        assert mcp.write_file(str(f), "new content") is True
        assert f.read_text(encoding="utf-8") == "new content"

    def test_success_overwrite(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old")
        mcp.write_file(str(f), "new")
        assert f.read_text(encoding="utf-8") == "new"

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.write_file(str(d), "content")

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.write_file("/etc/evil.txt", "bad")


class TestWriteBinaryFile:
    def test_success(self, tmp_path):
        f = tmp_path / "bin_file.bin"
        assert mcp.write_binary_file(str(f), b"\xff\xfe") is True
        assert f.read_bytes() == b"\xff\xfe"

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.write_binary_file(str(d), b"\x00")


class TestAppendToFile:
    def test_success_existing(self, tmp_path):
        f = tmp_path / "append.txt"
        f.write_text("line1\n", encoding="utf-8")
        mcp.append_to_file(str(f), "line2\n")
        assert f.read_text(encoding="utf-8") == "line1\nline2\n"

    def test_success_creates_new(self, tmp_path):
        f = tmp_path / "new_append.txt"
        assert not f.exists()
        mcp.append_to_file(str(f), "first line")
        assert f.read_text(encoding="utf-8") == "first line"

    def test_failure_is_directory(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        with pytest.raises(IsADirectoryError):
            mcp.append_to_file(str(d), "x")

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.append_to_file("/etc/evil.txt", "x")
