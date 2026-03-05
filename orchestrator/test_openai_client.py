#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/openai_client.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json

from . import openai_client as oc


class TestGetModelName:
    def test_high(self):
        """model_preference='high'이면 HIGH_PERF_MODEL_NAME 반환"""
        with patch.object(oc, "HIGH_PERF_MODEL_NAME", "gpt-4o"):
            result = oc._get_model_name("high")
            assert result == "gpt-4o"

    def test_standard(self):
        """model_preference='standard'이면 STANDARD_MODEL_NAME 반환"""
        with patch.object(oc, "STANDARD_MODEL_NAME", "gpt-4o-mini"):
            result = oc._get_model_name("standard")
            assert result == "gpt-4o-mini"

    def test_auto_high_default(self):
        """auto + default_type='high'이면 HIGH_PERF_MODEL_NAME 반환"""
        with patch.object(oc, "HIGH_PERF_MODEL_NAME", "gpt-4o"):
            result = oc._get_model_name("auto", default_type="high")
            assert result == "gpt-4o"

    def test_auto_standard_default(self):
        """auto + default_type='standard'이면 STANDARD_MODEL_NAME 반환"""
        with patch.object(oc, "STANDARD_MODEL_NAME", "gpt-4o-mini"):
            result = oc._get_model_name("auto", default_type="standard")
            assert result == "gpt-4o-mini"


class TestCallOpenAI:
    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        """OPENAI_API_KEY 미설정 시 RuntimeError 발생"""
        with patch.dict("os.environ", {}, clear=True):
            with patch("os.getenv", return_value=None):
                with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                    await oc._call_openai("prompt", "system", "gpt-4o")

    @pytest.mark.asyncio
    async def test_response_parsed(self):
        """정상 응답에서 content 추출"""
        fake_response = {
            "choices": [{"message": {"content": "안녕하세요"}}],
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

        with patch("os.getenv", return_value="test-key"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await oc._call_openai("prompt", "system", "gpt-4o")
        assert result == "안녕하세요"

    @pytest.mark.asyncio
    async def test_json_format_adds_response_format(self):
        """json_format=True 시 payload에 response_format 포함"""
        fake_response = {
            "choices": [{"message": {"content": '{"key": "val"}'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}

        captured_payload = {}

        async def fake_post(url, headers, json):
            captured_payload.update(json)
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = fake_post

        with patch("os.getenv", return_value="test-key"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await oc._call_openai("prompt", "system", "gpt-4o", json_format=True)

        assert captured_payload.get("response_format") == {"type": "json_object"}


class TestGenerateTitle:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_default(self):
        """OPENAI_API_KEY 미설정 시 기본 제목 반환"""
        with patch("os.getenv", return_value=None):
            result = await oc.generate_title_for_conversation(["a", "b"])
            assert result == "Untitled_Conversation"

    @pytest.mark.asyncio
    async def test_short_history(self):
        """history가 2개 미만이면 '새로운_대화' 반환"""
        with patch("os.getenv", return_value="fake-key"):
            result = await oc.generate_title_for_conversation(["single"])
            assert result == "새로운_대화"

    @pytest.mark.asyncio
    async def test_exception_returns_fallback(self):
        """_call_openai 예외 시 'Untitled_Conversation' 반환"""
        with patch("os.getenv", return_value="fake-key"):
            with patch.object(oc, "_call_openai", side_effect=Exception("오류")):
                result = await oc.generate_title_for_conversation(["a", "b"])
                assert result == "Untitled_Conversation"
