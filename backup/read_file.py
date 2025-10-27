#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지정된 경로의 텍스트 파일을 읽어 그 내용을 반환합니다."""

import logging
import os
from pathlib import Path
from typing import Union

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_file(path: Union[str, Path], encoding: str = 'utf-8') -> str:
    """지정된 경로의 텍스트 파일 내용을 읽어 문자열로 반환합니다.

    이 함수는 파일 경로의 유효성을 검사하고, 파일이 존재하며 읽기 가능한지
    확인한 후, 지정된 인코딩으로 파일의 전체 내용을 읽어옵니다.
    보안을 위해 경로가 디렉토리이거나 존재하지 않는 경우 등 다양한 예외
    상황을 명확하게 처리합니다.

    Args:
        path (Union[str, Path]): 읽을 파일의 전체 또는 상대 경로입니다.
            Pathlib의 Path 객체도 지원합니다.
        encoding (str, optional): 파일을 읽을 때 사용할 인코딩 방식입니다.
            기본값은 'utf-8'입니다.

    Returns:
        str: 성공 시, 파일에서 읽어온 전체 텍스트 내용입니다.

    Raises:
        ValueError: 제공된 경로가 유효하지 않은 값(None 또는 빈 문자열)일 경우 발생합니다.
        FileNotFoundError: 지정된 경로에 파일이 존재하지 않을 경우 발생합니다.
        PermissionError: 파일을 읽을 수 있는 권한이 없을 경우 발생합니다.
        IsADirectoryError: 지정된 경로가 파일이 아닌 디렉토리일 경우 발생합니다.
        UnicodeDecodeError: 파일 내용을 지정된 인코딩으로 디코딩할 수 없을 경우 발생합니다.
        IOError: 그 외 다양한 입출력 관련 오류 발생 시 발생합니다.

    Example:
        >>> # 'example.txt' 파일이 "Hello, World!" 내용을 가질 때
        >>> try:
        ...     content = read_file('example.txt')
        ...     print(content)
        ... except FileNotFoundError:
        ...     print("Error: File not found.")
        'Hello, World!'
    """
    if not path:
        logger.error("Invalid path provided: path is empty or None.")
        raise ValueError("파일 경로는 비어있을 수 없습니다.")

    try:
        # 경로를 Path 객체로 변환하여 일관성 및 안정성 확보
        file_path = Path(path).resolve(strict=True)
        logger.info(f"Attempting to read file at resolved path: {file_path}")

        # 경로가 파일인지 재차 확인
        if not file_path.is_file():
            # resolve(strict=True)가 FileNotFoundError를 발생시키지만,
            # 경로가 심볼릭 링크 등 다른 타입일 경우를 대비한 방어 코드
            raise IsADirectoryError(f"지정된 경로는 파일이 아닙니다: {file_path}")

        # 파일 내용을 지정된 인코딩으로 읽기
        content = file_path.read_text(encoding=encoding)
        logger.info(f"Successfully read {len(content)} characters from {file_path}")
        return content

    except FileNotFoundError:
        logger.error(f"File not found at the specified path: {path}")
        raise  # 예외를 그대로 다시 발생시켜 호출자에게 전파
    except PermissionError:
        logger.error(f"Permission denied to read file: {path}")
        raise
    except IsADirectoryError:
        logger.error(f"The specified path is a directory, not a file: {path}")
        raise
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error reading file {path} with '{encoding}': {e}")
        raise
    except IOError as e:
        logger.error(f"An I/O error occurred while reading {path}: {e}")
        raise
    except Exception as e:
        # 예상치 못한 다른 모든 예외 처리
        logger.critical(f"An unexpected error occurred for path {path}: {e}")
        raise IOError(f"파일을 읽는 중 예상치 못한 오류 발생: {e}")
