#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_git_version_control.py

git_version_control.py의 MCP 함수들에 대한 단위 테스트입니다.
pytest 프레임워크를 사용하며, 실제 파일 시스템에 영향을 주지 않기 위해
임시 디렉토리 내에서 로컬 Git 저장소를 생성하고 테스트를 수행합니다.
"""

import os
import pytest
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

# 테스트 대상 모듈 임포트
from . import git_version_control as mcp

# --- Pytest Fixtures ---

@pytest.fixture
def local_repo(tmp_path: Path) -> Path:
    """
    테스트를 위한 비어있는 로컬 Git 저장소를 생성하는 Fixture.
    """
    repo_path = tmp_path / "test_repo"
    mcp.git_init(str(repo_path))
    # 기본 브랜치 이름을 'main'으로 설정 (최신 Git 기본값)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=str(repo_path))
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=str(repo_path))
    subprocess.run(['git', 'branch', '-M', 'main'], cwd=str(repo_path))
    return repo_path

@pytest.fixture
def remote_repo(tmp_path: Path) -> Path:
    """
    테스트를 위한 'bare' 원격 저장소를 생성하는 Fixture.
    """
    repo_path = tmp_path / "remote_repo.git"
    mcp.git_init(str(repo_path))
    # bare 저장소로 만들기
    subprocess.run(['git', 'config', '--bool', 'core.bare', 'true'], cwd=str(repo_path))
    return repo_path

# --- 테스트 케이스 ---

class TestGitInit:
    def test_git_init_success(self, tmp_path: Path):
        """성공 케이스: git_init가 .git 디렉토리를 성공적으로 생성하는지 테스트."""
        repo_path = tmp_path / "new_repo"
        result_path = mcp.git_init(str(repo_path))
        assert repo_path.is_dir()
        assert (repo_path / ".git").is_dir()
        assert result_path == str(repo_path.resolve())

    def test_git_init_in_nonexistent_parent(self, tmp_path: Path):
        """엣지 케이스: 존재하지 않는 상위 디렉토리에 init 시도 시 성공하는지 테스트."""
        repo_path = tmp_path / "nonexistent" / "new_repo"
        mcp.git_init(str(repo_path))
        assert (repo_path / ".git").is_dir()

class TestGitClone:
    def test_git_clone_success(self, remote_repo: Path, tmp_path: Path):
        """성공 케이스: bare 저장소를 성공적으로 복제하는지 테스트."""
        clone_path = tmp_path / "cloned_repo"
        result_path = mcp.git_clone(str(remote_repo), str(clone_path))
        assert clone_path.is_dir()
        assert (clone_path / ".git").is_dir()
        assert result_path == str(clone_path.resolve())

    def test_git_clone_failure_non_empty_dir(self, remote_repo: Path, tmp_path: Path):
        """실패 케이스: 비어있지 않은 디렉토리에 복제 시 ValueError 발생하는지 테스트."""
        clone_path = tmp_path / "non_empty"
        clone_path.mkdir()
        (clone_path / "some_file.txt").touch()
        with pytest.raises(ValueError, match="비어있지 않습니다"):
            mcp.git_clone(str(remote_repo), str(clone_path))

    def test_git_clone_failure_invalid_url(self, tmp_path: Path):
        """엣지 케이스: 유효하지 않은 URL로 복제 시 GitCommandError 발생하는지 테스트."""
        clone_path = tmp_path / "bad_clone"
        invalid_url = "/nonexistent/repo.git"
        with pytest.raises(mcp.GitCommandError):
            mcp.git_clone(invalid_url, str(clone_path))

class TestGitWorkflow:
    def test_status_add_commit_workflow(self, local_repo: Path):
        """성공 케이스: status, add, commit의 기본 워크플로우 테스트."""
        # 1. 초기 상태 확인
        status_before = mcp.git_status(str(local_repo))
        assert "No commits yet" in status_before
        assert "nothing to commit" in status_before

        # 2. 파일 생성 및 추가
        test_file = local_repo / "test.txt"
        test_file.write_text("hello world")
        mcp.git_add(str(local_repo), ["test.txt"])

        # 3. 추가 후 상태 확인
        status_after_add = mcp.git_status(str(local_repo))
        assert "Changes to be committed" in status_after_add
        assert "new file:   test.txt" in status_after_add

        # 4. 커밋
        commit_msg = "Initial commit"
        commit_result = mcp.git_commit(str(local_repo), commit_msg)
        assert "1 file changed" in commit_result
        assert commit_msg in commit_result

        # 5. 커밋 후 상태 확인
        status_after_commit = mcp.git_status(str(local_repo))
        assert "nothing to commit, working tree clean" in status_after_commit

    def test_commit_failure_empty_message(self, local_repo: Path):
        """실패 케이스: 빈 커밋 메시지로 커밋 시 ValueError 발생하는지 테스트."""
        (local_repo / "file.txt").touch()
        mcp.git_add(str(local_repo), ["."])
        with pytest.raises(ValueError, match="커밋 메시지는 비어 있을 수 없습니다"):
            mcp.git_commit(str(local_repo), "  ")

    def test_add_failure_empty_list(self, local_repo: Path):
        """실패 케이스: 빈 파일 리스트로 add 시 ValueError 발생하는지 테스트."""
        with pytest.raises(ValueError, match="스테이징할 파일이 제공되지 않았습니다"):
            mcp.git_add(str(local_repo), [])

class TestGitRemoteOperations:
    @pytest.fixture
    def setup_repos(self, tmp_path: Path):
        # 1. 원격 저장소 경로 설정 및 생성
        remote_repo_path = tmp_path / "remote_repo.git"
        remote_repo_path.mkdir()

        # ✅ 해결 방법: 반드시 '--bare' 옵션을 사용하여 초기화합니다.
        # 베어 저장소는 워킹 트리 없이 순수 Git 데이터만 관리하여 중앙 서버 역할을 합니다.
        subprocess.run(["git", "init", "--bare"], cwd=str(remote_repo_path), check=True)

        # 2. 로컬 저장소 생성
        local_repo_path = tmp_path / "test_repo_path"
        local_repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=str(local_repo_path), check=True)
        
        # 테스트용 임시 저장소에만 적용될 사용자 정보를 설정합니다.
        subprocess.run(
            ["git", "config", "user.name", "Pytest User"],
            cwd=str(local_repo_path),
            check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "pytest@example.com"],
            cwd=str(local_repo_path),
            check=True
        )
        subprocess.run(["git", "branch", "-m", "main"], cwd=local_repo_path, check=True)
        # 3. 로컬 저장소에 원격 저장소 ('origin') 연결
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo_path)],
            cwd=str(local_repo_path),
            check=True
        )
        
        # 기본 브랜치 이름을 'main'으로 설정 (선택 사항이지만 권장)
        subprocess.run(["git", "config", "init.defaultBranch", "main"], cwd=str(local_repo_path), check=True)


        return local_repo_path, remote_repo_path

    def test_push_pull_fetch_workflow(self, setup_repos, tmp_path: Path):
        """성공 케이스: push, clone, pull, fetch 워크플로우 테스트."""
        local_repo, remote_repo = setup_repos

        # git init으로 자동 생성된 'master' 브랜치를 'main'으로 변경합니다.
        # 이 코드는 git 명령어를 직접 실행합니다.
        import subprocess
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=str(local_repo), # 실행 위치를 local_repo로 지정
            check=True,          # 에러 발생 시 예외를 던짐
            capture_output=True  # stdout, stderr를 캡처
        )

        # 1. 로컬에서 커밋 생성 후 푸시
        (local_repo / "a.txt").write_text("content a")
        mcp.git_add(str(local_repo), ["a.txt"])
        mcp.git_commit(str(local_repo), "commit a")
        push_result = mcp.git_push(str(local_repo), "origin", "main")
        assert "main -> main" in push_result

        # 원격 저장소(bare repository)의 기본 브랜치(HEAD)를 'main'으로 설정
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=str(remote_repo), # 실행 위치를 '원격 저장소'로 지정
            check=True,
            capture_output=True
        )

        # 2. 다른 로컬 저장소로 클론하여 변경사항 확인
        clone_repo_2 = tmp_path / "clone2"
        mcp.git_clone(str(remote_repo), str(clone_repo_2))
        assert (clone_repo_2 / "a.txt").exists()
        assert (clone_repo_2 / "a.txt").read_text() == "content a"

        # 3. 첫 번째 로컬 저장소에서 추가 변경 후 푸시
        (local_repo / "b.txt").write_text("content b")
        mcp.git_add(str(local_repo), ["b.txt"])
        mcp.git_commit(str(local_repo), "commit b")
        mcp.git_push(str(local_repo), "origin", "main")

        # 4. 두 번째 클론에서 fetch 후 상태 확인
        mcp.git_fetch(str(clone_repo_2), "origin")
        status_after_fetch = mcp.git_status(str(clone_repo_2))
        assert "Your branch is behind 'origin/main' by 1 commit" in status_after_fetch

        # 5. pull을 통해 변경사항 동기화
        pull_result = mcp.git_pull(str(clone_repo_2), "origin", "main")
        assert "Updating" in pull_result
        assert (clone_repo_2 / "b.txt").exists()
        assert (clone_repo_2 / "b.txt").read_text() == "content b"

    def test_push_failure_no_remote(self, local_repo: Path):
        """실패 케이스: 원격이 설정되지 않은 상태에서 푸시 시 GitCommandError 발생하는지 테스트."""
        (local_repo / "f.txt").touch()
        mcp.git_add(str(local_repo), ["."])
        mcp.git_commit(str(local_repo), "msg")
        with pytest.raises(mcp.GitCommandError, match="'origin' does not appear to be a git repository"):
            mcp.git_push(str(local_repo))

@pytest.fixture
def mock_subprocess(monkeypatch):
    """ subprocess.run 함수를 모킹하는 fixture """
    mock = MagicMock()
    # 기본적으로 성공(returncode=0)을 시뮬레이션하는 CompletedProcess 객체를 반환하도록 설정
    mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
    monkeypatch.setattr(subprocess, "run", mock)
    return mock

# --- 테스트 케이스 ---

class TestGitCreateBranch:
    def test_success(self, mock_subprocess):
        # 성공 케이스
        branch_name = "feature/new-feature"
        mcp.git_create_branch(branch_name)
        # git branch <branch_name> 명령어가 정확히 호출되었는지 확인
        mock_subprocess.assert_called_once_with(
            ["git", "branch", branch_name],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

    def test_failure_invalid_name(self, mock_subprocess):
        # 실패 케이스: 유효하지 않은 브랜치 이름
        with pytest.raises(ValueError, match="유효하지 않은 브랜치 이름입니다"):
            mcp.git_create_branch("invalid name")
        mock_subprocess.assert_not_called() # 유효성 검사 실패 시 subprocess.run이 호출되면 안 됨

    def test_edge_case_numeric_name(self, mock_subprocess):
        # 엣지 케이스: 숫자로만 된 브랜치 이름
        branch_name = "12345"
        mcp.git_create_branch(branch_name)
        mock_subprocess.assert_called_once_with(
            ["git", "branch", branch_name],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )


class TestGitListBranches:
    def test_success(self, mock_subprocess):
        # 성공 케이스
        mock_output = "* main\n  develop\n  remotes/origin/main\n"
        mock_subprocess.return_value.stdout = mock_output
        result = mcp.git_list_branches()
        # 반환값이 정확히 파싱되었는지 확인
        assert result == ["* main", "develop", "remotes/origin/main"]
        mock_subprocess.assert_called_once_with(
            ["git", "branch", "-a"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

    def test_edge_case_no_branches(self, mock_subprocess):
        # 엣지 케이스: 브랜치가 하나도 없을 때 (git init 직후)
        mock_subprocess.return_value.stdout = ""
        result = mcp.git_list_branches()
        assert result == []


class TestGitRevertCommit:
    def test_success(self, mock_subprocess):
        # 성공 케이스
        commit_hash = "abcdef1234567890"
        mcp.git_revert_commit(commit_hash)
        mock_subprocess.assert_called_once_with(
            ["git", "revert", "--no-edit", commit_hash],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

    def test_failure_command_error(self, mock_subprocess):
        # 실패 케이스: Git 명령어 실행 실패 (예: 충돌)
        commit_hash = "abcdef123"
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="CONFLICT")
        # with pytest.raises(subprocess.CalledProcessError):
        with pytest.raises(mcp.GitCommandError, match="CONFLICT"):
            mcp.git_revert_commit(commit_hash)

    def test_failure_invalid_hash(self, mock_subprocess):
        # 실패 케이스: 유효하지 않은 커밋 해시
        with pytest.raises(ValueError, match="유효하지 않은 커밋 해시 형식입니다"):
            mcp.git_revert_commit("invalid-hash!")
        mock_subprocess.assert_not_called()


class TestGitLog:
    def test_success_default_limit(self, mock_subprocess):
        # 성공 케이스: 기본 limit 사용
        mock_subprocess.return_value.stdout = "abcdef (HEAD -> main) Initial commit"
        result = mcp.git_log()
        assert result == "abcdef (HEAD -> main) Initial commit"
        # limit이 10으로 잘 설정되었는지 확인
        mock_subprocess.assert_called_once_with(
            ["git", "log", "-n10", "--oneline"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

    def test_success_custom_limit(self, mock_subprocess):
        # 성공 케이스: 사용자 정의 limit 사용
        mcp.git_log(limit=5)
        mock_subprocess.assert_called_once_with(
            ["git", "log", "-n5", "--oneline"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

    def test_failure_invalid_limit(self, mock_subprocess):
        # 실패 케이스: 유효하지 않은 limit
        with pytest.raises(ValueError, match="limit은 0보다 큰 정수여야 합니다."):
            mcp.git_log(limit=0)
        with pytest.raises(ValueError):
            mcp.git_log(limit=-1)
        with pytest.raises(ValueError):
            mcp.git_log(limit="abc")
        mock_subprocess.assert_not_called()

# 나머지 함수들에 대한 테스트도 위와 유사한 방식으로 구현할 수 있습니다.
# 지면 관계상 대표적인 함수들의 테스트만 상세히 작성했습니다.

# git_switch_branch 테스트
class TestGitSwitchBranch:
    def test_success(self, mock_subprocess):
        mcp.git_switch_branch("develop")
        mock_subprocess.assert_called_once_with(
            ["git", "switch", "develop"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

# git_merge 테스트
class TestGitMerge:
    def test_success(self, mock_subprocess):
        mcp.git_merge("feature/branch")
        mock_subprocess.assert_called_once_with(
            ["git", "merge", "feature/branch"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )

# git_get_current_branch 테스트
class TestGetCurrentBranch:
    def test_success(self, mock_subprocess):
        mock_subprocess.return_value.stdout = "main"
        result = mcp.git_get_current_branch()
        assert result == "main"
        mock_subprocess.assert_called_once_with(
            ["git", "branch", "--show-current"],
            check=True, capture_output=True, text=True, encoding='utf-8', cwd='.'
        )
