#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지정된 경로에 새로운 디렉토리(폴더)를 생성합니다."""

import logging
from pathlib import Path
from typing import Union

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_directory(path: Union[str, Path], exist_ok: bool = False) -> str:
    """지정된 경로에 새로운 디렉토리를 생성합니다.

    이 함수는 경로 문자열이나 Path 객체를 받아 디렉토리를 생성합니다.
    필요한 모든 상위 부모 디렉토리도 함께 생성합니다. (`parents=True`)
    멱등성(Idempotency)을 위해 `exist_ok=True`로 설정하면 대상 디렉토리가
    이미 존재하더라도 오류를 발생시키지 않고 정상적으로 종료됩니다.

    Args:
        path (Union[str, Path]): 생성할 디렉토리의 경로입니다.
        exist_ok (bool, optional): 디렉토리가 이미 존재할 때 오류를 발생시키지
            않을지 여부를 결정합니다. 기본값은 False입니다.

    Returns:
        str: 성공 시, 생성된 디렉토리의 절대 경로를 문자열로 반환합니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우.
        FileExistsError: 경로가 이미 존재하는데 `exist_ok`가 False일 경우,
                         또는 경로에 동일한 이름의 파일이 이미 존재할 경우.
        PermissionError: 디렉토리를 생성할 권한이 없을 경우.

    Example:
        >>> # 새로운 디렉토리 생성
        >>> created_path = create_directory('./data/raw_data')
        >>> print(f"디렉토리 생성 완료: {created_path}")

        >>> # 이미 존재해도 오류를 내지 않음
        >>> create_directory('./data/raw_data', exist_ok=True)
    """
    if not path:
        raise ValueError("디렉토리 경로는 비어있을 수 없습니다.")

    logger.info(f"Attempting to create directory: {path} (exist_ok={exist_ok})")
    
    try:
        dir_path = Path(path)
        dir_path.mkdir(parents=True, exist_ok=exist_ok)
        
        resolved_path = str(dir_path.resolve())
        logger.info(f"Successfully created or confirmed directory at: {resolved_path}")
        return resolved_path

    except FileExistsError as e:
        logger.error(f"Failed to create directory. A file with the same name exists: {path}")
        raise FileExistsError(f"해당 경로에 파일이 이미 존재하여 디렉토리를 생성할 수 없습니다: {path}") from e
    except PermissionError as e:
        logger.error(f"Permission denied to create directory at: {path}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred while creating directory {path}: {e}")
        raise IOError(f"디렉토리 생성 중 예상치 못한 오류 발생: {e}")
