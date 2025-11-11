#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""file_management MCPs 모음에 대한 단위 테스트."""

import pytest
from pathlib import Path

# 테스트 대상 함수 임포트
from mcp_modules.file_management import (
    create_directory,
    list_directory,
    rename,
    delete_file,
    delete_empty_directory,
)

# --- create_directory Tests ---
def test_create_directory_success(tmp_path: Path):
    new_dir = tmp_path / "new_dir"
    result_path = create_directory(new_dir)
    assert new_dir.exists()
    assert new_dir.is_dir()
    assert str(new_dir.resolve()) == result_path

def test_create_directory_nested(tmp_path: Path):
    nested_dir = tmp_path / "parent" / "child"
    create_directory(nested_dir)
    assert nested_dir.exists()

def test_create_directory_already_exists_ok(tmp_path: Path):
    create_directory(tmp_path, exist_ok=True) # Should not raise error

def test_create_directory_already_exists_fail(tmp_path: Path):
    with pytest.raises(FileExistsError):
        # Create it first
        (tmp_path / "exists").mkdir()
        create_directory(tmp_path / "exists", exist_ok=False)

# --- list_directory Tests ---
def test_list_directory_success(tmp_path: Path):
    (tmp_path / "file1.txt").touch()
    (tmp_path / "subdir").mkdir()
    items = list_directory(tmp_path)
    assert sorted(items) == ["file1.txt", "subdir"]

def test_list_directory_empty(tmp_path: Path):
    items = list_directory(tmp_path)
    assert items == []

def test_list_directory_not_found():
    with pytest.raises(FileNotFoundError):
        list_directory("non_existent_dir")

# --- rename Tests ---
def test_rename_file_success(tmp_path: Path):
    old_file = tmp_path / "old.txt"
    old_file.touch()
    result_path = rename(old_file, "new.txt")
    assert not old_file.exists()
    assert (tmp_path / "new.txt").exists()
    assert "new.txt" in result_path

def test_rename_fail_source_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        rename(tmp_path / "nonexistent.txt", "new.txt")

def test_rename_fail_destination_exists(tmp_path: Path):
    (tmp_path / "file1.txt").touch()
    (tmp_path / "file2.txt").touch()
    with pytest.raises(FileExistsError):
        rename(tmp_path / "file1.txt", "file2.txt")

# --- delete_file Tests ---
def test_delete_file_success(tmp_path: Path):
    file_to_delete = tmp_path / "deleteme.txt"
    file_to_delete.touch()
    assert delete_file(file_to_delete)
    assert not file_to_delete.exists()

def test_delete_file_not_found():
    with pytest.raises(FileNotFoundError):
        delete_file("non_existent_file.tmp")

def test_delete_file_is_directory(tmp_path: Path):
    with pytest.raises(IsADirectoryError):
        delete_file(tmp_path)

# --- delete_empty_directory Tests ---
def test_delete_empty_directory_success(tmp_path: Path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert delete_empty_directory(empty_dir)
    assert not empty_dir.exists()

def test_delete_non_empty_directory_fail(tmp_path: Path):
    non_empty_dir = tmp_path / "not_empty"
    non_empty_dir.mkdir()
    (non_empty_dir / "file.txt").touch()
    with pytest.raises(OSError):
        delete_empty_directory(non_empty_dir)
