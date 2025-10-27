#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일 또는 디렉토리의 이름을 변경하거나 다른 위치로 이동시킵니다."""

import logging
from pathlib import Path
from typing import Union

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def rename(source_path: Union[str, Path], destination_path: Union[str, Path]) -> str:
    """파일 또는 디렉토리의 이름을 변경하거나 다른 위치로 이동시킵니다.

    이 함수는 `source_path`에 있는 파일이나 디렉토리를 `destination_path`로
    이름을 바꾸거나 이동시킵니다. 안전을 위해 대상 경로가 이미 존재할 경우,
    덮어쓰지 않고 FileExistsError를 발생시킵니다.

    Args:
        source_path (Union[str, Path]): 이름을 바꿀 원본 파일 또는 디렉토리의 경로.
        destination_path (Union[str, Path]): 새로운 파일 또는 디렉토리의 경로.

    Returns:
        str: 성공 시, 변경된 새로운 경로의 절대 경로를 문자열로 반환합니다.

    Raises:
        ValueError: 원본 또는 대상 경로가 유효하지 않은 값일 경우.
        FileNotFoundError: 원본 경로가 존재하지 않을 경우.
        FileExistsError: 대상 경로에 이미 파일이나 디렉토리가 존재할 경우.
        PermissionError: 작업을 수행할 권한이 없을 경우.

    Example:
        >>> # 파일 이름 변경
        >>> rename('old_name.txt', 'new_name.txt')
        '/path/to/new_name.txt'
        >>> # 파일을 다른 디렉토리로 이동
        >>> rename('data.csv', 'archive/data_2025.csv')
        '/path/to/archive/data_2025.csv'
    """
    if not source_path or not destination_path:
        raise ValueError("원본과 대상 경로는 비어있을 수 없습니다.")

    logger.info(f"Attempting to rename/move from '{source_path}' to '{destination_path}'")

    src = Path(source_path)
    dest = Path(destination_path)

    if not src.exists():
        raise FileNotFoundError(f"원본 경로가 존재하지 않습니다: {src}")
    
    if dest.exists():
        raise FileExistsError(f"대상 경로에 이미 파일이나 디렉토리가 존재합니다: {dest}")

    try:
        # 대상의 부모 디렉토리가 없으면 생성
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        src.rename(dest)
        
        resolved_path = str(dest.resolve())
        logger.info(f"Successfully renamed/moved to: {resolved_path}")
        return resolved_path
        
    except PermissionError as e:
        logger.error(f"Permission denied for rename operation: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during rename: {e}")
        raise IOError(f"이름 변경/이동 중 예상치 못한 오류 발생: {e}")
