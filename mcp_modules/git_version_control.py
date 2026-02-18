#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git_version_control.py: AI 에이전트를 위한 Git 버전 관리 MCP 라이브러리

Git 저장소의 상태 조회, 커밋, 브랜치 관리, 원격 저장소 연동 등
다양한 Git 작업을 수행하는 함수를 제공합니다.

MCP 서버 대체 가능 여부:
  - git MCP 서버로 대부분의 기능 대체 가능
  - git_revert_commit, git_list_branches 등 일부 함수는 로컬 구현 필요
"""

import logging
import os
import re
import subprocess
import sys
from typing import List, Optional

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --- 입력값 검증 정규식 ---
VALID_GIT_URL_REGEX = re.compile(r'^(https?://|git@|ssh://).+')
VALID_BRANCH_NAME_REGEX = re.compile(r'^[a-zA-Z0-9._/\-]+$')
VALID_COMMIT_HASH_REGEX = re.compile(r'^[0-9a-f]{7,40}$')


def _run_git(args: List[str], repo_path: Optional[str] = None) -> str:
    """내부 헬퍼: Git 명령어를 실행하고 stdout을 반환합니다.

    Args:
        args (List[str]): git 이후의 인자 목록 (예: ["status", "--short"]).
        repo_path (Optional[str]): 실행 디렉토리. None이면 os.getcwd() 사용.

    Returns:
        str: 명령어 stdout 출력 (strip 처리).

    Raises:
        subprocess.CalledProcessError: git 명령어 실행 실패 시.
        FileNotFoundError: git 실행 파일이 없는 경우.
    """
    cwd = repo_path or os.getcwd()
    cmd = ["git"] + args
    logger.info(f"git 실행: {' '.join(cmd)} (cwd={cwd})")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        cwd=cwd,
    )
    return result.stdout.strip()


def git_status(repo_path: Optional[str] = None) -> str:
    """Git 저장소의 현재 상태를 반환합니다.

    Args:
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git status 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> status = git_status()
        >>> isinstance(status, str)
        True
    """
    return _run_git(["status"], repo_path)


def git_add(file_path: str, repo_path: Optional[str] = None) -> str:
    """파일 또는 디렉토리를 스테이징 영역에 추가합니다.

    Args:
        file_path (str): 추가할 파일/디렉토리 경로. "." 이면 전체 추가.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git add 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_add("README.md")
    """
    return _run_git(["add", file_path], repo_path)


def git_commit(message: str, repo_path: Optional[str] = None) -> str:
    """스테이징된 변경사항을 커밋합니다.

    Args:
        message (str): 커밋 메시지.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git commit 출력 문자열.

    Raises:
        ValueError: 커밋 메시지가 비어 있는 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_commit("feat: add new feature")
    """
    if not message or not message.strip():
        raise ValueError("커밋 메시지는 비어 있을 수 없습니다.")
    return _run_git(["commit", "-m", message], repo_path)


def git_push(
    remote: str = "origin",
    branch: str = "main",
    repo_path: Optional[str] = None,
) -> str:
    """로컬 브랜치를 원격 저장소에 푸시합니다.

    Args:
        remote (str): 원격 저장소 이름. 기본값은 "origin".
        branch (str): 푸시할 브랜치 이름. 기본값은 "main".
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git push 출력 문자열.

    Raises:
        ValueError: branch 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_push("origin", "main")
    """
    if not VALID_BRANCH_NAME_REGEX.match(branch):
        raise ValueError(f"유효하지 않은 브랜치 이름: {branch}")
    return _run_git(["push", remote, branch], repo_path)


def git_pull(
    remote: str = "origin",
    branch: str = "main",
    repo_path: Optional[str] = None,
) -> str:
    """원격 저장소에서 최신 변경사항을 가져와 병합합니다.

    Args:
        remote (str): 원격 저장소 이름. 기본값은 "origin".
        branch (str): 가져올 브랜치 이름. 기본값은 "main".
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git pull 출력 문자열.

    Raises:
        ValueError: branch 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_pull()
    """
    if not VALID_BRANCH_NAME_REGEX.match(branch):
        raise ValueError(f"유효하지 않은 브랜치 이름: {branch}")
    return _run_git(["pull", remote, branch], repo_path)


def git_log(limit: int = 10, repo_path: Optional[str] = None) -> str:
    """커밋 로그를 한 줄 형식으로 반환합니다.

    Args:
        limit (int): 반환할 최대 커밋 수. 기본값은 10.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git log --oneline 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # log = git_log(5)
    """
    return _run_git(["log", "--oneline", f"-n{limit}"], repo_path)


def git_diff(
    file_path: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> str:
    """작업 디렉토리와 인덱스의 차이를 반환합니다.

    Args:
        file_path (Optional[str]): 특정 파일만 diff. None이면 전체.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git diff 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # diff = git_diff("README.md")
    """
    args = ["diff"]
    if file_path:
        args.append(file_path)
    return _run_git(args, repo_path)


def git_clone(url: str, dest_path: Optional[str] = None) -> str:
    """원격 Git 저장소를 로컬에 복제합니다.

    Args:
        url (str): 복제할 저장소 URL (http/https/git@/ssh:// 형식).
        dest_path (Optional[str]): 복제할 로컬 경로. None이면 현재 디렉토리에 생성.

    Returns:
        str: git clone 출력 문자열.

    Raises:
        ValueError: URL 형식이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_clone("https://github.com/example/repo.git", "/tmp/repo")
    """
    if not VALID_GIT_URL_REGEX.match(url):
        raise ValueError(f"유효하지 않은 Git URL: {url}")
    args = ["clone", url]
    if dest_path:
        args.append(dest_path)
    return _run_git(args)


def git_init(repo_path: Optional[str] = None) -> str:
    """현재 또는 지정한 디렉토리에 Git 저장소를 초기화합니다.

    Args:
        repo_path (Optional[str]): 초기화할 경로. None이면 현재 디렉토리.

    Returns:
        str: git init 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_init("/tmp/new_repo")
    """
    return _run_git(["init"], repo_path)


def git_create_branch(branch_name: str, repo_path: Optional[str] = None) -> str:
    """새 브랜치를 생성합니다.

    Args:
        branch_name (str): 생성할 브랜치 이름.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git branch 출력 문자열.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_create_branch("feature/new-feature")
    """
    if not VALID_BRANCH_NAME_REGEX.match(branch_name):
        raise ValueError(f"유효하지 않은 브랜치 이름: {branch_name}")
    return _run_git(["branch", branch_name], repo_path)


def git_list_branches(repo_path: Optional[str] = None) -> List[str]:
    """로컬 및 원격 브랜치 목록을 반환합니다.

    Args:
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        List[str]: 브랜치 이름 목록 (현재 브랜치 앞의 * 제거, strip 처리).

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # branches = git_list_branches()
    """
    output = _run_git(["branch", "-a"], repo_path)
    branches = []
    for line in output.splitlines():
        name = line.strip().lstrip('* ').strip()
        if name:
            branches.append(name)
    return branches


def git_checkout(branch_name: str, repo_path: Optional[str] = None) -> str:
    """지정한 브랜치로 전환합니다.

    Args:
        branch_name (str): 전환할 브랜치 이름.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git checkout 출력 문자열.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_checkout("main")
    """
    if not VALID_BRANCH_NAME_REGEX.match(branch_name):
        raise ValueError(f"유효하지 않은 브랜치 이름: {branch_name}")
    return _run_git(["checkout", branch_name], repo_path)


def git_merge(branch_name: str, repo_path: Optional[str] = None) -> str:
    """지정한 브랜치를 현재 브랜치에 병합합니다.

    Args:
        branch_name (str): 병합할 브랜치 이름.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git merge 출력 문자열.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시 (병합 충돌 포함).

    Example:
        >>> # git_merge("feature/new-feature")
    """
    if not VALID_BRANCH_NAME_REGEX.match(branch_name):
        raise ValueError(f"유효하지 않은 브랜치 이름: {branch_name}")
    return _run_git(["merge", branch_name], repo_path)


def git_stash(repo_path: Optional[str] = None) -> str:
    """작업 디렉토리의 변경사항을 임시 저장(stash)합니다.

    Args:
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git stash 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_stash()
    """
    return _run_git(["stash"], repo_path)


def git_stash_pop(repo_path: Optional[str] = None) -> str:
    """가장 최근의 stash를 꺼내어 작업 디렉토리에 적용합니다.

    Args:
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git stash pop 출력 문자열.

    Raises:
        subprocess.CalledProcessError: stash가 없거나 충돌 발생 시.

    Example:
        >>> # git_stash_pop()
    """
    return _run_git(["stash", "pop"], repo_path)


def git_tag(tag_name: str, message: Optional[str] = None, repo_path: Optional[str] = None) -> str:
    """태그를 생성합니다.

    Args:
        tag_name (str): 생성할 태그 이름.
        message (Optional[str]): 어노테이트 태그 메시지. None이면 경량 태그.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git tag 출력 문자열.

    Raises:
        ValueError: 태그 이름이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_tag("v1.0.0", "Release v1.0.0")
    """
    if not VALID_BRANCH_NAME_REGEX.match(tag_name):
        raise ValueError(f"유효하지 않은 태그 이름: {tag_name}")
    if message:
        args = ["tag", "-a", tag_name, "-m", message]
    else:
        args = ["tag", tag_name]
    return _run_git(args, repo_path)


def git_remote_add(name: str, url: str, repo_path: Optional[str] = None) -> str:
    """원격 저장소를 추가합니다.

    Args:
        name (str): 원격 저장소 이름 (예: "origin").
        url (str): 원격 저장소 URL.
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git remote add 출력 문자열.

    Raises:
        ValueError: URL 형식이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_remote_add("origin", "https://github.com/example/repo.git")
    """
    if not VALID_GIT_URL_REGEX.match(url):
        raise ValueError(f"유효하지 않은 Git URL: {url}")
    return _run_git(["remote", "add", name, url], repo_path)


def git_fetch(remote: str = "origin", repo_path: Optional[str] = None) -> str:
    """원격 저장소에서 최신 정보를 가져옵니다 (병합 없음).

    Args:
        remote (str): 원격 저장소 이름. 기본값은 "origin".
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git fetch 출력 문자열.

    Raises:
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_fetch()
    """
    return _run_git(["fetch", remote], repo_path)


def git_revert_commit(commit_hash: str, repo_path: Optional[str] = None) -> str:
    """지정한 커밋을 되돌리는 새 커밋을 생성합니다.

    Args:
        commit_hash (str): 되돌릴 커밋의 해시 (7~40자 16진수).
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git revert 출력 문자열.

    Raises:
        ValueError: commit_hash 형식이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_revert_commit("abc1234")
    """
    if not VALID_COMMIT_HASH_REGEX.match(commit_hash):
        raise ValueError(f"유효하지 않은 커밋 해시: {commit_hash}")
    return _run_git(["revert", "--no-edit", commit_hash], repo_path)


def git_show(commit_hash: str, repo_path: Optional[str] = None) -> str:
    """특정 커밋의 상세 정보와 변경 내용을 반환합니다.

    Args:
        commit_hash (str): 조회할 커밋 해시 (7~40자 16진수).
        repo_path (Optional[str]): 저장소 경로. None이면 현재 디렉토리.

    Returns:
        str: git show 출력 문자열.

    Raises:
        ValueError: commit_hash 형식이 유효하지 않은 경우.
        subprocess.CalledProcessError: git 명령어 실패 시.

    Example:
        >>> # git_show("abc1234")
    """
    if not VALID_COMMIT_HASH_REGEX.match(commit_hash):
        raise ValueError(f"유효하지 않은 커밋 해시: {commit_hash}")
    return _run_git(["show", commit_hash], repo_path)
