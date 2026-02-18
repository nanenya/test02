#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_network_atomic.py: AI 에이전트를 위한 웹/네트워크 원자 작업 MCP 라이브러리

HTTP 요청, DNS 조회, 파일 다운로드, RSS 파싱, 이메일 발송, SSL 인증서 조회 등
다양한 네트워크 기능을 제공합니다.

MCP 서버 대체 가능 여부:
  - fetch MCP 서버의 fetch 도구로 fetch_url_content, api_get_request 부분 대체 가능
  - ping_host, resolve_dns, get_ssl_certificate_info 등은 로컬 구현 필요
"""

import ftplib
import ipaddress
import logging
import os
import re
import smtplib
import socket
import ssl
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

# httpx: 동기 HTTP 클라이언트 (requests 대신 사용)
import httpx

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --- 보안 관련 설정 ---
ALLOWED_BASE_PATH = Path(
    os.environ.get("ALLOWED_BASE_PATH", Path(__file__).resolve().parent.parent)
).resolve()

# SSRF 방지: 접근 차단할 내부 네트워크 대역
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
]

# 호스트명 검증 정규식 (도메인 / IPv4 / IPv6 기본)
VALID_HOSTNAME_REGEX = re.compile(
    r'^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*'
    r'([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$'
)


def _validate_path(path: str) -> Path:
    """경로가 ALLOWED_BASE_PATH 내에 있는지 검증합니다."""
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ALLOWED_BASE_PATH):
        logger.error(f"허용되지 않은 경로 접근 시도: {path}")
        raise ValueError(f"보안 오류: 허용된 디렉토리 외부의 경로에는 접근할 수 없습니다: {path}")
    return resolved


def _validate_url(url: str) -> None:
    """URL이 안전한지 검증합니다. http/https 스키마만 허용하고 내부 IP를 차단합니다.

    Args:
        url (str): 검증할 URL.

    Raises:
        ValueError: 허용되지 않는 스키마이거나 내부 IP에 해당하는 경우.
    """
    if not url.startswith(('http://', 'https://')):
        raise ValueError(f"허용되지 않는 URL 스키마입니다 (http/https만 허용): {url}")
    # 호스트 추출 후 IP 확인
    try:
        parsed_host = url.split('/')[2].split(':')[0]
        try:
            ip = ipaddress.ip_address(parsed_host)
            for net in PRIVATE_NETWORKS:
                if ip in net:
                    raise ValueError(f"SSRF 방지: 내부 IP 주소에 접근할 수 없습니다: {parsed_host}")
        except ipaddress.AddressValueError:
            # 도메인 이름인 경우 - DNS 조회는 실행 시점에 맡김
            pass
    except (IndexError, ValueError) as e:
        if "SSRF" in str(e):
            raise
        # URL 파싱 실패 시 통과 (httpx가 처리)


def fetch_url_content(url: str, timeout: int = 10) -> str:
    """URL에서 텍스트 콘텐츠를 가져옵니다.

    Args:
        url (str): 가져올 URL (http/https).
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        str: 응답 텍스트.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> content = fetch_url_content("https://httpbin.org/get")
    """
    logger.info(f"URL 콘텐츠 가져오기: {url}")
    _validate_url(url)
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


def download_file_from_url(url: str, local_path: str, timeout: int = 60) -> bool:
    """URL에서 파일을 스트리밍으로 다운로드하여 로컬에 저장합니다.

    Args:
        url (str): 다운로드할 파일 URL (http/https).
        local_path (str): 저장할 로컬 경로.
        timeout (int): 요청 타임아웃(초). 기본값 60.

    Returns:
        bool: 성공 시 True.

    Raises:
        ValueError: 허용되지 않는 URL이거나 로컬 경로가 ALLOWED_BASE_PATH 외부인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> # download_file_from_url("https://example.com/file.zip", "/tmp/file.zip")
    """
    logger.info(f"파일 다운로드: {url} → {local_path}")
    _validate_url(url)
    resolved = _validate_path(local_path)
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
        response.raise_for_status()
        with open(resolved, 'wb') as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)
    logger.info(f"다운로드 완료: {resolved}")
    return True


def api_get_request(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> Any:
    """HTTP GET 요청을 보내고 JSON 응답을 반환합니다.

    Args:
        url (str): 요청 URL (http/https).
        params (Optional[Dict]): 쿼리 파라미터.
        headers (Optional[Dict]): 추가 헤더.
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        Any: 파싱된 JSON 데이터.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> result = api_get_request("https://httpbin.org/json")
    """
    logger.info(f"API GET 요청: {url}")
    _validate_url(url)
    response = httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def api_post_request(
    url: str,
    data: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> Any:
    """HTTP POST 요청을 보내고 JSON 응답을 반환합니다.

    Args:
        url (str): 요청 URL (http/https).
        data (Optional[Dict]): form-encoded 데이터.
        json_body (Optional[Dict]): JSON 바디.
        headers (Optional[Dict]): 추가 헤더.
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        Any: 파싱된 JSON 데이터.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> result = api_post_request("https://httpbin.org/post", json_body={"key": "value"})
    """
    logger.info(f"API POST 요청: {url}")
    _validate_url(url)
    response = httpx.post(url, data=data, json=json_body, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def api_put_request(
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> Any:
    """HTTP PUT 요청을 보내고 JSON 응답을 반환합니다.

    Args:
        url (str): 요청 URL (http/https).
        json_body (Optional[Dict]): JSON 바디.
        headers (Optional[Dict]): 추가 헤더.
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        Any: 파싱된 JSON 데이터.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> # result = api_put_request("https://httpbin.org/put", json_body={"key": "val"})
    """
    logger.info(f"API PUT 요청: {url}")
    _validate_url(url)
    response = httpx.put(url, json=json_body, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def api_delete_request(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> Any:
    """HTTP DELETE 요청을 보내고 JSON 응답을 반환합니다.

    Args:
        url (str): 요청 URL (http/https).
        headers (Optional[Dict]): 추가 헤더.
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        Any: 파싱된 JSON 데이터.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> # result = api_delete_request("https://httpbin.org/delete")
    """
    logger.info(f"API DELETE 요청: {url}")
    _validate_url(url)
    response = httpx.delete(url, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def get_http_status(url: str, timeout: int = 10) -> int:
    """URL의 HTTP 상태 코드를 반환합니다.

    HEAD 요청을 먼저 시도하고, 실패 시 GET 요청으로 폴백합니다.
    요청 자체가 실패하면 -1을 반환합니다.

    Args:
        url (str): 확인할 URL (http/https).
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        int: HTTP 상태 코드. 요청 실패 시 -1.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.

    Example:
        >>> code = get_http_status("https://httpbin.org/status/200")
        >>> code == 200
        True
    """
    logger.info(f"HTTP 상태 코드 확인: {url}")
    _validate_url(url)
    try:
        response = httpx.head(url, timeout=timeout, follow_redirects=True)
        return response.status_code
    except httpx.HTTPStatusError as e:
        return e.response.status_code
    except Exception:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
            return response.status_code
        except Exception as e2:
            logger.warning(f"HTTP 상태 코드 확인 실패: {e2}")
            return -1


def get_http_headers(url: str, timeout: int = 10) -> Dict[str, str]:
    """URL의 HTTP 응답 헤더를 딕셔너리로 반환합니다.

    Args:
        url (str): 확인할 URL (http/https).
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        Dict[str, str]: HTTP 응답 헤더 딕셔너리.

    Raises:
        ValueError: 허용되지 않는 URL인 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> headers = get_http_headers("https://httpbin.org/get")
        >>> isinstance(headers, dict)
        True
    """
    logger.info(f"HTTP 헤더 조회: {url}")
    _validate_url(url)
    response = httpx.head(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return dict(response.headers)


def ping_host(host: str, count: int = 4) -> str:
    """호스트에 ping을 보내고 결과를 반환합니다.

    Args:
        host (str): 대상 호스트명 또는 IP 주소.
        count (int): 보낼 ping 패킷 수. 기본값 4.

    Returns:
        str: ping 명령어 출력 또는 오류 메시지.

    Raises:
        ValueError: 호스트명 형식이 유효하지 않은 경우.

    Example:
        >>> result = ping_host("8.8.8.8", count=1)
        >>> isinstance(result, str)
        True
    """
    logger.info(f"ping 시도: {host} (count={count})")
    # 내부 IP 차단
    try:
        ip = ipaddress.ip_address(host)
        for net in PRIVATE_NETWORKS:
            if ip in net:
                raise ValueError(f"SSRF 방지: 내부 IP 주소에 ping할 수 없습니다: {host}")
    except ValueError as e:
        if "SSRF" in str(e):
            raise
        # IP 파싱 실패 → 도메인 이름으로 간주하여 검증
        if not VALID_HOSTNAME_REGEX.match(host):
            raise ValueError(f"유효하지 않은 호스트명: {host}") from None

    # OS별 ping 플래그
    flag = "-n" if sys.platform == "win32" else "-c"
    try:
        result = subprocess.run(
            ["ping", flag, str(count), host],
            capture_output=True,
            text=True,
            timeout=count * 5,
        )
        output = result.stdout + result.stderr
        logger.info(f"ping 완료: returncode={result.returncode}")
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"ping 타임아웃: {host}"
    except FileNotFoundError:
        return "오류: ping 명령어를 찾을 수 없습니다."


def resolve_dns(hostname: str) -> str:
    """호스트명의 IP 주소를 DNS 조회로 반환합니다.

    Args:
        hostname (str): 조회할 호스트명.

    Returns:
        str: 해석된 IP 주소. 실패 시 빈 문자열.

    Example:
        >>> ip = resolve_dns("localhost")
        >>> ip in ("127.0.0.1", "::1")
        True
    """
    logger.info(f"DNS 조회: {hostname}")
    try:
        ip = socket.gethostbyname(hostname)
        logger.info(f"DNS 조회 성공: {hostname} → {ip}")
        return ip
    except socket.gaierror as e:
        logger.warning(f"DNS 조회 실패: {hostname}, 오류: {e}")
        return ""


def parse_rss_feed(url: str, timeout: int = 10) -> List[Dict[str, str]]:
    """RSS/Atom 피드 URL을 파싱하여 항목 목록을 반환합니다.

    Args:
        url (str): RSS/Atom 피드 URL (http/https).
        timeout (int): 요청 타임아웃(초). 기본값 10.

    Returns:
        List[Dict[str, str]]: 피드 항목 목록. 각 항목은 title, link, summary 키를 가짐.

    Raises:
        ValueError: 허용되지 않는 URL이거나 feedparser가 없는 경우.
        httpx.HTTPError: HTTP 요청 실패 시.

    Example:
        >>> # items = parse_rss_feed("https://example.com/feed.rss")
    """
    logger.info(f"RSS 피드 파싱: {url}")
    _validate_url(url)
    try:
        import feedparser
    except ImportError:
        raise ValueError("feedparser 라이브러리가 필요합니다. 'pip install feedparser'로 설치하세요.")
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    items = []
    for entry in feed.entries:
        items.append({
            "title": getattr(entry, "title", ""),
            "link": getattr(entry, "link", ""),
            "summary": getattr(entry, "summary", ""),
        })
    logger.info(f"{len(items)}개 RSS 항목 파싱 완료")
    return items


def send_email_smtp(
    to_address: str,
    subject: str,
    body: str,
) -> bool:
    """SMTP를 통해 이메일을 발송합니다.

    환경변수 SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS가 반드시 설정되어야 합니다.

    Args:
        to_address (str): 수신자 이메일 주소.
        subject (str): 이메일 제목.
        body (str): 이메일 본문 텍스트.

    Returns:
        bool: 발송 성공 시 True.

    Raises:
        EnvironmentError: 필수 환경변수 미설정 시.
        smtplib.SMTPException: SMTP 발송 실패 시.

    Example:
        >>> # 환경변수 설정 후: send_email_smtp("to@example.com", "제목", "본문")
    """
    logger.info(f"이메일 발송 시도: {to_address}")
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        raise EnvironmentError(
            "이메일 발송에 필요한 환경변수가 설정되지 않았습니다: "
            "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS"
        )

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_address

    with smtplib.SMTP_SSL(smtp_host, int(smtp_port)) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    logger.info(f"이메일 발송 완료: {to_address}")
    return True


def get_ssl_certificate_info(hostname: str, port: int = 443) -> Dict[str, Any]:
    """호스트의 SSL 인증서 정보를 반환합니다.

    Args:
        hostname (str): 조회할 호스트명.
        port (int): HTTPS 포트. 기본값 443.

    Returns:
        Dict[str, Any]: SSL 인증서 정보 딕셔너리 (subject, issuer, notAfter 등).

    Raises:
        ValueError: 호스트명이 유효하지 않은 경우.
        ssl.SSLError: SSL 연결 실패 시.
        socket.gaierror: DNS 조회 실패 시.

    Example:
        >>> info = get_ssl_certificate_info("google.com")
        >>> "subject" in info
        True
    """
    logger.info(f"SSL 인증서 정보 조회: {hostname}:{port}")
    if not VALID_HOSTNAME_REGEX.match(hostname):
        raise ValueError(f"유효하지 않은 호스트명: {hostname}")
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()
    logger.info(f"SSL 인증서 조회 완료: {hostname}")
    return cert


def fetch_dynamic_content(url: str) -> str:
    """Selenium을 사용하여 JavaScript가 렌더링된 동적 웹 페이지 내용을 가져옵니다.

    Args:
        url (str): 가져올 URL (http/https).

    Returns:
        str: 렌더링된 페이지 소스.

    Raises:
        ImportError: selenium이 설치되지 않은 경우.
        ValueError: 허용되지 않는 URL인 경우.

    Example:
        >>> # content = fetch_dynamic_content("https://example.com")
    """
    logger.info(f"동적 콘텐츠 가져오기 (Selenium): {url}")
    _validate_url(url)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        raise ImportError(
            "selenium 라이브러리가 필요합니다. 'pip install selenium'으로 설치하세요."
        )
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        content = driver.page_source
    finally:
        driver.quit()
    logger.info(f"동적 콘텐츠 가져오기 완료: {url}")
    return content


def ftp_upload_file(
    ftp_host: str,
    ftp_user: str,
    ftp_pass: str,
    local_path: str,
    remote_path: str,
    port: int = 21,
) -> bool:
    """FTP(TLS)를 통해 로컬 파일을 원격 서버에 업로드합니다.

    Args:
        ftp_host (str): FTP 서버 호스트명 또는 IP.
        ftp_user (str): FTP 사용자명.
        ftp_pass (str): FTP 비밀번호.
        local_path (str): 업로드할 로컬 파일 경로.
        remote_path (str): 업로드 대상 원격 경로.
        port (int): FTP 포트. 기본값 21.

    Returns:
        bool: 업로드 성공 시 True.

    Raises:
        ValueError: local_path가 ALLOWED_BASE_PATH 외부인 경우.
        FileNotFoundError: 로컬 파일이 존재하지 않는 경우.
        ftplib.Error: FTP 연결 또는 업로드 실패 시.

    Example:
        >>> # ftp_upload_file("ftp.example.com", "user", "pass", "/tmp/file.txt", "/remote/file.txt")
    """
    logger.info(f"FTP 업로드: {local_path} → {ftp_host}:{remote_path}")
    resolved = _validate_path(local_path)
    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {local_path}")
    with ftplib.FTP_TLS() as ftp:
        ftp.connect(ftp_host, port)
        ftp.login(ftp_user, ftp_pass)
        ftp.prot_p()
        with open(resolved, 'rb') as f:
            ftp.storbinary(f"STOR {remote_path}", f)
    logger.info(f"FTP 업로드 완료: {remote_path}")
    return True


def ftp_download_file(
    ftp_host: str,
    ftp_user: str,
    ftp_pass: str,
    remote_path: str,
    local_path: str,
    port: int = 21,
) -> bool:
    """FTP(TLS)를 통해 원격 파일을 로컬에 다운로드합니다.

    Args:
        ftp_host (str): FTP 서버 호스트명 또는 IP.
        ftp_user (str): FTP 사용자명.
        ftp_pass (str): FTP 비밀번호.
        remote_path (str): 다운로드할 원격 파일 경로.
        local_path (str): 저장할 로컬 파일 경로.
        port (int): FTP 포트. 기본값 21.

    Returns:
        bool: 다운로드 성공 시 True.

    Raises:
        ValueError: local_path가 ALLOWED_BASE_PATH 외부인 경우.
        ftplib.Error: FTP 연결 또는 다운로드 실패 시.

    Example:
        >>> # ftp_download_file("ftp.example.com", "user", "pass", "/remote/file.txt", "/tmp/file.txt")
    """
    logger.info(f"FTP 다운로드: {ftp_host}:{remote_path} → {local_path}")
    resolved = _validate_path(local_path)
    with ftplib.FTP_TLS() as ftp:
        ftp.connect(ftp_host, port)
        ftp.login(ftp_user, ftp_pass)
        ftp.prot_p()
        with open(resolved, 'wb') as f:
            ftp.retrbinary(f"RETR {remote_path}", f.write)
    logger.info(f"FTP 다운로드 완료: {resolved}")
    return True
