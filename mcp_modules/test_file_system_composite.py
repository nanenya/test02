#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""file_system_composite 모듈에 대한 단위 테스트."""

import pytest
from pathlib import Path
import os
import shutil

# 테스트 대상 모듈 임포트
from .file_system_composite import (
    move,
    copy_directory,
    find_files,
    find_text_in_files,
    find_large_files,
    read_specific_lines,
    replace_text_in_file,
    get_directory_size,
    batch_rename,
    delete_directory_recursively,
)

# --- 테스트 픽스처 ---

@pytest.fixture
def setup_test_environment(tmp_path: Path):
    """테스트를 위한 다양한 파일과 디렉토리 구조를 생성합니다."""
    # 루트 디렉토리
    src = tmp_path / "source"
    src.mkdir()
    
    # 하위 디렉토리 및 파일
    (src / "docs").mkdir()
    (src / "img").mkdir()
    
    (src / "main.py").write_text("import os\n# Main script\n")
    (src / "README.md").write_text("# Project\nThis is a test project.\nERROR in line 3.")
    (src / "docs" / "guide.txt").write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
    (src / "img" / "photo_01.jpg").touch()
    (src / "img" / "photo_02.png").touch()
    
    # 대용량 파일
    large_file = src / "large_file.bin"
    large_file.write_bytes(b'\0' * (2 * 1024 * 1024)) # 2MB 파일

    return tmp_path

# --- 테스트 케이스 ---

class TestMoveAndCopy:
    def test_move_file(self, setup_test_environment):
        src_path = setup_test_environment / "source" / "main.py"
        dest_path = setup_test_environment / "main_moved.py"
        result = move(src_path, dest_path)
        assert not src_path.exists()
        assert dest_path.exists()
        assert Path(result).name == "main_moved.py"

    def test_move_to_dir(self, setup_test_environment):
        src_path = setup_test_environment / "source" / "README.md"
        dest_dir = setup_test_environment / "dest_dir"
        dest_dir.mkdir()
        move(src_path, dest_dir)
        assert not src_path.exists()
        assert (dest_dir / "README.md").exists()

    def test_move_fail_not_found(self):
        with pytest.raises(FileNotFoundError):
            move("non_existent.txt", "somewhere.txt")

    def test_copy_directory(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        dest_dir = setup_test_environment / "source_copy"
        result = copy_directory(src_dir, dest_dir)
        assert dest_dir.is_dir()
        assert (dest_dir / "main.py").exists()
        assert (dest_dir / "docs" / "guide.txt").exists()
        assert Path(result).name == "source_copy"

    def test_copy_directory_fail_exists(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        dest_dir = setup_test_environment / "dest"
        dest_dir.mkdir()
        with pytest.raises(FileExistsError):
            copy_directory(src_dir, dest_dir)

class TestSearchAndFind:
    def test_find_files(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        py_files = find_files(src_dir, "*.py")
        img_files = find_files(src_dir, "photo_*")
        assert len(py_files) == 1
        assert Path(py_files[0]).name == "main.py"
        assert len(img_files) == 2

    def test_find_text_in_files(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        results = find_text_in_files(src_dir, "ERROR")
        assert len(results) == 1
        key = next(iter(results))
        assert Path(key).name == "README.md"
        assert results[key] == [3]

    def test_find_large_files(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        large_files = find_large_files(src_dir, min_size_mb=1)
        assert len(large_files) == 1
        assert Path(large_files[0]).name == "large_file.bin"
        assert find_large_files(src_dir, min_size_mb=3) == []
    
    def test_find_large_files_fail_value(self):
        with pytest.raises(ValueError):
            find_large_files(".", -1)

class TestContentManipulation:
    def test_read_specific_lines(self, setup_test_environment):
        file_path = setup_test_environment / "source" / "docs" / "guide.txt"
        content = read_specific_lines(file_path, 2, 4)
        assert content == "Line 2\nLine 3\nLine 4\n"

    def test_read_specific_lines_fail_range(self, setup_test_environment):
        file_path = setup_test_environment / "source" / "docs" / "guide.txt"
        with pytest.raises(ValueError):
            read_specific_lines(file_path, 4, 2)
    
    def test_replace_text_in_file(self, setup_test_environment):
        file_path = setup_test_environment / "source" / "README.md"
        assert "test project" in file_path.read_text()
        result = replace_text_in_file(file_path, "test project", "production system")
        assert result is True
        assert "production system" in file_path.read_text()
        
    def test_replace_text_no_change(self, setup_test_environment):
        file_path = setup_test_environment / "source" / "README.md"
        result = replace_text_in_file(file_path, "non_existent_text", "new_text")
        assert result is False

    def test_get_directory_size(self, setup_test_environment):
        src_dir = setup_test_environment / "source"
        size = get_directory_size(src_dir)
        # 2MB + a few bytes for text files
        assert size > 2 * 1024 * 1024

class TestBatchProcessing:
    def test_batch_rename(self, setup_test_environment):
        img_dir = setup_test_environment / "source" / "img"
        result = batch_rename(img_dir, "photo_*.png", "image_{}.png")
        assert not (img_dir / "photo_02.png").exists()
        assert (img_dir / "image_02.png").exists()
        assert len(result) == 1
        
    def test_batch_rename_fail_format(self, setup_test_environment):
        with pytest.raises(ValueError):
            batch_rename(setup_test_environment, "photo.jpg", "image.jpg")

    def test_delete_directory_recursively(self, setup_test_environment):
        dir_to_delete = setup_test_environment / "source"
        assert dir_to_delete.exists()
        delete_directory_recursively(dir_to_delete)
        assert not dir_to_delete.exists()

    def test_delete_fail_not_directory(self, setup_test_environment):
        file_path = setup_test_environment / "source" / "main.py"
        with pytest.raises(NotADirectoryError):
            delete_directory_recursively(file_path)
