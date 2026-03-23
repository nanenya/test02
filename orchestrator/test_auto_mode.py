#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_auto_mode.py
"""자동 모드 민감 데이터 감지 + 히스토리 자동 요약 단위 테스트."""

import pytest
import sys
import os

# main.py는 orchestrator 패키지 밖에 있으므로 경로 조정
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)


class TestSensitiveDataDetection:
    """_check_sensitive_data() 테스트."""

    def _get_fn(self):
        import importlib
        import main as m
        return m._check_sensitive_data

    def test_no_sensitive_data(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "read_file", "arguments": {"path": "/tmp/a.txt"}}]}
        assert fn(group) == []

    def test_password_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "run", "arguments": {"cmd": "password=secret123"}}]}
        assert len(fn(group)) > 0

    def test_api_key_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "call", "arguments": {"key": "api_key=sk-abcdef"}}]}
        assert len(fn(group)) > 0

    def test_aws_key_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "upload", "arguments": {"cred": "AKIAIOSFODNN7EXAMPLE"}}]}
        assert len(fn(group)) > 0

    def test_github_token_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "push", "arguments": {"token": "ghp_" + "a" * 36}}]}
        assert len(fn(group)) > 0

    def test_pem_key_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "ssh", "arguments": {"key": "-----BEGIN RSA PRIVATE KEY-----"}}]}
        assert len(fn(group)) > 0

    def test_empty_group(self):
        fn = self._get_fn()
        assert fn({}) == []
        assert fn({"tasks": []}) == []


class TestSecurityContextDetection:
    """_check_security_context() 테스트."""

    def _get_fn(self):
        import main as m
        return m._check_security_context

    def test_safe_tool(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "read_file", "arguments": {}}]}
        assert fn(group) == []

    def test_git_push_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "git_push", "arguments": {}}]}
        assert "git_push" in fn(group)

    def test_network_request_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "network_request", "arguments": {}}]}
        assert "network_request" in fn(group)

    def test_send_email_detected(self):
        fn = self._get_fn()
        group = {"tasks": [{"tool_name": "send_email", "arguments": {}}]}
        assert "send_email" in fn(group)

    def test_multiple_tools(self):
        fn = self._get_fn()
        group = {
            "tasks": [
                {"tool_name": "read_file", "arguments": {}},
                {"tool_name": "git_push", "arguments": {}},
                {"tool_name": "http_post", "arguments": {}},
            ]
        }
        result = fn(group)
        assert "git_push" in result
        assert "http_post" in result
        assert "read_file" not in result


@pytest.mark.asyncio
class TestMaybeAutoSummarize:
    """_maybe_auto_summarize() 테스트."""

    async def test_below_threshold_no_summarize(self):
        from unittest.mock import AsyncMock, patch
        from orchestrator.api import _maybe_auto_summarize
        from orchestrator.constants import HISTORY_AUTO_SUMMARIZE_THRESHOLD

        short_history = ["항목"] * (HISTORY_AUTO_SUMMARIZE_THRESHOLD - 1)
        with patch("orchestrator._api_helpers.summarize_history", new_callable=AsyncMock) as mock_sum:
            result = await _maybe_auto_summarize(short_history)
        mock_sum.assert_not_called()
        assert result == short_history

    async def test_above_threshold_triggers_summarize(self):
        from unittest.mock import AsyncMock, patch
        from orchestrator.api import _maybe_auto_summarize
        from orchestrator.constants import HISTORY_AUTO_SUMMARIZE_THRESHOLD, HISTORY_KEEP_RECENT

        long_history = [f"항목_{i}" for i in range(HISTORY_AUTO_SUMMARIZE_THRESHOLD + 5)]
        with patch("orchestrator._api_helpers.summarize_history", new_callable=AsyncMock) as mock_sum:
            mock_sum.return_value = "요약된 내용"
            result = await _maybe_auto_summarize(long_history)

        mock_sum.assert_called_once()
        assert len(result) == 1 + HISTORY_KEEP_RECENT
        assert "요약된 내용" in result[0]

    async def test_already_summarized_skips(self):
        """최근 항목에 이미 요약 마커가 있으면 재요약하지 않음."""
        from unittest.mock import AsyncMock, patch
        from orchestrator.api import _maybe_auto_summarize
        from orchestrator.constants import (
            HISTORY_AUTO_SUMMARIZE_THRESHOLD,
            HISTORY_KEEP_RECENT,
            HISTORY_SUMMARY_MARKER,
        )

        long_history = [f"항목_{i}" for i in range(HISTORY_AUTO_SUMMARIZE_THRESHOLD + 5)]
        long_history.append(f"{HISTORY_SUMMARY_MARKER}\n이미 요약됨")
        with patch("orchestrator._api_helpers.summarize_history", new_callable=AsyncMock) as mock_sum:
            result = await _maybe_auto_summarize(long_history)
        mock_sum.assert_not_called()
        assert result == long_history

    async def test_summarize_failure_returns_original(self):
        """요약 실패 시 원본 반환."""
        from unittest.mock import AsyncMock, patch
        from orchestrator.api import _maybe_auto_summarize
        from orchestrator.constants import HISTORY_AUTO_SUMMARIZE_THRESHOLD

        long_history = [f"항목_{i}" for i in range(HISTORY_AUTO_SUMMARIZE_THRESHOLD + 5)]
        with patch("orchestrator._api_helpers.summarize_history", new_callable=AsyncMock) as mock_sum:
            mock_sum.return_value = ""  # 빈 요약 = 실패
            result = await _maybe_auto_summarize(long_history)
        assert result == long_history
