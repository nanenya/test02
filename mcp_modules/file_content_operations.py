#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_content_operations.py: AI 에이전트를 위한 파일 내용 읽기/쓰기 MCP 라이브러리

파일의 내용을 읽고 쓰는 기능을 제공합니다. 텍스트 및 바이너리 파일 모두
지원하며, 경로 조작(Path Traversal) 공격을 방지하기 위해 ALLOWED_BASE_PATH
검증이 적용됩니다.

MCP 서버 대체 가능 여부:
  - filesystem MCP 서버의 read_file, write_file 도구로 텍스트 read/write 대체 가능
  - read_binary_file, write_binary_file, append_to_file 은 로컬 구현 필요
"""

import logging
import os
import sys
from pathlib import Path

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


def read_file(path: str, encoding: str = 'utf-8') -> str:
    """파일 내용을 텍스트로 읽어 반환합니다.

    Args:
        path (str): 읽을 파일의 경로.
        encoding (str): 파일 인코딩. 기본값은 'utf-8'.

    Returns:
        str: 파일의 전체 텍스트 내용.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.
        IsADirectoryError: 경로가 디렉토리인 경우.

    Example:
        >>> content = read_file("/etc/hostname")
        >>> isinstance(content, str)
        True
    """
    logger.info(f"파일 읽기 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다: {path}")
    content = resolved.read_text(encoding=encoding)
    logger.info(f"파일 읽기 완료: {resolved} ({len(content)} 문자)")
    return content


def read_binary_file(path: str) -> bytes:
    """파일 내용을 바이너리로 읽어 bytes 객체로 반환합니다.

    Args:
        path (str): 읽을 파일의 경로.

    Returns:
        bytes: 파일의 바이너리 내용.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.
        IsADirectoryError: 경로가 디렉토리인 경우.

    Example:
        >>> data = read_binary_file("/etc/hostname")
        >>> isinstance(data, bytes)
        True
    """
    logger.info(f"바이너리 파일 읽기 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다: {path}")
    data = resolved.read_bytes()
    logger.info(f"바이너리 파일 읽기 완료: {resolved} ({len(data)} 바이트)")
    return data


def write_file(path: str, content: str, encoding: str = 'utf-8') -> bool:
    """파일에 텍스트 내용을 씁니다. 파일이 없으면 새로 생성하고, 있으면 덮어씁니다.

    Args:
        path (str): 쓸 파일의 경로.
        content (str): 파일에 쓸 텍스트 내용.
        encoding (str): 파일 인코딩. 기본값은 'utf-8'.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        IsADirectoryError: 경로가 디렉토리인 경우.

    Example:
        >>> write_file("/tmp/test.txt", "hello world")
        True
    """
    logger.info(f"파일 쓰기 시도: {path}")
    resolved = _validate_path(path)
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다: {path}")
    resolved.write_text(content, encoding=encoding)
    logger.info(f"파일 쓰기 완료: {resolved} ({len(content)} 문자)")
    return True


def write_binary_file(path: str, content: bytes) -> bool:
    """파일에 바이너리 내용을 씁니다. 파일이 없으면 새로 생성하고, 있으면 덮어씁니다.

    Args:
        path (str): 쓸 파일의 경로.
        content (bytes): 파일에 쓸 바이너리 내용.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        IsADirectoryError: 경로가 디렉토리인 경우.

    Example:
        >>> write_binary_file("/tmp/test.bin", b"\x00\x01\x02")
        True
    """
    logger.info(f"바이너리 파일 쓰기 시도: {path}")
    resolved = _validate_path(path)
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다: {path}")
    resolved.write_bytes(content)
    logger.info(f"바이너리 파일 쓰기 완료: {resolved} ({len(content)} 바이트)")
    return True


def append_to_file(path: str, content: str, encoding: str = 'utf-8') -> bool:
    """파일 끝에 텍스트 내용을 추가합니다. 파일이 없으면 새로 생성합니다.

    Args:
        path (str): 내용을 추가할 파일의 경로.
        content (str): 추가할 텍스트 내용.
        encoding (str): 파일 인코딩. 기본값은 'utf-8'.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        IsADirectoryError: 경로가 디렉토리인 경우.

    Example:
        >>> append_to_file("/tmp/test.txt", "\\n추가된 내용")
        True
    """
    logger.info(f"파일 내용 추가 시도: {path}")
    resolved = _validate_path(path)
    if resolved.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다: {path}")
    with open(resolved, mode='a', encoding=encoding) as f:
        f.write(content)
    logger.info(f"파일 내용 추가 완료: {resolved} ({len(content)} 문자 추가)")
    return True
