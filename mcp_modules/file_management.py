#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_management.py: AI 에이전트를 위한 파일 관리 MCP 라이브러리

파일과 디렉토리의 생성, 목록 조회, 이름 변경, 삭제 등 기본 파일 관리 기능을
제공합니다. 경로 조작(Path Traversal) 공격을 방지하기 위해 ALLOWED_BASE_PATH
검증이 적용됩니다.

MCP 서버 대체 가능 여부:
  - filesystem MCP 서버의 create_directory, list_directory, move_file 도구로 일부 대체 가능
  - rename, delete_file, delete_empty_directory 는 로컬 구현 필요
"""

import logging
import os
import sys
from pathlib import Path
from typing import List

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --- 보안 관련 설정 ---
ALLOWED_BASE_PATH = Path(
    os.environ.get("ALLOWED_BASE_PATH", Path(__file__).resolve().parent.parent)
).resolve()


def _validate_path(path: str) -> Path:
    """경로가 ALLOWED_BASE_PATH 내에 있는지 검증하고 절대 경로 Path 객체를 반환합니다.

    Args:
        path (str): 검증할 경로 문자열.

    Returns:
        Path: 검증된 절대 경로 Path 객체.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
    """
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ALLOWED_BASE_PATH):
        logger.error(f"허용되지 않은 경로 접근 시도: {path}")
        raise ValueError(f"보안 오류: 허용된 디렉토리 외부의 경로에는 접근할 수 없습니다: {path}")
    return resolved


def create_directory(path: str, exist_ok: bool = True) -> bool:
    """지정한 경로에 디렉토리를 생성합니다. 중간 경로도 함께 생성합니다.

    Args:
        path (str): 생성할 디렉토리 경로.
        exist_ok (bool): True이면 이미 존재하는 경우 오류 없이 통과. 기본값은 True.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileExistsError: exist_ok=False이고 디렉토리가 이미 존재하는 경우.

    Example:
        >>> create_directory("/tmp/test_mcp_dir")
        True
    """
    logger.info(f"디렉토리 생성 시도: {path}")
    resolved = _validate_path(path)
    resolved.mkdir(parents=True, exist_ok=exist_ok)
    logger.info(f"디렉토리 생성 완료: {resolved}")
    return True


def list_directory(path: str) -> List[str]:
    """지정한 디렉토리의 파일 및 하위 디렉토리 이름 목록을 반환합니다.

    Args:
        path (str): 목록을 조회할 디렉토리 경로.

    Returns:
        List[str]: 파일 및 디렉토리 이름 목록.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        NotADirectoryError: 경로가 디렉토리가 아닌 경우.
        FileNotFoundError: 경로가 존재하지 않는 경우.

    Example:
        >>> entries = list_directory("/tmp")
        >>> isinstance(entries, list)
        True
    """
    logger.info(f"디렉토리 목록 조회: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {path}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"디렉토리가 아닙니다: {path}")
    entries = os.listdir(resolved)
    logger.info(f"{len(entries)}개 항목 발견: {resolved}")
    return entries


def rename(source_path: str, new_name: str) -> str:
    """파일 또는 디렉토리의 이름을 변경합니다.

    new_name은 이름만 지정해야 하며, 경로 구분자(/, \\)를 포함할 수 없습니다.
    다른 디렉토리로의 이동은 file_system_composite.move()를 사용하세요.

    Args:
        source_path (str): 이름을 변경할 파일 또는 디렉토리의 경로.
        new_name (str): 새 이름 (경로 구분자 포함 불가).

    Returns:
        str: 변경 후 새 경로 문자열.

    Raises:
        ValueError: new_name에 경로 구분자가 포함된 경우, 또는 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: source_path가 존재하지 않는 경우.

    Example:
        >>> # rename("/tmp/old_name.txt", "new_name.txt")
    """
    logger.info(f"이름 변경 시도: {source_path} → {new_name}")
    if '/' in new_name or '\\' in new_name:
        raise ValueError(f"new_name에 경로 구분자를 포함할 수 없습니다: {new_name}")
    resolved_source = _validate_path(source_path)
    if not resolved_source.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {source_path}")
    new_path = resolved_source.parent / new_name
    _validate_path(str(new_path))
    resolved_source.rename(new_path)
    logger.info(f"이름 변경 완료: {new_path}")
    return str(new_path)


def delete_file(path: str) -> bool:
    """지정한 파일을 삭제합니다.

    Args:
        path (str): 삭제할 파일 경로.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.
        IsADirectoryError: 경로가 디렉토리인 경우 (디렉토리 삭제는 delete_empty_directory 사용).

    Example:
        >>> # delete_file("/tmp/test_file.txt")
    """
    logger.info(f"파일 삭제 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다. delete_empty_directory를 사용하세요: {path}")
    resolved.unlink()
    logger.info(f"파일 삭제 완료: {resolved}")
    return True


def delete_empty_directory(path: str) -> bool:
    """비어 있는 디렉토리를 삭제합니다.

    내용이 있는 디렉토리는 삭제할 수 없습니다.
    재귀적 삭제는 file_system_composite.delete_directory_recursively()를 사용하세요.

    Args:
        path (str): 삭제할 빈 디렉토리 경로.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 경로가 존재하지 않는 경우.
        NotADirectoryError: 경로가 디렉토리가 아닌 경우.
        OSError: 디렉토리가 비어 있지 않은 경우.

    Example:
        >>> # delete_empty_directory("/tmp/empty_dir")
    """
    logger.info(f"빈 디렉토리 삭제 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"디렉토리가 아닙니다: {path}")
    os.rmdir(resolved)  # 내용이 있으면 OSError 발생
    logger.info(f"빈 디렉토리 삭제 완료: {resolved}")
    return True
