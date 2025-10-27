#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Composite Code & Execution Primitives
=====================================
이 모듈은 파일 실행, 패키지 관리, 버전 관리, 컨테이너 제어 등
복잡한 코드 및 시스템 실행 작업을 위한 복합 MCP(Mission Control Primitives)를 제공합니다.
모든 함수는 보안을 위해 외부 입력을 신중하게 검증하고 처리합니다.
"""

import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List

# --- 로거 설정 ---
# 프로덕션 환경에서는 JSON 포맷터 등을 사용하여 더 구조화된 로깅을 구성하는 것이 좋습니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 보안을 위한 상수 정의 ---
# 패키지 이름에 허용되는 정규식 (알파벳, 숫자, -, _, .)
VALID_PACKAGE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9\-_.]+$")
# Git URL에 대한 기본적인 정규식 (http(s) 또는 git@으로 시작)
VALID_GIT_URL_REGEX = re.compile(r"^(https?://|git@).*")
# Docker 이미지/컨테이너 이름에 대한 정규식
VALID_DOCKER_NAME_REGEX = re.compile(r"^[a-zA-Z0-9\-_./:]+$")


def _run_command(command_parts: List[str], cwd: str = None) -> str:
    """
    내부적으로 사용되는 셸 명령어 실행 함수.

    보안을 위해 명령어와 인자를 분리된 리스트로 받아 실행합니다.
    이를 통해 셸 인젝션 공격을 방지합니다.

    Args:
        command_parts (List[str]): 명령어와 각 인자를 포함하는 리스트.
        cwd (str, optional): 명령어를 실행할 작업 디렉토리. Defaults to None.

    Returns:
        str: 명령어 실행 결과의 표준 출력(stdout).

    Raises:
        FileNotFoundError: 명령어가 시스템에 존재하지 않을 경우 발생합니다.
        subprocess.CalledProcessError: 명령어가 0이 아닌 종료 코드로 실패했을 경우 발생합니다.
        subprocess.TimeoutExpired: 명령어가 지정된 시간 내에 완료되지 않을 경우 발생합니다.
    """
    logger.info(f"명령어 실행: {' '.join(command_parts)} (작업 디렉토리: {cwd or '.'})")
    try:
        # shlex.join을 사용하면 리스트를 안전한 문자열로 보여줄 수 있습니다.
        # 실제 실행은 리스트 형태로 전달하여 셸 인젝션을 방지합니다.
        process = subprocess.run(
            command_parts,
            check=True,  # 실패 시 CalledProcessError 발생
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=300,  # 5분 타임아웃
            cwd=cwd
        )
        logger.info(f"명령어 성공: {' '.join(command_parts)}")
        # stdout의 마지막 개행 문자를 제거하여 반환
        return process.stdout.strip()
    except FileNotFoundError as e:
        logger.error(f"명령어 '{command_parts[0]}'를 찾을 수 없습니다: {e}")
        raise
    except subprocess.CalledProcessError as e:
        error_message = (
            f"명령어 실행 실패: {' '.join(command_parts)}\n"
            f"종료 코드: {e.returncode}\n"
            f"표준 출력: {e.stdout.strip()}\n"
            f"표준 에러: {e.stderr.strip()}"
        )
        logger.error(error_message)
        raise
    except subprocess.TimeoutExpired as e:
        logger.error(f"명령어 시간 초과: {' '.join(command_parts)}: {e}")
        raise
    except Exception as e:
        logger.error(f"알 수 없는 오류 발생: {' '.join(command_parts)}: {e}")
        raise


def run_python_script(script_path: str) -> str:
    """
    지정된 경로의 파이썬 스크립트 파일을 실행하고 결과를 반환합니다.

    Args:
        script_path (str): 실행할 파이썬 스크립트의 경로.

    Returns:
        str: 스크립트 실행의 표준 출력(stdout) 결과.

    Raises:
        FileNotFoundError: 스크립트 파일이 존재하지 않을 경우 발생합니다.
        ValueError: 제공된 경로가 유효하지 않은 경우 발생합니다.
        subprocess.CalledProcessError: 스크립트 실행 중 오류가 발생한 경우.

    Example:
        >>> # test_script.py 내용: print("Hello World")
        >>> run_python_script("test_script.py")
        'Hello World'
    """
    logger.debug(f"스크립트 실행 요청: {script_path}")
    path = Path(script_path)
    if not path.is_file():
        raise FileNotFoundError(f"스크립트 파일을 찾을 수 없습니다: {script_path}")

    command = ["python", str(path.resolve())]
    return _run_command(command)


def install_python_package(package_name: str) -> str:
    """
    pip을 이용해 특정 파이썬 패키지를 설치합니다.

    Args:
        package_name (str): 설치할 파이썬 패키지의 이름. (예: "requests", "numpy==1.23.5")

    Returns:
        str: pip install 명령어의 표준 출력 결과.

    Raises:
        ValueError: 패키지 이름이 유효하지 않은 형식이거나 위험한 문자를 포함한 경우.
        subprocess.CalledProcessError: 패키지 설치에 실패한 경우.

    Example:
        >>> install_python_package("requests")
        '...Successfully installed requests-x.y.z...'
    """
    logger.debug(f"패키지 설치 요청: {package_name}")
    # 보안: 패키지 이름에 위험한 문자가 있는지 확인
    if not VALID_PACKAGE_NAME_REGEX.match(package_name.split("==")[0]):
        raise ValueError(f"유효하지 않은 패키지 이름입니다: {package_name}")

    command = ["python", "-m", "pip", "install", package_name]
    return _run_command(command)


def uninstall_python_package(package_name: str) -> str:
    """
    pip을 이용해 설치된 파이썬 패키지를 삭제합니다.

    Args:
        package_name (str): 삭제할 파이썬 패키지의 이름.

    Returns:
        str: pip uninstall 명령어의 표준 출력 결과.

    Raises:
        ValueError: 패키지 이름이 유효하지 않은 형식이거나 위험한 문자를 포함한 경우.
        subprocess.CalledProcessError: 패키지 삭제에 실패한 경우.

    Example:
        >>> uninstall_python_package("requests")
        '...Successfully uninstalled requests-x.y.z...'
    """
    logger.debug(f"패키지 삭제 요청: {package_name}")
    if not VALID_PACKAGE_NAME_REGEX.match(package_name):
        raise ValueError(f"유효하지 않은 패키지 이름입니다: {package_name}")

    command = ["python", "-m", "pip", "uninstall", "-y", package_name]
    return _run_command(command)


def lint_code_file(file_path: str, linter: str = "flake8") -> str:
    """
    코드 파일의 문법 오류나 스타일 문제를 검사(linting)합니다.

    Args:
        file_path (str): 린트 검사를 수행할 파일의 경로.
        linter (str, optional): 사용할 린터. 기본값은 "flake8".

    Returns:
        str: 린트 검사 결과. 문제가 없는 경우 빈 문자열을 반환할 수 있습니다.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우 발생합니다.
        ValueError: 지원하지 않는 린터를 지정한 경우.
        subprocess.CalledProcessError: 린트 검사 중 오류가 발생한 경우(보통 린트 위반 사항이 발견되었을 때).

    Example:
        >>> # test.py 내용: import os; x = 1 # E702, F401 오류 발생
        >>> lint_code_file("test.py")
        "test.py:1:1: F401 'os' imported but unused\ntest.py:1:11: E702 multiple statements on one line (semicolon)"
    """
    logger.debug(f"코드 린트 요청: {file_path} (린터: {linter})")
    if linter not in ["flake8", "black"]: # 지원하는 린터 목록
        raise ValueError(f"지원하지 않는 린터입니다: {linter}")

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    command = [linter, str(path.resolve())]
    if linter == "black":
        command.append("--check") # black은 --check 옵션으로 검사만 수행

    try:
        return _run_command(command)
    except subprocess.CalledProcessError as e:
        # 린터는 문제를 발견하면 0이 아닌 코드를 반환하는 경우가 많으므로,
        # 표준 출력/에러를 결과로 반환하는 것이 더 유용합니다.
        return f"Lint issues found:\nSTDOUT:\n{e.stdout.strip()}\nSTDERR:\n{e.stderr.strip()}"


def format_code_file(file_path: str) -> str:
    """
    코드 포매터(black)를 실행하여 코드 스타일을 자동으로 정리합니다.

    Args:
        file_path (str): 코드 포맷팅을 적용할 파일의 경로.

    Returns:
        str: 포맷팅 결과 메시지.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우 발생합니다.
        subprocess.CalledProcessError: 포맷팅 중 오류가 발생한 경우.

    Example:
        >>> # test.py 내용: x=1
        >>> format_code_file("test.py")
        'reformatted test.py'
    """
    logger.debug(f"코드 포맷팅 요청: {file_path}")
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    command = ["black", str(path.resolve())]
    return _run_command(command)


def get_git_status(repo_path: str) -> str:
    """
    지정된 로컬 저장소의 git 상태를 확인합니다.

    Args:
        repo_path (str): git 저장소의 경로.

    Returns:
        str: 'git status' 명령어의 실행 결과.

    Raises:
        FileNotFoundError: 지정된 경로가 디렉토리가 아니거나 존재하지 않을 경우.
        subprocess.CalledProcessError: git 명령어 실행에 실패한 경우 (예: git 저장소가 아님).

    Example:
        >>> get_git_status(".")
        'On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean'
    """
    logger.debug(f"Git 상태 확인 요청: {repo_path}")
    path = Path(repo_path)
    if not path.is_dir():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {repo_path}")

    command = ["git", "status"]
    return _run_command(command, cwd=str(path.resolve()))


def clone_git_repository(repo_url: str, clone_path: str) -> str:
    """
    원격 Git 저장소를 지정된 경로에 복제(clone)합니다.

    Args:
        repo_url (str): 복제할 원격 저장소의 URL.
        clone_path (str): 저장소를 복제할 로컬 디렉토리 경로.

    Returns:
        str: 성공적으로 복제되었다는 메시지.

    Raises:
        ValueError: Git URL이 유효하지 않은 형식일 경우.
        FileExistsError: 복제할 경로에 이미 파일이나 디렉토리가 존재하는 경우.
        subprocess.CalledProcessError: git clone 명령어 실행에 실패한 경우.

    Example:
        >>> clone_git_repository("https://github.com/user/repo.git", "./my-repo")
        "Cloning into './my-repo'..."
    """
    logger.debug(f"Git 클론 요청: {repo_url} -> {clone_path}")
    if not VALID_GIT_URL_REGEX.match(repo_url):
        raise ValueError("유효하지 않은 Git URL 형식입니다.")

    path = Path(clone_path)
    if path.exists():
        raise FileExistsError(f"지정한 경로가 이미 존재합니다: {clone_path}")

    command = ["git", "clone", repo_url, str(path.resolve())]
    result = _run_command(command)
    return f"저장소 {repo_url}을(를) {clone_path}에 성공적으로 복제했습니다.\n{result}"


def setup_python_venv(path: str) -> str:
    """
    지정된 경로에 파이썬 가상 환경을 생성합니다.

    Args:
        path (str): 가상 환경을 생성할 디렉토리 경로.

    Returns:
        str: 가상 환경이 성공적으로 생성되었다는 메시지.

    Raises:
        FileExistsError: 지정된 경로가 이미 존재하는 경우.
        subprocess.CalledProcessError: 가상 환경 생성에 실패한 경우.

    Example:
        >>> setup_python_venv("./my-venv")
        '가상 환경이 ./my-venv 에 성공적으로 생성되었습니다.'
    """
    logger.debug(f"가상 환경 생성 요청: {path}")
    venv_path = Path(path)
    if venv_path.exists():
        raise FileExistsError(f"지정한 경로가 이미 존재합니다: {path}")

    command = ["python", "-m", "venv", str(venv_path.resolve())]
    _run_command(command)
    return f"가상 환경이 {path} 에 성공적으로 생성되었습니다."


def build_docker_image(dockerfile_path: str, image_name: str) -> str:
    """
    지정된 Dockerfile을 사용하여 새로운 도커 이미지를 빌드합니다.

    Args:
        dockerfile_path (str): Dockerfile이 위치한 디렉토리 경로.
        image_name (str): 빌드할 이미지의 이름과 태그 (예: "my-app:1.0").

    Returns:
        str: 'docker build' 명령어의 실행 결과.

    Raises:
        FileNotFoundError: Dockerfile 경로가 디렉토리가 아니거나 존재하지 않을 경우.
        ValueError: 이미지 이름이 유효하지 않은 형식일 경우.
        subprocess.CalledProcessError: 이미지 빌드에 실패한 경우.

    Example:
        >>> build_docker_image(".", "my-test-app:latest")
        '...Successfully built a1b2c3d4e5f6\nSuccessfully tagged my-test-app:latest'
    """
    logger.debug(f"Docker 이미지 빌드 요청: {image_name} from {dockerfile_path}")
    if not VALID_DOCKER_NAME_REGEX.match(image_name):
        raise ValueError(f"유효하지 않은 Docker 이미지 이름입니다: {image_name}")

    path = Path(dockerfile_path)
    if not path.is_dir():
        raise FileNotFoundError(f"Dockerfile 디렉토리를 찾을 수 없습니다: {dockerfile_path}")

    command = ["docker", "build", "-t", image_name, "."]
    return _run_command(command, cwd=str(path.resolve()))


def run_container_from_image(image_name: str, ports: Dict[int, int] = None) -> str:
    """
    지정된 도커 이미지로 컨테이너를 실행합니다.

    Args:
        image_name (str): 실행할 도커 이미지의 이름.
        ports (Dict[int, int], optional): 포트 매핑. {host_port: container_port}. Defaults to None.

    Returns:
        str: 실행된 컨테이너의 ID.

    Raises:
        ValueError: 이미지 이름이 유효하지 않거나 포트 번호가 잘못된 경우.
        subprocess.CalledProcessError: 컨테이너 실행에 실패한 경우.

    Example:
        >>> run_container_from_image("hello-world")
        'abcdef123456...'
        >>> run_container_from_image("nginx:latest", ports={8080: 80})
        'fedcba654321...'
    """
    logger.debug(f"Docker 컨테이너 실행 요청: {image_name}, 포트: {ports}")
    if not VALID_DOCKER_NAME_REGEX.match(image_name):
        raise ValueError(f"유효하지 않은 Docker 이미지 이름입니다: {image_name}")

    command = ["docker", "run", "-d"] # -d: detached mode

    if ports:
        for host_port, container_port in ports.items():
            if not (0 < host_port < 65536 and 0 < container_port < 65536):
                raise ValueError("포트 번호는 1과 65535 사이여야 합니다.")
            command.extend(["-p", f"{host_port}:{container_port}"])

    command.append(image_name)
    return _run_command(command)


def get_container_logs(container_id: str) -> str:
    """
    실행 중인 도커 컨테이너의 로그를 가져옵니다.

    Args:
        container_id (str): 로그를 조회할 컨테이너의 ID 또는 이름.

    Returns:
        str: 해당 컨테이너의 로그.

    Raises:
        ValueError: 컨테이너 ID 형식이 유효하지 않은 경우.
        subprocess.CalledProcessError: 컨테이너 로그 조회에 실패한 경우 (예: 컨테이너가 없음).

    Example:
        >>> get_container_logs("my-running-container")
        'Server started on port 80...'
    """
    logger.debug(f"Docker 로그 요청: {container_id}")
    if not VALID_DOCKER_NAME_REGEX.match(container_id):
        raise ValueError(f"유효하지 않은 컨테이너 ID 형식입니다: {container_id}")

    command = ["docker", "logs", container_id]
    return _run_command(command)
