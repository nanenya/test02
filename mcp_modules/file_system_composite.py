#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일 시스템 복합 MCP(Composite Mission Control Primitives) 모음.

이 모듈은 파일 및 디렉토리 관리를 위한 고수준 복합 기능들을 제공합니다.
각 함수는 상세한 유효성 검사, 예외 처리, 로깅을 포함하여 안정적이고
예측 가능한 동작을 보장하도록 설계되었습니다.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Union
from .file_content_operations import read_file

# --- 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. 이동 및 복사 (Move & Copy)
# ==============================================================================

def move(source: Union[str, Path], destination: Union[str, Path]) -> str:
    """파일 또는 디렉토리를 다른 위치로 이동하거나 이름을 변경합니다.

    `shutil.move`를 사용하여 운영체제 수준에서 효율적으로 작업을 수행합니다.
    대상 경로가 디렉토리이면 해당 디렉토리 안으로 소스를 이동합니다.

    Args:
        source (Union[str, Path]): 이동할 원본 파일 또는 디렉토리의 경로입니다.
        destination (Union[str, Path]): 이동할 대상 경로입니다.

    Returns:
        str: 최종적으로 이동된 파일 또는 디렉토리의 절대 경로를 반환합니다.

    Raises:
        FileNotFoundError: 원본 경로가 존재하지 않을 경우 발생합니다.
        shutil.Error: 대상이 이미 존재하거나 권한 문제 등 이동 중 오류 발생 시.

    Example:
        >>> # 파일 이름 변경
        >>> move('old_name.txt', 'new_name.txt')
        '/path/to/new_name.txt'
        >>> # 파일을 디렉토리로 이동
        >>> move('data.csv', 'archive/')
        '/path/to/archive/data.csv'
    """
    logger.info(f"Attempting to move '{source}' to '{destination}'")
    if not Path(source).exists():
        raise FileNotFoundError(f"원본 경로가 존재하지 않습니다: {source}")
    
    try:
        final_path = shutil.move(str(source), str(destination))
        logger.info(f"Successfully moved to '{final_path}'")
        return str(Path(final_path).resolve())
    except shutil.Error as e:
        logger.error(f"Failed to move '{source}': {e}")
        raise

def copy_directory(source_dir: Union[str, Path], dest_dir: Union[str, Path]) -> str:
    """디렉토리의 모든 내용을 재귀적으로 복사합니다.

    `shutil.copytree`를 사용하여 디렉토리 구조와 파일을 모두 복사합니다.
    대상 디렉토리는 존재하지 않아야 합니다.

    Args:
        source_dir (Union[str, Path]): 복사할 원본 디렉토리 경로입니다.
        dest_dir (Union[str, Path]): 복사될 대상 디렉토리 경로입니다.

    Returns:
        str: 성공 시, 생성된 대상 디렉토리의 절대 경로를 반환합니다.

    Raises:
        NotADirectoryError: 원본 경로가 디렉토리가 아닐 경우 발생합니다.
        FileExistsError: 대상 디렉토리가 이미 존재할 경우 발생합니다.
        shutil.Error: 복사 중 권한 문제 등 오류 발생 시.

    Example:
        >>> copy_directory('project/src', 'project/backup/src_v1')
        '/path/to/project/backup/src_v1'
    """
    logger.info(f"Attempting to copy directory '{source_dir}' to '{dest_dir}'")
    src = Path(source_dir)
    if not src.is_dir():
        raise NotADirectoryError(f"원본 경로는 디렉토리여야 합니다: {source_dir}")

    try:
        shutil.copytree(str(source_dir), str(dest_dir))
        resolved_path = str(Path(dest_dir).resolve())
        logger.info(f"Directory successfully copied to '{resolved_path}'")
        return resolved_path
    except (FileExistsError, shutil.Error) as e:
        logger.error(f"Failed to copy directory '{source_dir}': {e}")
        raise

# ==============================================================================
# 2. 검색 및 탐색 (Search & Find)
# ==============================================================================

