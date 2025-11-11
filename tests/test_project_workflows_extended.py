# tests/test_project_workflows_extended.py

import pytest
import os
from pathlib import Path as RealPath # 실제 경로 구성을 위해 이름 변경하여 임포트
from unittest.mock import MagicMock, ANY, call

# --- 테스트 대상 모듈 임포트 ---
from mcp_modules.project_workflows import (
    setup_project_environment,
    install_and_save_package,
    check_for_outdated_packages,
    scaffold_test_file_prompt,
    run_specific_test_and_get_context,
    view_and_discard_changes,
    autofix_lint_errors,
    apply_git_patch,
    complete_feature_branch,
    GitCommandError
)

# --- 모의(Mock) 객체 픽스처 ---

@pytest.fixture
def mock_deps(mocker):
    """
    project_workflows의 신규 MCP 9개가 의존하는
    모든 하위 MCP 및 라이브러리를 모의(Mock) 처리합니다.
    """
    mocks = {}
    
    # 중요: 모듈이 *사용되는* 위치인 'base'를 기준으로 패치합니다.
    base = "mcp_modules.project_workflows"

    # --- Pathlib 모의 처리 ---
    # Path 클래스 자체를 모의 객체로 교체
    mocks["Path"] = mocker.patch(f"{base}.Path")
    
    # Path(...)가 반환할 기본 인스턴스 모의 객체를 생성
    mock_path_instance = MagicMock(name="default_path_instance")
    
    # Path(...)가 항상 위 인스턴스를 반환하도록 설정
    mocks["Path"].return_value = mock_path_instance
    
    # (Path / "filename") 처럼 / 연산자가 쓰일 때도 
    # 기본적으로 자기 자신(mock_path_instance)을 반환하도록 설정
    mock_path_instance.__truediv__.return_value = mock_path_instance
    
    # 기본적으로 .exists()는 False를 반환하도록 설정
    mock_path_instance.exists.return_value = False
    
    # --- MCP 모의 처리 ---
    mocks["setup_python_venv"] = mocker.patch(f"{base}.setup_python_venv")
    mocks["_run_command"] = mocker.patch(f"{base}._run_command")
    mocks["read_file"] = mocker.patch(f"{base}.read_file")
    mocks["append_to_file"] = mocker.patch(f"{base}.append_to_file")
    mocks["git_status"] = mocker.patch(f"{base}.git_status")
    mocks["git_diff"] = mocker.patch(f"{base}.git_diff")
    mocks["ask_user_for_confirmation"] = mocker.patch(f"{base}.ask_user_for_confirmation")
    mocks["_run_git_command"] = mocker.patch(f"{base}._run_git_command")
    mocks["write_file"] = mocker.patch(f"{base}.write_file")
    mocks["git_get_current_branch"] = mocker.patch(f"{base}.git_get_current_branch")
    mocks["git_push"] = mocker.patch(f"{base}.git_push")
    
    # 복합 MCP인 switch_to_main_and_pull 자체를 모의 처리
    mocks["switch_to_main_and_pull"] = mocker.patch(f"{base}.switch_to_main_and_pull")

    yield mocks


# --- 테스트 케이스 ---

def test_setup_project_environment(mock_deps):
    """
    [성공] 가상 환경을 생성하고 requirements.txt를 설치합니다.
    """
    # (수정) Arrange: Path 모의를 정교하게 설정
    # 이 테스트만을 위해 mock_deps에서 제공된 Path 모의를 오버라이드합니다.

    # 1. 경로 문자열 정의
    repo_str = "my_repo"
    venv_dir = ".venv"
    # os.path.join을 사용해 플랫폼 호환 경로 생성
    venv_str = os.path.join(repo_str, venv_dir)
    req_str = os.path.join(repo_str, "requirements.txt")
    bin_str = "Scripts" if os.name == "nt" else "bin"
    pip_exe = "pip.exe" if os.name == "nt" else "pip"
    pip_str = os.path.join(venv_str, bin_str, pip_exe)

    # 2. 모의 객체 생성
    mock_repo_path = MagicMock(name="repo_path_inst")
    mock_venv_path = MagicMock(name="venv_path_inst")
    mock_req_path = MagicMock(name="req_path_inst")
    mock_bin_path = MagicMock(name="bin_path_inst")
    mock_pip_path = MagicMock(name="pip_path_inst")

    # 3. Path() 생성자 모의
    # mock_deps['Path']는 mocker.patch(...) 객체입니다.
    # 이 객체의 side_effect를 이 테스트에 맞게 재설정합니다.
    mock_deps["Path"].side_effect = lambda x: {
        repo_str: mock_repo_path,
        venv_str: mock_venv_path  # Path("my_repo/.venv") 호출 시
    }.get(str(x), MagicMock()) # str(x)로 감싸서 Path 객체가 와도 처리

    # 4. (Path / ...) 연산자 모의
    mock_repo_path.__truediv__.side_effect = lambda x: {
        venv_dir: mock_venv_path,
        "requirements.txt": mock_req_path
    }.get(x)

    mock_venv_path.__truediv__.side_effect = lambda x: {
        bin_str: mock_bin_path
    }.get(x)

    mock_bin_path.__truediv__.return_value = mock_pip_path

    # 5. str() 변환 모의
    mock_venv_path.__str__.return_value = venv_str
    mock_req_path.__str__.return_value = req_str
    mock_pip_path.__str__.return_value = pip_str

    # 6. .exists() 모의
    mock_req_path.exists.return_value = True # requirements.txt가 존재함

    # 7. MCP 모의
    mock_deps["setup_python_venv"].return_value = "venv created"
    mock_deps["_run_command"].return_value = "pip install successful"

    # Act
    result = setup_project_environment(repo_str, venv_dir=venv_dir)

    # Assert
    mock_deps["setup_python_venv"].assert_called_once_with(venv_str)
    mock_deps["_run_command"].assert_called_once_with(
        [pip_str, "install", "-r", req_str], cwd=repo_str
    )
    assert "설치 완료" in result

