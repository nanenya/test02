#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_web_network_atomic.py: web_network_atomic 모듈에 대한 단위 테스트

httpx, socket, subprocess 등을 mock하여 실제 네트워크 요청 없이 테스트합니다.
"""

import pytest
import socket
from unittest.mock import patch, MagicMock

from . import web_network_atomic as mcp


@pytest.fixture(autouse=True)
def patch_allowed_base(tmp_path, monkeypatch):
    """ALLOWED_BASE_PATH를 tmp_path로 교체"""
    monkeypatch.setattr("mcp_modules.web_network_atomic.ALLOWED_BASE_PATH", tmp_path)


# --- _validate_url 테스트 ---
class TestValidateUrl:
    def test_success_https(self):
        mcp._validate_url("https://example.com/path")  # 예외 없으면 통과

    def test_success_http(self):
        mcp._validate_url("http://example.com")

    def test_failure_ftp_scheme(self):
        with pytest.raises(ValueError, match="허용되지 않는 URL 스키마"):
            mcp._validate_url("ftp://example.com")

    def test_failure_private_ip_10(self):
        with pytest.raises(ValueError, match="SSRF"):
            mcp._validate_url("http://10.0.0.1/secret")

    def test_failure_private_ip_192(self):
        with pytest.raises(ValueError, match="SSRF"):
            mcp._validate_url("http://192.168.1.1/secret")

    def test_failure_loopback(self):
        with pytest.raises(ValueError, match="SSRF"):
            mcp._validate_url("http://127.0.0.1/admin")


# --- fetch_url_content 테스트 ---
class TestFetchUrlContent:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.text = "<html>hello</html>"
        mock_resp.raise_for_status = MagicMock()
        with patch("mcp_modules.web_network_atomic.httpx.get", return_value=mock_resp) as mock_get:
            result = mcp.fetch_url_content("https://example.com")
        assert result == "<html>hello</html>"

    def test_failure_invalid_url(self):
        with pytest.raises(ValueError):
            mcp.fetch_url_content("ftp://example.com")


# --- api_get_request 테스트 ---
class TestApiGetRequest:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"key": "value"}
        mock_resp.raise_for_status = MagicMock()
        with patch("mcp_modules.web_network_atomic.httpx.get", return_value=mock_resp):
            result = mcp.api_get_request("https://api.example.com/data")
        assert result == {"key": "value"}

    def test_failure_ssrf(self):
        with pytest.raises(ValueError, match="SSRF"):
            mcp.api_get_request("http://172.16.0.1/admin")


# --- api_post_request 테스트 ---
class TestApiPostRequest:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"created": True}
        mock_resp.raise_for_status = MagicMock()
        with patch("mcp_modules.web_network_atomic.httpx.post", return_value=mock_resp):
            result = mcp.api_post_request("https://api.example.com/create", json_body={"name": "test"})
        assert result == {"created": True}


# --- get_http_status 테스트 ---
class TestGetHttpStatus:
    def test_success_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("mcp_modules.web_network_atomic.httpx.head", return_value=mock_resp):
            result = mcp.get_http_status("https://example.com")
        assert result == 200

    def test_failure_returns_minus_one(self):
        import httpx as _httpx
        with patch("mcp_modules.web_network_atomic.httpx.head", side_effect=_httpx.ConnectError("fail")):
            with patch("mcp_modules.web_network_atomic.httpx.get", side_effect=_httpx.ConnectError("fail")):
                result = mcp.get_http_status("https://example.com")
        assert result == -1

    def test_failure_invalid_url(self):
        with pytest.raises(ValueError):
            mcp.get_http_status("ftp://invalid")


# --- resolve_dns 테스트 ---
class TestResolveDns:
    def test_success(self):
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            result = mcp.resolve_dns("example.com")
        assert result == "93.184.216.34"

    def test_failure_returns_empty(self):
        with patch("socket.gethostbyname", side_effect=socket.gaierror("fail")):
            result = mcp.resolve_dns("nonexistent.invalid")
        assert result == ""


# --- ping_host 테스트 ---
class TestPingHost:
    def test_success(self):
        mock_result = MagicMock()
        mock_result.stdout = "PING 8.8.8.8: 56 data bytes\n64 bytes from 8.8.8.8"
        mock_result.stderr = ""
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = mcp.ping_host("8.8.8.8", count=1)
        assert "8.8.8.8" in result

    def test_failure_private_ip(self):
        with pytest.raises(ValueError, match="SSRF"):
            mcp.ping_host("10.0.0.1")

    def test_failure_invalid_hostname(self):
        with pytest.raises(ValueError, match="유효하지 않은 호스트명"):
            mcp.ping_host("invalid host name!")


# --- download_file_from_url 테스트 ---
class TestDownloadFileFromUrl:
    def test_success(self, tmp_path):
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=ctx_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)
        ctx_mock.raise_for_status = MagicMock()
        ctx_mock.iter_bytes = MagicMock(return_value=[b"hello", b" world"])
        with patch("mcp_modules.web_network_atomic.httpx.stream", return_value=ctx_mock):
            result = mcp.download_file_from_url(
                "https://example.com/file.bin",
                str(tmp_path / "downloaded.bin"),
            )
        assert result is True

    def test_failure_path_traversal(self):
        with pytest.raises(ValueError, match="보안 오류"):
            mcp.download_file_from_url("https://example.com/file.bin", "/etc/malicious")


# --- fetch_dynamic_content ImportError 테스트 ---
class TestFetchDynamicContent:
    def test_failure_selenium_not_installed(self):
        with patch.dict("sys.modules", {"selenium": None, "selenium.webdriver": None}):
            with pytest.raises(ImportError, match="selenium"):
                mcp.fetch_dynamic_content("https://example.com")


# --- send_email_smtp 테스트 ---
class TestSendEmailSmtp:
    def test_failure_missing_env(self, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_PORT", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASS", raising=False)
        with pytest.raises(EnvironmentError, match="환경변수"):
            mcp.send_email_smtp("to@example.com", "Subject", "Body")

    def test_success(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "user@example.com")
        monkeypatch.setenv("SMTP_PASS", "password")
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP_SSL", return_value=mock_smtp):
            result = mcp.send_email_smtp("to@example.com", "Subject", "Body")
        assert result is True
