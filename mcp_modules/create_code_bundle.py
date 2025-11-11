#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mcp_modules/create_code_bundle.py

import logging
from pathlib import Path
from typing import List
import sys # sys는 로깅이나 print 외의 용도로 사용하지 않는 것이 좋습니다.

# --- [1. 문제의 코드 (추정)] ---
#
# try:
#     import pathspec
# except ImportError:
#     print("Error: pathspec library is not installed...", file=sys.stderr)
#     exit(1) # <-- 이 코드가 서버 전체를 중단시킵니다!
#
# --- [1. 수정 완료] ---

logger = logging.getLogger(__name__)

def create_code_bundle_with_gitignore(repo_path: str) -> str:
    """
    지정된 경로에서 .gitignore 규칙을 존중하면서 모든 텍스트 기반 파일을
    하나의 '코드 번들' 문자열로 결합합니다.
    AI에게 전체 코드베이스를 한 번에 제공할 때 유용합니다.

    [Dependency] 이 MCP는 'pathspec' 라이브러리가 필요합니다.
    """
    
    # --- [2. 올바른 수정] ---
    # 임포트(import)는 함수 내부에서 시도해야 합니다.
    try:
        import pathspec
    except ImportError:
        logger.error("create_code_bundle_with_gitignore: 'pathspec' 라이브러리가 설치되어 있지 않습니다.")
        # exit() 대신, 이 오류를 발생시킵니다.
        # api.py의 execute_group이 이 오류를 잡아 EXECUTION_ERROR로 사용자에게 보고합니다.
        raise ModuleNotFoundError(
            "이 도구를 사용하려면 'pathspec' 라이브S러리가 필요합니다. "
            "사용자에게 'pip install pathspec'을 요청하세요."
        )
    # --- [2. 수정 완료] ---

    logger.info(f"'{repo_path}'에서 .gitignore를 반영한 코드 번들 생성을 시작합니다.")
    
    base_dir = Path(repo_path).resolve()
    gitignore_path = base_dir / ".gitignore"
    
    lines = []
    if gitignore_path.exists():
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning(f".gitignore 파일({gitignore_path})을 읽는 중 오류 발생: {e}")
    else:
        logger.warning(f".gitignore 파일을 찾을 수 없어({gitignore_path}), 일부 불필요한 파일이 포함될 수 있습니다.")
    
    # .gitignore 규칙 로드 (gitwildmatch 스타일)
    spec = pathspec.PathSpec.from_lines('gitwildmatch', lines)
    
    all_files = []
    # 일반적으로 제외할 디렉토리 및 파일 패턴
    exclude_patterns = {'.git', 'venv', '__pycache__', '.vscode', '.idea'}
    
    for file_path in base_dir.rglob('*'):
        if file_path.is_file():
            relative_path = file_path.relative_to(base_dir)
            
            # 1. 일반적인 제외 패턴 확인
            if any(part in exclude_patterns for part in relative_path.parts):
                continue
                
            # 2. .gitignore 규칙 확인
            if not spec.match_file(str(relative_path)):
                all_files.append(file_path)
    
    logger.info(f".gitignore를 적용하여 총 {len(all_files)}개의 파일을 찾았습니다.")
    
    combined_content = ""
    for file_path in all_files:
        try:
            # 바이너리 파일이나 너무 큰 파일은 건너뛰기
            if file_path.stat().st_size > 5_000_000: # 5MB
                logger.warning(f"'{file_path}' 파일이 너무 커서(5MB 초과) 건너뜁니다.")
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # AI가 파일 경로를 명확히 인지하도록 헤더 추가
            combined_content += f"\n--- START OF {file_path.relative_to(base_dir)} ---\n"
            combined_content += content
            combined_content += f"\n--- END OF {file_path.relative_to(base_dir)} ---\n"
            
        except (UnicodeDecodeError, PermissionError):
            logger.warning(f"'{file_path}'는 텍스트 파일이 아니거나 읽을 수 없어 건너뜁니다.")
        except Exception as e:
            logger.warning(f"'{file_path}' 파일 읽기 실패: {e}. 건너뜁니다.")
    
    logger.info("모든 파일 읽기 및 코드 번들 결합 완료.")
    return combined_content

# (참고) 만약 파일에 함수가 여러 개 있다면, pathspec을 사용하는 모든 함수에
# try-except 임포트 구문을 넣어주어야 합니다.
