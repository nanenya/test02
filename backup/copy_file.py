#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원본 파일의 내용을 대상 경로에 그대로 복사하여 새로운 파일을 생성합니다."""

import logging
import shutil
from pathlib import Path
from typing import Union

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def copy_file(
    source_path: Union[str, Path],
    destination_path: Union[str, Path],
    overwrite: bool = False
) -> str:
    """원본 파일의 내용을 대상 경로에 그대로 복사하여 새로운 파일을 생성합니다.

    이 함수는 원본 파일이 실제로 존재하는 파일인지, 대상 경로는 쓰기 가능한지 등을
    사전에 검증합니다. 대상 경로가 디렉토리일 경우, 원본 파일명 그대로 해당
    디렉토리 내에 파일을 복사합니다. `shutil.copy2`를 사용하여 파일 메타데이터
    (예: 수정 시간, 권한)도 함께 복사합니다.

    Args:
        source_path (Union[str, Path]): 복사할 원본 파일의 경로입니다.
        destination_path (Union[str, Path]): 파일을 복사하여 생성할 대상 경로입니다.
            경로가 디렉토리이면, 해당 디렉토리 안에 원본 파일명으로 생성됩니다.
        overwrite (bool, optional): 대상 경로에 파일이 이미 존재할 경우 덮어쓸지
            여부를 결정합니다. 기본값은 False로, 덮어쓰지 않고 예외를 발생시킵니다.

    Returns:
        str: 성공 시, 최종적으로 생성된 파일의 절대 경로를 문자열로 반환합니다.

    Raises:
        ValueError: 원본 또는 대상 경로가 유효하지 않은 값(None, 빈 문자열)일 경우.
        FileNotFoundError: 원본 파일이 존재하지 않을 경우.
        IsADirectoryError: 원본 경로가 파일이 아닌 디렉토리일 경우.
        FileExistsError: 대상 경로에 파일이 이미 존재하고 `overwrite`가 False일 경우.
        PermissionError: 원본 파일을 읽거나 대상 경로에 쓸 권한이 없을 경우.
        shutil.SameFileError: 원본과 대상 경로가 동일한 파일을 가리킬 경우.

    Example:
        >>> # 'source.txt'를 'destination.txt'로 복사
        >>> final_path = copy_file('path/to/source.txt', 'path/to/destination.txt')
        >>> print(f"파일이 다음 경로에 복사되었습니다: {final_path}")

        >>> # 'data.csv' 파일을 'backup/' 디렉토리 안으로 복사
        >>> final_path = copy_file('data.csv', 'backup/')
        >>> print(f"파일이 다음 경로에 복사되었습니다: {final_path}")
    """
    logger.info(
        f"Copy operation started. Source: '{source_path}', "
        f"Destination: '{destination_path}', Overwrite: {overwrite}"
    )

    # 1. 경로 유효성 검사
    if not source_path or not destination_path:
        raise ValueError("원본과 대상 경로는 비어있을 수 없습니다.")

    src = Path(source_path)
    dest = Path(destination_path)

    # 2. 원본 경로 검증
    if not src.exists():
        raise FileNotFoundError(f"원본 파일이 존재하지 않습니다: {src}")
    if not src.is_file():
        raise IsADirectoryError(f"원본 경로는 파일이어야 합니다 (디렉토리 감지): {src}")

    # 3. 대상 경로 처리 및 검증
    if dest.is_dir():
        # 대상 경로가 디렉토리이면, 원본 파일명을 사용하여 최종 경로 설정
        final_dest = dest / src.name
        logger.info(f"Destination is a directory. Final path set to: {final_dest}")
    else:
        final_dest = dest

    if final_dest.exists() and not overwrite:
        raise FileExistsError(
            f"대상 경로에 파일이 이미 존재합니다. 덮어쓰려면 `overwrite=True`로 설정하세요: {final_dest}"
        )

    # 4. 복사 실행
    try:
        # 대상 디렉토리가 존재하지 않으면 생성
        final_dest.parent.mkdir(parents=True, exist_ok=True)

        # shutil.copy2는 메타데이터까지 복사하여 더 안정적임
        shutil.copy2(src, final_dest)

        resolved_path = str(final_dest.resolve())
        logger.info(f"File successfully copied to: {resolved_path}")
        return resolved_path

    except PermissionError as e:
        logger.error(f"Permission denied during copy operation: {e}")
        raise
    except shutil.SameFileError as e:
        logger.error(f"Source and destination paths are the same file: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during file copy: {e}")
        raise IOError(f"파일 복사 중 예상치 못한 오류 발생: {e}")
