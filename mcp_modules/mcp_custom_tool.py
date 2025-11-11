#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코드 번들링 및 집계(Aggregation)를 위한 MCP 모음.

이 모듈은 여러 소스 코드 파일을 특정 규칙에 따라 하나의 파일로 병합하는
고수준의 복합(Compound) MCP 함수를 제공합니다. .gitignore와 같은
제외 규칙을 지원하여 프로젝트 코드베이스를 쉽게 아카이빙하거나
LLM 컨텍스트에 주입할 수 있도록 돕습니다.
"""

import logging
import fnmatch
from pathlib import Path
from typing import Union, List, Optional

# --- 모듈 레벨 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 일반적인 프로젝트에서 제외할 기본 패턴 목록
DEFAULT_IGNORE_PATTERNS = [
    ".git/*",
    "venv/*",
    ".venv/*",
    "__pycache__/*",
    "*.pyc",
    "*.log",
    "*.tmp",
    ".DS_Store",
    "node_modules/*",
    "build/*",
    "dist/*",
    "*.egg-info/*",
]


def aggregate_python_files(
    root_dir: Union[str, Path],
    output_file: Union[str, Path],
    additional_ignore_patterns: Optional[List[str]] = None
) -> str:
    """
    지정된 디렉토리의 모든 Python 파일을 찾아 .gitignore 규칙에 따라 필터링한 후 하나의 파일로 병합합니다.

    이 함수는 다음 단계를 수행합니다:
    1. `root_dir`에서 `.gitignore` 파일을 읽어 제외 패턴을 로드합니다.
    2. 기본 제외 패턴 및 `additional_ignore_patterns`와 결합합니다.
    3. `root_dir`을 재귀적으로 탐색하여 모든 `.py` 파일을 찾습니다.
    4. 각 파일의 상대 경로가 제외 패턴과 일치하는지 확인합니다.
    5. 제외되지 않은 파일들의 내용을 읽어 `output_file`에 순차적으로 씁니다.
       각 파일 내용 앞에는 파일 경로를 나타내는 헤더가 추가됩니다.

    Args:
        root_dir (Union[str, Path]): 검색을 시작할 최상위 디렉토리 경로.
        output_file (Union[str, Path]): 모든 코드를 병합하여 저장할 파일 경로.
        additional_ignore_patterns (Optional[List[str]], optional):
            .gitignore 외에 추가로 적용할 무시 패턴 리스트. 기본값은 None.

    Returns:
        str: 성공적으로 생성된 출력 파일의 절대 경로.

    Raises:
        FileNotFoundError: `root_dir`가 존재하지 않거나 디렉토리가 아닌 경우.
        PermissionError: 파일/디렉토리 읽기 또는 쓰기 권한이 없는 경우.
        IOError: 파일 처리 중 예기치 않은 I/O 오류가 발생한 경우.
        ValueError: 입력 인자가 유효하지 않은 경우.
    """
    logger.info(f"'{root_dir}'의 파이썬 파일 집계 시작 -> '{output_file}'")

    # 1. 경로 객체로 변환 및 유효성 검사
    try:
        root_path = Path(root_dir).resolve()
        output_path = Path(output_file).resolve()

        if not root_path.is_dir():
            raise FileNotFoundError(f"루트 디렉토리를 찾을 수 없습니다: {root_path}")

        # 출력 파일의 상위 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

    except (PermissionError, FileNotFoundError) as e:
        logger.error(f"경로 설정 중 오류 발생: {e}")
        raise
    except Exception as e:
        logger.critical(f"경로 처리 중 예상치 못한 오류: {e}")
        raise IOError(f"경로 처리 중 예상치 못한 오류 발생: {e}")

    # 2. .gitignore 및 추가 패턴 로드
    all_ignore_patterns = set(DEFAULT_IGNORE_PATTERNS)
    if additional_ignore_patterns:
        all_ignore_patterns.update(additional_ignore_patterns)

    gitignore_path = root_path / ".gitignore"
    if gitignore_path.is_file():
        logger.info(f"'{gitignore_path}'에서 제외 패턴 로드 중.")
        try:
            with gitignore_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # 디렉토리 패턴 (예: 'logs/')을 와일드카드 패턴으로 변환
                        if line.endswith('/'):
                            all_ignore_patterns.add(line + '*')
                            all_ignore_patterns.add(line.rstrip('/'))
                        else:
                            all_ignore_patterns.add(line)
                            all_ignore_patterns.add(f'*/{line}') # 모든 하위 디렉토리에서도 매칭
        except Exception as e:
            logger.warning(f"'{gitignore_path}' 파일 읽기 실패: {e}")
            # .gitignore를 읽지 못해도 계속 진행

    # 최종 출력 파일 자체도 제외 목록에 추가
    try:
        relative_output_path = output_path.relative_to(root_path)
        all_ignore_patterns.add(str(relative_output_path))
    except ValueError:
        # 출력 파일이 루트 디렉토리 외부에 있으면 relative_to가 실패함. 이 경우 무시.
        pass
    
    logger.info(f"총 {len(all_ignore_patterns)}개의 제외 패턴 사용.")

    # 3. 파일 탐색 및 필터링
    aggregated_content = []
    files_to_process = list(root_path.rglob("*.py"))
    logger.info(f"총 {len(files_to_process)}개의 .py 파일 발견.")
    
    processed_count = 0
    for file_path in files_to_process:
        try:
            # Path 객체는 OS에 맞는 구분자를 사용하므로, fnmatch를 위해 표준 '/'로 변환
            relative_path_str = str(file_path.relative_to(root_path).as_posix())
            
            # fnmatch를 사용하여 패턴과 대조
            is_ignored = any(
                fnmatch.fnmatch(relative_path_str, pattern) or
                fnmatch.fnmatch(file_path.name, pattern)
                for pattern in all_ignore_patterns
            )

            if not is_ignored:
                logger.debug(f"처리 중: {relative_path_str}")
                header = f"# --- {relative_path_str} ---\n\n"
                try:
                    content = file_path.read_text(encoding="utf-8")
                    aggregated_content.append(header + content + "\n\n")
                    processed_count += 1
                except Exception as e:
                    logger.error(f"파일 읽기 오류 '{file_path}': {e}")
                    error_message = f"# Error reading {relative_path_str}: {e}\n\n"
                    aggregated_content.append(header + error_message)
            else:
                logger.debug(f"무시됨: {relative_path_str}")

        except Exception as e:
            logger.error(f"파일 경로 처리 중 오류 '{file_path}': {e}")


    # 4. 결과 파일 작성
    try:
        final_content = "".join(aggregated_content)
        output_path.write_text(final_content, encoding="utf-8")
        logger.info(f"성공: 총 {processed_count}개의 파일을 '{output_path}'에 병합했습니다.")
        return str(output_path)
    except PermissionError as e:
        logger.error(f"출력 파일 쓰기 권한 오류: {output_path}, {e}")
        raise
    except Exception as e:
        logger.critical(f"출력 파일 쓰기 중 예상치 못한 오류 발생: {e}")
        raise IOError(f"파일 '{output_path}' 쓰기 중 오류 발생: {e}")