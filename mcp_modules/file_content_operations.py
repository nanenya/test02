#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일 내용(Content) 처리를 위한 원자(Atomic) MCP 모음.

이 모듈은 텍스트 및 바이너리 파일에 대한 기본적인 CRUD(Create, Read, Update)
작업을 수행하는 고품질의 함수들을 제공합니다. 모든 함수는 보안, 안정성,
그리고 명확한 오류 처리를 최우선으로 고려하여 설계되었습니다.
"""

import logging
from pathlib import Path
from typing import Union, List, ByteString

# --- 모듈 레벨 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _prepare_write_path(path: Union[str, Path]) -> Path:
    """쓰기 작업을 위해 경로를 검증하고 준비하는 내부 헬퍼 함수."""
    if not path:
        raise ValueError("파일 경로는 비어있거나 None일 수 없습니다.")

    p = Path(path).resolve()

    if p.is_dir():
        raise IsADirectoryError(f"파일을 쓸 수 없습니다. 해당 경로는 디렉토리입니다: {p}")

    # 상위 디렉토리가 없으면 재귀적으로 생성
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_file(path: Union[str, Path], encoding: str = 'utf-8') -> str:
    """지정된 경로의 텍스트 파일 내용을 전부 읽어 문자열로 반환합니다.

    Args:
        path (Union[str, Path]): 읽을 파일의 경로.
        encoding (str, optional): 파일을 읽을 때 사용할 인코딩. 기본값 'utf-8'.

    Returns:
        str: 파일의 전체 텍스트 내용.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우.
        PermissionError: 파일을 읽을 권한이 없을 경우.
        IsADirectoryError: 경로가 파일이 아닌 디렉토리일 경우.
        UnicodeDecodeError: 지정된 인코딩으로 파일을 디코딩할 수 없을 경우.
        ValueError: 경로가 유효하지 않을 경우.
    
    Example:
        >>> content = read_file('my_document.txt')
        >>> print(content)
    """
    logger.info(f"Attempting to read text file: {path}")
    if not path:
        raise ValueError("파일 경로는 비어있거나 None일 수 없습니다.")
        
    try:
        p = Path(path).resolve(strict=True)
        if not p.is_file():
            raise IsADirectoryError(f"해당 경로는 파일이 아닙니다: {p}")
        
        content = p.read_text(encoding=encoding)
        logger.info(f"Successfully read {len(content)} characters from {p}")
        return content
    except (FileNotFoundError, PermissionError, IsADirectoryError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error reading file {path}: {e}")
        raise IOError(f"파일 읽기 중 예상치 못한 오류 발생: {e}")

def read_binary_file(path: Union[str, Path]) -> bytes:
    """지정된 경로의 바이너리 파일(이미지 등) 내용을 바이트 형태로 반환합니다.

    Args:
        path (Union[str, Path]): 읽을 바이너리 파일의 경로.

    Returns:
        bytes: 파일의 전체 바이너리 데이터.

    Raises:
        FileNotFoundError, PermissionError, IsADirectoryError, ValueError 등
    
    Example:
        >>> image_data = read_binary_file('photo.jpg')
    """
    logger.info(f"Attempting to read binary file: {path}")
    if not path:
        raise ValueError("파일 경로는 비어있거나 None일 수 없습니다.")

    try:
        p = Path(path).resolve(strict=True)
        if not p.is_file():
            raise IsADirectoryError(f"해당 경로는 파일이 아닙니다: {p}")

        content = p.read_bytes()
        logger.info(f"Successfully read {len(content)} bytes from {p}")
        return content
    except (FileNotFoundError, PermissionError, IsADirectoryError) as e:
        logger.error(f"Failed to read binary file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error reading binary file {path}: {e}")
        raise IOError(f"바이너리 파일 읽기 중 예상치 못한 오류 발생: {e}")

def write_file(path: Union[str, Path], content: str, encoding: str = 'utf-8') -> str:
    """지정된 경로에 텍스트 내용을 씁니다. 기존 파일은 덮어씁니다.

    Args:
        path (Union[str, Path]): 내용을 쓸 파일의 경로.
        content (str): 파일에 쓸 텍스트 내용.
        encoding (str, optional): 파일을 쓸 때 사용할 인코딩. 기본값 'utf-8'.

    Returns:
        str: 성공 시, 기록된 파일의 절대 경로.

    Raises:
        PermissionError, IsADirectoryError, ValueError 등
    
    Example:
        >>> final_path = write_file('log.txt', 'This is a log message.')
    """
    logger.info(f"Attempting to write text file: {path}")
    try:
        p = _prepare_write_path(path)
        p.write_text(content, encoding=encoding)
        logger.info(f"Successfully wrote {len(content)} characters to {p}")
        return str(p)
    except (PermissionError, IsADirectoryError) as e:
        logger.error(f"Failed to write file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error writing file {path}: {e}")
        raise IOError(f"파일 쓰기 중 예상치 못한 오류 발생: {e}")

def write_binary_file(path: Union[str, Path], content: ByteString) -> str:
    """지정된 경로에 바이너리 데이터를 씁니다. 기존 파일은 덮어씁니다.

    Args:
        path (Union[str, Path]): 내용을 쓸 파일의 경로.
        content (ByteString): 파일에 쓸 바이너리 데이터 (bytes, bytearray 등).

    Returns:
        str: 성공 시, 기록된 파일의 절대 경로.

    Raises:
        PermissionError, IsADirectoryError, ValueError 등
    
    Example:
        >>> data = b'\\xDE\\xAD\\xBE\\xEF'
        >>> final_path = write_binary_file('data.bin', data)
    """
    logger.info(f"Attempting to write binary file: {path}")
    try:
        p = _prepare_write_path(path)
        p.write_bytes(content)
        logger.info(f"Successfully wrote {len(content)} bytes to {p}")
        return str(p)
    except (PermissionError, IsADirectoryError) as e:
        logger.error(f"Failed to write binary file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error writing binary file {path}: {e}")
        raise IOError(f"바이너리 파일 쓰기 중 예상치 못한 오류 발생: {e}")

def append_to_file(path: Union[str, Path], content: str, encoding: str = 'utf-8') -> str:
    """기존 텍스트 파일의 끝에 내용을 추가합니다. 파일이 없으면 새로 생성합니다.

    Args:
        path (Union[str, Path]): 내용을 추가할 파일의 경로.
        content (str): 파일에 추가할 텍스트 내용.
        encoding (str, optional): 파일을 열 때 사용할 인코딩. 기본값 'utf-8'.

    Returns:
        str: 성공 시, 기록된 파일의 절대 경로.

    Raises:
        PermissionError, IsADirectoryError, ValueError 등
    
    Example:
        >>> final_path = append_to_file('log.txt', '\\nAnother log message.')
    """
    logger.info(f"Attempting to append to text file: {path}")
    try:
        p = _prepare_write_path(path)
        with p.open(mode='a', encoding=encoding) as f:
            f.write(content)
        logger.info(f"Successfully appended {len(content)} characters to {p}")
        return str(p)
    except (PermissionError, IsADirectoryError) as e:
        logger.error(f"Failed to append to file {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error appending to file {path}: {e}")
        raise IOError(f"파일 이어쓰기 중 예상치 못한 오류 발생: {e}")
