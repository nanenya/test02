#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_attributes.py: AI 에이전트를 위한 파일 속성 조회 MCP 라이브러리

이 모듈은 파일과 디렉토리의 메타데이터(존재 여부, 크기, 수정 시간 등)를
조회하는 함수들을 제공합니다.

MCP 서버 대체 가능 여부:
  - filesystem MCP 서버의 get_file_info 도구로 일부 대체 가능 (exists, size, mtime)
  - get_creation_time, get_current_working_directory 는 로컬 구현 필요
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def path_exists(path: str) -> bool:
    """경로(파일 또는 디렉토리)가 존재하는지 확인합니다.

    Args:
        path (str): 확인할 경로.

    Returns:
        bool: 경로가 존재하면 True, 그렇지 않으면 False.

    Example:
        >>> path_exists("/tmp")
        True
        >>> path_exists("/nonexistent_path_xyz")
        False
    """
    logger.info(f"경로 존재 여부 확인: {path}")
    return Path(path).exists()


def is_file(path: str) -> bool:
    """경로가 일반 파일인지 확인합니다.

    Args:
        path (str): 확인할 경로.

    Returns:
        bool: 경로가 파일이면 True, 그렇지 않으면 False.

    Example:
        >>> is_file("/etc/hostname")
        True
    """
    logger.info(f"파일 여부 확인: {path}")
    return Path(path).is_file()


def is_directory(path: str) -> bool:
    """경로가 디렉토리인지 확인합니다.

    Args:
        path (str): 확인할 경로.

    Returns:
        bool: 경로가 디렉토리이면 True, 그렇지 않으면 False.

    Example:
        >>> is_directory("/tmp")
        True
    """
    logger.info(f"디렉토리 여부 확인: {path}")
    return Path(path).is_dir()


def get_file_size(path: str) -> int:
    """파일 크기를 바이트 단위로 반환합니다.

    Args:
        path (str): 크기를 확인할 파일 경로.

    Returns:
        int: 파일 크기(바이트).

    Raises:
        FileNotFoundError: 경로가 존재하지 않는 경우.
        IsADirectoryError: 경로가 파일이 아니라 디렉토리인 경우.

    Example:
        >>> size = get_file_size("/etc/hostname")
        >>> isinstance(size, int)
        True
    """
    logger.info(f"파일 크기 조회: {path}")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    if p.is_dir():
        raise IsADirectoryError(f"경로가 디렉토리입니다. 파일 경로를 지정하세요: {path}")
    size = p.stat().st_size
    logger.info(f"파일 크기: {size} 바이트")
    return size


def get_modification_time(path: str) -> datetime:
    """파일 또는 디렉토리의 마지막 수정 시간을 반환합니다.

    Args:
        path (str): 수정 시간을 확인할 경로.

    Returns:
        datetime: 마지막 수정 시간 (로컬 시간 기준).

    Raises:
        FileNotFoundError: 경로가 존재하지 않는 경우.

    Example:
        >>> mtime = get_modification_time("/etc/hostname")
        >>> isinstance(mtime, datetime)
        True
    """
    logger.info(f"파일 수정 시간 조회: {path}")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    logger.info(f"수정 시간: {mtime}")
    return mtime


def get_creation_time(path: str) -> datetime:
    """파일 또는 디렉토리의 생성 시간을 반환합니다.

    참고: Linux에서는 진정한 생성 시간(st_birthtime)을 지원하지 않으며,
    st_ctime(상태 변경 시간, inode ctime)을 반환합니다.
    macOS에서는 st_birthtime(실제 생성 시간)을 반환합니다.

    Args:
        path (str): 생성 시간을 확인할 경로.

    Returns:
        datetime: 생성(또는 상태 변경) 시간 (로컬 시간 기준).

    Raises:
        FileNotFoundError: 경로가 존재하지 않는 경우.

    Example:
        >>> ctime = get_creation_time("/etc/hostname")
        >>> isinstance(ctime, datetime)
        True
    """
    logger.info(f"파일 생성 시간 조회: {path}")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    stat = p.stat()
    # macOS에서는 st_birthtime 사용, Linux에서는 st_ctime으로 대체
    ctime_ts = getattr(stat, 'st_birthtime', stat.st_ctime)
    ctime = datetime.fromtimestamp(ctime_ts)
    logger.info(f"생성 시간: {ctime}")
    return ctime


def get_current_working_directory() -> str:
    """현재 작업 디렉토리 경로를 문자열로 반환합니다.

    Returns:
        str: 현재 작업 디렉토리의 절대 경로.

    Example:
        >>> cwd = get_current_working_directory()
        >>> isinstance(cwd, str)
        True
    """
    logger.info("현재 작업 디렉토리 조회.")
    cwd = os.getcwd()
    logger.info(f"현재 작업 디렉토리: {cwd}")
    return cwd
