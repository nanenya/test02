#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_execution_atomic.py: AI 에이전트를 위한 레벨 1 원자(Atomic) MCP 핵심 라이브러리

이 모듈은 AI 에이전트가 운영체제, 파일 시스템, 코드 분석 등 기본적인 작업을
수행할 수 있도록 돕는 저수준(low-level)의 원자적 기능들을 제공합니다.
각 함수는 프로덕션 환경에서 사용될 것을 가정하여 보안, 로깅, 예외 처리를
중점적으로 고려하여 설계되었습니다.
"""

import logging
import os
import shlex
import socket
import subprocess
import sys
import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- 로깅 설정 ---
# 다른 시스템과 통합을 위해, 라이브러리 코드에서는 로거를 직접 설정하기보다
# 호출하는 쪽에서 설정하도록 하는 것이 가장 좋습니다.
# 여기서는 예시를 위해 기본 로거를 설정합니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# --- 보안 관련 설정 ---
# 실제 운영 환경에서는 허용/차단 목록을 외부 설정 파일이나 환경 변수에서 관리해야 합니다.
FORBIDDEN_COMMANDS = {'rm', 'mv', 'dd', 'mkfs'} # 매우 위험한 명령어 예시 집합
ALLOWED_BASE_PATH = Path(os.getcwd()).resolve() # 파일 접근을 현재 작업 디렉토리로 제한

def execute_shell_command(command: str, timeout: int = 10) -> str:
    """안전하게 셸 명령어를 실행하고 결과를 문자열로 반환합니다.

    보안을 위해 명령어와 인자를 분리하고, 실행 시간을 제한하며, 위험한 명령어 실행을 차단합니다.
    셸 주입(Shell Injection) 공격을 방지하기 위해 `shlex.split`를 사용합니다.

    Args:
        command (str): 실행할 셸 명령어 문자열. (예: "ls -l /tmp")
        timeout (int, optional): 명령어 실행 최대 대기 시간(초). 기본값은 10.

    Returns:
        str: 명령어 실행 성공 시 stdout 출력 결과. 실패 시 stderr 내용을 포함한 오류 메시지.

    Raises:
        ValueError: 실행이 금지된 위험한 명령어가 포함된 경우 발생합니다.
        TimeoutError: 지정된 시간 내에 명령어가 완료되지 않은 경우 발생합니다.

    Example:
        >>> result = execute_shell_command("echo 'hello world'")
        >>> print(result)
        hello world
    """
    logger.info(f"셸 명령어 실행 시도: {command}")
    try:
        # 셸 주입 공격 방지를 위해 명령어를 안전하게 분리
        args = shlex.split(command)
        
        # 보안 검사: 금지된 명령어 실행 차단
        if args and args[0] in FORBIDDEN_COMMANDS:
            logger.error(f"금지된 명령어 실행 시도 차단: {args[0]}")
            raise ValueError(f"보안 오류: '{args[0]}' 명령어는 실행할 수 없습니다.")

        # 자식 프로세스로 명령어 실행
        process = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False, # 오류 발생 시 예외를 자동으로 발생시키지 않음 (수동 처리)
            timeout=timeout
        )

        if process.returncode == 0:
            logger.info(f"명령어 실행 성공: {command}")
            return process.stdout.strip()
        else:
            logger.error(f"명령어 실행 실패: {command}, 오류: {process.stderr.strip()}")
            return f"오류 발생: {process.stderr.strip()}"

    except FileNotFoundError:
        logger.error(f"명령어를 찾을 수 없음: {command.split()[0]}")
        return f"오류 발생: '{command.split()[0]}' 명령어를 찾을 수 없습니다."
    except subprocess.TimeoutExpired:
        logger.error(f"명령어 실행 시간 초과: {command}")
        raise TimeoutError(f"'{command}' 명령어가 {timeout}초 내에 완료되지 않았습니다.")
    except ValueError as e: # 명시적으로 ValueError를 잡아서 다시 raise 합니다.
        logger.error(f"보안 오류 발생: {e}")
        raise e # 잡은 예외를 그대로 다시 발생시킴
    except Exception as e:
        logger.exception(f"셸 명령어 실행 중 예기치 않은 오류 발생: {command}")
        return f"예기치 않은 오류: {e}"

def execute_python_code(code_str: str, sandboxed: bool = False) -> Any:
    """파이썬 코드 문자열을 실행하고 결과를 반환합니다. (매우 위험)

    이 함수는 `exec`를 사용하므로 극도의 주의가 필요합니다.
    반드시 격리된 샌드박스 환경(예: Docker 컨테이너)에서만 호출되어야 합니다.
    안전장치로 `sandboxed` 인자를 True로 명시해야만 실행됩니다.

    Args:
        code_str (str): 실행할 파이썬 코드.
        sandboxed (bool, optional): 코드가 샌드박스 환경에서 실행되는지 여부.
            이 값이 True가 아니면 보안을 위해 코드를 실행하지 않습니다. 기본값은 False.

    Returns:
        Any: 코드 실행 결과. `result` 변수에 할당된 값을 반환합니다.
             결과가 없으면 None을 반환합니다.

    Raises:
        PermissionError: `sandboxed` 인자가 True로 설정되지 않은 경우 발생합니다.
        Exception: 코드 실행 중 발생하는 모든 예외.

    Example:
        >>> code = "result = 1 + 1"
        >>> execute_python_code(code, sandboxed=True)
        2
    """
    logger.warning(f"파이썬 코드 실행 시도 (샌드박스: {sandboxed}): {code_str[:50]}...")
    if not sandboxed:
        logger.critical("보안 위험: 샌드박스 환경이 아닌 곳에서 코드 실행 시도가 차단되었습니다.")
        raise PermissionError("보안 오류: 이 기능은 반드시 샌드박스 환경에서만 사용해야 합니다.")

    try:
        # 실행 결과를 담을 로컬 네임스페이스
        local_scope = {}
        exec(code_str, {}, local_scope)
        result = local_scope.get('result', None)
        logger.info("파이썬 코드 실행 성공.")
        return result
    except Exception as e:
        logger.exception("파이썬 코드 실행 중 오류 발생.")
        raise e

def read_code_file(path: str) -> str:
    """지정된 경로의 코드 파일 내용을 안전하게 읽어 문자열로 반환합니다.

    경로 조작(Path Traversal) 공격을 방지하기 위해 파일 경로를 검증합니다.

    Args:
        path (str): 읽을 파일의 경로.

    Returns:
        str: 파일의 전체 내용.

    Raises:
        ValueError: 파일 경로가 유효하지 않거나 허용된 경로를 벗어나는 경우.
        FileNotFoundError: 파일이 존재하지 않는 경우.
        PermissionError: 파일에 대한 읽기 권한이 없는 경우.
    """
    logger.info(f"파일 읽기 시도: {path}")
    try:
        # 경로 조작 공격 방지
        file_path = Path(path).resolve()
        if not file_path.is_relative_to(ALLOWED_BASE_PATH):
            logger.error(f"허용되지 않은 경로 접근 시도: {path}")
            raise ValueError("보안 오류: 허용된 디렉토리 외부의 파일에는 접근할 수 없습니다.")
        
        if not file_path.is_file():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

        return file_path.read_text(encoding='utf-8')
    
    except (FileNotFoundError, PermissionError, ValueError) as e:
        logger.error(f"파일 읽기 실패: {path}, 이유: {e}")
        raise e
    except Exception as e:
        logger.exception(f"파일 읽기 중 예기치 않은 오류 발생: {path}")
        raise IOError(f"파일을 읽는 중 오류가 발생했습니다: {e}")

def get_environment_variable(var_name: str) -> Optional[str]:
    """특정 환경 변수의 값을 조회합니다.

    Args:
        var_name (str): 조회할 환경 변수의 이름.

    Returns:
        Optional[str]: 환경 변수의 값. 존재하지 않으면 None을 반환합니다.

    Example:
        >>> # 'PATH' 환경 변수가 있다고 가정
        >>> get_environment_variable('PATH') is not None
        True
        >>> get_environment_variable('NON_EXISTENT_VAR_12345') is None
        True
    """
    logger.info(f"환경 변수 조회: {var_name}")
    return os.getenv(var_name)

def set_environment_variable(var_name: str, value: str) -> bool:
    """특정 환경 변수의 값을 설정하거나 새로 생성합니다.

    Args:
        var_name (str): 설정할 환경 변수의 이름.
        value (str): 할당할 값.

    Returns:
        bool: 설정 성공 시 True.
    
    Raises:
        ValueError: 변수 이름이나 값이 유효하지 않을 경우.
    """
    logger.info(f"환경 변수 설정: {var_name}")
    if not var_name or not isinstance(var_name, str):
        raise ValueError("환경 변수 이름은 빈 문자열일 수 없습니다.")
    try:
        os.environ[var_name] = str(value)
        return True
    except Exception as e:
        logger.error(f"환경 변수 설정 실패: {var_name}, 오류: {e}")
        return False

# execute_sql_query는 실제 구현 시 SQLAlchemy와 같은 라이브러리 사용을 권장합니다.
# 여기서는 개념을 보여주기 위한 의사(pseudo) 코드입니다.
def execute_sql_query(db_uri: str, query: str, params: Optional[Dict] = None) -> List[Dict]:
    """지정된 데이터베이스에 접속하여 SQL 쿼리를 안전하게 실행하고 결과를 반환합니다.

    SQL 주입(SQL Injection) 공격을 방지하기 위해 반드시 파라미터화된 쿼리를 사용해야 합니다.
    이 함수는 개념 증명을 위한 것이며, 실제 프로덕션에서는 SQLAlchemy 사용을 권장합니다.

    Args:
        db_uri (str): 데이터베이스 연결 정보 (예: "postgresql://user:pass@host/dbname").
        query (str): 실행할 SQL 쿼리문. 바인딩 변수는 `:key` 형태로 사용합니다.
        params (Optional[Dict]): 쿼리에 바인딩할 파라미터 딕셔너리.

    Returns:
        List[Dict]: 쿼리 결과. 각 행은 딕셔너리로 표현됩니다.

    Raises:
        ImportError: `sqlalchemy` 라이브러리가 설치되지 않은 경우.
        Exception: 데이터베이스 연결 또는 쿼리 실행 중 오류 발생 시.

    Example:
        >>> # 아래는 sqlalchemy가 설치되어 있고 DB가 실행중일 때 동작합니다.
        >>> # db_uri = "sqlite:///:memory:"
        >>> # query = "SELECT :p1 as col1, :p2 as col2;"
        >>> # params = {"p1": 1, "p2": "test"}
        >>> # result = execute_sql_query(db_uri, query, params)
        >>> # print(result)
        >>> # [{'col1': 1, 'col2': 'test'}]
    """
    logger.info(f"SQL 쿼리 실행 시도: {query[:50]}...")
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        logger.critical("SQLAlchemy 라이브러리가 필요합니다. 'pip install sqlalchemy'로 설치해주세요.")
        raise ImportError("SQLAlchemy is not installed.")

    try:
        engine = create_engine(db_uri)
        with engine.connect() as connection:
            # SQL Injection 방지를 위해 text()와 파라미터 바인딩 사용
            stmt = text(query)
            result = connection.execute(stmt, params or {})
            
            # 결과를 dict 리스트로 변환
            result_dicts = [row._asdict() for row in result]
            logger.info("SQL 쿼리 실행 성공.")
            return result_dicts
    except Exception as e:
        logger.exception("SQL 쿼리 실행 중 오류 발생.")
        raise e

def check_port_status(host: str, port: int, timeout: int = 3) -> Tuple[bool, str]:
    """특정 호스트의 포트가 열려 있는지 확인합니다.

    Args:
        host (str): 대상 호스트의 주소 (예: "google.com", "127.0.0.1").
        port (int): 확인할 포트 번호.
        timeout (int, optional): 연결 시도 대기 시간(초). 기본값은 3.

    Returns:
        Tuple[bool, str]: (포트 열림 여부, 상태 메시지) 튜플.
    """
    logger.info(f"포트 상태 확인 시도: {host}:{port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            status_message = f"성공: {host}:{port} 포트가 열려 있습니다."
            logger.info(status_message)
            return True, status_message
        else:
            status_message = f"실패: {host}:{port} 포트가 닫혀 있거나 접근할 수 없습니다."
            logger.warning(status_message)
            return False, status_message
    except socket.gaierror:
        error_message = f"오류: 호스트 이름을 확인할 수 없습니다: {host}"
        logger.error(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"예기치 않은 오류 발생: {e}"
        logger.exception(error_message)
        return False, error_message
    finally:
        sock.close()

def get_code_complexity(file_path: str) -> Dict[str, Any]:
    """코드 파일의 순환 복잡도(Cyclomatic Complexity)를 측정합니다.

    `radon` 라이브러리를 사용하여 코드의 유지보수성을 평가합니다.

    Args:
        file_path (str): 분석할 파이썬 파일의 경로.

    Returns:
        Dict[str, Any]: 파일의 복잡도 분석 결과 딕셔너리.

    Raises:
        FileNotFoundError: 파일이 존재하지 않는 경우.
        ValueError: radon 실행 실패 또는 결과 파싱 실패 시.
    """
    logger.info(f"코드 복잡도 분석 시도: {file_path}")
    if not Path(file_path).is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
    
    try:
        # radon을 JSON 출력 모드로 실행하여 안정적으로 결과 파싱
        command = f"radon cc -s -j {file_path}"
        result_json = execute_shell_command(command)
        
        if "오류 발생" in result_json:
            raise ValueError(f"radon 실행 실패: {result_json}")
        
        complexity_data = json.loads(result_json)
        logger.info(f"코드 복잡도 분석 성공: {file_path}")
        return complexity_data.get(file_path, {})
        
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"코드 복잡도 분석 결과 파싱 실패: {e}")
        raise ValueError(f"radon 결과 파싱 실패: {e}")
    except Exception as e:
        logger.exception(f"코드 복잡도 분석 중 예기치 않은 오류 발생: {file_path}")
        raise e

def get_function_signature(file_path: str, function_name: str) -> Optional[str]:
    """파이썬 파일 내에서 특정 함수의 시그니처를 추출합니다.

    `ast` 모듈을 사용하여 코드를 정적으로 분석하므로 코드를 직접 실행하지 않아 안전합니다.

    Args:
        file_path (str): 분석할 파이썬 파일의 경로.
        function_name (str): 시그니처를 추출할 함수의 이름.

    Returns:
        Optional[str]: 찾은 함수의 전체 시그니처 문자열. 함수를 찾지 못하면 None.

    Raises:
        FileNotFoundError: 파일이 존재하지 않는 경우.
    """
    logger.info(f"함수 시그니처 추출 시도: {file_path}의 {function_name}")
    try:
        code = read_code_file(file_path)
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                # astunparse와 같은 라이브러리를 사용하면 더 정확하지만,
                # 표준 라이브러리만으로 구현하기 위해 소스 코드에서 직접 추출
                lines = code.splitlines()
                # 데코레이터를 포함한 시작점부터 시그니처 끝까지 추출
                start_lineno = node.decorator_list[0].lineno if node.decorator_list else node.lineno
                end_lineno = node.body[0].lineno - 1
                
                signature_lines = lines[start_lineno-1:end_lineno]
                signature = ' '.join(line.strip() for line in signature_lines)
                logger.info(f"함수 시그니처 추출 성공: {function_name}")
                return signature
        
        logger.warning(f"함수를 찾지 못함: {function_name}")
        return None
    except FileNotFoundError:
        raise
    except Exception as e:
        logger.exception("함수 시그니처 추출 중 오류 발생.")
        return None

def list_installed_packages() -> List[Tuple[str, str]]:
    """현재 파이썬 환경에 설치된 패키지와 버전을 목록으로 반환합니다.

    `pip` 명령어를 실행하는 대신 `importlib.metadata`를 사용하여 더 안정적입니다.

    Returns:
        List[Tuple[str, str]]: (패키지 이름, 버전) 튜플의 리스트.
    """
    logger.info("설치된 패키지 목록 조회 시도.")
    try:
        from importlib import metadata
        packages = [(dist.metadata['name'], dist.version) for dist in metadata.distributions()]
        logger.info(f"{len(packages)}개의 설치된 패키지를 찾았습니다.")
        return sorted(packages, key=lambda x: x[0].lower())
    except Exception as e:
        logger.exception("설치된 패키지 목록 조회 중 오류 발생.")
        return []

def docker_list_containers() -> List[Dict]:
    """실행 중이거나 정지된 모든 도커 컨테이너 목록을 반환합니다.

    Returns:
        List[Dict]: 각 컨테이너의 정보를 담은 딕셔너리 리스트.
    
    Raises:
        ValueError: `docker` 명령어 실행 실패 시.
    """
    logger.info("도커 컨테이너 목록 조회 시도.")
    command = "docker ps -a --format '{{json .}}'"
    try:
        result = execute_shell_command(command)
        if not result:
            return []
        
        containers = [json.loads(line) for line in result.strip().split('\n')]
        logger.info(f"{len(containers)}개의 도커 컨테이너를 찾았습니다.")
        return containers
    except Exception as e:
        logger.error(f"도커 컨테이너 목록 조회 실패: {e}")
        raise ValueError("도커 컨테이너 목록을 가져오는 데 실패했습니다. 도커가 실행 중인지 확인하세요.")

def docker_list_images() -> List[Dict]:
    """로컬에 저장된 모든 도커 이미지 목록을 반환합니다.

    Returns:
        List[Dict]: 각 이미지의 정보를 담은 딕셔너리 리스트.

    Raises:
        ValueError: `docker` 명령어 실행 실패 시.
    """
    logger.info("도커 이미지 목록 조회 시도.")
    command = "docker images --format '{{json .}}'"
    try:
        result = execute_shell_command(command)
        if not result:
            return []

        images = [json.loads(line) for line in result.strip().split('\n')]
        logger.info(f"{len(images)}개의 도커 이미지를 찾았습니다.")
        return images
    except Exception as e:
        logger.error(f"도커 이미지 목록 조회 실패: {e}")
        raise ValueError("도커 이미지 목록을 가져오는 데 실패했습니다. 도커가 실행 중인지 확인하세요.")


