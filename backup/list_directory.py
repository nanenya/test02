#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지정된 디렉토리의 파일 및 하위 디렉토리 목록을 리스트로 반환합니다."""

import logging
from pathlib import Path
from typing import Union, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def list_directory(path: Union[str, Path]) -> List[str]:
    """지정된 디렉토리의 파일 및 하위 디렉토리 목록을 리스트로 반환합니다.

    이 함수는 주어진 경로의 바로 아래에 있는 항목들의 이름(문자열)을 리스트로
    반환합니다. 숨김 파일도 포함될 수 있으며, 재귀적으로 하위 디렉토리까지
    탐색하지는 않습니다.

    Args:
        path (Union[str, Path]): 내용을 조회할 디렉토리의 경로.

    Returns:
        List[str]: 디렉토리 내 항목들의 이름이 담긴 문자열 리스트.
                   디렉토리가 비어있으면 빈 리스트를 반환합니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우.
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우.
        FileNotFoundError: 지정된 경로가 존재하지 않을 경우.
        PermissionError: 디렉토리를 읽을 권한이 없을 경우.

    Example:
        >>> # 'my_project' 디렉토리에 'main.py', 'utils'가 있을 때
        >>> items = list_directory('./my_project')
        >>> print(items)
        ['main.py', 'utils']
    """
    if not path:
        raise ValueError("디렉토리 경로는 비어있을 수 없습니다.")

    logger.info(f"Attempting to list contents of directory: {path}")

    try:
        dir_path = Path(path)
        
        if not dir_path.exists():
            raise FileNotFoundError(f"지정된 경로가 존재하지 않습니다: {path}")

        if not dir_path.is_dir():
            raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {path}")

        contents = [item.name for item in dir_path.iterdir()]
        logger.info(f"Found {len(contents)} items in directory: {path}")
        return sorted(contents) # 일관된 결과를 위해 정렬

    except PermissionError as e:
        logger.error(f"Permission denied to read directory: {path}")
        raise
