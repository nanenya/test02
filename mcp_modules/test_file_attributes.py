#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""file_attributes MCP 모듈에 대한 단위 테스트."""

import pytest
from pathlib import Path
from datetime import datetime
import os

from .file_attributes import (
    path_exists,
    is_file,
    is_directory,
    get_file_size,
    get_modification_time,
    get_creation_time,
    get_current_working_directory
)

@pytest.fixture
def test_file(tmp_path: Path) -> Path:
    """테스트용 파일을 생성하는 Fixture."""
    file = tmp_path / "test_file.txt"
    file.write_text("hello pytest")
    return file

@pytest.fixture
def test_dir(tmp_path: Path) -> Path:
    """테스트용 디렉토리를 생성하는 Fixture."""
    directory = tmp_path / "test_dir"
    directory.mkdir()
    return directory

# --- path_exists Tests ---
def test_path_exists_for_file(test_file):
    assert path_exists(test_file) is True

def test_path_exists_for_dir(test_dir):
    assert path_exists(test_dir) is True

def test_path_exists_for_nonexistent():
    assert path_exists("non/existent/path") is False

# --- is_file Tests ---
def test_is_file_for_file(test_file):
    assert is_file(test_file) is True

def test_is_file_for_dir(test_dir):
    assert is_file(test_dir) is False

# --- is_directory Tests ---
def test_is_directory_for_dir(test_dir):
    assert is_directory(test_dir) is True

def test_is_directory_for_file(test_file):
    assert is_directory(test_file) is False

# --- get_file_size Tests ---
def test_get_file_size_success(test_file):
    assert get_file_size(test_file) == len("hello pytest")

def test_get_file_size_for_dir(test_dir):
    with pytest.raises(IsADirectoryError):
        get_file_size(test_dir)

def test_get_file_size_not_found():
    with pytest.raises(FileNotFoundError):
        get_file_size("non_existent_file.txt")

# --- get_modification_time Tests ---
def test_get_modification_time_returns_datetime(test_file):
    mod_time = get_modification_time(test_file)
    assert isinstance(mod_time, datetime)

def test_get_modification_time_not_found():
    with pytest.raises(FileNotFoundError):
        get_modification_time("non_existent_file.txt")

# --- get_creation_time Tests ---
def test_get_creation_time_returns_datetime(test_file):
    cre_time = get_creation_time(test_file)
    assert isinstance(cre_time, datetime)

def test_get_creation_time_not_found():
    with pytest.raises(FileNotFoundError):
        get_creation_time("non_existent_file.txt")

# --- get_current_working_directory Tests ---
def test_get_current_working_directory_returns_string():
    cwd = get_current_working_directory()
    assert isinstance(cwd, str)
    assert os.path.isdir(cwd) # 반환된 경로가 실제 디렉토리인지 확인

# --- Edge Case Tests ---
@pytest.mark.parametrize("func", [path_exists, is_file, is_directory])
def test_boolean_functions_with_invalid_path(func):
    """엣지 케이스: bool 반환 함수들에 None 또는 빈 경로 전달."""
    assert func(None) is False
    assert func("") is False

@pytest.mark.parametrize("func", [get_file_size, get_modification_time, get_creation_time])
def test_value_functions_with_invalid_path(func):
    """엣지 케이스: 값 반환 함수들에 None 또는 빈 경로 전달."""
    with pytest.raises(ValueError):
        func(None)
    with pytest.raises(ValueError):
        func("")
