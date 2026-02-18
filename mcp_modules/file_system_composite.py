#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_system_composite.py: AI 에이전트를 위한 복합 파일 시스템 작업 MCP 라이브러리

여러 원자적 파일 작업을 조합하여 검색, 이동, 복사, 텍스트 치환 등
더 복잡한 파일 시스템 작업을 제공합니다.

MCP 서버 대체 가능 여부:
  - filesystem MCP 서버의 search_files 도구로 find_files 부분 대체 가능
  - move는 filesystem MCP의 move_file로 대체 가능
  - 나머지 함수들은 로컬 구현 필요
"""

import itertools
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --- 보안 관련 설정 ---
ALLOWED_BASE_PATH = Path(
    os.environ.get("ALLOWED_BASE_PATH", Path(__file__).resolve().parent.parent)
).resolve()


def _validate_path(path: str) -> Path:
    """경로가 ALLOWED_BASE_PATH 내에 있는지 검증하고 절대 경로 Path 객체를 반환합니다.

    Args:
        path (str): 검증할 경로 문자열.

    Returns:
        Path: 검증된 절대 경로 Path 객체.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
    """
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ALLOWED_BASE_PATH):
        logger.error(f"허용되지 않은 경로 접근 시도: {path}")
        raise ValueError(f"보안 오류: 허용된 디렉토리 외부의 경로에는 접근할 수 없습니다: {path}")
    return resolved


def move(source: str, dest: str) -> str:
    """파일 또는 디렉토리를 다른 위치로 이동합니다.

    Args:
        source (str): 이동할 원본 경로.
        dest (str): 이동할 대상 경로.

    Returns:
        str: 이동 완료 후 실제 경로 문자열.

    Raises:
        ValueError: source 또는 dest가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: source가 존재하지 않는 경우.

    Example:
        >>> # move("/tmp/src/file.txt", "/tmp/dst/file.txt")
    """
    logger.info(f"이동 시도: {source} → {dest}")
    resolved_source = _validate_path(source)
    _validate_path(dest)
    if not resolved_source.exists():
        raise FileNotFoundError(f"원본 경로를 찾을 수 없습니다: {source}")
    result = shutil.move(str(resolved_source), dest)
    logger.info(f"이동 완료: {result}")
    return str(result)


def copy_directory(source_dir: str, dest_dir: str) -> str:
    """디렉토리 전체를 재귀적으로 복사합니다.

    Args:
        source_dir (str): 복사할 원본 디렉토리 경로.
        dest_dir (str): 복사될 대상 디렉토리 경로 (없으면 생성).

    Returns:
        str: 복사된 대상 디렉토리 경로.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: source_dir이 존재하지 않는 경우.
        NotADirectoryError: source_dir이 디렉토리가 아닌 경우.

    Example:
        >>> # copy_directory("/tmp/src_dir", "/tmp/dst_dir")
    """
    logger.info(f"디렉토리 복사 시도: {source_dir} → {dest_dir}")
    resolved_source = _validate_path(source_dir)
    _validate_path(dest_dir)
    if not resolved_source.exists():
        raise FileNotFoundError(f"원본 디렉토리를 찾을 수 없습니다: {source_dir}")
    if not resolved_source.is_dir():
        raise NotADirectoryError(f"원본 경로가 디렉토리가 아닙니다: {source_dir}")
    result = shutil.copytree(str(resolved_source), dest_dir)
    logger.info(f"디렉토리 복사 완료: {result}")
    return str(result)


def find_files(directory: str, pattern: str) -> List[str]:
    """지정한 디렉토리에서 glob 패턴에 매칭되는 파일을 재귀 탐색합니다.

    Args:
        directory (str): 탐색할 디렉토리 경로.
        pattern (str): glob 패턴 (예: "*.py", "**/*.txt").

    Returns:
        List[str]: 매칭된 파일 경로 목록.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: directory가 존재하지 않는 경우.

    Example:
        >>> files = find_files("/tmp", "*.txt")
        >>> isinstance(files, list)
        True
    """
    logger.info(f"파일 검색 시도: {directory} / 패턴: {pattern}")
    resolved = _validate_path(directory)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory}")
    matches = [str(p) for p in resolved.rglob(pattern)]
    logger.info(f"{len(matches)}개 파일 매칭: {pattern}")
    return matches


def find_text_in_files(directory: str, text: str) -> List[str]:
    """디렉토리 내 모든 텍스트 파일에서 특정 텍스트를 포함하는 파일을 검색합니다.

    바이너리 파일 또는 읽기 실패 파일은 건너뜁니다.

    Args:
        directory (str): 탐색할 디렉토리 경로.
        text (str): 검색할 텍스트.

    Returns:
        List[str]: 텍스트를 포함하는 파일 경로 목록.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: directory가 존재하지 않는 경우.

    Example:
        >>> result = find_text_in_files("/tmp", "hello")
        >>> isinstance(result, list)
        True
    """
    logger.info(f"텍스트 검색 시도: '{text}' in {directory}")
    resolved = _validate_path(directory)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory}")
    matched = []
    for root, _, files in os.walk(resolved):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='strict') as f:
                    for line in f:
                        if text in line:
                            matched.append(fpath)
                            break
            except (UnicodeDecodeError, PermissionError):
                continue
    logger.info(f"{len(matched)}개 파일에서 텍스트 발견")
    return matched


def find_large_files(directory: str, min_size_mb: float) -> List[str]:
    """지정한 크기 이상의 파일을 찾아 경로 목록으로 반환합니다.

    Args:
        directory (str): 탐색할 디렉토리 경로.
        min_size_mb (float): 최소 파일 크기 (MB 단위).

    Returns:
        List[str]: 기준 크기 이상 파일 경로 목록.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: directory가 존재하지 않는 경우.

    Example:
        >>> large = find_large_files("/tmp", 1.0)
        >>> isinstance(large, list)
        True
    """
    logger.info(f"대용량 파일 검색: {directory} / 최소 {min_size_mb}MB")
    resolved = _validate_path(directory)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory}")
    min_bytes = min_size_mb * 1024 * 1024
    large_files = []
    for root, _, files in os.walk(resolved):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.stat(fpath).st_size >= min_bytes:
                    large_files.append(fpath)
            except OSError:
                continue
    logger.info(f"{len(large_files)}개 대용량 파일 발견")
    return large_files


def read_specific_lines(path: str, start_line: int, end_line: int) -> List[str]:
    """파일의 특정 범위 줄(1-기반)을 읽어 반환합니다.

    Args:
        path (str): 읽을 파일 경로.
        start_line (int): 시작 줄 번호 (1-기반, 포함).
        end_line (int): 끝 줄 번호 (1-기반, 포함).

    Returns:
        List[str]: 해당 범위의 줄 목록 (줄바꿈 문자 포함).

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부이거나, 줄 번호가 유효하지 않은 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.

    Example:
        >>> lines = read_specific_lines("/etc/hostname", 1, 1)
        >>> isinstance(lines, list)
        True
    """
    logger.info(f"특정 줄 읽기 시도: {path} ({start_line}~{end_line}줄)")
    if start_line < 1 or end_line < start_line:
        raise ValueError(f"유효하지 않은 줄 번호: start_line={start_line}, end_line={end_line}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    with open(resolved, 'r', encoding='utf-8') as f:
        lines = list(itertools.islice(f, start_line - 1, end_line))
    logger.info(f"{len(lines)}줄 읽기 완료")
    return lines


def replace_text_in_file(path: str, old_text: str, new_text: str) -> bool:
    """파일 내 특정 텍스트를 다른 텍스트로 치환합니다.

    Args:
        path (str): 치환할 파일 경로.
        old_text (str): 찾을 텍스트.
        new_text (str): 대체할 텍스트.

    Returns:
        bool: 변경이 발생한 경우 True, 변경 없으면 False.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.

    Example:
        >>> replace_text_in_file("/tmp/test.txt", "hello", "world")
        True
    """
    logger.info(f"텍스트 치환 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    content = resolved.read_text(encoding='utf-8')
    new_content = content.replace(old_text, new_text)
    if new_content == content:
        logger.info("치환할 텍스트 없음, 변경 없음.")
        return False
    resolved.write_text(new_content, encoding='utf-8')
    logger.info(f"텍스트 치환 완료: {path}")
    return True


def get_directory_size(directory: str) -> int:
    """디렉토리 전체 크기(바이트)를 재귀적으로 계산합니다.

    Args:
        directory (str): 크기를 계산할 디렉토리 경로.

    Returns:
        int: 디렉토리 전체 크기 (바이트).

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 디렉토리가 존재하지 않는 경우.

    Example:
        >>> size = get_directory_size("/tmp")
        >>> isinstance(size, int)
        True
    """
    logger.info(f"디렉토리 크기 계산: {directory}")
    resolved = _validate_path(directory)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory}")
    total = 0
    for root, _, files in os.walk(resolved):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                total += os.stat(fpath).st_size
            except OSError:
                continue
    logger.info(f"디렉토리 크기: {total} 바이트")
    return total


def batch_rename(directory: str, pattern: str, new_name_format: str) -> List[str]:
    """디렉토리 내 패턴에 매칭되는 파일들을 일괄 이름 변경합니다.

    new_name_format은 '{}'를 포함해야 하며, 이 위치에 순서(0-기반)가 삽입됩니다.
    예: "file_{}.txt" → file_0.txt, file_1.txt, ...

    Args:
        directory (str): 대상 디렉토리 경로.
        pattern (str): glob 패턴 (예: "*.tmp").
        new_name_format (str): 새 이름 형식. '{}'를 반드시 포함.

    Returns:
        List[str]: 변경 완료된 새 파일 경로 목록.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부이거나, new_name_format에 '{}'가 없는 경우.
        FileNotFoundError: directory가 존재하지 않는 경우.

    Example:
        >>> # batch_rename("/tmp/files", "*.tmp", "renamed_{}.txt")
    """
    logger.info(f"일괄 이름 변경: {directory} / 패턴: {pattern} / 형식: {new_name_format}")
    if '{}' not in new_name_format:
        raise ValueError("new_name_format에 '{}'가 포함되어야 합니다.")
    resolved = _validate_path(directory)
    if not resolved.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory}")
    matched = sorted(resolved.glob(pattern))
    renamed = []
    for idx, fpath in enumerate(matched):
        new_name = new_name_format.format(idx)
        new_path = fpath.parent / new_name
        fpath.rename(new_path)
        renamed.append(str(new_path))
        logger.info(f"  {fpath.name} → {new_name}")
    logger.info(f"{len(renamed)}개 파일 이름 변경 완료")
    return renamed


def delete_directory_recursively(path: str) -> bool:
    """디렉토리를 내용물과 함께 재귀적으로 삭제합니다.

    경고: 이 작업은 되돌릴 수 없습니다. ALLOWED_BASE_PATH 검증이 반드시 적용됩니다.

    Args:
        path (str): 삭제할 디렉토리 경로.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 경로가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 경로가 존재하지 않는 경우.
        NotADirectoryError: 경로가 디렉토리가 아닌 경우.

    Example:
        >>> # delete_directory_recursively("/tmp/to_delete")
    """
    logger.info(f"디렉토리 재귀 삭제 시도: {path}")
    resolved = _validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"디렉토리가 아닙니다: {path}")
    shutil.rmtree(resolved)
    logger.info(f"디렉토리 재귀 삭제 완료: {resolved}")
    return True
