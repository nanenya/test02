#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_circuit_breaker.py
"""Circuit Breaker 단위 테스트."""

import time
import pytest
from unittest.mock import MagicMock, patch


def _make_http_error(status: int, body: str):
    """httpx.HTTPStatusError 모의 객체 생성."""
    import httpx
    request = MagicMock()
    response = MagicMock()
    response.status_code = status
    response.text = body
    return httpx.HTTPStatusError(message=f"{status}", request=request, response=response)


class TestDetectCircuitTrip:
    """_detect_circuit_trip() 에러 패턴 감지 테스트."""

    def setup_method(self):
        from orchestrator import llm_client
        self.fn = llm_client._detect_circuit_trip

    def test_anthropic_credit_exhausted(self):
        exc = _make_http_error(400, '{"error":{"message":"Your credit balance is too low to access the Anthropic API."}}')
        result = self.fn(exc, "claude")
        assert result is not None
        duration, reason = result
        assert duration == 24 * 3600
        assert "크레딧 소진" in reason

    def test_gemini_resource_exhausted(self):
        exc = _make_http_error(429, '{"error":{"status":"RESOURCE_EXHAUSTED","message":"Resource has been exhausted"}}')
        result = self.fn(exc, "gemini")
        assert result is not None
        duration, reason = result
        assert duration > 0
        assert "일일 quota" in reason

    def test_openai_insufficient_quota(self):
        exc = _make_http_error(429, '{"error":{"code":"insufficient_quota","message":"You exceeded your current quota"}}')
        result = self.fn(exc, "openai")
        assert result is not None
        duration, reason = result
        assert duration == 24 * 3600
        assert "billing quota" in reason

    def test_generic_rate_limit_429(self):
        exc = _make_http_error(429, '{"error":"rate limit exceeded"}')
        result = self.fn(exc, "gemini")
        assert result is not None
        duration, reason = result
        assert duration == 60
        assert "분당" in reason

    def test_normal_error_no_trip(self):
        """일반 에러는 circuit trip 없음."""
        exc = RuntimeError("일반 네트워크 오류")
        result = self.fn(exc, "gemini")
        assert result is None

    def test_ollama_connect_error_no_trip(self):
        """Ollama 연결 오류는 circuit trip 없음 (일시적 오류)."""
        exc = RuntimeError("Ollama 서버에 연결할 수 없습니다")
        result = self.fn(exc, "ollama")
        assert result is None


class TestCircuitBreakerState:
    """_trip / _is_tripped 상태 관리 테스트."""

    def setup_method(self):
        from orchestrator import llm_client
        llm_client._circuit_breaker.clear()
        self.trip = llm_client._trip
        self.is_tripped = llm_client._is_tripped
        self.cb = llm_client._circuit_breaker

    def test_trip_and_check(self):
        self.trip("claude", 3600, "테스트 차단")
        tripped, reason = self.is_tripped("claude")
        assert tripped is True
        assert "테스트 차단" in reason
        assert "남은 시간" in reason

    def test_expired_entry_auto_cleared(self):
        self.cb["claude"] = {"until": time.time() - 1, "reason": "만료됨"}
        tripped, reason = self.is_tripped("claude")
        assert tripped is False
        assert "claude" not in self.cb

    def test_not_tripped_provider(self):
        tripped, reason = self.is_tripped("ollama")
        assert tripped is False
        assert reason == ""


class TestGetProviderStatus:
    """get_provider_status() 전체 상태 반환 테스트."""

    def setup_method(self):
        from orchestrator import llm_client
        llm_client._circuit_breaker.clear()

    def test_all_available_by_default(self):
        from orchestrator.llm_client import get_provider_status
        status = get_provider_status()
        assert "gemini" in status
        assert "claude" in status
        assert status["gemini"]["available"] is True

    def test_tripped_provider_shows_unavailable(self):
        from orchestrator import llm_client
        llm_client._trip("claude", 3600, "크레딧 소진")
        status = llm_client.get_provider_status()
        assert status["claude"]["available"] is False
        assert "크레딧 소진" in status["claude"]["reason"]

    def test_in_fallback_chain_flag(self):
        from orchestrator.llm_client import get_provider_status
        status = get_provider_status()
        # 최소 1개는 폴백 체인에 포함돼야 함
        assert any(v["in_fallback_chain"] for v in status.values())
