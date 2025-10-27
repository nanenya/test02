#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일 및 디렉토리 관리를 위한 핵심 원자(Atomic) MCPs 모음."""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Union

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_directory(path: Union[str, Path], exist_ok: bool = True) -> str:
    """지정된 경로에 새로운 디렉토리(폴더)를 생성합니다.

    이 함수는 멱등성(Idempotency)을 보장하기 위해 기본적으로 대상 디렉토리가
    이미 존재하더라도 오류를 발생시키지 않습니다 (`exist_ok=True`).
    중첩된 경로(예: 'a/b/c')가 주어지면 모든 중간 디렉토리도 함께 생성합니다.

    Args:
        path (Union[str, Path]): 생성할 디렉토리의 경로입니다.
        exist_ok (bool, optional): 디렉토리가 이미 존재할 때 예외를 발생시킬지
            여부입니다. True이면 예외 없이 넘어갑니다. 기본값은 True입니다.

    Returns:
        str: 성공 시, 생성된 디렉토리의 절대 경로를 문자열로 반환합니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우.
        PermissionError: 디렉토리를 생성할 권한이 없을 경우.
        FileExistsError: 경로에 이미 파일이 존재하거나, `exist_ok=False`인데
            디렉토리가 이미 존재할 경우.

    Example:
        >>> new_dir_path = create_directory('./my_new_folder')
        >>> print(f"디렉토리 생성 완료: {new_dir_path}")
    """
    if not path:
        raise ValueError("디렉토리 경로는 비어있을 수 없습니다.")
    logger.info(f"Attempting to create directory: {path}")

    try:
        dir_path = Path(path)
        dir_path.mkdir(parents=True, exist_ok=exist_ok)
        resolved_path = str(dir_path.resolve())
        logger.info(f"Successfully created or ensured directory exists: {resolved_path}")
        return resolved_path
    except PermissionError as e:
        logger.error(f"Permission denied to create directory at {path}: {e}")
        raise
    except FileExistsError as e:
        logger.error(f"Path {path} already exists and is a file, or exist_ok=False: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while creating directory {path}: {e}")
        raise IOError(f"디렉토리 생성 중 예상치 못한 오류 발생: {e}")


def list_directory(path: Union[str, Path]) -> List[str]:
    """지정된 디렉토리의 파일 및 하위 디렉토리 목록을 리스트로 반환합니다.

    Args:
        path (Union[str, Path]): 내용을 조회할 디렉토리의 경로입니다.

    Returns:
        List[str]: 디렉토리 내의 파일 및 폴더 이름 목록입니다.

    Raises:
        ValueError: 경로가 유효하지 않은 값일 경우.
        FileNotFoundError: 디렉토리가 존재하지 않을 경우.
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우.
        PermissionError: 디렉토리에 접근할 권한이 없을 경우.

    Example:
        >>> contents = list_directory('.')
        >>> print(f"현재 디렉토리 내용: {contents}")
    """
    if not path:
        raise ValueError("디렉토리 경로는 비어있을 수 없습니다.")
    logger.info(f"Listing contents of directory: {path}")

    dir_path = Path(path)
    if not dir_path.exists():
        raise FileNotFoundError(f"지정된 디렉토리가 존재하지 않습니다: {path}")
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리가 아닙니다: {path}")

    try:
        items = [item.name for item in dir_path.iterdir()]
        logger.info(f"Found {len(items)} items in {path}")
        return items
    except PermissionError as e:
        logger.error(f"Permission denied to list directory {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while listing directory {path}: {e}")
        raise IOError(f"디렉토리 목록 조회 중 예상치 못한 오류 발생: {e}")


