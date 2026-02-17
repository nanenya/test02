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


class TestGetAllToolDescriptions:
    def test_returns_dict(self):
        """반환 타입이 dict"""
        result = tr.get_all_tool_descriptions()
        assert isinstance(result, dict)
