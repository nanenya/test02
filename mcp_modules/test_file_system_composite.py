#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_file_system_composite.py: file_system_composite 모듈에 대한 단위 테스트
"""

import pytest
from pathlib import Path

from . import file_system_composite as mcp


@pytest.fixture(autouse=True)
def patch_allowed_base(tmp_path, monkeypatch):
    """ALLOWED_BASE_PATH를 tmp_path로 교체"""
    monkeypatch.setattr("mcp_modules.file_system_composite.ALLOWED_BASE_PATH", tmp_path)


class TestMove:
    def test_success_file(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "dst.txt"
        result = mcp.move(str(src), str(dst))
        assert Path(result).exists()
        assert not src.exists()

    def test_failure_source_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.move(str(tmp_path / "nonexistent"), str(tmp_path / "dst"))

    def test_failure_path_traversal_source(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.move("/etc/passwd", "/tmp/dst")


class TestCopyDirectory:
    def test_success(self, tmp_path):
        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "file.txt").write_text("content")
        dst = tmp_path / "dst_dir"
        result = mcp.copy_directory(str(src), str(dst))
        assert Path(result).is_dir()
        assert (Path(result) / "file.txt").read_text() == "content"

    def test_failure_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            mcp.copy_directory(str(f), str(tmp_path / "dst"))

    def test_failure_nonexistent_source(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.copy_directory(str(tmp_path / "nonexistent"), str(tmp_path / "dst"))


class TestFindFiles:
    def test_success(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.py").write_text("y")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("z")
        results = mcp.find_files(str(tmp_path), "*.txt")
        assert len(results) == 2

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.find_files(str(tmp_path / "nonexistent"), "*.txt")

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.find_files("/etc", "*.conf")


class TestFindTextInFiles:
    def test_success(self, tmp_path):
        (tmp_path / "match.txt").write_text("hello world")
        (tmp_path / "nomatch.txt").write_text("goodbye")
        results = mcp.find_text_in_files(str(tmp_path), "hello")
        assert len(results) == 1
        assert "match.txt" in results[0]

    def test_skips_binary(self, tmp_path):
        (tmp_path / "binary.bin").write_bytes(b"\xff\xfe\x00")
        (tmp_path / "text.txt").write_text("target text")
        results = mcp.find_text_in_files(str(tmp_path), "target")
        assert len(results) == 1

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.find_text_in_files(str(tmp_path / "nonexistent"), "text")


class TestFindLargeFiles:
    def test_success(self, tmp_path):
        large = tmp_path / "large.txt"
        large.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB
        small = tmp_path / "small.txt"
        small.write_text("tiny")
        results = mcp.find_large_files(str(tmp_path), 1.0)
        assert len(results) == 1
        assert "large.txt" in results[0]

    def test_empty_result(self, tmp_path):
        (tmp_path / "tiny.txt").write_text("x")
        results = mcp.find_large_files(str(tmp_path), 100.0)
        assert results == []


class TestReadSpecificLines:
    def test_success(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("line1\nline2\nline3\n")
        result = mcp.read_specific_lines(str(f), 2, 3)
        assert len(result) == 2
        assert "line2" in result[0]

    def test_failure_invalid_range(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("a\nb\n")
        with pytest.raises(ValueError):
            mcp.read_specific_lines(str(f), 3, 1)

    def test_failure_zero_start(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("a\n")
        with pytest.raises(ValueError):
            mcp.read_specific_lines(str(f), 0, 1)

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.read_specific_lines(str(tmp_path / "nonexistent"), 1, 1)


class TestReplaceTextInFile:
    def test_success(self, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello world")
        result = mcp.replace_text_in_file(str(f), "hello", "goodbye")
        assert result is True
        assert f.read_text() == "goodbye world"

    def test_no_change(self, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("hello world")
        result = mcp.replace_text_in_file(str(f), "notfound", "x")
        assert result is False

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.replace_text_in_file(str(tmp_path / "nonexistent.txt"), "a", "b")


class TestGetDirectorySize:
    def test_success(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world!")
        size = mcp.get_directory_size(str(tmp_path))
        assert isinstance(size, int)
        assert size > 0

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert mcp.get_directory_size(str(empty)) == 0


class TestBatchRename:
    def test_success(self, tmp_path):
        for i in range(3):
            (tmp_path / f"old_{i}.tmp").write_text("x")
        result = mcp.batch_rename(str(tmp_path), "*.tmp", "renamed_{}.txt")
        assert len(result) == 3
        for p in result:
            assert Path(p).exists()
            assert "renamed_" in Path(p).name

    def test_failure_no_placeholder(self, tmp_path):
        with pytest.raises(ValueError):
            mcp.batch_rename(str(tmp_path), "*.tmp", "no_placeholder.txt")


class TestDeleteDirectoryRecursively:
    def test_success(self, tmp_path):
        d = tmp_path / "to_delete"
        d.mkdir()
        (d / "nested" ).mkdir()
        (d / "nested" / "file.txt").write_text("x")
        assert mcp.delete_directory_recursively(str(d)) is True
        assert not d.exists()

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.delete_directory_recursively(str(tmp_path / "nonexistent"))

    def test_failure_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            mcp.delete_directory_recursively(str(f))

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.delete_directory_recursively("/etc")
