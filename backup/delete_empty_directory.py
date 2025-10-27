#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비어 있는 디렉토리를 삭제합니다."""

import logging
from pathlib import Path
from typing import Union

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def delete_empty_directory(path: Union[str, Path]) -> bool:
    """비어 있는 디렉토리를 삭제합니다.

    이 함수는 지정된 경로가 존재하고, 디렉토리이며, 비어 있을 경우에만
    해당 디렉토리를 삭제합니다. 내용이 있는 디렉토리를 삭제하려고 하면
    OSError가 발생하여 데이터 손실을 방지합니다.

    Args:
        path (Union[str, Path]): 삭제할 비어 있는 디렉토리의 경로입니다.

    Returns:
        bool: 성공적으로 디렉토리를 삭제했을 경우 True를 반환합니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우.
        NotADirectoryError: 삭제하려는 대상이 디렉토리가 아닐 경우.
        FileNotFoundError: 삭제할 디렉토리가 존재하지 않을 경우.
        OSError: 디렉토리가 비어있지 않을 경우.
        PermissionError: 디렉토리를 삭제할 권한이 없을 경우.

    Example:
        >>> create_directory('empty_dir')
        >>> delete_empty_directory('empty_dir')
        True
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
        dir_path.rmdir() # <-- 이 작업에서만 OSError가 발생할 수 있습니다.
        logger.info(f"Successfully deleted empty directory: {path}")
        return True
    except OSError as e: # <-- 이제 "비어있지 않은 디렉토리" 오류만 정확히 잡습니다.
        logger.error(f"Failed to delete directory because it is not empty: {path}")
        raise OSError(f"디렉토리가 비어있지 않아 삭제할 수 없습니다: {path}") from e
    except PermissionError as e:
        logger.error(f"Permission denied to delete directory: {path}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while deleting directory {path}: {e}")
        raise IOError(f"디렉토리 삭제 중 예상치 못한 오류 발생: {e}")