def test_install_and_save_package(mock_deps):
    """
    [성공] 패키지를 설치하고, 버전을 확인한 뒤, requirements.txt에 추가합니다.
    """
    # (수정) Arrange: Path 모의를 정교하게 설정
    repo_str = "my_repo"
    req_str = f"{repo_str}/requirements.txt"

    mock_req_path = MagicMock(name="req_path")
    mock_req_path.exists.return_value = True # requirements.txt가 존재함
    mock_req_path.__str__.return_value = req_str
    
    mock_deps["Path"].return_value.__truediv__.return_value = mock_req_path

    # pip install, pip show
    mock_deps["_run_command"].side_effect = [
        "Install successful", # 1. pip install 결과
        "Name: requests\nVersion: 2.31.0\n", # 2. pip show 결과
    ]
    # requirements.txt 파일이 이미 존재하고, 끝에 개행이 없다고 가정
    mock_deps["read_file"].return_value = "numpy==1.23.0" # 개행 없음
    
    # Act
    result = install_and_save_package(repo_str, "requests")

    # Assert
    # 1. pip install 호출 확인
    mock_deps["_run_command"].assert_any_call(
        ["python", "-m", "pip", "install", "requests"], cwd=repo_str
    )
    # 2. pip show 호출 확인
    mock_deps["_run_command"].assert_any_call(
        ["python", "-m", "pip", "show", "requests"], cwd=repo_str
    )
    
    # 3. read_file 호출 확인
    mock_deps["read_file"].assert_called_once_with(req_str)
    
    # (수정) 4. append_to_file 호출 확인 (이제 prefix가 \n이 됨)
    mock_deps["append_to_file"].assert_called_once_with(
        req_str,
        "\nrequests==2.31.0\n"
    )
    assert "requests==2.31.0" in result
    assert "추가했습니다" in result

def test_check_for_outdated_packages(mock_deps):
    """
    [성공] 오래된 패키지 목록을 반환합니다.
    """
    # Arrange
    mock_deps["_run_command"].return_value = "requests 2.30.0 2.31.0"
    
    # Act
    result = check_for_outdated_packages("my_repo")
    
    # Assert
    mock_deps["_run_command"].assert_called_once_with(
        ["python", "-m", "pip", "list", "--outdated"], cwd="my_repo"
    )
    assert "오래된 패키지 목록" in result
    assert "requests 2.30.0 2.31.0" in result

def test_scaffold_test_file_prompt(mock_deps):
    """
    [성공] 소스 코드와 스타일 가이드를 읽어 AI 프롬프트를 생성합니다.
    """
    # Arrange
    mock_deps["read_file"].side_effect = [
        "def main_func(): pass", # 1. source_file
        "def test_example(): pass" # 2. style_guide
    ]
    
    # Act
    result = scaffold_test_file_prompt("src/main.py", "tests/test_example.py")
    
    # Assert
    assert mock_deps["read_file"].call_count == 2
    assert "def main_func(): pass" in result
    assert "def test_example(): pass" in result
    assert "[테스트 대상 소스 코드: src/main.py]" in result

def test_run_specific_test_and_get_context_fail(mock_deps):
    """
    [실패] 테스트가 실패하면 실패 로그를 반환합니다.
    """
    # Arrange
    # pytest 실패 시 예외 발생 및 stderr/stdout 캡처
    mock_exception = Exception("Test failed")
    mock_exception.stdout = "== 1 failed =="
    mock_exception.stderr = "AssertionError"
    mock_deps["_run_command"].side_effect = mock_exception
    
    # Act
    result = run_specific_test_and_get_context("my_repo", "tests/test_main.py")
    
    # Assert
    mock_deps["_run_command"].assert_called_once_with(
        ["pytest", "tests/test_main.py"], cwd="my_repo"
    )
    assert "테스트 실패" in result
    assert "== 1 failed ==" in result
    assert "AssertionError" in result

