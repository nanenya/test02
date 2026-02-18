#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_git_version_control.py: git_version_control 모듈에 대한 단위 테스트

실제 git 명령어 실행을 방지하기 위해 _run_git을 mock합니다.
입력값 검증(URL, branch name, commit hash) 위주로 테스트합니다.
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock

from . import git_version_control as mcp


@pytest.fixture
def mock_run_git():
    """_run_git을 mock으로 교체하는 fixture"""
    with patch("mcp_modules.git_version_control._run_git", return_value="ok") as m:
        yield m


class TestGitStatus:
    def test_success(self, mock_run_git):
        result = mcp.git_status()
        assert result == "ok"
        mock_run_git.assert_called_once_with(["status"], None)

    def test_with_repo_path(self, mock_run_git):
        mcp.git_status("/some/repo")
        mock_run_git.assert_called_once_with(["status"], "/some/repo")


class TestGitCommit:
    def test_success(self, mock_run_git):
        result = mcp.git_commit("feat: add feature")
        assert result == "ok"

    def test_failure_empty_message(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_commit("")

    def test_failure_whitespace_only(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_commit("   ")


class TestGitPush:
    def test_success(self, mock_run_git):
        result = mcp.git_push("origin", "main")
        assert result == "ok"
        mock_run_git.assert_called_once_with(["push", "origin", "main"], None)

    def test_failure_invalid_branch(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 브랜치"):
            mcp.git_push(branch="invalid branch!")

    def test_valid_branch_with_slash(self, mock_run_git):
        result = mcp.git_push(branch="feature/new")
        assert result == "ok"


class TestGitPull:
    def test_success(self, mock_run_git):
        result = mcp.git_pull()
        assert result == "ok"

    def test_failure_invalid_branch(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_pull(branch="bad branch!")


class TestGitLog:
    def test_success(self, mock_run_git):
        result = mcp.git_log(5)
        assert result == "ok"
        mock_run_git.assert_called_once_with(["log", "--oneline", "-n5"], None)


class TestGitClone:
    def test_success_https(self, mock_run_git):
        result = mcp.git_clone("https://github.com/example/repo.git")
        assert result == "ok"

    def test_success_git_at(self, mock_run_git):
        result = mcp.git_clone("git@github.com:example/repo.git")
        assert result == "ok"

    def test_failure_invalid_url(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 Git URL"):
            mcp.git_clone("ftp://invalid.url")

    def test_failure_bare_path(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 Git URL"):
            mcp.git_clone("/local/path")


class TestGitCreateBranch:
    def test_success(self, mock_run_git):
        result = mcp.git_create_branch("feature/test")
        assert result == "ok"

    def test_failure_invalid_name(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 브랜치"):
            mcp.git_create_branch("invalid name!")

    def test_failure_empty_name(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_create_branch("")


class TestGitListBranches:
    def test_success_parses_output(self):
        with patch(
            "mcp_modules.git_version_control._run_git",
            return_value="* main\n  feature/test\n  remotes/origin/main",
        ):
            branches = mcp.git_list_branches()
        assert "main" in branches
        assert "feature/test" in branches
        assert "remotes/origin/main" in branches

    def test_empty_output(self):
        with patch("mcp_modules.git_version_control._run_git", return_value=""):
            branches = mcp.git_list_branches()
        assert branches == []


class TestGitRevertCommit:
    def test_success(self, mock_run_git):
        result = mcp.git_revert_commit("abc1234")
        assert result == "ok"
        mock_run_git.assert_called_once_with(["revert", "--no-edit", "abc1234"], None)

    def test_success_full_hash(self, mock_run_git):
        result = mcp.git_revert_commit("a" * 40)
        assert result == "ok"

    def test_failure_invalid_hash_short(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 커밋 해시"):
            mcp.git_revert_commit("abc123")  # 6자 (7자 미만)

    def test_failure_invalid_hash_non_hex(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 커밋 해시"):
            mcp.git_revert_commit("xyz1234")


class TestGitShow:
    def test_success(self, mock_run_git):
        result = mcp.git_show("abc1234")
        assert result == "ok"

    def test_failure_invalid_hash(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_show("INVALID!")


class TestGitTag:
    def test_success_lightweight(self, mock_run_git):
        result = mcp.git_tag("v1.0.0")
        assert result == "ok"
        mock_run_git.assert_called_once_with(["tag", "v1.0.0"], None)

    def test_success_annotated(self, mock_run_git):
        result = mcp.git_tag("v1.0.0", message="Release v1.0.0")
        assert result == "ok"
        mock_run_git.assert_called_once_with(["tag", "-a", "v1.0.0", "-m", "Release v1.0.0"], None)

    def test_failure_invalid_tag(self, mock_run_git):
        with pytest.raises(ValueError):
            mcp.git_tag("invalid tag!")


class TestGitRemoteAdd:
    def test_success(self, mock_run_git):
        result = mcp.git_remote_add("origin", "https://github.com/example/repo.git")
        assert result == "ok"

    def test_failure_invalid_url(self, mock_run_git):
        with pytest.raises(ValueError, match="유효하지 않은 Git URL"):
            mcp.git_remote_add("origin", "not-a-url")
