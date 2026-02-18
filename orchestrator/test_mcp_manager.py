#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/mcp_manager.py에 대한 단위 테스트"""

import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from . import mcp_manager as mm


class TestRegistryIO:
    def test_load_nonexistent_returns_empty(self):
        """존재하지 않는 파일 로드 시 빈 레지스트리 반환"""
        result = mm.load_registry("/tmp/nonexistent_test_registry_xyz.json")
        assert result["servers"] == []
        assert result["tool_name_aliases"] == {}

    def test_save_and_load_roundtrip(self):
        """저장 후 로드하면 동일한 데이터 반환"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            registry = {
                "version": "1.0",
                "servers": [
                    {"name": "test-server", "package": "test-pkg",
                     "package_manager": "npm", "command": "npx",
                     "args": ["-y", "test-pkg"], "env": None,
                     "enabled": True, "added_at": "2026-01-01",
                     "description": "test"}
                ],
                "tool_name_aliases": {"old_name": "new_name"},
            }
            mm.save_registry(registry, path)
            loaded = mm.load_registry(path)
            assert loaded["servers"][0]["name"] == "test-server"
            assert loaded["tool_name_aliases"]["old_name"] == "new_name"
        finally:
            os.unlink(path)


class TestAddRemoveServer:
    def _empty_registry(self):
        return {"version": "1.0", "servers": [], "tool_name_aliases": {}}

    def test_add_server(self):
        """서버 추가 성공"""
        reg = self._empty_registry()
        entry = mm.add_server(reg, "my-server", "my-pkg", "npm", description="test desc")
        assert entry["name"] == "my-server"
        assert len(reg["servers"]) == 1

    def test_add_duplicate_raises(self):
        """중복 이름 추가 시 ValueError"""
        reg = self._empty_registry()
        mm.add_server(reg, "my-server", "my-pkg", "npm")
        with pytest.raises(ValueError, match="already exists"):
            mm.add_server(reg, "my-server", "other-pkg", "npm")

    def test_remove_server(self):
        """서버 제거 성공"""
        reg = self._empty_registry()
        mm.add_server(reg, "my-server", "my-pkg", "npm")
        assert mm.remove_server(reg, "my-server") is True
        assert len(reg["servers"]) == 0

    def test_remove_nonexistent(self):
        """존재하지 않는 서버 제거 시 False"""
        reg = self._empty_registry()
        assert mm.remove_server(reg, "no-such") is False

    def test_enable_disable(self):
        """활성/비활성 토글"""
        reg = self._empty_registry()
        mm.add_server(reg, "my-server", "my-pkg", "npm")
        assert mm.enable_server(reg, "my-server", enabled=False) is True
        assert reg["servers"][0]["enabled"] is False
        assert mm.enable_server(reg, "my-server", enabled=True) is True
        assert reg["servers"][0]["enabled"] is True

    def test_enable_nonexistent(self):
        """존재하지 않는 서버 활성화 시 False"""
        reg = self._empty_registry()
        assert mm.enable_server(reg, "no-such", True) is False

    def test_get_servers_enabled_only(self):
        """enabled_only=True 시 비활성 서버 제외"""
        reg = self._empty_registry()
        mm.add_server(reg, "a", "a-pkg", "npm")
        mm.add_server(reg, "b", "b-pkg", "npm")
        mm.enable_server(reg, "b", enabled=False)
        enabled = mm.get_servers(reg, enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0]["name"] == "a"

    def test_get_servers_all(self):
        """enabled_only=False 시 모든 서버 반환"""
        reg = self._empty_registry()
        mm.add_server(reg, "a", "a-pkg", "npm")
        mm.add_server(reg, "b", "b-pkg", "npm")
        mm.enable_server(reg, "b", enabled=False)
        all_servers = mm.get_servers(reg, enabled_only=False)
        assert len(all_servers) == 2


class TestSearchPackages:
    @patch.object(mm, "search_npm")
    def test_search_npm_only(self, mock_npm):
        """manager='npm'이면 npm만 검색"""
        mock_npm.return_value = [{"name": "pkg", "description": "d", "version": "1.0"}]
        result = mm.search_packages("test", manager="npm")
        assert "npm" in result
        assert "pip" not in result
        mock_npm.assert_called_once_with("test")

    @patch.object(mm, "search_pip")
    def test_search_pip_only(self, mock_pip):
        """manager='pip'이면 pip만 검색"""
        mock_pip.return_value = [{"name": "pkg", "description": "d", "version": "1.0"}]
        result = mm.search_packages("test", manager="pip")
        assert "pip" in result
        assert "npm" not in result

    @patch.object(mm, "search_npm")
    @patch.object(mm, "search_pip")
    def test_search_all(self, mock_pip, mock_npm):
        """manager='all'이면 둘 다 검색"""
        mock_npm.return_value = []
        mock_pip.return_value = []
        result = mm.search_packages("test", manager="all")
        assert "npm" in result
        assert "pip" in result


class TestToolOverlap:
    def test_overlap_found(self):
        """중복 도구가 있으면 리포트에 포함"""
        new_tools = [
            {"name": "read_file", "description": "new read"},
            {"name": "unique_tool", "description": "unique"},
        ]
        existing = {"read_file": "existing read", "write_file": "existing write"}
        overlaps = mm.get_tool_overlap_report(new_tools, existing)
        assert len(overlaps) == 1
        assert overlaps[0]["name"] == "read_file"

    def test_no_overlap(self):
        """중복이 없으면 빈 리스트"""
        new_tools = [{"name": "brand_new", "description": "new"}]
        existing = {"read_file": "existing"}
        overlaps = mm.get_tool_overlap_report(new_tools, existing)
        assert len(overlaps) == 0


class TestMigration:
    def test_migrate_creates_json(self):
        """마이그레이션 시 JSON 파일 생성"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        os.unlink(path)  # 파일이 없는 상태에서 시작

        try:
            registry = mm.migrate_from_hardcoded(path)
            assert os.path.exists(path)
            assert len(registry["servers"]) == 3  # 기본 3개 서버
            names = [s["name"] for s in registry["servers"]]
            assert "filesystem" in names
            assert "git" in names
            assert "fetch" in names
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestResolveArgs:
    def test_dot_replaced(self):
        """'.'가 cwd로 치환됨"""
        result = mm._resolve_args(["-y", "pkg", "."])
        assert result[2] == os.getcwd()

    def test_cwd_replaced(self):
        """'$CWD'가 cwd로 치환됨"""
        result = mm._resolve_args(["$CWD"])
        assert result[0] == os.getcwd()

    def test_other_args_unchanged(self):
        """다른 인자는 변경 없음"""
        result = mm._resolve_args(["-y", "pkg", "--flag"])
        assert result == ["-y", "pkg", "--flag"]
