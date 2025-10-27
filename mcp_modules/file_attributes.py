#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일 시스템 경로의 속성과 상태를 확인하는 유틸리티 함수 모음입니다."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Union

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Helper Function ---
def _validate_and_get_path(path: Union[str, Path]) -> Path:
    """내부용 헬퍼: 경로 유효성을 검사하고 Path 객체로 반환합니다."""
    if not path:
        raise ValueError("파일 경로는 비어있거나 None일 수 없습니다.")
    return Path(path)

# --- MCP Functions ---

def path_exists(path: Union[str, Path]) -> bool:
    """해당 경로에 파일이나 디렉토리가 존재하는지 확인합니다.

    Args:
        path (Union[str, Path]): 존재 여부를 확인할 경로입니다.

    Returns:
        bool: 경로가 존재하면 True, 그렇지 않으면 False를 반환합니다.

    Example:
        >>> path_exists('C:/Users')
        True
        >>> path_exists('non_existent_folder/file.txt')
        False
    """
    try:
        p = _validate_and_get_path(path)
        return p.exists()
    except ValueError:
        return False # 잘못된 경로는 존재하지 않는 것으로 간주

def is_file(path: Union[str, Path]) -> bool:
    """해당 경로가 실제 파일을 가리키는지 확인합니다.

    Args:
        path (Union[str, Path]): 파일인지 확인할 경로입니다.

    Returns:
        bool: 경로가 존재하며 파일이면 True, 그렇지 않으면 False를 반환합니다.

    Example:
        >>> is_file('my_document.txt')
        True
        >>> is_file('my_folder/')
        False
    """
    try:
        p = _validate_and_get_path(path)
        return p.is_file()
    except ValueError:
        return False

def is_directory(path: Union[str, Path]) -> bool:
    """해당 경로가 실제 디렉토리(폴더)를 가리키는지 확인합니다.

    Args:
        path (Union[str, Path]): 디렉토리인지 확인할 경로입니다.

    Returns:
        bool: 경로가 존재하며 디렉토리이면 True, 그렇지 않으면 False를 반환합니다.

    Example:
        >>> is_directory('C:/Windows')
        True
        >>> is_directory('my_script.py')
        False
    """
    try:
        p = _validate_and_get_path(path)
        return p.is_dir()
    except ValueError:
        return False

def get_file_size(path: Union[str, Path]) -> int:
    """파일의 크기를 바이트(byte) 단위로 반환합니다.

    Args:
        path (Union[str, Path]): 크기를 조회할 파일의 경로입니다.

    Returns:
        int: 파일의 크기(bytes).

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우 발생합니다.
        IsADirectoryError: 경로가 파일이 아닌 디렉토리일 경우 발생합니다.
        PermissionError: 파일에 접근할 권한이 없을 경우 발생합니다.
    """
    logger.info(f"Requesting file size for: {path}")
    p = _validate_and_get_path(path)
    if not p.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
    if not p.is_file():
        raise IsADirectoryError(f"경로가 파일이 아닙니다. 디렉토리의 크기를 조회할 수 없습니다: {p}")
    
    try:
        size = p.stat().st_size
        logger.info(f"File size of {p} is {size} bytes.")
        return size
    except PermissionError as e:
        logger.error(f"Permission denied for {p}: {e}")
        raise

def get_modification_time(path: Union[str, Path]) -> datetime:
    """파일이 마지막으로 수정된 시간을 datetime 객체로 반환합니다.

    Args:
        path (Union[str, Path]): 수정 시간을 조회할 파일 또는 디렉토리의 경로입니다.

    Returns:
        datetime: 마지막 수정 시간을 담은 datetime 객체.

    Raises:
        FileNotFoundError: 경로가 존재하지 않을 경우 발생합니다.
    """
    logger.info(f"Requesting modification time for: {path}")
    p = _validate_and_get_path(path)
    if not p.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {p}")
        
    timestamp = p.stat().st_mtime
    mod_time = datetime.fromtimestamp(timestamp)
    logger.info(f"Modification time for {p} is {mod_time}.")
    return mod_time

def get_creation_time(path: Union[str, Path]) -> datetime:
    """파일이 생성된 시간을 datetime 객체로 반환합니다.

    참고: Unix/Linux 계열 시스템에서는 '생성 시간'이 아닌 '마지막 메타데이터
    변경 시간(ctime)'을 반환할 수 있어 시스템에 따라 의미가 다를 수 있습니다.

    Args:
        path (Union[str, Path]): 생성 시간을 조회할 파일 또는 디렉토리의 경로입니다.

    Returns:
        datetime: 생성 시간을 담은 datetime 객체.

    Raises:
        FileNotFoundError: 경로가 존재하지 않을 경우 발생합니다.
    """
    logger.info(f"Requesting creation time for: {path}")
    p = _validate_and_get_path(path)
    if not p.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {p}")
        
    try:
        # os.path.getctime()는 플랫폼별 생성 시간을 더 잘 처리함
        timestamp = os.path.getctime(p)
        cre_time = datetime.fromtimestamp(timestamp)
        logger.info(f"Creation time for {p} is {cre_time}.")
        return cre_time
    except OSError as e:
        logger.error(f"Could not get creation time for {p}: {e}")
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {p}")


def get_current_working_directory() -> str:
    """현재 스크립트가 실행 중인 작업 디렉토리의 절대 경로를 반환합니다.

    Returns:
        str: 현재 작업 디렉토리의 절대 경로.
    """
    cwd = Path.cwd()
    logger.info(f"Current working directory is: {cwd}")
    return str(cwd)
