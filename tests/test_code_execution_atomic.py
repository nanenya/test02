#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_code_execution_automic.py: code_execution_atomic 모듈에 대한 단위 테스트
"""

import pytest
from unittest.mock import patch, MagicMock
import os
import subprocess
from pathlib import Path

# 테스트 대상 모듈 임포트
from mcp_modules import code_execution_atomic as mcp

# --- 테스트를 위한 Fixture 설정 ---
@pytest.fixture
def temp_file(tmp_path):
    """테스트용 임시 파일을 생성하는 Fixture"""
    file_path = tmp_path / "test_script.py"
    content = (
        "def sample_function(a, b):\n"
        "    \"\"\"This is a sample function.\"\"\"\n"
        "    if a > 0:\n"
        "        return a + b\n"
        "    else:\n"
        "        return a - b\n"
    )
    file_path.write_text(content, encoding="utf-8")
    return file_path

# --- 각 함수별 테스트 클래스 ---

class TestExecuteShellCommand:
    def test_success(self):
        """성공 케이스: 간단한 echo 명령어 실행"""
        result = mcp.execute_shell_command("echo 'success'")
        assert result == "success"

    def test_failure_command_not_found(self):
        """실패 케이스: 존재하지 않는 명령어"""
        result = mcp.execute_shell_command("non_existent_command_12345")
        assert "오류 발생" in result
        assert "찾을 수 없습니다" in result

    def test_edge_case_forbidden_command(self):
        """엣지 케이스: 금지된 명령어 실행 시도"""
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.execute_shell_command("rm -rf /")

    def test_edge_case_timeout(self):
        """엣지 케이스: 명령어 시간 초과"""
        with pytest.raises(TimeoutError):
            mcp.execute_shell_command("sleep 2", timeout=1)

class TestExecutePythonCode:
    def test_success(self):
        """성공 케이스: 간단한 연산 코드 실행"""
        result = mcp.execute_python_code("result = 10 * 2", sandboxed=True)
        assert result == 20

    def test_failure_no_sandbox_flag(self):
        """실패 케이스: sandboxed=True 플래그 없이 실행"""
        with pytest.raises(PermissionError, match="보안 오류"):
            mcp.execute_python_code("result = 1 + 1")

    def test_edge_case_syntax_error(self):
        """엣지 케이스: 문법 오류가 있는 코드"""
        with pytest.raises(SyntaxError):
            mcp.execute_python_code("result = 1 +", sandboxed=True)

class TestReadCodeFile:
    # def test_success(self, temp_file):
    @patch('mcp_modules.code_execution_atomic.ALLOWED_BASE_PATH', new_callable=lambda: Path('/tmp'))
    def test_success(self, mock_allowed_path, temp_file):
        """성공 케이스: 생성된 임시 파일 읽기"""
        content = mcp.read_code_file(str(temp_file))
        assert "def sample_function(a, b):" in content

    def test_failure_file_not_found(self):
        """실패 케이스: 존재하지 않는 파일 읽기"""
        with pytest.raises(FileNotFoundError):
            mcp.read_code_file("non_existent_file.py")

    @patch('mcp_modules.code_execution_atomic.ALLOWED_BASE_PATH', Path('/allowed'))
    def test_edge_case_path_traversal(self):
        """엣지 케이스: 허용된 경로 외부 접근 시도"""
        with pytest.raises(ValueError, match="보안 오류"):
            # 실제 파일이 존재하지 않아도 경로 검증에서 먼저 실패해야 함
            mcp.read_code_file("/etc/passwd")

class TestEnvironmentVariables:
    def test_get_set_variable_success(self):
        """성공 케이스: 환경 변수 설정 및 조회"""
        var_name = "MCP_TEST_VAR"
        var_value = "hello_world"
        
        # 초기 상태 확인 (없어야 함)
        assert mcp.get_environment_variable(var_name) is None
        
        # 설정
        assert mcp.set_environment_variable(var_name, var_value) is True
        
        # 조회 확인
        assert mcp.get_environment_variable(var_name) == var_value
        
        # 환경 정리
        del os.environ[var_name]

    def test_get_non_existent_variable(self):
        """엣지 케이스: 존재하지 않는 환경 변수 조회"""
        assert mcp.get_environment_variable("NON_EXISTENT_VAR_98765") is None

class TestCheckPortStatus:
    @patch('socket.socket')
    def test_success_port_open(self, mock_socket):
        """성공 케이스: 포트가 열려있는 경우"""
        mock_sock_instance = mock_socket.return_value
        mock_sock_instance.connect_ex.return_value = 0 # 0이면 성공
        
        is_open, message = mcp.check_port_status("localhost", 80)
        assert is_open is True
        assert "열려 있습니다" in message

    @patch('socket.socket')
    def test_failure_port_closed(self, mock_socket):
        """실패 케이스: 포트가 닫혀있는 경우"""
        mock_sock_instance = mock_socket.return_value
        mock_sock_instance.connect_ex.return_value = 111 # Connection refused
        
        is_open, message = mcp.check_port_status("localhost", 8080)
        assert is_open is False
        assert "닫혀 있거나" in message

    def test_edge_case_invalid_host(self):
        """엣지 케이스: 유효하지 않은 호스트"""
        is_open, message = mcp.check_port_status("invalid.hostname.for.test", 80)
        assert is_open is False
        assert "호스트 이름을 확인할 수 없습니다" in message

class TestGetFunctionSignature:
    # def test_success(self, temp_file):
    @patch('mcp_modules.code_execution_atomic.ALLOWED_BASE_PATH', new_callable=lambda: Path('/tmp'))
    def test_success(self, mock_allowed_path, temp_file):
        """성공 케이스: 함수 시그니처 추출"""
        signature = mcp.get_function_signature(str(temp_file), "sample_function")
        assert signature == "def sample_function(a, b):"

    def test_failure_function_not_found(self, temp_file):
        """실패 케이스: 존재하지 않는 함수"""
        signature = mcp.get_function_signature(str(temp_file), "non_existent_function")
        assert signature is None

    def test_edge_case_file_not_found(self):
        """엣지 케이스: 파일이 없음"""
        with pytest.raises(FileNotFoundError):
            mcp.get_function_signature("no_file.py", "any_function")

# Docker, SQL, Radon 등 외부 의존성이 있는 기능들은 Mocking을 통해 테스트
@patch('mcp_modules.code_execution_atomic.execute_shell_command')
class TestExternalDependencies:
    def test_docker_list_containers_success(self, mock_shell):
        """Docker 컨테이너 목록 조회 성공 케이스"""
        mock_output = '{"ID":"123","Names":"test-container"}\n{"ID":"456","Names":"db-container"}'
        mock_shell.return_value = mock_output
        
        containers = mcp.docker_list_containers()
        assert len(containers) == 2
        assert containers[0]['ID'] == '123'
        mock_shell.assert_called_with("docker ps -a --format '{{json .}}'")

    def test_docker_list_images_empty(self, mock_shell):
        """Docker 이미지 목록이 비어있는 엣지 케이스"""
        mock_shell.return_value = ""
        images = mcp.docker_list_images()
        assert images == []

    def test_get_code_complexity_failure(self, mock_shell, tmp_path: Path):
        """Radon 실행 실패 케이스"""
        # 1. 임시 파일을 생성합니다.
        fake_file = tmp_path / "any_file.py"
        fake_file.write_text("def my_func(): pass") # 내용은 중요하지 않습니다.

        mock_shell.return_value = "오류 발생: radon을 찾을 수 없습니다."
        with pytest.raises(ValueError, match="radon 실행 실패"):
            # 2. 존재하지 않는 파일 이름 대신, 방금 만든 임시 파일의 경로를 전달합니다.
            #    경로 객체(Path)를 문자열로 변환해줍니다.
            mcp.get_code_complexity(str(fake_file))

