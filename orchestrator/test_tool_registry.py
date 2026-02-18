#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/tool_registry.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, MagicMock
import importlib

from . import tool_registry as tr
from . import config


class TestLoadLocalModules:
    def setup_method(self):
        """각 테스트 전 TOOLS/TOOL_DESCRIPTIONS 초기화"""
        tr.TOOLS.clear()
        tr.TOOL_DESCRIPTIONS.clear()

    def test_successful_load(self):
        """정상 모듈 로드 시 TOOLS에 함수가 등록됨"""
        tr._load_local_modules()
        assert len(tr.TOOLS) > 0
        assert len(tr.TOOL_DESCRIPTIONS) > 0

    def test_failed_module_logged(self):
        """존재하지 않는 모듈 로드 시 에러 로깅 후 계속 진행"""
        original = config.LOCAL_MODULES[:]
        try:
            config.LOCAL_MODULES.append("non_existent_module_xyz")
            tr._load_local_modules()
            # 기존 정상 모듈은 로드됨
            assert len(tr.TOOLS) > 0
        finally:
            config.LOCAL_MODULES[:] = original

    def test_all_tools_have_descriptions(self):
        """로드된 모든 도구에 설명이 있음"""
        tr._load_local_modules()
        for name in tr.TOOLS:
            assert name in tr.TOOL_DESCRIPTIONS


class TestGetTool:
    def setup_method(self):
        tr.TOOLS.clear()
        tr.TOOL_DESCRIPTIONS.clear()
        tr._mcp_tools.clear()

    def test_local_tool(self):
        """로컬 도구 이름으로 함수 반환"""
        dummy_func = lambda: None
        tr.TOOLS["my_tool"] = dummy_func
        assert tr.get_tool("my_tool") is dummy_func

    def test_alias_resolution(self):
        """별칭으로 MCP 도구 검색"""
        session_mock = MagicMock()
        tr._mcp_tools["read_file"] = {
            "session": session_mock,
            "server": "filesystem",
            "description": "test",
            "input_schema": {},
        }
        # config에 read_file -> read_file 별칭이 있음
        result = tr.get_tool("read_file")
        assert result is not None
        assert callable(result)

    def test_nonexistent_tool(self):
        """존재하지 않는 도구는 None 반환"""
        assert tr.get_tool("no_such_tool_xyz") is None


class TestToolProviders:
    def setup_method(self):
        tr.TOOLS.clear()
        tr.TOOL_DESCRIPTIONS.clear()
        tr._mcp_tools.clear()
        tr._tool_providers.clear()
        tr._tool_server_preferences.clear()

    def test_get_tool_providers_empty(self):
        """제공자가 없으면 빈 리스트"""
        assert tr.get_tool_providers("nonexistent") == []

    def test_get_tool_providers_single(self):
        """단일 제공자 반환"""
        session_mock = MagicMock()
        tr._tool_providers["read_file"] = [
            {"server": "filesystem", "session": session_mock, "description": "read"}
        ]
        result = tr.get_tool_providers("read_file")
        assert len(result) == 1
        assert result[0]["server"] == "filesystem"

    def test_get_tool_providers_multiple(self):
        """다중 제공자 반환"""
        s1, s2 = MagicMock(), MagicMock()
        tr._tool_providers["read_file"] = [
            {"server": "fs1", "session": s1, "description": "read1"},
            {"server": "fs2", "session": s2, "description": "read2"},
        ]
        result = tr.get_tool_providers("read_file")
        assert len(result) == 2

    def test_set_tool_preference_valid(self):
        """유효한 서버로 선호 설정 성공"""
        session_mock = MagicMock()
        tr._tool_providers["read_file"] = [
            {"server": "fs1", "session": session_mock, "description": "read"},
            {"server": "fs2", "session": session_mock, "description": "read"},
        ]
        assert tr.set_tool_preference("read_file", "fs2") is True
        assert tr._tool_server_preferences["read_file"] == "fs2"

    def test_set_tool_preference_invalid_server(self):
        """존재하지 않는 서버로 선호 설정 실패"""
        tr._tool_providers["read_file"] = [
            {"server": "fs1", "session": MagicMock(), "description": "read"},
        ]
        assert tr.set_tool_preference("read_file", "nonexistent") is False

    def test_get_duplicate_tools(self):
        """2개 이상 서버가 제공하는 도구만 반환"""
        s1, s2 = MagicMock(), MagicMock()
        tr._tool_providers["read_file"] = [
            {"server": "fs1", "session": s1, "description": "r1"},
            {"server": "fs2", "session": s2, "description": "r2"},
        ]
        tr._tool_providers["unique_tool"] = [
            {"server": "fs1", "session": s1, "description": "u"},
        ]
        dups = tr.get_duplicate_tools()
        assert "read_file" in dups
        assert "unique_tool" not in dups
        assert dups["read_file"] == ["fs1", "fs2"]

    def test_get_tool_uses_preference(self):
        """선호 서버가 설정되면 해당 세션 사용"""
        s1, s2 = MagicMock(), MagicMock()
        tr._mcp_tools["read_file"] = {
            "session": s1, "server": "fs1",
            "description": "read", "input_schema": {},
        }
        tr._tool_providers["read_file"] = [
            {"server": "fs1", "session": s1, "description": "r1"},
            {"server": "fs2", "session": s2, "description": "r2"},
        ]
        tr._tool_server_preferences["read_file"] = "fs2"
        wrapper = tr.get_tool("read_file")
        assert wrapper is not None
        assert callable(wrapper)


class TestGetAllToolDescriptions:
    def test_returns_dict(self):
        """반환 타입이 dict"""
        result = tr.get_all_tool_descriptions()
        assert isinstance(result, dict)