def find_files(directory: Union[str, Path], pattern: str) -> List[str]:
    """특정 디렉토리 하위에서 파일명 패턴과 일치하는 모든 파일을 재귀적으로 찾습니다.

    Args:
        directory (Union[str, Path]): 검색을 시작할 최상위 디렉토리입니다.
        pattern (str): 찾을 파일의 패턴 (예: '*.py', 'report_*.docx').

    Returns:
        List[str]: 패턴과 일치하는 파일들의 절대 경로 리스트를 반환합니다.

    Raises:
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우 발생합니다.

    Example:
        >>> find_files('project/src', '*.py')
        ['/path/to/project/src/main.py', '/path/to/project/src/utils/helpers.py']
    """
    logger.info(f"Searching for files with pattern '{pattern}' in '{directory}'")
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {directory}")

    found_files = [str(p.resolve()) for p in dir_path.rglob(pattern) if p.is_file()]
    logger.info(f"Found {len(found_files)} matching files.")
    return found_files

def find_text_in_files(directory: Union[str, Path], text: str) -> Dict[str, List[int]]:
    """특정 디렉토리의 모든 텍스트 파일에서 주어진 텍스트를 검색합니다.

    Args:
        directory (Union[str, Path]): 검색할 텍스트 파일이 있는 디렉토리입니다.
        text (str): 검색할 텍스트 문자열입니다.

    Returns:
        Dict[str, List[int]]: {파일명: [줄 번호]} 형태로 결과를 반환합니다.

    Raises:
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우 발생합니다.

    Example:
        >>> find_text_in_files('logs/', 'ERROR')
        {'/path/to/logs/app.log': [10, 25], '/path/to/logs/db.log': [101]}
    """
    logger.info(f"Searching for text '{text}' in directory '{directory}'")
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {directory}")

    results = {}
    for file_path in dir_path.rglob('*'):
        if file_path.is_file():
            try:
                with file_path.open('r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if text in line:
                            abs_path = str(file_path.resolve())
                            if abs_path not in results:
                                results[abs_path] = []
                            results[abs_path].append(i)
            except (UnicodeDecodeError, PermissionError):
                # 바이너리 파일이나 읽을 수 없는 파일은 건너뜁니다.
                logger.warning(f"Skipping non-text or unreadable file: {file_path}")
                continue
    logger.info(f"Found text in {len(results)} files.")
    return results

def find_large_files(directory: Union[str, Path], min_size_mb: int) -> List[str]:
    """지정된 크기(MB) 이상의 대용량 파일을 찾습니다.

    Args:
        directory (Union[str, Path]): 검색을 시작할 디렉토리입니다.
        min_size_mb (int): 파일 크기의 최소 기준 (MB 단위).

    Returns:
        List[str]: 기준보다 크거나 같은 파일들의 절대 경로 리스트를 반환합니다.

    Raises:
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우 발생합니다.
        ValueError: `min_size_mb`가 0보다 작은 음수일 경우.

    Example:
        >>> find_large_files('/data', 1024) # 1GB 이상 파일 검색
        ['/data/videos/movie.mkv', '/data/db_backup.zip']
    """
    if min_size_mb < 0:
        raise ValueError("min_size_mb는 0 이상의 정수여야 합니다.")
    logger.info(f"Searching for files larger than {min_size_mb}MB in '{directory}'")
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {directory}")

    min_size_bytes = min_size_mb * 1024 * 1024
    large_files = []
    for file_path in dir_path.rglob('*'):
        if file_path.is_file():
            try:
                if file_path.stat().st_size >= min_size_bytes:
                    large_files.append(str(file_path.resolve()))
            except FileNotFoundError:
                # 심볼릭 링크 등 순회 중 파일이 사라진 경우
                continue
    logger.info(f"Found {len(large_files)} large files.")
    return large_files

# ==============================================================================
# 3. 내용 조작 (Content Manipulation)
# ==============================================================================

def read_specific_lines(path: Union[str, Path], start_line: int, end_line: int) -> str:
    """파일의 특정 줄 범위만 읽어옵니다. 줄 번호는 1부터 시작합니다.

    Args:
        path (Union[str, Path]): 읽을 파일의 경로입니다.
        start_line (int): 읽기 시작할 줄 번호 (포함).
        end_line (int): 읽기를 마칠 줄 번호 (포함).

    Returns:
        str: 지정된 범위의 텍스트 내용을 합친 문자열을 반환합니다.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우.
        ValueError: 줄 번호가 유효하지 않을 경우 (예: start > end, < 1).

    Example:
        >>> # 파일의 10번째부터 20번째 줄까지 읽기
        >>> content = read_specific_lines('app.log', 10, 20)
    """
    if start_line < 1 or end_line < start_line:
        raise ValueError("줄 번호 범위가 유효하지 않습니다 (start >= 1, end >= start).")
    logger.info(f"Reading lines {start_line}-{end_line} from '{path}'")
    
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    try:
        with file_path.open('r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 슬라이스는 0-based index이므로 조정
        selected_lines = lines[start_line-1:end_line]
        return "".join(selected_lines)
    except Exception as e:
        logger.error(f"Failed to read specific lines from '{path}': {e}")
        raise

def replace_text_in_file(path: Union[str, Path], old_text: str, new_text: str) -> bool:
    """파일 내의 특정 문자열을 찾아 다른 문자열로 모두 교체합니다.

    파일 전체 내용을 메모리에 로드하므로 매우 큰 파일에는 주의가 필요합니다.

    Args:
        path (Union[str, Path]): 수정할 파일의 경로입니다.
        old_text (str): 바꿀 대상이 되는 기존 문자열입니다.
        new_text (str): 새로 바꿀 문자열입니다.

    Returns:
        bool: 하나 이상의 변경이 발생했다면 True, 변경이 없었다면 False를 반환합니다.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우.

    Example:
        >>> # 설정 파일에서 DB 주소 변경
        >>> updated = replace_text_in_file('config.ini', 'localhost', 'db.prod.server')
    """
    logger.info(f"Replacing '{old_text}' with '{new_text}' in file '{path}'")
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    try:
        original_content = file_path.read_text('utf-8')
        if old_text not in original_content:
            logger.info("No text to replace. File remains unchanged.")
            return False
            
        new_content = original_content.replace(old_text, new_text)
        file_path.write_text(new_content, 'utf-8')
        logger.info("File was successfully updated.")
        return True
    except Exception as e:
        logger.error(f"Failed to replace text in '{path}': {e}")
        raise

def get_directory_size(directory: Union[str, Path]) -> int:
    """디렉토리와 그 하위 모든 파일의 총 크기를 바이트 단위로 계산합니다.

    Args:
        directory (Union[str, Path]): 크기를 계산할 디렉토리 경로.

    Returns:
        int: 디렉토리의 총 크기 (bytes).

    Raises:
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우 발생합니다.

    Example:
        >>> total_bytes = get_directory_size('my_project/')
        >>> print(f"Total size: {total_bytes / (1024*1024):.2f} MB")
    """
    logger.info(f"Calculating total size of directory '{directory}'")
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {directory}")

    total_size = 0
    for entry in dir_path.rglob('*'):
        if entry.is_file():
            try:
                total_size += entry.stat().st_size
            except FileNotFoundError:
                # 순회 중 파일이 삭제된 경우
                continue
    logger.info(f"Total size of '{directory}' is {total_size} bytes.")
    return total_size

# ==============================================================================
# 4. 일괄 처리 (Batch Processing)
# ==============================================================================

def batch_rename(directory: Union[str, Path], pattern: str, new_name_format: str) -> Dict[str, str]:
    """특정 패턴의 파일들을 찾아 정해진 형식으로 일괄 이름을 변경합니다.

    `new_name_format`에서 `{}`는 패턴의 `*` 부분과 치환됩니다.
    예: pattern='img_*.jpg', new_name_format='paris_{}.jpg'
        'img_001.jpg' -> 'paris_001.jpg'

    Args:
        directory (Union[str, Path]): 대상 파일들이 있는 디렉토리.
        pattern (str): 변경할 파일들을 찾는 패턴 (e.g., 'img_*.jpg'). `*`는 한 번만 사용 가능.
        new_name_format (str): 새 파일 이름 형식. `{}`를 포함해야 합니다.

    Returns:
        Dict[str, str]: {원본 경로: 새 경로} 형태의 변경 내역 딕셔너리.

    Raises:
        NotADirectoryError: 경로가 디렉토리가 아닐 경우.
        ValueError: 패턴이나 새 이름 형식이 잘못되었을 경우.

    Example:
        >>> batch_rename('photos/', 'IMG_*.JPG', 'Vacation_{}.jpg')
        {'/path/photos/IMG_01.JPG': '/path/photos/Vacation_01.jpg'}
    """
    if '*' not in pattern or '{}' not in new_name_format:
        raise ValueError("패턴에는 '*'가, 새 이름 형식에는 '{}'가 포함되어야 합니다.")
    if pattern.count('*') > 1:
        raise ValueError("패턴에서 와일드카드 '*'는 한 번만 사용할 수 있습니다.")

    logger.info(f"Starting batch rename in '{directory}' with pattern '{pattern}'")
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {directory}")

    prefix, suffix = pattern.split('*')
    renamed_files = {}

    for old_path in dir_path.glob(pattern):
        if old_path.is_file():
            name = old_path.name
            # `*`에 해당하는 부분 추출
            wildcard_part = name.removeprefix(prefix).removesuffix(suffix)
            
            new_name = new_name_format.format(wildcard_part)
            new_path = old_path.with_name(new_name)

            if new_path.exists():
                logger.warning(f"Skipping rename for '{old_path}' because target '{new_path}' already exists.")
                continue

            old_path.rename(new_path)
            renamed_files[str(old_path)] = str(new_path)
            logger.info(f"Renamed '{old_path}' to '{new_path}'")
            
    return renamed_files

def delete_directory_recursively(path: Union[str, Path]) -> str:
    """비어있지 않은 디렉토리와 그 안의 모든 하위 파일/디렉토리를 삭제합니다.

    매우 파괴적인 작업이므로 사용에 극도의 주의가 필요합니다.

    Args:
        path (Union[str, Path]): 삭제할 디렉토리의 경로.

    Returns:
        str: 성공적으로 삭제되었다는 메시지를 반환합니다.

    Raises:
        NotADirectoryError: 지정된 경로가 디렉토리가 아닐 경우.
        PermissionError: 권한이 없어 삭제에 실패할 경우.

    Example:
        >>> # 절대 사용에 주의!
        >>> delete_directory_recursively('/tmp/obsolete_data')
        'Directory /tmp/obsolete_data and all its contents have been deleted.'
    """
    logger.warning(f"Attempting to recursively delete directory: {path}. This is a destructive operation.")
    dir_path = Path(path)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"지정된 경로는 디렉토리여야 합니다: {path}")

    try:
        shutil.rmtree(dir_path)
        message = f"Directory {dir_path} and all its contents have been deleted."
        logger.info(message)
        return message
    except PermissionError as e:
        logger.error(f"Permission denied while trying to delete {path}: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error while deleting {path}: {e}")
        raise

def read_multiple_files(file_paths: List[str]) -> str:
    """
    여러 개의 텍스트 파일 경로를 리스트로 받아,
    각 파일의 내용을 읽어 하나의 문자열로 결합합니다.
    AI가 코드베이스 전체를 분석할 때 유용합니다.

    Args:
        file_paths (List[str]): 읽어올 파일들의 경로 리스트.

    Returns:
        str: 각 파일의 내용이 파일명 헤더와 함께 결합된 단일 문자열.

    Raises:
        FileNotFoundError: 리스트의 파일 중 하나라도 존재하지 않으면 발생.
        IOError: 파일 읽기 중 오류 발생 시.
    """
    logger.info(f"{len(file_paths)}개의 파일 내용을 읽기 시작합니다.")
    combined_content = ""

    # AI가 파일 맥락을 구분할 수 있도록 파일명 헤더를 추가합니다.
    for file_path in file_paths:
        try:
            content = read_file(file_path) # 기존 Atomic MCP 재사용
            combined_content += f"\n--- START OF {file_path} ---\n"
            combined_content += content
            combined_content += f"\n--- END OF {file_path} ---\n"
        except Exception as e:
            logger.warning(f"'{file_path}' 파일 읽기 실패: {e}. 건너뜁니다.")
            combined_content += f"\n--- FAILED TO READ {file_path}: {e} ---\n"

    logger.info("모든 파일 읽기 및 결합 완료.")
    return combined_content
