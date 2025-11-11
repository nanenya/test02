#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_web_network_atomic.py

web_network_atomic.py의 함수들에 대한 단위 테스트입니다.
`pytest`와 `pytest-mock`, `requests-mock`을 사용하여 외부 의존성을 격리하고 테스트합니다.
"""

import pytest
import requests
import requests_mock
from requests.exceptions import RequestException, HTTPError
import socket
import subprocess
import smtplib
import ssl
from ftplib import FTP_TLS

# 테스트 대상 모듈 임포트
from mcp_modules import web_network_atomic

# --- _validate_and_sanitize_url 테스트 ---
def test_validate_url_success():
    assert web_network_atomic._validate_and_sanitize_url("https://google.com") == "https://google.com"

def test_validate_url_invalid_format():
    with pytest.raises(ValueError, match="URL 형식이 잘못되었습니다"):
        web_network_atomic._validate_and_sanitize_url("htp:/google.com")

def test_validate_url_private_ip(mocker):
    mocker.patch('socket.gethostbyname', return_value='192.168.1.1')
    mocker.patch('socket.inet_aton') # is_private를 흉내내기 위해 추가
    socket.inet_aton.return_value.is_private = True
    with pytest.raises(ValueError, match="내부 네트워크 IP로의 요청은 허용되지 않습니다"):
        web_network_atomic._validate_and_sanitize_url("https://private-host.com")

# --- fetch_url_content 테스트 ---
def test_fetch_url_content_success(requests_mock):
    url = "https://test.com"
    requests_mock.get(url, text="<html>Success</html>")
    assert web_network_atomic.fetch_url_content(url) == "<html>Success</html>"

def test_fetch_url_content_http_error(requests_mock):
    url = "https://test.com"
    requests_mock.get(url, status_code=404)
    with pytest.raises(HTTPError):
        web_network_atomic.fetch_url_content(url)

def test_fetch_url_content_network_error(requests_mock):
    url = "https://test.com"
    requests_mock.get(url, exc=RequestException("Network Error"))
    with pytest.raises(RequestException):
        web_network_atomic.fetch_url_content(url)

# --- download_file_from_url 테스트 ---
def test_download_file_success(requests_mock, tmp_path):
    url = "https://test.com/file.txt"
    save_dir = tmp_path
    save_path = save_dir / "file.txt"
    requests_mock.get(url, content=b"file content")
    
    result_path = web_network_atomic.download_file_from_url(url, str(save_path))
    assert save_path.read_bytes() == b"file content"
    assert result_path == str(save_path.resolve())

def test_download_file_unsafe_path():
    with pytest.raises(ValueError, match="저장 경로가 안전하지 않거나"):
        web_network_atomic.download_file_from_url("https://test.com/file", "/nonexistent/dir/file.txt")

# --- API 요청 함수들 테스트 ---
@pytest.mark.parametrize("api_func, method", [
    (web_network_atomic.api_get_request, "GET"),
    (web_network_atomic.api_post_request, "POST"),
    (web_network_atomic.api_put_request, "PUT"),
])
def test_api_requests_success(requests_mock, api_func, method):
    url = "https://api.test.com/data"
    mock_response = {"status": "ok"}
    requests_mock.register_uri(method, url, json=mock_response, status_code=200)
    
    response = api_func(url) if method == "GET" else api_func(url, data={"key": "val"})
    assert response == mock_response

def test_api_delete_request_success(requests_mock):
    url = "https://api.test.com/data/1"
    requests_mock.delete(url, status_code=204) # No Content
    response = web_network_atomic.api_delete_request(url)
    assert response == {}

def test_api_requests_json_decode_error(requests_mock):
    url = "https://api.test.com/badjson"
    requests_mock.get(url, text="this is not json")
    with pytest.raises(ValueError, match="JSON으로 파싱할 수 없습니다"):
        web_network_atomic.api_get_request(url)
        
# --- get_http_status 테스트 ---
def test_get_http_status_success(requests_mock):
    url = "https://test.com"
    requests_mock.head(url, status_code=200)
    assert web_network_atomic.get_http_status(url) == 200

def test_get_http_status_not_found(requests_mock):
    url = "https://test.com/notfound"
    requests_mock.head(url, status_code=404)
    # requests.head는 4xx/5xx에 대해 예외를 발생시키지 않음
    assert web_network_atomic.get_http_status(url) == 404
    
# --- ping_host 테스트 ---
def test_ping_host_success(mocker):
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.returncode = 0
    assert web_network_atomic.ping_host("google.com") is True

def test_ping_host_fail(mocker):
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.returncode = 1
    assert web_network_atomic.ping_host("unreachable-host") is False

def test_ping_host_command_injection():
    with pytest.raises(ValueError, match="유효하지 않은 호스트 이름"):
        web_network_atomic.ping_host("google.com; ls -la")
        
# --- resolve_dns 테스트 ---
def test_resolve_dns_success(mocker):
    mocker.patch('socket.gethostbyname', return_value="1.2.3.4")
    assert web_network_atomic.resolve_dns("test.com") == "1.2.3.4"

def test_resolve_dns_fail(mocker):
    mocker.patch('socket.gethostbyname', side_effect=socket.gaierror)
    assert web_network_atomic.resolve_dns("nonexistent.domain.xyz") == ""

# --- parse_rss_feed 테스트 ---
def test_parse_rss_feed_success(mocker):
    class MockEntry:
        def __init__(self, title, link, summary):
            self.title = title
            self.link = link
            self.summary = summary
        def get(self, key, default=''):
            return getattr(self, key, default)

    class MockFeed:
        bozo = 0
        entries = [MockEntry('Title 1', 'http://link1', 'Summary 1')]

    mocker.patch('feedparser.parse', return_value=MockFeed())
    result = web_network_atomic.parse_rss_feed("http://test.com/rss.xml")
    assert len(result) == 1
    assert result[0]['title'] == 'Title 1'

def test_parse_rss_feed_bozo(mocker):
    class MockFeed:
        bozo = 1
        bozo_exception = "Parse Error"
        entries = []
    mocker.patch('feedparser.parse', return_value=MockFeed())
    result = web_network_atomic.parse_rss_feed("http://test.com/bad-rss.xml")
    assert result == [] # 여전히 entries를 반환해야 함

# --- send_email_smtp 테스트 ---
def test_send_email_smtp_success(mocker):
    mocker.patch.dict('os.environ', {
        "SMTP_SERVER": "smtp.test.com", "SMTP_PORT": "587",
        "SMTP_SENDER_EMAIL": "sender@test.com", "SMTP_SENDER_PASSWORD": "pass"
    })
    mock_smtp = mocker.patch('smtplib.SMTP').return_value.__enter__.return_value
    assert web_network_atomic.send_email_smtp("receiver@test.com", "Subj", "Body") is True
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_with("sender@test.com", "pass")
    mock_smtp.sendmail.assert_called_once()
    
def test_send_email_smtp_missing_env_vars():
    with pytest.raises(ValueError, match="환경 변수가 모두 설정되지 않았습니다"):
        web_network_atomic.send_email_smtp("test@test.com", "S", "B")
        
# --- get_ssl_certificate_info 테스트 ---
def test_get_ssl_certificate_info_success(mocker):
    mock_cert = {
        'issuer': ((('commonName', 'GTS CA 1P5'),),),
        'subject': ((('commonName', '*.google.com'),),),
        'notAfter': 'Oct 29 23:59:59 2024 GMT'
    }
    mock_ssock = mocker.MagicMock()
    mock_ssock.getpeercert.return_value = mock_cert
    
    # mock_wrap_socket = mocker.patch('ssl.create_default_context().wrap_socket').return_value.__enter__.return_value
    # 'ssl.create_default_context' 함수 자체를 patching 해야 합니다.
    mock_context = mocker.patch('ssl.create_default_context').return_value
    mock_wrap_socket = mock_context.wrap_socket.return_value.__enter__.return_value
    mock_wrap_socket.getpeercert.return_value = mock_cert
    
    mocker.patch('socket.create_connection')
    
    info = web_network_atomic.get_ssl_certificate_info("google.com")
    assert info['issuer'] == 'GTS CA 1P5'
    assert info['subject'] == '*.google.com'

# --- FTP 함수들 테스트 ---
@pytest.mark.parametrize("upload_mode", [True, False])
def test_ftp_operations_success(mocker, tmp_path, upload_mode):
    # 1. FTP_TLS 클래스 자체를 모의(mock) 객체로 만듭니다.
    mock_ftp_class = mocker.patch('mcp_modules.web_network_atomic.FTP_TLS')
    #mock_ftp_class = mocker.patch('ftplib.FTP_TLS')

    # 2. FTP_TLS()로 생성되는 인스턴스에 대한 mock 객체를 가져옵니다.
    mock_ftps_instance = mock_ftp_class.return_value

    # 3. with 구문을 통과할 수 있도록 __enter__ 설정을 해줍니다.
    mock_ftps = mock_ftps_instance.__enter__.return_value

    # 4. 🔥 타임아웃을 막기 위해 login, quit 등의 메서드가
    #    호출되었을 때 정상적으로 응답하는 것처럼 설정합니다.
    mock_ftps.connect.return_value = "220 FTP server ready." # <-- 이 줄을 추가하세요!
    mock_ftps.login.return_value = "230 Login successful."
    mock_ftps.quit.return_value = "221 Goodbye."
    # 만약 실제 코드에서 다른 FTP 명령(예: cwd, set_pasv)을 사용한다면,
    # 해당 명령들도 여기에 추가로 설정해주어야 합니다.
    # 예: mock_ftps.cwd.return_value = "250 Directory successfully changed."
    # mock_ftps = mocker.patch('ftplib.FTP_TLS').return_value.__enter__.return_value
    local_file = tmp_path / "local.txt"
    local_file.write_text("data")
    
    if upload_mode:
        result = web_network_atomic.ftp_upload_file("ftp.test.com", "user", "pass", str(local_file), "/remote.txt")
        mock_ftps.storbinary.assert_called_once()
    else:
        result = web_network_atomic.ftp_download_file("ftp.test.com", "user", "pass", "/remote.txt", str(local_file))
        mock_ftps.retrbinary.assert_called_once()

    assert result is True
    mock_ftps.login.assert_called_with("user", "pass")
    mock_ftps.prot_p.assert_called_once()
