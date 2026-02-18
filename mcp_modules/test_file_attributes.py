#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_file_attributes.py: file_attributes 모듈에 대한 단위 테스트
"""

import pytest
from datetime import datetime
from pathlib import Path

from . import file_attributes as mcp


@pytest.fixture
def sample_file(tmp_path):
    """테스트용 임시 파일 생성"""
    f = tmp_path / "test_file.txt"
    f.write_text("hello world", encoding="utf-8")
    return f


@pytest.fixture
def sample_dir(tmp_path):
    """테스트용 임시 디렉토리 생성"""
    d = tmp_path / "test_dir"
    d.mkdir()
    return d


class TestPathExists:
    def test_success_file(self, sample_file):
        assert mcp.path_exists(str(sample_file)) is True

    def test_success_directory(self, sample_dir):
        assert mcp.path_exists(str(sample_dir)) is True

    def test_failure_nonexistent(self, tmp_path):
        assert mcp.path_exists(str(tmp_path / "nonexistent")) is False


class TestIsFile:
    def test_success(self, sample_file):
        assert mcp.is_file(str(sample_file)) is True

    def test_failure_directory(self, sample_dir):
        assert mcp.is_file(str(sample_dir)) is False

    def test_failure_nonexistent(self, tmp_path):
        assert mcp.is_file(str(tmp_path / "nonexistent")) is False


class TestIsDirectory:
    def test_success(self, sample_dir):
        assert mcp.is_directory(str(sample_dir)) is True

    def test_failure_file(self, sample_file):
        assert mcp.is_directory(str(sample_file)) is False

    def test_failure_nonexistent(self, tmp_path):
        assert mcp.is_directory(str(tmp_path / "nonexistent")) is False


class TestGetFileSize:
    def test_success(self, sample_file):
        size = mcp.get_file_size(str(sample_file))
        assert isinstance(size, int)
        assert size == len("hello world".encode("utf-8"))

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.get_file_size(str(tmp_path / "nonexistent"))

    def test_failure_directory(self, sample_dir):
        with pytest.raises(IsADirectoryError):
            mcp.get_file_size(str(sample_dir))


class TestGetModificationTime:
    def test_success(self, sample_file):
        mtime = mcp.get_modification_time(str(sample_file))
        assert isinstance(mtime, datetime)

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.get_modification_time(str(tmp_path / "nonexistent"))


class TestGetCreationTime:
    def test_success(self, sample_file):
        ctime = mcp.get_creation_time(str(sample_file))
        assert isinstance(ctime, datetime)

    def test_failure_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcp.get_creation_time(str(tmp_path / "nonexistent"))


class TestGetCurrentWorkingDirectory:
    def test_success(self):
        cwd = mcp.get_current_working_directory()
        assert isinstance(cwd, str)
        assert len(cwd) > 0
        assert Path(cwd).is_dir()
