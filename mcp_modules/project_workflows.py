#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_workflows.py

AI 기반 개발 프로젝트의 공통 워크플로우를 자동화하는
고수준 복합 MCP(Composite Mission Control Primitives) 모음입니다.

(수정) 개발 및 디버깅, 의존성 관리 워크플로우 9개 추가.
"""

import logging
import os
import re
import ast
from typing import Dict, List, Optional
from pathlib import Path

# --- 로거 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 기존 MCP 모듈 임포트 ---
try:
    # 파일 시스템
    from .file_system_composite import (
        read_multiple_files, read_specific_lines
    )
    from .file_content_operations import (
        write_file, read_file, append_to_file
    )
    
    # Git (이전 대화에서 생성한 git_list_all_files 포함)
    from .git_version_control import (
        git_init, git_add_remote, git_add, git_commit, git_get_current_branch,
        git_create_branch, git_switch_branch, git_push, git_status, git_diff,
        git_log, git_revert_commit, git_pull, git_create_tag, git_fetch,
        git_list_all_files, _run_git_command, GitCommandError
    )
    
    # 사용자 상호작용
    from .user_interaction_composite import (
        ask_user_for_input, ask_user_for_confirmation, ask_for_multiline_input,
        present_options_and_get_choice, present_checkbox_and_get_choices
    )
    from .user_interaction_atomic import show_message
    
    # 코드 실행
    from .code_execution_composite import (
        lint_code_file, _run_command, setup_python_venv
    )
    
    # 웹
    from .web_network_atomic import fetch_url_content

except ImportError:
    # 이 모듈이 단독으로 테스트될 경우를 대비
    logger.error("워크플로우 MCP는 다른 MCP 모듈과 함께 실행되어야 합니다.")
    # 필요한 함수들을 임시로 정의 (테스트용)
    def _mock_mcp(*args, **kwargs):
        logger.warning(f"Mock MCP called with: {args}, {kwargs}")
        return "Mock Result"
    
    git_init = git_add_remote = git_add = git_commit = git_get_current_branch = \
    git_create_branch = git_switch_branch = git_push = git_status = git_diff = \
    git_log = git_revert_commit = git_pull = git_create_tag = git_fetch = \
    git_list_all_files = read_multiple_files = write_file = read_file = \
    append_to_file = read_specific_lines = setup_python_venv = \
    ask_user_for_input = ask_user_for_confirmation = ask_for_multiline_input = \
    present_options_and_get_choice = present_checkbox_and_get_choices = \
    show_message = lint_code_file = fetch_url_content = _run_command = _mock_mcp
    
    def _run_git_command(*args, **kwargs):
        return _mock_mcp(*args, **kwargs)
    
    class GitCommandError(Exception):
        pass


# ==============================================================================
# 1. 기존 워크플로우 MCP (11개)
# ==============================================================================

def initialize_project_repository(
    repo_path: str, 
    gitignore_template: str = "Python"
) -> str:
    """
    새 프로젝트 폴더를 Git 저장소로 만들고, .gitignore 파일까지 생성하여 첫 커밋을 완료합니다.
    사용자에게 원격 저장소 주소를 물어 'origin'으로 등록합니다.

    Args:
        repo_path (str): Git 저장소를 초기화할 디렉토리 경로.
        gitignore_template (str): .gitignore.io에서 가져올 템플릿 이름. (예: "Python,Node")

    Returns:
        str: 성공 메시지.
    """
    try:
        logger.info(f"'{repo_path}'에서 Git 저장소 초기화를 시작합니다...")
        git_init(repo_path)
        
        # .gitignore.io API를 사용해 .gitignore 파일 생성
        logger.info(f"'{gitignore_template}' 템플릿으로 .gitignore 파일을 생성합니다.")
        gi_url = f"https://www.toptal.com/developers/gitignore/api/{gitignore_template.lower()}"
        gi_content = fetch_url_content(gi_url)
        write_file(str(Path(repo_path) / ".gitignore"), gi_content)
        
        git_add(repo_path, files=[".gitignore"])
        git_commit(repo_path, message="Initial commit: Add .gitignore")
        
        logger.info("첫 커밋을 완료했습니다.")
        
        if ask_user_for_confirmation("지금 원격 저장소(remote) 주소를 등록하시겠습니까?"):
            remote_url = ask_user_for_input("원격 저장소 URL을 입력하세요 (예: https://...):")
            if remote_url:
                git_add_remote(repo_path, "origin", remote_url)
                return f"저장소 초기화 및 원격 저장소 'origin' 등록 완료: {repo_path}"

        return f"저장소 초기화 완료 (원격 저장소 미등록): {repo_path}"
        
    except Exception as e:
        logger.error(f"프로젝트 초기화 중 오류 발생: {e}")
        raise

def start_new_feature_branch(repo_path: str) -> str:
    """
    사용자에게 새 브랜치 이름을 물어본 뒤, 해당 브랜치를 생성하고 즉시 그 브랜치로 전환합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.

    Returns:
        str: 성공 메시지 (예: "새 브랜치 'feature/login'을(를) 생성하고 전환했습니다.")
    """
    branch_name = ask_user_for_input("생성할 새 브랜치 이름을 입력하세요 (예: feature/login):")
    if not branch_name:
        return "브랜치 생성이 취소되었습니다."
        
    try:
        logger.info(f"새 브랜치 '{branch_name}' 생성 및 전환 시도...")
        git_create_branch(repo_path, branch_name)
        git_switch_branch(repo_path, branch_name)
        
        msg = f"새 브랜치 '{branch_name}'을(를) 생성하고 전환했습니다."
        logger.info(msg)
        return msg
    except Exception as e:
        logger.error(f"새 브랜치 생성 중 오류 발생: {e}")
        raise

def commit_and_push_changes(repo_path: str, default_message: str = "") -> str:
    """
    모든 변경 사항을 스테이징하고, 사용자에게 커밋 메시지를 확인(입력)받은 뒤,
    현재 브랜치로 'origin'에 푸시합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        default_message (str): AI가 제안하거나 기본으로 사용할 커밋 메시지.

    Returns:
        str: 성공 메시지.
    """
    try:
        status = git_status(repo_path)
        logger.info(f"현재 Git 상태:\n{status}")
        
        commit_msg = ask_user_for_input(
            "커밋 메시지를 입력하세요 (Enter 시 기본값 사용):",
            default=default_message or "AI 에이전트에 의한 코드 변경"
        )
        if not commit_msg:
            return "커밋이 취소되었습니다."
            
        logger.info("모든 변경 사항을 스테이징합니다...")
        git_add(repo_path, files=['.'])
        
        logger.info(f"'{commit_msg}' 메시지로 커밋합니다...")
        git_commit(repo_path, commit_msg)
        
        current_branch = git_get_current_branch(repo_path)
        if not current_branch:
            raise GitCommandError("현재 브랜치를 확인할 수 없습니다 (Detached HEAD 상태일 수 있음).")
            
        logger.info(f"'origin/{current_branch}'(으)로 푸시합니다...")
        push_result = git_push(repo_path, "origin", current_branch)
        
        return f"커밋 및 푸시 완료.\n{push_result}"
        
    except Exception as e:
        logger.error(f"커밋 및 푸시 중 오류 발생: {e}")
        raise

def analyze_and_lint_project(repo_path: str) -> str:
    """
    .gitignore를 준수하는 프로젝트 내의 모든 Python 파일(.py)에 대해 LINT(flake8) 검사를
    수행하고, 문제가 발견된 파일의 결과만 요약하여 반환합니다.

    Args:
        repo_path (str): 검사할 Git 저장소의 경로.

    Returns:
        str: LINT 검사 결과 요약.
    """
    logger.info(f"'{repo_path}'의 모든 Python 파일에 대해 LINT 검사를 시작합니다.")
    try:
        all_files = git_list_all_files(repo_path)
        py_files = [f for f in all_files if f.endswith(".py")]
        
        if not py_files:
            return "검사할 Python 파일이 없습니다."
            
        logger.info(f"총 {len(py_files)}개의 Python 파일 검사 중...")
        
        lint_issues = []
        for file_path in py_files:
            try:
                # lint_code_file은 문제가 없으면 빈 문자열을, 있으면 오류를 반환합니다.
                # (mcp_modules/code_execution_composite.py의 로직에 따라 다름)
                # 여기서는 'lint_code_file'이 오류 발견 시 예외를 발생시킨다고 가정합니다.
                lint_result = lint_code_file(str(Path(repo_path) / file_path))
                if lint_result: # 문제가 있는데 예외가 아닌 문자열을 반환한 경우
                     lint_issues.append(f"--- {file_path} ---\n{lint_result}")
            except Exception as e:
                # CalledProcessError 등 LINT가 문제를 발견했을 때
                error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
                if error_output:
                    lint_issues.append(f"--- {file_path} ---\n{error_output}")
                else:
                    lint_issues.append(f"--- {file_path} ---\n{str(e)}")

        if not lint_issues:
            return f"LINT 검사 완료: {len(py_files)}개의 모든 파일이 깨끗합니다."
        else:
            return f"LINT 검사 완료. {len(lint_issues)}개 파일에서 문제가 발견되었습니다:\n\n" + "\n\n".join(lint_issues)

    except Exception as e:
        logger.error(f"LINT 분석 중 오류 발생: {e}")
        raise

def revert_last_ai_commit(repo_path: str) -> str:
    """
    가장 최근의 커밋(아마도 AI가 생성한)을 되돌릴지(revert) 사용자에게 확인하고 실행합니다.
    (revert는 되돌리는 새 커밋을 생성합니다)

    Args:
        repo_path (str): 대상 Git 저장소의 경로.

    Returns:
        str: 작업 성공 또는 취소 메시지.
    """
    try:
        log_output = git_log(repo_path, limit=1)
        if not log_output:
            return "되돌릴 커밋이 없습니다."
            
        last_commit_hash = log_output.split()[0]
        
        if ask_user_for_confirmation(f"가장 최근 커밋을 되돌리시겠습니까?\n\n{log_output}"):
            logger.info(f"커밋 {last_commit_hash} 되돌리기를 실행합니다...")
            git_revert_commit(repo_path, last_commit_hash)
            return f"커밋 {last_commit_hash}을(를) 되돌리는 새 커밋을 생성했습니다."
        else:
            return "작업이 취소되었습니다."
    except Exception as e:
        logger.error(f"커밋 되돌리기 중 오류 발생: {e}")
        raise

def load_and_analyze_project_code(repo_path: str) -> str:
    """
    .gitignore를 준수하는 프로젝트 내의 모든 파일을 읽어 하나의 문자열로 결합합니다.
    AI가 전체 코드베이스의 맥락을 파악하고 분석/수정 작업을 준비할 때 사용됩니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.

    Returns:
        str: "--- START OF [filepath] ---" 형식으로 구분된 전체 코드 문자열.
    """
    try:
        logger.info(f"'{repo_path}'의 전체 코드 로드를 시작합니다...")
        all_files = git_list_all_files(repo_path)
        
        if not all_files:
            return "프로젝트에 파일이 없습니다."
            
        logger.info(f"총 {len(all_files)}개 파일의 내용을 결합합니다.")
        # read_multiple_files가 파일 경로를 repo_path 기준으로 처리하도록 수정
        full_paths = [str(Path(repo_path) / f) for f in all_files]
        combined_code = read_multiple_files(full_paths)
        
        return combined_code
        
    except Exception as e:
        logger.error(f"프로젝트 코드 로드 중 오류 발생: {e}")
        raise

def switch_to_main_and_pull(repo_path: str, branch_name: str = "main") -> str:
    """
    프로젝트의 메인 브랜치(기본 'main')로 전환하고,
    원격 저장소(origin)의 최신 변경 사항을 pull 받습니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        branch_name (str): 동기화할 기본 브랜치 이름.

    Returns:
        str: 성공 메시지.
    """
    try:
        logger.info(f"'{branch_name}' 브랜치로 전환합니다...")
        git_switch_branch(repo_path, branch_name)
        
        logger.info(f"'origin/{branch_name}'에서 최신 변경 사항을 PULL합니다...")
        pull_result = git_pull(repo_path, "origin", branch_name)
        
        return f"'{branch_name}' 브랜치로 전환 및 최신화 완료.\n{pull_result}"
    except Exception as e:
        logger.error(f"메인 브랜치 동기화 중 오류 발생: {e}")
        raise

def publish_new_version_tag(repo_path: str, remote: str = "origin") -> str:
    """
    새 버전 릴리스를 위해 사용자에게 태그 이름과 릴리스 노트를 입력받아
    Git 태그를 생성하고 원격 저장소(origin)에 푸시합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        remote (str): 태그를 푸시할 원격 저장소 이름.

    Returns:
        str: 성공 또는 취소 메시지.
    """
    tag_name = ask_user_for_input("새 버전 태그 이름을 입력하세요 (예: v1.0.1):")
    if not tag_name:
        return "태그 생성이 취소되었습니다."
        
    release_notes = ask_for_multiline_input(
        "릴리스 노트를 입력하세요 (Markdown 지원, 종료하려면 EOF 입력):"
    )
    if not release_notes:
        release_notes = f"Release {tag_name}" # 기본 메시지
        
    try:
        logger.info(f"'{tag_name}' 태그를 생성합니다...")
        git_create_tag(repo_path, tag_name, release_notes)
        
        # git_push MCP는 브랜치 전용이므로, 태그 푸시를 위해 _run_git_command 사용
        logger.info(f"'{remote}'(으)로 태그를 푸시합니다...")
        push_command = ["git", "push", remote, tag_name]
        push_result = _run_git_command(push_command, cwd=repo_path)
        
        return f"태그 '{tag_name}' 생성 및 원격 저장소 푸시 완료.\n{push_result}"
        
    except Exception as e:
        logger.error(f"태그 게시 중 오류 발생: {e}")
        raise

def run_project_tests(repo_path: str, test_framework: str = "auto") -> str:
    """
    프로젝트의 자동화된 테스트(pytest 또는 unittest)를 안전하게 실행하고 결과를 반환합니다.
    이는 AI가 수정한 코드를 검증하는 데 사용됩니다.

    Args:
        repo_path (str): 테스트를 실행할 저장소 경로.
        test_framework (str): 'pytest', 'unittest', 'auto' 중 선택.
            'auto'는 pytest.ini를 먼저 찾고, 없으면 unittest를 시도합니다.

    Returns:
        str: 테스트 실행 결과 (stdout + stderr).
    """
    command: List[str]
    
    if test_framework == "auto":
        if (Path(repo_path) / "pytest.ini").exists():
            framework_to_run = "pytest"
        else:
            framework_to_run = "unittest"
    else:
        framework_to_run = test_framework

    if framework_to_run == "pytest":
        command = ["pytest"]
        logger.info("pytest를 사용하여 테스트를 실행합니다...")
    elif framework_to_run == "unittest":
        command = ["python", "-m", "unittest", "discover"]
        logger.info("unittest를 사용하여 테스트를 실행합니다...")
    else:
        raise ValueError(f"지원하지 않는 테스트 프레임워크입니다: {test_framework}")

    try:
        # code_execution_composite의 _run_command 사용 (셸 인젝션 방지)
        result = _run_command(command, cwd=repo_path)
        logger.info("테스트 성공.")
        return f"테스트 성공:\n{result}"
    except Exception as e:
        # 테스트 실패 시 CalledProcessError 발생
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        if not error_output:
            error_output = str(e)
        logger.warning(f"테스트 실패:\n{error_output}")
        # 실패도 유효한 '결과'이므로 예외를 다시 발생시키지 않고 반환합니다.
        return f"테스트 실패:\n{error_output}"


def request_ai_code_review(repo_path: str) -> str:
    """
    현재 스테이징된(staged) 변경 사항에 대한 'git diff'를 생성합니다.
    AI에게 이 diff를 전달하여 코드 리뷰를 요청하는 프롬프트를 준비합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.

    Returns:
        str: AI에게 코드 리뷰를 요청하는 프롬프트 문자열.
    """
    logger.info("스테이징된 변경 사항에 대한 코드 리뷰를 준비합니다.")
    try:
        # --staged 옵션으로 스테이징된 내용의 diff만 가져옵니다.
        diff_command = ["git", "diff", "--staged"]
        staged_diff = _run_git_command(diff_command, cwd=repo_path)
        
        if not staged_diff:
            return "코드 리뷰 요청 실패: 스테이징된 변경 사항이 없습니다."
            
        prompt = (
            "다음은 제가 수정한 코드의 diff입니다. "
            "코드 리뷰를 수행해 주세요. (버그, 스타일, 성능, 보안 관점)\n\n"
            "```diff\n"
            f"{staged_diff}\n"
            "```"
        )
        return prompt
        
    except Exception as e:
        logger.error(f"코드 리뷰 준비 중 오류 발생: {e}")
        raise

def clean_up_merged_branches(repo_path: str, remote: str = "origin") -> str:
    """
    원격 저장소(remote)에 이미 병합(merge)된 로컬 브랜치 목록을 보여주고,
    사용자가 선택한 브랜치들을 안전하게 삭제합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        remote (str): 기준이 되는 원격 저장소 이름.

    Returns:
        str: 작업 결과 요약.
    """
    try:
        logger.info(f"'{remote}'의 최신 정보를 가져옵니다...")
        git_fetch(repo_path, remote=remote)
        
        current_branch = git_get_current_branch(repo_path)
        
        # 원격에 병합된 로컬 브랜치 목록 조회
        merged_command = ["git", "branch", "--merged", f"{remote}/main"] # main 기준
        merged_output = _run_git_command(merged_command, cwd=repo_path)
        
        branches_to_clean = []
        for line in merged_output.split('\n'):
            branch_name = line.strip()
            # 현재 브랜치, main, develop 브랜치는 제외
            if branch_name.startswith("*"):
                continue
            if branch_name in ["main", "master", "develop"]:
                continue
            if branch_name:
                branches_to_clean.append(branch_name)
                
        if not branches_to_clean:
            return "정리할 브랜치가 없습니다. (이미 병합된 로컬 브랜치 없음)"
            
        selected_branches = present_checkbox_and_get_choices(
            "다음 브랜치들은 원격 'main'에 병합되었습니다. 삭제할 브랜치를 선택하세요:",
            choices=branches_to_clean
        )
        
        if not selected_branches:
            return "브랜치 정리가 취소되었습니다."
            
        deleted_log = []
        for branch in selected_branches:
            try:
                # -d 옵션으로 안전하게 삭제
                delete_command = ["git", "branch", "-d", branch]
                result = _run_git_command(delete_command, cwd=repo_path)
                deleted_log.append(result)
            except Exception as e:
                deleted_log.append(f"'{branch}' 삭제 실패: {e}")
                
        return f"브랜치 정리 완료:\n" + "\n".join(deleted_log)

    except Exception as e:
        logger.error(f"브랜치 정리 중 오류 발생: {e}")
        raise


# ==============================================================================
# 2. 신규 워크플로우 MCP (요청 6 + 추천 3 = 9개)
# ==============================================================================

def setup_project_environment(repo_path: str, venv_dir: str = ".venv") -> str:
    """
    프로젝트의 Python 가상 환경을 설정하고 'requirements.txt'의 의존성을 설치합니다.
    (워크플로우: 가상 환경 생성 -> requirements.txt 설치)

    Args:
        repo_path (str): 프로젝트 루트 디렉토리 경로.
        venv_dir (str): 생성할 가상 환경 디렉토리 이름.

    Returns:
        str: 성공 메시지.
    """
    logger.info(f"'{repo_path}'에 가상 환경 설정을 시작합니다...")
    
    venv_path = str(Path(repo_path) / venv_dir)
    req_path = Path(repo_path) / "requirements.txt"
    
    # 1. 가상 환경 생성 (멱등성 보장)
    try:
        venv_result = setup_python_venv(venv_path)
        logger.info(venv_result)
    except FileExistsError:
        logger.warning(f"가상 환경이 이미 존재합니다: {venv_path}")
    
    # 2. requirements.txt 설치
    if not req_path.exists():
        msg = f"가상 환경 생성 완료. 'requirements.txt' 파일이 없어 의존성을 설치하지 않았습니다."
        logger.warning(msg)
        return msg
        
    logger.info(f"'requirements.txt' 파일의 의존성을 설치합니다...")
    
    # OS 호환 가능한 pip 실행 경로
    pip_exe = "pip.exe" if os.name == "nt" else "pip"
    pip_path = str(Path(venv_path) / ("Scripts" if os.name == "nt" else "bin") / pip_exe)
    
    try:
        install_command = [pip_path, "install", "-r", str(req_path)]
        install_result = _run_command(install_command, cwd=repo_path)
        
        return f"가상 환경 설정 및 의존성 설치 완료.\n{install_result}"
    except Exception as e:
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        raise IOError(f"'requirements.txt' 설치 실패: {error_output}")


def install_and_save_package(
    repo_path: str, 
    package_name: str, 
    requirements_file: str = "requirements.txt"
) -> str:
    """
    Python 패키지를 'pip install'로 설치하고,
    설치된 정확한 버전을 'requirements.txt' 파일에 추가(append)합니다.

    Args:
        repo_path (str): 'requirements.txt'가 위치한 프로젝트 루트 경로.
        package_name (str): 설치할 패키지 이름 (예: "requests", "numpy")
        requirements_file (str): 버전을 기록할 파일 이름.

    Returns:
        str: 성공 메시지 (예: "requests==2.31.0을 설치하고 requirements.txt에 추가했습니다.")
    """
    logger.info(f"'{package_name}' 패키지 설치를 시작합니다...")
    try:
        # 1. 패키지 설치
        install_command = ["python", "-m", "pip", "install", package_name]
        install_result = _run_command(install_command, cwd=repo_path)
        logger.info(f"설치 완료: {install_result}")

        # 2. 설치된 버전 확인
        show_command = ["python", "-m", "pip", "show", package_name]
        show_result = _run_command(show_command, cwd=repo_path)
        
        version_match = re.search(r"Version: (.+)", show_result)
        if not version_match:
            raise ValueError(f"'{package_name}'의 설치된 버전을 찾을 수 없습니다.")
            
        version = version_match.group(1).strip()
        package_spec = f"{package_name}=={version}"

        # 3. requirements.txt에 추가
        req_path = Path(repo_path) / requirements_file
        logger.info(f"'{package_spec}'을(를) '{req_path}' 파일에 추가합니다.")
        
        # 파일 끝에 개행 문자가 없으면 추가
        current_content = read_file(str(req_path)) if req_path.exists() else ""
        prefix = "\n" if current_content and not current_content.endswith("\n") else ""
        
        append_to_file(str(req_path), f"{prefix}{package_spec}\n")
        
        return f"'{package_spec}'을(를) 설치하고 '{requirements_file}'에 추가했습니다."
        
    except Exception as e:
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        raise RuntimeError(f"패키지 설치 및 저장 중 오류: {e} - {error_output}")


def check_for_outdated_packages(repo_path: str) -> str:
    """
    'pip list --outdated'를 실행하여 오래된 Python 패키지 목록을 보고합니다.
    AI가 프로젝트 유지보수 작업을 시작할 때 유용합니다.

    Args:
        repo_path (str): 프로젝트 경로 (pip 실행 컨텍스트).

    Returns:
        str: 'pip list --outdated'의 실행 결과.
    """
    logger.info("오래된 패키지가 있는지 확인합니다...")
    command = ["python", "-m", "pip", "list", "--outdated"]
    try:
        result = _run_command(command, cwd=repo_path)
        if not result:
            return "모든 패키지가 최신 버전입니다."
        return f"오래된 패키지 목록:\n{result}"
    except Exception as e:
        # 'pip' 자체가 오류를 낼 경우 (예: venv 설정 오류)
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        raise RuntimeError(f"패키지 확인 중 오류: {e} - {error_output}")


def scaffold_test_file_prompt(
    source_file_path: str, 
    test_style_guide_path: str
) -> str:
    """
    AI가 새 테스트 코드를 생성할 수 있도록, 소스 코드와 테스트 스타일 가이드(예시)를
    포함한 프롬프트를 생성합니다. (AI 플래너의 RAG 준비 단계)

    Args:
        source_file_path (str): 테스트를 생성할 대상 소스 코드 파일 경로.
        test_style_guide_path (str): 참고할 테스트 코드 예시 파일 경로.

    Returns:
        str: AI에게 테스트 생성을 요청하는 완성된 프롬프트.
    """
    logger.info(f"'{source_file_path}'에 대한 테스트 코드 생성 프롬프트를 준비합니다.")
    try:
        source_code = read_file(source_file_path)
        style_guide_code = read_file(test_style_guide_path)
        
        prompt = f"""
        당신은 Python 테스트 코드 작성 전문가입니다.
        다음 소스 코드에 대해 'pytest'와 'pytest-mock'을 사용한 단위 테스트를 작성해 주세요.

        [테스트 스타일 가이드 (이 코드의 형식을 따르세요)]
        ```python
        {style_guide_code}
        ```

        [테스트 대상 소스 코드: {source_file_path}]
        ```python
        {source_code}
        ```

        [지시사항]
        - 위 스타일 가이드를 철저히 준수하세요 (예: fixture 사용, mocker 활용).
        - 모든 공개 함수와 주요 엣지 케이스를 커버하는 테스트를 작성해 주세요.
        - 마크다운 래퍼를 포함한 완전한 테스트 파일 코드를 반환해 주세요.

        [테스트 코드]
        """
        return prompt.strip()
        
    except Exception as e:
        logger.error(f"테스트 프롬프트 생성 중 오류: {e}")
        raise


def run_specific_test_and_get_context(
    repo_path: str, 
    test_path: str
) -> str:
    """
    'pytest'를 사용해 지정된 개별 테스트(파일 또는 함수)를 실행합니다.
    테스트 통과 시 성공 메시지를, 실패 시 상세한 오류 로그를 반환합니다.
    (AI가 오류를 보고 수정 계획을 세울 수 있도록)

    Args:
        repo_path (str): pytest를 실행할 프로젝트 루트 경로.
        test_path (str): 실행할 테스트 파일 또는 함수 경로 (예: "tests/test_main.py::test_func")

    Returns:
        str: 테스트 성공 메시지 또는 실패 로그.
    """
    logger.info(f"지정된 테스트 실행: pytest {test_path}")
    command = ["pytest", test_path]
    
    try:
        result = _run_command(command, cwd=repo_path)
        logger.info(f"테스트 통과: {test_path}")
        return f"테스트 통과:\n{result}"
    except Exception as e:
        # pytest는 실패 시 0이 아닌 코드를 반환하며 예외 발생
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        if not error_output:
            error_output = str(e)
            
        logger.warning(f"테스트 실패: {test_path}\n{error_output}")
        # AI가 오류를 분석할 수 있도록 전체 로그를 반환
        return f"테스트 실패: {test_path}\n{error_output}"


def view_and_discard_changes(repo_path: str) -> str:
    """
    현재 작업 디렉토리의 변경 사항(Untracked/Modified)을 'git diff'로 보여주고,
    사용자가 승인하면 모든 변경 사항을 폐기(discard)합니다.

    Args:
        repo_path (str): Git 저장소 경로.

    Returns:
        str: 작업 성공 또는 취소 메시지.
    """
    logger.info("현재 Git 변경 사항을 확인합니다...")
    try:
        status = git_status(repo_path)
        diff = git_diff(repo_path)
        
        if "nothing to commit" in status and not diff:
            return "폐기할 변경 사항이 없습니다."
            
        prompt = (
            "다음 변경 사항이 감지되었습니다. 모두 폐기하시겠습니까?\n\n"
            f"[상태 요약]\n{status}\n\n"
            f"[상세 변경 내역]\n{diff}\n"
        )
        
        if ask_user_for_confirmation(prompt):
            logger.warning("모든 로컬 변경 사항을 폐기합니다...")
            # 1. Modified 변경 사항 되돌리기
            _run_git_command(["git", "restore", "."], cwd=repo_path)
            # 2. Untracked 파일 및 디렉토리 제거
            _run_git_command(["git", "clean", "-fd"], cwd=repo_path)
            
            return "모든 로컬 변경 사항을 폐기했습니다."
        else:
            return "작업이 취소되었습니다."
            
    except Exception as e:
        logger.error(f"변경 사항 폐기 중 오류: {e}")
        raise

# ==============================================================================
# 3. 추가 추천 워크플로우 MCP (3개)
# ==============================================================================

def autofix_lint_errors(repo_path: str) -> str:
    """
    [추천] 'black'과 'isort'를 실행하여 프로젝트 전체의 코드 스타일을 자동으로 수정합니다.
    AI가 생성한 코드의 스타일을 일관되게 맞출 때 유용합니다.

    Args:
        repo_path (str): 포맷팅을 적용할 프로젝트 루트 경로.

    Returns:
        str: 'black'과 'isort'의 실행 결과 요약.
    """
    logger.info(f"'{repo_path}'의 코드 스타일 자동 수정을 시작합니다 (isort, black)...")
    results = []
    
    try:
        # 1. isort 실행
        isort_command = ["isort", "."]
        isort_result = _run_command(isort_command, cwd=repo_path)
        results.append(f"[isort 결과]\n{isort_result}")
    except Exception as e:
        results.append(f"[isort 실행 실패]\n{e}")
        
    try:
        # 2. black 실행
        black_command = ["black", "."]
        black_result = _run_command(black_command, cwd=repo_path)
        results.append(f"[black 결과]\n{black_result}")
    except Exception as e:
        results.append(f"[black 실행 실패]\n{e}")
        
    return "코드 자동 수정 완료:\n\n" + "\n\n".join(results)


def apply_git_patch(repo_path: str, patch_content: str) -> str:
    """
    [추천] AI가 생성한 diff/patch 문자열을 임시 파일로 저장한 뒤,
    'git apply'를 통해 현재 작업 디렉토리에 적용합니다.

    Args:
        repo_path (str): 패치를 적용할 Git 저장소 경로.
        patch_content (str): AI가 제공한 '.patch' 또는 'diff' 형식의 문자열.

    Returns:
        str: 'git apply' 성공 또는 실패 메시지.
    """
    patch_file = Path(repo_path) / ".temp_ai_patch.patch"
    try:
        logger.info("AI가 제안한 패치를 임시 파일로 저장합니다...")
        write_file(str(patch_file), patch_content)
        
        logger.info(f"'{patch_file.name}' 패치를 적용합니다...")
        # 3-way merge 옵션으로 충돌을 더 잘 처리
        apply_command = ["git", "apply", "--3way", str(patch_file.name)]
        result = _run_git_command(apply_command, cwd=repo_path)
        
        return f"패치 적용 성공:\n{result}"
        
    except Exception as e:
        error_output = getattr(e, 'stdout', '') + getattr(e, 'stderr', '')
        raise RuntimeError(f"패치 적용 실패: {e} - {error_output}")
    finally:
        # 작업 완료 후 임시 패치 파일 삭제
        if patch_file.exists():
            patch_file.unlink()
            logger.info("임시 패치 파일을 삭제했습니다.")


def complete_feature_branch(repo_path: str, main_branch: str = "main") -> str:
    """
    [추천] 현재 기능 브랜치 작업을 완료하고, 'main' 브랜치로 병합 및 정리합니다.
    (워크플로우: main 전환 -> main 최신화 -> 기능 브랜치 병합 -> main 푸시 -> 기능 브랜치 삭제)

    Args:
        repo_path (str): 대상 Git 저장소 경로.
        main_branch (str): 병합의 기준이 될 메인 브랜치 이름.

    Returns:
        str: 작업 성공 요약.
    """
    logger.info("기능 브랜치 병합 및 정리 워크플로우를 시작합니다.")
    try:
        feature_branch = git_get_current_branch(repo_path)
        if not feature_branch:
            raise GitCommandError("현재 브랜치를 확인할 수 없습니다 (Detached HEAD?).")
        if feature_branch == main_branch:
            raise GitCommandError(f"이미 '{main_branch}' 브랜치에 있습니다. 기능 브랜치에서 실행해야 합니다.")

        logger.info(f"현재 기능 브랜치: {feature_branch}")
        
        # 1. 메인 브랜치로 전환 및 최신화
        switch_result = switch_to_main_and_pull(repo_path, branch_name=main_branch)
        logger.info(switch_result)
        
        # 2. 기능 브랜치 병합
        logger.info(f"'{feature_branch}'을(를) '{main_branch}'(으)로 병합합니다...")
        merge_command = ["git", "merge", "--no-ff", feature_branch] # No-Fast-Forward
        merge_result = _run_git_command(merge_command, cwd=repo_path)
        logger.info(f"병합 완료:\n{merge_result}")
        
        # 3. 메인 브랜치 푸시
        push_result = git_push(repo_path, "origin", main_branch)
        logger.info(f"푸시 완료:\n{push_result}")
        
        # 4. 로컬 기능 브랜치 삭제
        logger.info(f"로컬 브랜치 '{feature_branch}'을(를) 삭제합니다...")
        delete_command = ["git", "branch", "-d", feature_branch]
        delete_result = _run_git_command(delete_command, cwd=repo_path)
        
        return (
            f"워크플로우 완료:\n"
            f"1. '{feature_branch}'가 '{main_branch}'에 병합되었습니다.\n"
            f"2. '{main_branch}'가 'origin'에 푸시되었습니다.\n"
            f"3. 로컬 브랜치 '{feature_branch}'가 삭제되었습니다."
        )

    except Exception as e:
        logger.error(f"기능 브랜치 완료 중 오류: {e}")
        # 충돌 또는 오류 발생 시 사용자 개입을 위해 현재 상태를 알림
        try:
            current_status = git_status(repo_path)
            raise RuntimeError(f"워크플로우 실패: {e}\n\n현재 상태:\n{current_status}")
        except Exception as status_e:
            raise RuntimeError(f"워크플로우 실패: {e}\n(현재 상태 확인도 실패: {status_e})")
