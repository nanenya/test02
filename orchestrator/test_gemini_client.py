#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/gemini_client.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json

from . import gemini_client as gc
from .models import ExecutionGroup


class TestTruncateHistory:
    def test_empty_history(self):
        """빈 history는 빈 문자열 반환"""
        assert gc._truncate_history([]) == ""

    def test_normal_history(self):
        """정상 history는 줄바꿈으로 연결"""
        history = ["사용자 요청: hello", "결과: world"]
        result = gc._truncate_history(history)
        assert "hello" in result
        assert "world" in result

    def test_truncation_over_max_chars(self):
        """max_chars 초과 시 최신 항목 우선 보존, 생략 표시 포함"""
        history = [f"item_{i}" * 100 for i in range(10)]
        result = gc._truncate_history(history, max_chars=500)
        assert "이전 기록 생략" in result

    def test_single_item_exceeds_max(self):
        """단일 항목이 max_chars를 초과해도 최소 1개는 포함"""
        history = ["a" * 10000]
        result = gc._truncate_history(history, max_chars=100)
        assert "a" in result

    def test_default_max_chars_is_constant(self):
        """기본 max_chars가 DEFAULT_HISTORY_MAX_CHARS 상수와 일치"""
        assert gc.DEFAULT_HISTORY_MAX_CHARS == 6000


class TestGetModelName:
    def test_high_preference(self):
        """model_preference='high'이면 HIGH_PERF_MODEL_NAME 반환"""
        result = gc._get_model_name("high")
        assert result == gc.HIGH_PERF_MODEL_NAME

    def test_standard_preference(self):
        """model_preference='standard'이면 STANDARD_MODEL_NAME 반환"""
        result = gc._get_model_name("standard")
        assert result == gc.STANDARD_MODEL_NAME

    def test_auto_uses_config_active_model(self):
        """auto 모드는 model_config.json의 active_model 우선 반환"""
        with patch("orchestrator.model_manager.load_config", return_value={
            "active_provider": "gemini", "active_model": "gemini-test-model"
        }):
            result = gc._get_model_name("auto", default_type="high")
            assert result == "gemini-test-model"

    def test_auto_with_high_default_fallback(self):
        """auto + active_model 비어있을 때 default_type='high'이면 HIGH_PERF_MODEL_NAME 폴백"""
        with patch("orchestrator.model_manager.load_config", return_value={
            "active_provider": "gemini", "active_model": ""
        }):
            result = gc._get_model_name("auto", default_type="high")
            assert result == gc.HIGH_PERF_MODEL_NAME

    def test_auto_with_standard_default_fallback(self):
        """auto + active_model 비어있을 때 default_type='standard'이면 STANDARD_MODEL_NAME 폴백"""
        with patch("orchestrator.model_manager.load_config", return_value={
            "active_provider": "gemini", "active_model": ""
        }):
            result = gc._get_model_name("auto", default_type="standard")
            assert result == gc.STANDARD_MODEL_NAME

    def test_auto_fallback_on_exception(self):
        """auto + model_manager 오류 시 default_type 폴백"""
        with patch("orchestrator.model_manager.load_config", side_effect=Exception("fail")):
            result = gc._get_model_name("auto", default_type="high")
            assert result == gc.HIGH_PERF_MODEL_NAME


class TestGenerateExecutionPlan:
    @pytest.mark.asyncio
    async def test_no_client_raises_runtime_error(self):
        """client=None일 때 RuntimeError 발생"""
        with patch.object(gc, "client", None):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                await gc.generate_execution_plan("test", "", [])


class TestGenerateFinalAnswer:
    @pytest.mark.asyncio
    async def test_no_client_raises_runtime_error(self):
        """client=None일 때 RuntimeError 발생"""
        with patch.object(gc, "client", None):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                await gc.generate_final_answer([])


class TestGenerateTitleForConversation:
    @pytest.mark.asyncio
    async def test_no_client_returns_default(self):
        """client=None일 때 기본 제목 반환"""
        with patch.object(gc, "client", None):
            result = await gc.generate_title_for_conversation(["a", "b"])
            assert result == "Untitled_Conversation"

    @pytest.mark.asyncio
    async def test_short_history_returns_new_conversation(self):
        """history가 2개 미만이면 '새로운_대화' 반환"""
        with patch.object(gc, "client", MagicMock()):
            result = await gc.generate_title_for_conversation(["single"])
            assert result == "새로운_대화"
