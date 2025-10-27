#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지정된 파일을 삭제합니다."""

import logging
from pathlib import Path
from typing import Union

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def delete_file(path: Union[str, Path], missing_ok: bool = False) -> bool:
    """지정된 파일을 삭제합니다.

    이 함수는 경로에 해당하는 파일이 실제로 존재하는 파일인지 확인한 후 삭제합니다.
    `missing_ok=True`로 설정하면 대상 파일이 존재하지 않더라도 FileNotFoundError
    예외를 발생시키지 않고 정상적으로(True) 반환하여 멱등성을 보장합니다.

    Args:
        path (Union[str, Path]): 삭제할 파일의 경로입니다.
        missing_ok (bool, optional): 삭제할 파일이 존재하지 않을 때 오류를
            발생시키지 않을지 여부. 기본값은 False입니다.

    Returns:
        bool: 파일이 성공적으로 삭제되었거나, missing_ok=True이고 파일이
              원래부터 없었을 경우 True를 반환합니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우.
        IsADirectoryError: 삭제하려는 대상이 파일이 아닌 디렉토리일 경우.
        FileNotFoundError: `missing_ok`가 False이고 파일이 존재하지 않을 경우.
        PermissionError: 파일을 삭제할 권한이 없을 경우.

    Example:
        >>> # 'temp.log' 파일 삭제
        >>> delete_file('logs/temp.log')
        True
        >>> # 파일이 없어도 오류를 내지 않음
        >>> delete_file('non_existent_file.tmp', missing_ok=True)
        True
    """
    if not path:
        raise ValueError("파일 경로는 비어있을 수 없습니다.")

    logger.info(f"Attempting to delete file: {path} (missing_ok={missing_ok})")

    try:
        file_path = Path(path)
        
        # 경로가 존재하지 않을 경우 처리
        if not file_path.exists():
            if missing_ok:
                logger.warning(f"File not found, but missing_ok is True. Skipping: {path}")
                return True
            else:
                raise FileNotFoundError(f"삭제할 파일이 존재하지 않습니다: {path}")

        # 경로가 디렉토리일 경우 에러 처리
        if file_path.is_dir():
            raise IsADirectoryError(f"삭제 대상은 파일이어야 합니다 (디렉토리 감지): {path}")

        file_path.unlink()
        logger.info(f"Successfully deleted file: {path}")
        return True

    except PermissionError as e:
        logger.error(f"Permission denied to delete file: {path}")
        raise
