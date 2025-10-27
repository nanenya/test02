#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지정된 소스 디렉토리의 모든 내용을 하나의 압축 파일(zip)로 생성합니다."""

import logging
import os
import shutil
from pathlib import Path
from typing import Union, Dict

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _calculate_directory_size(directory: Path) -> int:
    """디렉토리 내 모든 파일의 총 크기를 바이트 단위로 계산합니다."""
    total_size = 0
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # 심볼릭 링크 등 깨진 파일을 방지
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

def backup_directory(
    source_directory: Union[str, Path],
    destination_path: Union[str, Path],
    overwrite: bool = False
) -> Dict[str, Union[str, int]]:
    """지정된 디렉토리의 모든 내용을 zip 압축 파일로 백업하는 워크플로우입니다.

    이 워크플로우는 다음 단계를 순차적으로 수행합니다:
    1. 원본 디렉토리와 대상 경로의 유효성을 검증합니다.
    2. 원본 디렉토리의 총 크기를 계산합니다.
    3. `shutil.make_archive`를 사용하여 모든 내용을 zip 파일로 압축합니다.
    4. 생성된 압축 파일의 크기를 확인합니다.
    5. 성공 시, 작업 결과(경로, 원본 크기, 압축 크기)를 반환합니다.

    Args:
        source_directory (Union[str, Path]): 백업할 원본 디렉토리의 경로입니다.
        destination_path (Union[str, Path]): 생성될 zip 압축 파일의 전체 경로입니다.
            (예: '/backups/archive.zip')
        overwrite (bool, optional): 대상 경로에 압축 파일이 이미 존재할 경우
            덮어쓸지 여부를 결정합니다. 기본값은 False입니다.

    Returns:
        Dict[str, Union[str, int]]: 성공 시, 백업 작업의 상세 정보를 담은 딕셔너리.
            {
                'archive_path': '생성된 파일의 절대 경로 (str)',
                'source_size_bytes': 원본 디렉토리의 총 크기 (int),
                'archive_size_bytes': 생성된 압축 파일의 크기 (int)
            }

    Raises:
        ValueError: 경로가 유효하지 않거나 원본 경로가 디렉토리가 아닐 경우.
        FileNotFoundError: 원본 디렉토리가 존재하지 않을 경우.
        FileExistsError: 대상 파일이 이미 존재하고 `overwrite`가 False일 경우.
        PermissionError: 파일 시스템 읽기/쓰기 권한이 없을 경우.
        shutil.Error: 압축 과정에서 오류가 발생했을 경우.

    Example:
        >>> result = backup_directory('./my_project', '/tmp/project_backup.zip', overwrite=True)
        >>> print(f"백업 완료: {result['archive_path']}")
        >>> print(f"원본 크기: {result['source_size_bytes']} bytes")
    """
    logger.info(f"Workflow 'backup_directory' started for source: '{source_directory}'")

    # 1. 경로 유효성 검사
    if not source_directory or not destination_path:
        raise ValueError("원본 디렉토리와 대상 경로는 비어있을 수 없습니다.")

    src_path = Path(source_directory).resolve()
    dest_path = Path(destination_path).resolve()

    # 2. 원본 디렉토리 검증
    if not src_path.exists():
        raise FileNotFoundError(f"원본 디렉토리가 존재하지 않습니다: {src_path}")
    if not src_path.is_dir():
        raise ValueError(f"지정된 원본 경로는 디렉토리가 아닙니다: {src_path}")

    # 3. 대상 파일 경로 검증
    if dest_path.exists() and not overwrite:
        raise FileExistsError(f"대상 파일이 이미 존재합니다: {dest_path}")
    if dest_path.is_dir():
        raise IsADirectoryError(f"대상 경로는 파일 경로여야 합니다 (디렉토리 감지): {dest_path}")

    try:
        # 4. 워크플로우 실행: 크기 계산 및 압축
        logger.info("Calculating size of the source directory...")
        source_size = _calculate_directory_size(src_path)
        logger.info(f"Source size: {source_size} bytes.")

        # 대상 파일의 부모 디렉토리 생성
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating archive at '{dest_path}'...")
        # shutil.make_archive는 확장자를 자동으로 붙이므로, 확장자 없는 이름을 전달
        archive_base_name = str(dest_path.with_suffix(''))

        # 압축 실행
        archive_path_str = shutil.make_archive(
            base_name=archive_base_name,
            format='zip',
            root_dir=str(src_path)
        )

        archive_path = Path(archive_path_str)
        archive_size = archive_path.stat().st_size
        logger.info(f"Archive created successfully. Size: {archive_size} bytes.")

        # 5. 결과 반환
        return {
            'archive_path': str(archive_path),
            'source_size_bytes': source_size,
            'archive_size_bytes': archive_size
        }

    except PermissionError as e:
        logger.error(f"Permission denied during backup workflow: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during backup workflow: {e}")
        # 실패 시 생성되었을 수 있는 불완전한 파일 삭제
        if dest_path.exists():
            dest_path.unlink()
        raise shutil.Error(f"압축 파일 생성 중 오류 발생: {e}")
