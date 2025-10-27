#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_execution_composite 모듈에 대한 단위 테스트
===============================================
pytest와 mocker를 사용하여 외부 프로세스 실행 없이 각 MCP의 로직,
입력 유효성 검사, 오류 처리를 테스트합니다.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

# 테스트 대상 모듈 임포트
from .code_execution_composite import (
    build_docker_image,
    clone_git_repository,
    format_code_file,
    get_container_logs,
    get_git_status,
    install_python_package,
    lint_code_file,
    run_container_from_image,
    run_python_script,
    setup_python_venv,
    uninstall_python_package
)

# --- _run_command에 대한 Mock 설정 ---
# 모든 테스트에서 `_run_command` 함수를 모킹하여 실제 셸 명령어가 실행되지 않도록 합니다.
@pytest.fixture
def mock_run_command():
    with patch("mcp_modules.code_execution_composite._run_command") as mock_run:
        yield mock_run

# --- 각 함수에 대한 테스트 케이스 ---

class TestRunPythonScript:
    # 성공 케이스
    def test_run_python_script_success(self, mock_run_command, tmp_path):
        script = tmp_path / "test.py"
        script.write_text("print('hello')")
        mock_run_command.return_value = "hello"

        result = run_python_script(str(script))

        assert result == "hello"
        mock_run_command.assert_called_once_with(["python", str(script.resolve())])

    # 실패 케이스 (파일 없음)
    def test_run_python_script_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_python_script("non_existent_script.py")

    # 엣지 케이스 (명령어 실패)
    def test_run_python_script_command_error(self, mock_run_command, tmp_path):
        script = tmp_path / "error.py"
        script.write_text("import sys; sys.exit(1)")
        mock_run_command.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="error")

        with pytest.raises(subprocess.CalledProcessError):
            run_python_script(str(script))


class TestPackageManagement:
    # 성공 케이스
    def test_install_package_success(self, mock_run_command):
        mock_run_command.return_value = "Successfully installed requests"
        result = install_python_package("requests")
        assert "Successfully installed" in result
        mock_run_command.assert_called_once_with(["python", "-m", "pip", "install", "requests"])

    # 성공 케이스
    def test_uninstall_package_success(self, mock_run_command):
        mock_run_command.return_value = "Successfully uninstalled requests"
        result = uninstall_python_package("requests")
        assert "Successfully uninstalled" in result
        mock_run_command.assert_called_once_with(["python", "-m", "pip", "uninstall", "-y", "requests"])

    # 실패 케이스 (잘못된 패키지 이름)
    @pytest.mark.parametrize("invalid_name", ["requests; rm -rf /", "numpy && ls", " "])
    def test_install_invalid_package_name(self, invalid_name):
        with pytest.raises(ValueError):
            install_python_package(invalid_name)

    # 실패 케이스 (잘못된 패키지 이름)
    @pytest.mark.parametrize("invalid_name", ["requests; rm -rf /", "numpy && ls", " "])
    def test_uninstall_invalid_package_name(self, invalid_name):
        with pytest.raises(ValueError):
            uninstall_python_package(invalid_name)


class TestCodeTools:
    # 성공 케이스
    def test_lint_code_file_success(self, mock_run_command, tmp_path):
        file = tmp_path / "code.py"
        file.write_text("x = 1\n")
        mock_run_command.return_value = ""  # 문제 없을 때
        result = lint_code_file(str(file))
        assert result == ""
        mock_run_command.assert_called_once_with(["flake8", str(file.resolve())])

    # 성공 케이스
    def test_format_code_file_success(self, mock_run_command, tmp_path):
        file = tmp_path / "code.py"
        file.write_text("x=1")
        mock_run_command.return_value = f"reformatted {file.resolve()}"
        result = format_code_file(str(file))
        assert "reformatted" in result
        mock_run_command.assert_called_once_with(["black", str(file.resolve())])

    # 실패 케이스 (파일 없음)
    def test_lint_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            lint_code_file("non_existent_file.py")


class TestGitTools:
    # 성공 케이스
    def test_get_git_status_success(self, mock_run_command, tmp_path):
        mock_run_command.return_value = "On branch main"
        result = get_git_status(str(tmp_path))
        assert "On branch main" in result
        mock_run_command.assert_called_once_with(["git", "status"], cwd=str(tmp_path.resolve()))

    # 성공 케이스
    def test_clone_git_repository_success(self, mock_run_command, tmp_path):
        clone_dir = tmp_path / "repo"
        url = "https://github.com/user/repo.git"
        mock_run_command.return_value = "Cloning into..."
        result = clone_git_repository(url, str(clone_dir))
        assert "성공적으로 복제했습니다" in result
        mock_run_command.assert_called_once_with(["git", "clone", url, str(clone_dir.resolve())])

    # 실패 케이스 (잘못된 URL)
    def test_clone_invalid_url(self):
        with pytest.raises(ValueError):
            clone_git_repository("ftp://invalid-url.com", "./repo")

    # 엣지 케이스 (경로 이미 존재)
    def test_clone_path_exists(self, tmp_path):
        clone_dir = tmp_path / "repo"
        clone_dir.mkdir()
        with pytest.raises(FileExistsError):
            clone_git_repository("https://github.com/user/repo.git", str(clone_dir))


class TestVenv:
    # 성공 케이스
    def test_setup_python_venv_success(self, mock_run_command, tmp_path):
        venv_dir = tmp_path / "venv"
        result = setup_python_venv(str(venv_dir))
        assert "성공적으로 생성되었습니다" in result
        mock_run_command.assert_called_once_with(["python", "-m", "venv", str(venv_dir.resolve())])

    # 실패 케이스 (경로 이미 존재)
    def test_setup_venv_path_exists(self, tmp_path):
        venv_dir = tmp_path / "venv"
        venv_dir.mkdir()
        with pytest.raises(FileExistsError):
            setup_python_venv(str(venv_dir))


class TestDockerTools:
    # 성공 케이스
    def test_build_docker_image_success(self, mock_run_command, tmp_path):
        image_name = "my-app:1.0"
        mock_run_command.return_value = "Successfully built..."
        result = build_docker_image(str(tmp_path), image_name)
        assert "Successfully built" in result
        mock_run_command.assert_called_once_with(["docker", "build", "-t", image_name, "."], cwd=str(tmp_path.resolve()))

    # 성공 케이스
    def test_run_container_success(self, mock_run_command):
        image_name = "nginx"
        container_id = "a1b2c3d4"
        mock_run_command.return_value = container_id
        result = run_container_from_image(image_name, ports={8080: 80})
        assert result == container_id
        mock_run_command.assert_called_once_with(["docker", "run", "-d", "-p", "8080:80", image_name])

    # 성공 케이스
    def test_get_container_logs_success(self, mock_run_command):
        container_id = "a1b2c3d4"
        logs = "Server is running"
        mock_run_command.return_value = logs
        result = get_container_logs(container_id)
        assert result == logs
        mock_run_command.assert_called_once_with(["docker", "logs", container_id])

    # 실패 케이스 (잘못된 이미지 이름)
    def test_build_invalid_image_name(self, tmp_path):
        with pytest.raises(ValueError):
            build_docker_image(str(tmp_path), "Invalid Name!")

    # 실패 케이스 (잘못된 포트 번호)
    def test_run_invalid_port(self):
        with pytest.raises(ValueError):
            run_container_from_image("nginx", ports={99999: 80})