def test_view_and_discard_changes_confirmed(mock_deps):
    """
    [성공] 사용자가 승인 시 'git restore'와 'git clean'을 호출합니다.
    """
    # Arrange
    mock_deps["git_status"].return_value = "Modified: file.py"
    mock_deps["git_diff"].return_value = "+ new line"
    mock_deps["ask_user_for_confirmation"].return_value = True # 승인
    
    # Act
    result = view_and_discard_changes("my_repo")
    
    # Assert
    mock_deps["ask_user_for_confirmation"].assert_called_once()
    # 1. Modified 되돌리기
    mock_deps["_run_git_command"].assert_any_call(
        ["git", "restore", "."], cwd="my_repo"
    )
    # 2. Untracked 제거
    mock_deps["_run_git_command"].assert_any_call(
        ["git", "clean", "-fd"], cwd="my_repo"
    )
    assert "폐기했습니다" in result

def test_autofix_lint_errors(mock_deps):
    """
    [성공] isort와 black을 순서대로 호출합니다.
    """
    # Arrange
    mock_deps["_run_command"].side_effect = [
        "isort fixed 2 files",
        "black reformatted 1 file"
    ]
    
    # Act
    result = autofix_lint_errors("my_repo")
    
    # Assert
    expected_calls = [
        call(["isort", "."], cwd="my_repo"),
        call(["black", "."], cwd="my_Grepo")
    ]
    # (수정) call 객체가 cwd="my_repo"를 올바르게 비교하도록 수정
    mock_deps["_run_command"].assert_has_calls([
        call(["isort", "."], cwd="my_repo"),
        call(["black", "."], cwd="my_repo")
    ])
    assert "isort fixed" in result
    assert "black reformatted" in result

def test_apply_git_patch(mock_deps):
    """
    [성공] AI 패치를 임시 파일로 저장하고 'git apply'를 실행합니다.
    """
    # (수정) Arrange: Path 모의를 정교하게 설정
    repo_str = "my_repo"
    patch_content = "diff --git a/file.py b/file.py"
    temp_patch_name = ".temp_ai_patch.patch"
    patch_str = f"{repo_str}/{temp_patch_name}"

    mock_patch_file = MagicMock(name="patch_file")
    mock_patch_file.exists.return_value = True # finally에서 unlink를 호출하도록
    mock_patch_file.name = temp_patch_name
    mock_patch_file.__str__.return_value = patch_str

    mock_deps["Path"].return_value.__truediv__.return_value = mock_patch_file
    
    mock_deps["_run_git_command"].return_value = "Patch applied"
    
    # Act
    result = apply_git_patch(repo_str, patch_content)

    # Assert
    # 1. 패치 파일 저장
    mock_deps["write_file"].assert_called_once_with(patch_str, patch_content)
    
    # 2. git apply 실행
    mock_deps["_run_git_command"].assert_called_once_with(
        ["git", "apply", "--3way", temp_patch_name], cwd=repo_str
    )
    
    # 3. 임시 파일 삭제
    mock_patch_file.exists.assert_called_once()
    mock_patch_file.unlink.assert_called_once()
    assert "패치 적용 성공" in result

def test_complete_feature_branch(mock_deps):
    """
    [성공] 기능 브랜치를 main에 병합하고 정리하는 워크플로우를 실행합니다.
    """
    # Arrange
    mock_deps["git_get_current_branch"].return_value = "feature/login"
    mock_deps["switch_to_main_and_pull"].return_value = "Switched and pulled main"
    
    # _run_git_command는 2번(merge, branch -d) 호출됨
    mock_deps["_run_git_command"].side_effect = [
        "Merge successful", # 1. git merge
        "Deleted branch feature/login" # 2. git branch -d
    ]
    # git_push는 1번 호출됨
    mock_deps["git_push"].return_value = "Pushed to origin/main"

    # Act
    result = complete_feature_branch("my_repo", main_branch="main")
    
    # Assert
    # 1. 현재 브랜치 확인
    mock_deps["git_get_current_branch"].assert_called_once_with("my_repo")
    
    # 2. main 전환 및 풀 (복합 MCP)
    mock_deps["switch_to_main_and_pull"].assert_called_once_with("my_repo", branch_name="main")
    
    # 3. 병합 (No-FF)
    mock_deps["_run_git_command"].assert_any_call(
        ["git", "merge", "--no-ff", "feature/login"], cwd="my_repo"
    )
    
    # 4. main 푸시
    mock_deps["git_push"].assert_called_once_with("my_repo", "origin", "main")
    
    # 5. 브랜치 삭제
    mock_deps["_run_git_command"].assert_any_call(
        ["git", "branch", "-d", "feature/login"], cwd="my_repo"
    )
    
    assert "워크플로우 완료" in result
    assert "병합되었습니다" in result
    assert "삭제되었습니다" in result
