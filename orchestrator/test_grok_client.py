#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/grok_client.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from . import grok_client as gc


class TestGetModelName:
    def test_high(self):
        """model_preference='high'이면 HIGH_PERF_MODEL_NAME 반환"""
        with patch.object(gc, "HIGH_PERF_MODEL_NAME", "grok-3"):
            result = gc._get_model_name("high")
            assert result == "grok-3"

    def test_standard(self):
        """model_preference='standard'이면 STANDARD_MODEL_NAME 반환"""
        with patch.object(gc, "STANDARD_MODEL_NAME", "grok-3-mini"):
            result = gc._get_model_name("standard")
            assert result == "grok-3-mini"

    def test_auto_high_default(self):
        """auto + default_type='high'이면 HIGH_PERF_MODEL_NAME 반환"""
        with patch.object(gc, "HIGH_PERF_MODEL_NAME", "grok-3"):
            result = gc._get_model_name("auto", default_type="high")
            assert result == "grok-3"

    def test_auto_standard_default(self):
        """auto + default_type='standard'이면 STANDARD_MODEL_NAME 반환"""
        with patch.object(gc, "STANDARD_MODEL_NAME", "grok-3-mini"):
            result = gc._get_model_name("auto", default_type="standard")
            assert result == "grok-3-mini"


class TestCallGrok:
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        """XAI_API_KEY 미설정 시 RuntimeError 발생"""
        with patch("os.getenv", return_value=None):
            with pytest.raises(RuntimeError, match="XAI_API_KEY"):
                await gc._call_grok("prompt", "system", "grok-3")

    @pytest.mark.asyncio
    async def test_response_parsed(self):
        """정상 응답에서 content 추출"""
        fake_response = {
            "choices": [{"message": {"content": "Grok 응답"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("os.getenv", return_value="test-xai-key"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await gc._call_grok("prompt", "system", "grok-3")
        assert result == "Grok 응답"

    @pytest.mark.asyncio
    async def test_uses_xai_base_url(self):
        """xAI API URL (api.x.ai)로 요청을 전송"""
        fake_response = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}

        called_url = {}

        async def fake_post(url, headers, json):
            called_url["url"] = url
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = fake_post

        with patch("os.getenv", return_value="test-xai-key"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await gc._call_grok("prompt", "system", "grok-3")

        assert "api.x.ai" in called_url.get("url", "")


class TestGenerateTitle:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_default(self):
        """XAI_API_KEY 미설정 시 기본 제목 반환"""
        with patch("os.getenv", return_value=None):
            result = await gc.generate_title_for_conversation(["a", "b"])
            assert result == "Untitled_Conversation"

    @pytest.mark.asyncio
    async def test_short_history(self):
        """history가 2개 미만이면 '새로운_대화' 반환"""
        with patch("os.getenv", return_value="fake-key"):
            result = await gc.generate_title_for_conversation(["single"])
            assert result == "새로운_대화"

    @pytest.mark.asyncio
    async def test_exception_returns_fallback(self):
        """_call_grok 예외 시 'Untitled_Conversation' 반환"""
        with patch("os.getenv", return_value="fake-key"):
            with patch.object(gc, "_call_grok", side_effect=Exception("오류")):
                result = await gc.generate_title_for_conversation(["a", "b"])
                assert result == "Untitled_Conversation"
