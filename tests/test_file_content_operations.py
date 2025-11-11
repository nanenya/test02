#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""file_content_operations 모듈에 대한 단위 테스트."""

import pytest
from pathlib import Path
from mcp_modules.file_content_operations import (
    read_file,
    read_binary_file,
    write_file,
    write_binary_file,
    append_to_file,
)

class TestReadFile:
    def test_read_success(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("hello world")
        assert read_file(p) == "hello world"

    def test_read_not_found(self):
        with pytest.raises(FileNotFoundError):
            read_file("non_existent.txt")
            
    def test_read_is_directory(self, tmp_path):
        with pytest.raises(IsADirectoryError):
            read_file(tmp_path)

class TestReadBinaryFile:
    def test_read_success(self, tmp_path):
        p = tmp_path / "test.bin"
        p.write_bytes(b"\xde\xad\xbe\xef")
        assert read_binary_file(p) == b"\xde\xad\xbe\xef"

class TestWriteFile:
    def test_write_new_file(self, tmp_path):
        p = tmp_path / "new.txt"
        content = "new content"
        write_file(p, content)
        assert p.read_text() == content

    def test_overwrite_existing_file(self, tmp_path):
        p = tmp_path / "existing.txt"
        p.write_text("old")
        write_file(p, "new")
        assert p.read_text() == "new"

    def test_write_creates_parent_dir(self, tmp_path):
        p = tmp_path / "subdir" / "file.txt"
        write_file(p, "data")
        assert p.exists()

    def test_write_to_directory_path_fails(self, tmp_path):
        with pytest.raises(IsADirectoryError):
            write_file(tmp_path, "fail content")

class TestWriteBinaryFile:
    def test_write_success(self, tmp_path):
        p = tmp_path / "data.bin"
        content = b'\x01\x02\x03'
        write_binary_file(p, content)
        assert p.read_bytes() == content

class TestAppendToFile:
    def test_append_to_existing(self, tmp_path):
        p = tmp_path / "log.txt"
        p.write_text("line1")
        append_to_file(p, "\nline2")
        assert p.read_text() == "line1\nline2"

    def test_append_creates_new_file(self, tmp_path):
        p = tmp_path / "new_log.txt"
        append_to_file(p, "initial entry")
        assert p.read_text() == "initial entry"
        
    def test_append_multiple_times(self, tmp_path):
        p = tmp_path / "multi_log.txt"
        append_to_file(p, "a")
        append_to_file(p, "b")
        append_to_file(p, "c")
        assert p.read_text() == "abc"