def rename(source_path: Union[str, Path], new_name: str) -> str:
    """파일 또는 디렉토리의 이름을 변경합니다.

    Args:
        source_path (Union[str, Path]): 이름을 변경할 원본 파일 또는 디렉토리의 경로.
        new_name (str): 적용할 새로운 이름 (경로 포함 불가, 순수 이름만).

    Returns:
        str: 이름이 변경된 후의 새로운 절대 경로를 반환합니다.

    Raises:
        ValueError: 경로 또는 새 이름이 유효하지 않을 경우.
        FileNotFoundError: 원본 경로가 존재하지 않을 경우.
        FileExistsError: 동일한 위치에 새로운 이름의 파일/디렉토리가 이미 존재할 경우.
        PermissionError: 이름 변경 권한이 없을 경우.

    Example:
        >>> updated_path = rename('old_name.txt', 'new_name.txt')
        >>> print(f"이름 변경 완료: {updated_path}")
    """
    if not source_path or not new_name:
        raise ValueError("원본 경로와 새로운 이름은 비어있을 수 없습니다.")
    if '/' in new_name or '\\' in new_name:
        raise ValueError("새 이름에는 경로 구분자('\\', '/')를 포함할 수 없습니다.")
    logger.info(f"Attempting to rename '{source_path}' to '{new_name}'")

    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"원본 경로가 존재하지 않습니다: {source_path}")

    # 1. 파일 존재 여부를 먼저 확인하여 FileExistsError를 직접 발생시킵니다.
    dest_path = src.with_name(new_name)
    if dest_path.exists():
        raise FileExistsError(f"대상 이름 '{new_name}'이(가) 이미 존재합니다.")

    # 2. try 블록은 실제 파일 시스템 작업(rename)에서 발생할 수 있는 예외만 처리하도록 합니다.
    try:
        src.rename(dest_path)
        resolved_path = str(dest_path.resolve())
        logger.info(f"Successfully renamed to: {resolved_path}")
        return resolved_path
    except PermissionError as e:
        logger.error(f"Permission denied to rename {source_path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during rename: {e}")
        raise IOError(f"이름 변경 중 예상치 못한 오류 발생: {e}")


def delete_file(path: Union[str, Path]) -> bool:
    """지정된 파일을 삭제합니다.

    Args:
        path (Union[str, Path]): 삭제할 파일의 경로입니다.

    Returns:
        bool: 파일 삭제 성공 시 True를 반환합니다.

    Raises:
        ValueError: 경로가 유효하지 않을 경우.
        FileNotFoundError: 파일이 존재하지 않을 경우.
        IsADirectoryError: 경로가 파일이 아닌 디렉토리일 경우.
        PermissionError: 파일 삭제 권한이 없을 경우.

    Example:
        >>> delete_file('file_to_delete.txt')
    """
    if not path:
        raise ValueError("파일 경로는 비어있을 수 없습니다.")
    logger.info(f"Attempting to delete file: {path}")

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"삭제할 파일이 존재하지 않습니다: {path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"삭제 대상은 파일이어야 합니다 (디렉토리 감지): {path}")

    try:
        file_path.unlink()
        logger.info(f"Successfully deleted file: {path}")
        return True
    except PermissionError as e:
        logger.error(f"Permission denied to delete file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while deleting file {path}: {e}")
        raise IOError(f"파일 삭제 중 예상치 못한 오류 발생: {e}")


def delete_empty_directory(path: Union[str, Path]) -> bool:
    """비어 있는 디렉토리를 삭제합니다.

    디렉토리가 비어있지 않은 경우 예외를 발생시킵니다.

    Args:
        path (Union[str, Path]): 삭제할 비어있는 디렉토리의 경로입니다.

    Returns:
        bool: 디렉토리 삭제 성공 시 True를 반환합니다.

    Raises:
        ValueError: 경로가 유효하지 않을 경우.
        FileNotFoundError: 디렉토리가 존재하지 않을 경우.
        NotADirectoryError: 경로가 디렉토리가 아닐 경우.
        PermissionError: 디렉토리 삭제 권한이 없을 경우.
        OSError: 디렉토리가 비어있지 않을 경우.

    Example:
        >>> delete_empty_directory('./empty_folder')
    """
    if not path:
        raise ValueError("디렉토리 경로는 비어있을 수 없습니다.")
    logger.info(f"Attempting to delete empty directory: {path}")

    dir_path = Path(path)
    if not dir_path.exists():
        raise FileNotFoundError(f"삭제할 디렉토리가 존재하지 않습니다: {path}")
    if not dir_path.is_dir():
        raise NotADirectoryError(f"삭제 대상은 디렉토리여야 합니다: {path}")

    try:
        dir_path.rmdir()
        logger.info(f"Successfully deleted empty directory: {path}")
        return True
    except OSError as e:
        # Directory not empty
        logger.error(f"Failed to delete directory {path} as it is not empty: {e}")
        raise
    except PermissionError as e:
        logger.error(f"Permission denied to delete directory {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while deleting directory {path}: {e}")
        raise IOError(f"디렉토리 삭제 중 예상치 못한 오류 발생: {e}")
