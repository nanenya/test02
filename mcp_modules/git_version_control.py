#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git_version_control.py

Git 버전 관리 작업을 수행하는 MCP(Mission Control Primitive) 모음입니다.
이 모듈은 로컬 파일 시스템에서 Git 명령어를 실행하여 저장소 생성, 복제,
상태 확인, 커밋, 푸시, 풀 등의 핵심 기능을 안전하게 래핑합니다.
"""

import logging
import os
import re
import subprocess
import shlex
from typing import List, Optional

# --- 로거 설정 ---
# 이 모듈을 사용하는 애플리케이션에서 로깅 설정을 구성하는 것을 권장합니다.
# 기본 로거가 설정되지 않은 경우를 대비한 기본 설정입니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 사용자 정의 예외 ---
class GitCommandError(Exception):
    """Git 명령어 실행 중 오류가 발생했을 때 사용되는 사용자 정의 예외입니다."""
    def __init__(self, message, stderr=None):
        super().__init__(message)
        self.stderr = stderr

    def __str__(self):
        if self.stderr:
            return f"{super().__str__()}\n--- Git Error ---\n{self.stderr}"
        return super().__str__()

# --- 헬퍼 함수 ---
def _is_valid_git_ref_name(name: str) -> bool:
    """
    브랜치나 태그 이름이 Git의 규칙에 맞는지 검사합니다.
    규칙: 공백이나 ASCII 제어 문자를 포함하지 않으며, 특정 특수문자로 시작하거나 끝나지 않습니다.
    """
    # Git refname 규칙을 단순화하여 일반적인 케이스를 검증합니다.
    # 공백, 이중 점(..), 역슬래시(\) 등을 포함할 수 없습니다.
    if " " in name or ".." in name or "\\" in name:
        return False
    # 일반적으로 사용되는 안전한 문자셋(영숫자, '-', '_', '/', '.')으로 제한합니다.
    if not re.match(r'^[a-zA-Z0-9/._-]+$', name):
        return False
    return True

def _is_valid_commit_hash(hash_str: str) -> bool:
    """ commit 해시가 유효한 형식인지 검사합니다. (40자리의 16진수 문자열) """
    return bool(re.match(r'^[0-9a-f]{7,40}$', hash_str))

def _run_git_command(command: List[str]) -> str:
    """
    지정된 Git 명령어를 안전하게 실행하고 결과를 반환하는 중앙 함수.

    Args:
        command (List[str]): 'git'으로 시작하는 명령어와 인자 리스트.

    Returns:
        str: 명령어 실행 성공 시 표준 출력(stdout) 결과.

    Raises:
        subprocess.CalledProcessError: Git 명령어 실행 실패 시 발생.
        FileNotFoundError: 'git' 실행 파일을 찾을 수 없을 때 발생.
    """
    try:
        logger.info(f"실행할 Git 명령어: {' '.join(command)}")
        # shell=False 와 인자 리스트 전달로 셸 주입 공격을 방지합니다.
        # text=True: stdout/stderr를 텍스트로 디코딩합니다.
        # check=True: 리턴 코드가 0이 아닐 경우 CalledProcessError를 발생시킵니다.
        result = subprocess.run(
            command, cwd=cwd, check=True, text=True, encoding='utf-8',
            stdout=subprocess.PIPE,  # 표준 출력을 받기 위해 설정
            stderr=subprocess.PIPE   # 표준 에러를 받기 위해 설정
        )
        logger.info(f"명령어 실행 성공. stdout 길이: {len(result.stdout)}")
        # stdout과 stderr에 내용이 모두 있을 수 있으므로 합쳐서 반환
        output = result.stdout.strip()
        error_output = result.stderr.strip()
        return f"{output}\n{error_output}".strip()
    except FileNotFoundError:
        logger.error("'git' 명령어를 찾을 수 없습니다. 시스템에 Git이 설치되어 있는지 확인하세요.")
        raise
    except subprocess.CalledProcessError as e:
        # Git 명령어 실패 시, 에러 내용을 로그에 상세히 기록합니다.
        logger.error(f"Git 명령어 실행 실패: {' '.join(command)}")
        logger.error(f"Return Code: {e.returncode}")
        logger.error(f"Stdout: {e.stdout.strip()}")
        logger.error(f"Stderr: {e.stderr.strip()}")
        # 에러를 다시 발생시켜 호출한 쪽에서 처리할 수 있도록 합니다.
        raise

def _run_git_command(command: List[str], cwd: str) -> str:
    """
    지정된 작업 디렉토리에서 Git 명령어를 안전하게 실행하고 결과를 반환합니다.

    Args:
        command (List[str]): 실행할 Git 명령어와 인자들의 리스트.
        cwd (str): 명령어를 실행할 디렉토리 경로.

    Returns:
        str: 명령어 실행 결과(stdout).

    Raises:
        GitCommandError: 명령어 실행 실패 시 발생.
        FileNotFoundError: 작업 디렉토리(cwd)가 존재하지 않을 경우 발생.
    """
    if not os.path.isdir(cwd):
        raise FileNotFoundError(f"작업 디렉토리를 찾을 수 없습니다: {cwd}")

    try:
        logger.info(f"'{cwd}'에서 Git 명령어 실행: {' '.join(command)}")
        # shell=False (기본값)는 셸 인젝션 공격을 방지합니다.
        process = subprocess.run(
            command,
            cwd=cwd,
            check=True,  # 반환 코드가 0이 아니면 CalledProcessError 발생
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        logger.info(f"명령어 성공: {' '.join(command)}")
        return process.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_message = f"Git 명령어 실행 실패: {' '.join(command)}"
        logger.error(f"{error_message}\nstderr: {e.stderr.strip()}")
        raise GitCommandError(error_message, stderr=e.stderr.strip()) from e
    except Exception as e:
        error_message = f"Git 명령어 실행 중 예기치 않은 오류 발생: {' '.join(command)}"
        logger.error(error_message, exc_info=True)
        raise GitCommandError(error_message) from e


# --- MCP 함수들 ---

def git_init(path: str) -> str:
    """
    지정된 경로에 새로운 Git 저장소를 초기화합니다.

    Args:
        path (str): Git 저장소를 초기화할 디렉토리 경로. 디렉토리가 없다면 생성됩니다.

    Returns:
        str: 성공 시, 초기화된 저장소의 절대 경로를 반환합니다.

    Raises:
        GitCommandError: 'git init' 명령어 실행 실패 시 발생합니다.
        OSError: 디렉토리 생성에 실패했을 경우 발생합니다.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_path = git_init(tmpdir)
        ...     print(os.path.isdir(os.path.join(repo_path, '.git')))
        True
    """
    logger.info(f"'{path}' 경로에 Git 저장소 초기화를 시작합니다.")
    try:
        # 대상 디렉토리가 없으면 생성 (exist_ok=True로 멱등성 보장)
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        logger.error(f"디렉토리 생성 실패: {path}", exc_info=True)
        raise

    command = ['git', 'init']
    _run_git_command(command, cwd=path)
    abs_path = os.path.abspath(path)
    logger.info(f"성공적으로 Git 저장소를 초기화했습니다: {abs_path}")
    return abs_path

def git_clone(repo_url: str, local_path: str) -> str:
    """
    원격 저장소를 지정된 로컬 경로로 복제(clone)합니다.

    Args:
        repo_url (str): 복제할 원격 Git 저장소의 URL.
        local_path (str): 저장소를 복제할 로컬 디렉토리 경로.

    Returns:
        str: 성공 시, 복제된 로컬 저장소의 절대 경로를 반환합니다.

    Raises:
        GitCommandError: 'git clone' 명령어 실행 실패 시 발생합니다.
        ValueError: local_path가 비어있지 않은 디렉토리일 경우 발생합니다.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # 이 예제는 실제 네트워크 연결을 시도하므로 테스트 시 주의가 필요합니다.
        ...     # repo_path = git_clone("https://github.com/git/git.git", tmpdir)
        ...     # print(os.path.isdir(os.path.join(repo_path, '.git')))
        ...     pass # 실제 실행 방지를 위해 pass
    """
    logger.info(f"'{repo_url}'을(를) '{local_path}'(으)로 복제를 시작합니다.")
    # 보안: local_path에 파일이 있으면 Git이 오류를 내지만, 미리 확인하여 명확한 오류 제공
    if os.path.exists(local_path) and os.listdir(local_path):
        raise ValueError(f"대상 경로 '{local_path}'가 비어있지 않습니다.")

    # clone은 특정 디렉토리 '내부'가 아니라 '상위' 디렉토리에서 실행해야 함.
    parent_dir = os.path.dirname(local_path)
    repo_name = os.path.basename(local_path)

    if not parent_dir:
        parent_dir = "." # 현재 디렉토리

    os.makedirs(parent_dir, exist_ok=True)

    # 보안: repo_url 인자는 명령어 리스트에 분리하여 전달, 셸 인젝션 방지
    command = ['git', 'clone', repo_url, repo_name]
    _run_git_command(command, cwd=parent_dir)
    abs_path = os.path.abspath(local_path)
    logger.info(f"성공적으로 저장소를 복제했습니다: {abs_path}")
    return abs_path

def git_status(repo_path: str) -> str:
    """
    현재 작업 디렉토리의 Git 상태를 반환합니다.

    Args:
        repo_path (str): Git 상태를 확인할 저장소의 경로.

    Returns:
        str: 'git status' 명령어의 전체 출력 문자열.

    Raises:
        GitCommandError: 'git status' 명령어 실행 실패 시 발생합니다.
        FileNotFoundError: repo_path가 유효한 디렉토리가 아닐 경우 발생합니다.

    Example:
        >>> # repo_path = git_init('./my-test-repo')
        >>> # status = git_status(repo_path)
        >>> # assert 'On branch' in status
        >>> pass
    """
    logger.info(f"'{repo_path}'의 Git 상태를 확인합니다.")
    command = ['git', 'status']
    status_output = _run_git_command(command, cwd=repo_path)
    logger.debug(f"Git 상태:\n{status_output}")
    return status_output

def git_add(repo_path: str, files: List[str]) -> None:
    """
    특정 파일 목록을 스테이징(staging) 영역에 추가합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        files (List[str]): 스테이징할 파일들의 리스트. '.'를 사용하여 모든 변경사항을 추가할 수 있습니다.

    Returns:
        None: 성공적으로 완료되면 아무것도 반환하지 않습니다.

    Raises:
        GitCommandError: 'git add' 명령어 실행 실패 시 발생합니다.
        ValueError: 파일 리스트가 비어있을 경우 발생합니다.

    Example:
        >>> # repo_path = git_init('./my-test-repo')
        >>> # with open(os.path.join(repo_path, 'test.txt'), 'w') as f:
        ... #     f.write('hello')
        >>> # git_add(repo_path, ['test.txt'])
        >>> pass
    """
    if not files:
        raise ValueError("스테이징할 파일이 제공되지 않았습니다.")

    logger.info(f"'{repo_path}'에서 파일 스테이징: {files}")
    # 보안: 파일 이름에 공백이나 특수문자가 있을 수 있으므로 shlex.quote 대신 리스트로 전달
    command = ['git', 'add'] + files
    _run_git_command(command, cwd=repo_path)
    logger.info("파일을 성공적으로 스테이징했습니다.")


def git_commit(repo_path: str, message: str) -> str:
    """
    스테이징된 변경 사항들을 메시지와 함께 커밋합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        message (str): 커밋에 사용할 메시지.

    Returns:
        str: 'git commit' 명령어의 결과 메시지 (보통 커밋 요약 정보).

    Raises:
        GitCommandError: 'git commit' 명령어 실행 실패 시 발생합니다.
        ValueError: 커밋 메시지가 비어있을 경우 발생합니다.

    Example:
        >>> # ... git_add 실행 후 ...
        >>> # commit_result = git_commit(repo_path, "첫 번째 커밋")
        >>> # assert '1 file changed' in commit_result
        >>> pass
    """
    if not message.strip():
        raise ValueError("커밋 메시지는 비어 있을 수 없습니다.")

    logger.info(f"'{repo_path}'에서 커밋 생성: {message}")
    # 보안: 메시지 인자는 명령어 리스트에 분리하여 전달
    command = ['git', 'commit', '-m', message]
    result = _run_git_command(command, cwd=repo_path)
    logger.info("성공적으로 커밋했습니다.")
    return result

def git_push(repo_path: str, remote: str = "origin", branch: str = "main") -> str:
    """
    로컬 커밋을 원격 저장소로 푸시합니다.

    경고: 이 기능은 원격 저장소의 상태를 변경하며 네트워크 연결이 필요합니다.
          인증 정보(SSH 키, 사용자 이름/비밀번호)가 시스템에 사전 설정되어 있어야 합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        remote (str, optional): 푸시할 원격 저장소의 이름. 기본값은 'origin'.
        branch (str, optional): 푸시할 브랜치의 이름. 기본값은 'main'.

    Returns:
        str: 'git push' 명령어의 결과 메시지.

    Raises:
        GitCommandError: 'git push' 명령어 실행 실패 시 발생합니다.

    Example:
        >>> # ... 원격 저장소 설정 후 ...
        >>> # push_result = git_push(repo_path, 'origin', 'main')
        >>> pass
    """
    logger.warning(f"'{repo_path}'에서 원격 저장소 '{remote}/{branch}'(으)로 푸시를 시도합니다. 원격 상태가 변경될 수 있습니다.")
    command = ["git", "push", remote, branch]
    try:
        # check=True를 사용하면 실패 시 CalledProcessError가 자동으로 발생합니다.
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            cwd=repo_path, 
            check=True # 이 옵션이 중요합니다!
        )
        # 성공 메시지는 stderr에 있을 가능성이 높음
        return result.stderr.strip()
    except subprocess.CalledProcessError as e:
        # Git 명령어 실패 시, 잡은 예외를 우리의 커스텀 예외로 변환하여 다시 발생시킵니다.
        # e.stderr에 Git의 실제 에러 메시지가 담겨 있습니다.
        raise GitCommandError(f"Git push 실패: {e.stderr.strip()}") from e

def git_pull(repo_path: str, remote: str = "origin", branch: str = "main") -> str:
    """
    원격 저장소의 최신 변경 사항을 가져와 현재 브랜치에 병합(pull)합니다.

    경고: 이 기능은 로컬 파일 시스템의 내용을 변경하며 충돌(conflict)을 유발할 수 있습니다.
          네트워크 연결이 필요합니다.

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        remote (str, optional): 풀(pull)할 원격 저장소의 이름. 기본값은 'origin'.
        branch (str, optional): 풀(pull)할 브랜치의 이름. 기본값은 'main'.

    Returns:
        str: 'git pull' 명령어의 결과 메시지.

    Raises:
        GitCommandError: 'git pull' 명령어 실행 실패 시 발생합니다.

    Example:
        >>> # ... 원격 저장소에 변경사항이 있을 경우 ...
        >>> # pull_result = git_pull(repo_path, 'origin', 'main')
        >>> pass
    """
    logger.warning(f"'{repo_path}'에서 원격 저장소 '{remote}/{branch}'의 변경사항을 풀(pull)합니다. 로컬 파일이 변경될 수 있습니다.")
    command = ['git', 'pull', remote, branch]
    result = _run_git_command(command, cwd=repo_path)
    logger.info(f"성공적으로 '{remote}/{branch}'에서 풀(pull)했습니다.")
    return result

def git_fetch(repo_path: str, remote: str = "origin") -> str:
    """
    원격 저장소의 최신 내역을 가져오지만, 로컬 브랜치에 병합은 하지 않습니다(fetch).

    Args:
        repo_path (str): 대상 Git 저장소의 경로.
        remote (str, optional): 페치(fetch)할 원격 저장소의 이름. 기본값은 'origin'.

    Returns:
        str: 'git fetch' 명령어의 결과 메시지 (보통 빈 문자열).

    Raises:
        GitCommandError: 'git fetch' 명령어 실행 실패 시 발생합니다.

    Example:
        >>> # ... 원격 저장소에 변경사항이 있을 경우 ...
        >>> # fetch_result = git_fetch(repo_path, 'origin')
        >>> pass
    """
    logger.info(f"'{repo_path}'에서 원격 저장소 '{remote}'의 내역을 페치(fetch)합니다.")
    command = ['git', 'fetch', remote]
    result = _run_git_command(command, cwd=repo_path)
    logger.info(f"성공적으로 '{remote}'에서 페치(fetch)했습니다.")
    return result

def git_create_branch(branch_name: str, cwd: str = "."):
    """
    새로운 로컬 브랜치를 생성합니다.

    Args:
        branch_name (str): 생성할 브랜치의 이름.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 형식일 때 발생합니다.
        subprocess.CalledProcessError: Git 명령어 실행에 실패했을 때 발생합니다.

    Example:
        >>> git_create_branch("feature/new-login-page")
    """
    if not _is_valid_git_ref_name(branch_name):
        raise ValueError(f"유효하지 않은 브랜치 이름입니다: '{branch_name}'")
    _run_git_command(["git", "branch", branch_name], cwd=cwd)
    logger.info(f"성공적으로 브랜치를 생성했습니다: {branch_name}")


def git_switch_branch(branch_name: str, cwd: str = "."):
    """
    지정된 브랜치로 전환합니다. (git switch 사용)

    Args:
        branch_name (str): 전환할 브랜치의 이름.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 형식일 때 발생합니다.
        subprocess.CalledProcessError: 존재하지 않는 브랜치 등으로 전환에 실패했을 때 발생합니다.

    Example:
        >>> git_switch_branch("main")
    """
    if not _is_valid_git_ref_name(branch_name):
        raise ValueError(f"유효하지 않은 브랜치 이름입니다: '{branch_name}'")
    _run_git_command(["git", "switch", branch_name], cwd=cwd)
    logger.info(f"성공적으로 브랜치를 전환했습니다: {branch_name}")


def git_list_branches(cwd: str = ".") -> List[str]:
    """
    로컬 및 원격 브랜치 목록을 반환합니다.

    Returns:
        List[str]: 모든 브랜치 이름의 리스트. 현재 활성화된 브랜치는 이름 앞에 '*'가 붙습니다.

    Example:
        >>> branches = git_list_branches()
        >>> print(branches)
        ['* main', 'develop', 'remotes/origin/main']
    """
    output = _run_git_command(["git", "branch", "-a"], cwd=cwd)
    return [line.strip() for line in output.split('\n') if line]


def git_merge(branch_to_merge: str, cwd: str = "."):
    """
    다른 브랜치의 변경 사항을 현재 브랜치로 병합(merge)합니다.

    경고: 이 기능은 현재 작업 디렉토리의 상태를 변경하는 위험한 작업입니다.
    실행 전 반드시 작업 내용을 커밋하거나 스태시(stash)해야 합니다.
    충돌(conflict) 발생 시, 명령어는 실패하며 사용자가 직접 해결해야 합니다.

    Args:
        branch_to_merge (str): 현재 브랜치로 병합할 대상 브랜치의 이름.

    Raises:
        ValueError: 브랜치 이름이 유효하지 않은 형식일 때 발생합니다.
        subprocess.CalledProcessError: 병합 중 충돌이 발생하거나 다른 문제가 생겼을 때 발생합니다.

    Example:
        >>> git_merge("develop")
    """
    if not _is_valid_git_ref_name(branch_to_merge):
        raise ValueError(f"유효하지 않은 브랜치 이름입니다: '{branch_to_merge}'")
    logger.warning(f"'{branch_to_merge}' 브랜치를 현재 브랜치로 병합합니다. 작업 디렉토리가 변경될 수 있습니다.")
    _run_git_command(["git", "merge", branch_to_merge], cwd=cwd)
    logger.info(f"성공적으로 브랜치를 병합했습니다: {branch_to_merge}")


def git_log(limit: int = 10, cwd: str = ".") -> str:
    """
    최근 커밋 기록을 지정된 수만큼 보여줍니다.

    Args:
        limit (int, optional): 가져올 커밋의 최대 개수. 기본값은 10입니다.

    Returns:
        str: 포맷팅된 git 로그 문자열.

    Raises:
        ValueError: limit이 0 이하의 정수가 아닐 경우 발생합니다.

    Example:
        >>> print(git_log(5))
    """
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit은 0보다 큰 정수여야 합니다.")
    return _run_git_command(["git", "log", f"-n{limit}", "--oneline"], cwd=cwd)


def git_diff(file: Optional[str] = None) -> str:
    """
    변경되었지만 아직 스테이징되지 않은 내용의 차이를 보여줍니다.

    Args:
        file (Optional[str], optional): 특정 파일의 변경 내용만 보려면 파일 경로를 지정합니다.
                                      None이면 모든 변경 내용을 보여줍니다. 기본값은 None입니다.

    Returns:
        str: 'git diff' 결과 문자열. 변경 내용이 없으면 빈 문자열을 반환합니다.
    """
    command = ["git", "diff"]
    if file:
        command.append(file)
    return _run_git_command(command)


def git_add_remote(name: str, url: str):
    """
    새로운 원격 저장소 주소를 추가합니다.

    Args:
        name (str): 원격 저장소의 별칭 (예: 'origin', 'upstream').
        url (str): 원격 저장소의 URL.

    Raises:
        ValueError: 원격 저장소 이름이나 URL이 유효하지 않을 때 발생합니다.

    Example:
        >>> git_add_remote("upstream", "https://github.com/some/repo.git")
    """
    if not _is_valid_git_ref_name(name):
        raise ValueError(f"유효하지 않은 원격 저장소 이름입니다: '{name}'")
    # URL에 대한 간단한 검증 (http로 시작하는지)
    if not url.startswith(('http://', 'https://', 'git@')):
        raise ValueError(f"유효하지 않은 URL 형식입니다: '{url}'")
    _run_git_command(["git", "remote", "add", name, url])
    logger.info(f"성공적으로 원격 저장소를 추가했습니다: {name} -> {url}")


def git_create_tag(tag_name: str, message: str):
    """
    현재 커밋에 주석(annotated) 태그를 생성합니다.

    Args:
        tag_name (str): 생성할 태그의 이름 (예: 'v1.0.0').
        message (str): 태그에 대한 설명 메시지.

    Raises:
        ValueError: 태그 이름이 유효하지 않은 형식일 때 발생합니다.

    Example:
        >>> git_create_tag("v1.0.1", "Release version 1.0.1")
    """
    if not _is_valid_git_ref_name(tag_name):
        raise ValueError(f"유효하지 않은 태그 이름입니다: '{tag_name}'")
    _run_git_command(["git", "tag", "-a", tag_name, "-m", message], cwd=cwd)
    logger.info(f"성공적으로 태그를 생성했습니다: {tag_name}")


def git_list_tags() -> List[str]:
    """
    저장소에 존재하는 모든 태그의 목록을 반환합니다.

    Returns:
        List[str]: 태그 이름의 리스트.
    """
    output = _run_git_command(["git", "tag"], cwd=cwd)
    return [line.strip() for line in output.split('\n') if line]


def git_revert_commit(commit_hash: str, cwd: str = "."):
    """
    특정 커밋에서 발생한 변경 사항을 되돌리는 새로운 커밋을 생성합니다.

    경고: 이 기능은 새로운 커밋을 생성하여 과거의 변경을 되돌립니다.
    히스토리를 직접 수정하지는 않지만, 현재 브랜치에 새로운 커밋이 추가됩니다.

    Args:
        commit_hash (str): 되돌릴 대상 커밋의 해시.

    Raises:
        ValueError: 커밋 해시가 유효하지 않은 형식일 때 발생합니다.
        subprocess.CalledProcessError: 되돌리기 중 충돌이 발생하거나 다른 문제가 생겼을 때 발생합니다.
    """
    if not _is_valid_commit_hash(commit_hash):
        raise ValueError(f"유효하지 않은 커밋 해시 형식입니다: '{commit_hash}'")
    logger.warning(f"커밋 '{commit_hash}'의 변경 사항을 되돌리는 새로운 커밋을 생성합니다.")
    # --no-edit 옵션으로 revert 커밋 메시지를 자동으로 생성하도록 합니다.
    _run_git_command(["git", "revert", "--no-edit", commit_hash], cwd=cwd)
    logger.info(f"성공적으로 커밋을 되돌렸습니다: {commit_hash}")


def git_show_commit_details(commit_hash: str, cwd: str = ".") -> str:
    """
    특정 커밋의 상세 정보와 변경된 내용(diff)을 보여줍니다.

    Args:
        commit_hash (str): 조회할 커밋의 해시.

    Returns:
        str: 해당 커밋의 상세 정보 문자열.

    Raises:
        ValueError: 커밋 해시가 유효하지 않은 형식일 때 발생합니다.
    """
    if not _is_valid_commit_hash(commit_hash):
        raise ValueError(f"유효하지 않은 커밋 해시 형식입니다: '{commit_hash}'")
    return _run_git_command(["git", "show", commit_hash], cwd=cwd)


def git_get_current_branch(cwd: str = ".") -> str:
    """
    현재 작업 중인 브랜치의 이름을 반환합니다.

    Returns:
        str: 현재 브랜치의 이름. detached HEAD 상태인 경우, 해당 상태임을 알리는 메시지를 반환할 수 있습니다.
    """
    # 'git branch --show-current'는 detached HEAD 상태에서 빈 값을 반환합니다.
    return _run_git_command(["git", "branch", "--show-current"], cwd=cwd)
