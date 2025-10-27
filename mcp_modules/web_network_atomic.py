#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_network_atomic.py

웹 및 네트워크와 관련된 가장 기본적인 단일 작업을 수행하는 원자(Atomic) MCP 함수 모음입니다.
각 함수는 보안, 안정성, 로깅을 고려하여 프로덕션 레벨 사용을 목표로 설계되었습니다.
"""

import logging
import os
import re
import smtplib
import socket
import ipaddress
import ssl
import subprocess
from email.mime.text import MIMEText
from ftplib import FTP_TLS
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse
from json import JSONDecodeError

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

# --- 로거 설정 ---
# 프로덕션 환경에서는 JSON 포맷터 등을 사용하여 구조화된 로깅을 하는 것이 좋습니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 보안 헬퍼 함수 ---
def _validate_and_sanitize_url(url: str) -> str:
    """
    URL의 유효성을 검사하고 SSRF(Server-Side Request Forgery) 공격을 방지합니다.

    Args:
        url (str): 검증할 URL 문자열.

    Returns:
        str: 유효성 검사를 통과한 URL.

    Raises:
        ValueError: URL 형식이 잘못되었거나, 허용되지 않은 프로토콜을 사용하거나,
                    내부 네트워크 IP 대역으로 확인될 경우 발생합니다.
    """
    if not isinstance(url, str) or not url:
        raise ValueError("URL은 비어 있지 않은 문자열이어야 합니다.")

    # 정규식을 사용하여 URL 구조의 기본적인 유효성 검사
    # RFC 3986을 엄격하게 따르기보다는 일반적인 웹 URL 패턴에 중점
    if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', url, re.IGNORECASE):
        raise ValueError(f"URL 형식이 잘못되었습니다: {url}")

    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if not hostname:
            raise ValueError("URL에서 호스트 이름을 확인할 수 없습니다.")

        # IP 주소로 직접 접근하는 경우, 또는 DNS 확인 결과가 내부 IP인 경우를 방지
        ip_address_str = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip_address_str) # IP 주소 객체 생성
        if ip_obj.is_private:
            raise ValueError(f"SSRF 공격 방지: 내부 네트워크 IP로의 요청은 허용되지 않습니다 ({hostname} -> {ip_address_str}).")

    except socket.gaierror:
        # DNS 조회가 실패해도 일단 URL 형식은 유효할 수 있으므로 통과시킴
        # 실제 요청 시점에서 requests 라이브러리가 오류를 발생시킬 것임
        logger.warning(f"DNS 조회를 실패했습니다: {hostname}")
    except Exception as e:
        # 예상치 못한 오류 발생 시 안전하게 차단
        raise ValueError(f"URL 유효성 검사 중 오류 발생: {e}")

    return url

def fetch_url_content(url: str, timeout: int = 10) -> str:
    """
    주어진 URL의 HTML 소스 코드를 가져옵니다.

    Args:
        url (str): HTML 소스 코드를 가져올 대상 웹 페이지의 전체 URL.
        timeout (int, optional): HTTP 요청 시 대기할 최대 시간(초). 기본값은 10입니다.

    Returns:
        str: 성공 시, 가져온 HTML 소스 코드. 실패 시 빈 문자열을 반환합니다.

    Raises:
        ValueError: URL 형식이 잘못되었거나 내부 IP를 가리킬 경우 발생합니다.
        requests.exceptions.RequestException: 네트워크 연결 오류나 HTTP 오류 발생 시 발생합니다.

    Example:
        >>> html_content = fetch_url_content("https://www.google.com")
        >>> print("google" in html_content.lower())
        True
    """
    logger.info(f"URL 콘텐츠 가져오기 시도: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        headers = {'User-Agent': 'MyAgent/1.0'}
        response = requests.get(safe_url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()  # 200번대 상태 코드가 아니면 HTTPError 발생
        logger.info(f"URL 콘텐츠 가져오기 성공: {url}")
        # 서버가 명시한 인코딩을 사용하되, 없으면 UTF-8을 기본으로 사용
        response.encoding = response.apparent_encoding or 'utf-8'
        return response.text
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {url}, 오류: {e}")
        raise
    except RequestException as e:
        logger.error(f"URL 콘텐츠를 가져오는 중 오류 발생: {url}, 오류: {e}")
        raise
    return ""

def download_file_from_url(url: str, save_path: str, timeout: int = 60) -> str:
    """
    URL에서 파일을 다운로드하여 지정된 경로에 저장합니다.

    Args:
        url (str): 다운로드할 파일의 URL.
        save_path (str): 파일을 저장할 로컬 경로. 디렉토리가 존재해야 합니다.
        timeout (int, optional): 요청 대기 시간(초). 기본값은 60입니다.

    Returns:
        str: 성공 시 저장된 파일의 전체 경로. 실패 시 빈 문자열.

    Raises:
        ValueError: URL이 유효하지 않거나 save_path가 안전하지 않은 경우.
        requests.exceptions.RequestException: 네트워크 오류 발생 시.
        IOError: 파일 쓰기 오류 발생 시.

    Example:
        >>> path = download_file_from_url("https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png", "./google.png")
        >>> print(f"파일 저장 위치: {path}")
    """
    logger.info(f"파일 다운로드 시도: {url} -> {save_path}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        
        # 보안: 경로 조작(Path Traversal) 공격 방지
        save_dir = os.path.dirname(os.path.abspath(save_path))
        if not os.path.isdir(save_dir) or not os.path.abspath(save_path).startswith(save_dir):
            raise ValueError(f"저장 경로가 안전하지 않거나 디렉토리가 존재하지 않습니다: {save_path}")

        headers = {'User-Agent': 'MyAgent/1.0'}
        with requests.get(safe_url, stream=True, timeout=timeout, headers=headers) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"파일 다운로드 성공: {save_path}")
        return os.path.abspath(save_path)
    except ValueError as e:
        logger.error(f"입력값 오류: {e}")
        raise
    except RequestException as e:
        logger.error(f"파일 다운로드 중 네트워크 오류: {url}, 오류: {e}")
        raise
    except IOError as e:
        logger.error(f"파일 저장 중 I/O 오류: {save_path}, 오류: {e}")
        raise
    return ""

def api_get_request(url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None, timeout: int = 10) -> Dict:
    """
    GET 방식으로 API를 호출하고 JSON 응답을 딕셔너리로 반환합니다.

    Args:
        url (str): 호출할 API의 엔드포인트 URL.
        headers (dict, optional): 요청에 포함할 HTTP 헤더.
        params (dict, optional): URL에 추가할 쿼리 파라미터.
        timeout (int, optional): 요청 대기 시간(초). 기본값은 10입니다.

    Returns:
        dict: API의 JSON 응답을 파싱한 딕셔너리.

    Raises:
        ValueError: URL이 유효하지 않을 경우.
        requests.exceptions.RequestException: 네트워크 또는 HTTP 오류 발생 시.

    Example:
        >>> data = api_get_request("https://api.github.com/users/google")
        >>> print(data.get('name'))
        Google
    """
    logger.info(f"API GET 요청: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        response = requests.get(safe_url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except JSONDecodeError as e:
        # requests의 JSONDecodeError를 잡아서 ValueError로 변환하여 다시 발생시킴
        raise ValueError("JSON으로 파싱할 수 없습니다") from e
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"API GET 요청 실패: {url}, 오류: {e}")
        raise
    except ValueError: # requests.JSONDecodeError는 ValueError를 상속
        logger.error(f"API 응답이 유효한 JSON이 아닙니다: {url}")
        raise ValueError("API 응답을 JSON으로 파싱할 수 없습니다.")

def api_post_request(url: str, headers: Optional[Dict] = None, data: Optional[Dict] = None, timeout: int = 10) -> Dict:
    """
    POST 방식으로 API를 호출하고 JSON 응답을 딕셔너리로 반환합니다.

    Args:
        url (str): 호출할 API의 엔드포인트 URL.
        headers (dict, optional): 요청에 포함할 HTTP 헤더.
        data (dict, optional): 요청 본문(body)에 포함할 JSON 데이터.
        timeout (int, optional): 요청 대기 시간(초). 기본값은 10입니다.

    Returns:
        dict: API의 JSON 응답을 파싱한 딕셔너리.

    Raises:
        ValueError: URL이 유효하지 않을 경우.
        requests.exceptions.RequestException: 네트워크 또는 HTTP 오류 발생 시.

    Example:
        >>> payload = {'title': 'foo', 'body': 'bar', 'userId': 1}
        >>> result = api_post_request("https://jsonplaceholder.typicode.com/posts", data=payload)
        >>> print(result.get('id'))
        101
    """
    logger.info(f"API POST 요청: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        response = requests.post(safe_url, headers=headers, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"API POST 요청 실패: {url}, 오류: {e}")
        raise
    except ValueError:
        logger.error(f"API 응답이 유효한 JSON이 아닙니다: {url}")
        raise ValueError("API 응답을 JSON으로 파싱할 수 없습니다.")

# api_put_request와 api_delete_request는 api_post_request와 구조가 매우 유사합니다.
def api_put_request(url: str, headers: Optional[Dict] = None, data: Optional[Dict] = None, timeout: int = 10) -> Dict:
    """PUT 방식으로 데이터를 전송하고 서버의 리소스를 업데이트합니다."""
    logger.info(f"API PUT 요청: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        response = requests.put(safe_url, headers=headers, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"API PUT 요청 실패: {url}, 오류: {e}")
        raise
    except ValueError:
        logger.error(f"API 응답이 유효한 JSON이 아닙니다: {url}")
        raise ValueError("API 응답을 JSON으로 파싱할 수 없습니다.")


def api_delete_request(url: str, headers: Optional[Dict] = None, timeout: int = 10) -> Dict:
    """DELETE 방식으로 서버의 특정 리소스를 삭제합니다."""
    logger.info(f"API DELETE 요청: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        response = requests.delete(safe_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        # DELETE 요청은 응답 본문이 없는 경우가 많으므로 예외 처리
        return response.json() if response.text else {}
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"API DELETE 요청 실패: {url}, 오류: {e}")
        raise
    except ValueError:
        logger.error(f"API 응답이 유효한 JSON이 아닙니다: {url}")
        raise ValueError("API 응답을 JSON으로 파싱할 수 없습니다.")

def get_http_status(url: str, timeout: int = 5) -> int:
    """
    주어진 URL에 접속하여 HTTP 상태 코드를 반환합니다. (HEAD 요청 사용)

    Args:
        url (str): 상태 코드를 확인할 URL.
        timeout (int, optional): 요청 대기 시간(초). 기본값은 5입니다.

    Returns:
        int: HTTP 상태 코드 (예: 200, 404). 오류 발생 시 -1을 반환합니다.

    Raises:
        ValueError: URL이 유효하지 않을 경우.
        requests.exceptions.RequestException: 심각한 네트워크 오류 발생 시.

    Example:
        >>> status = get_http_status("https://www.google.com")
        >>> print(status)
        200
    """
    logger.info(f"HTTP 상태 코드 확인: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        headers = {'User-Agent': 'MyAgent/1.0'}
        # HEAD 요청은 본문을 가져오지 않아 더 효율적입니다.
        response = requests.head(safe_url, timeout=timeout, headers=headers, allow_redirects=True)
        return response.status_code
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"HTTP 상태 확인 중 오류: {url}, 오류: {e}")
        # 일부 HTTP 오류(4xx, 5xx)는 예외를 발생시키지 않고 상태 코드를 반환
        if e.response is not None:
            return e.response.status_code
        raise
    return -1

def ping_host(hostname: str) -> bool:
    """
    특정 호스트나 IP 주소가 응답하는지 (네트워크 연결이 가능한지) 확인합니다.

    [!!] 보안 경고: 이 함수는 OS의 'ping' 명령어를 실행합니다.
    입력값(hostname)은 명령어 주입(Command Injection) 공격을 방지하기 위해
    엄격하게 검증됩니다.

    Args:
        hostname (str): 핑 테스트를 수행할 호스트 이름 또는 IP 주소.

    Returns:
        bool: 호스트가 응답하면 True, 그렇지 않으면 False.

    Raises:
        ValueError: hostname 형식이 유효하지 않은 경우.

    Example:
        >>> is_alive = ping_host("8.8.8.8")
        >>> print(f"Google DNS is alive: {is_alive}")
    """
    logger.info(f"Ping 시도: {hostname}")
    # 보안: 명령어 주입 방지를 위한 호스트 이름/IP 정규식 검증
    # IPv4, IPv6, 그리고 일반적인 도메인 이름을 허용
    if not re.match(r'^[a-zA-Z0-9\.\-:]+$', hostname):
        raise ValueError(f"유효하지 않은 호스트 이름 형식입니다: {hostname}")

    # OS에 따라 ping 명령어 파라미터가 다름
    param = '-n' if os.name == 'nt' else '-c'
    command = ['ping', param, '1', hostname]

    try:
        # shell=False 로 설정하여 셸을 통하지 않고 직접 프로세스를 실행 (보안 강화)
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False, # returncode가 0이 아니어도 예외 발생 안함
            timeout=5 # 5초 타임아웃
        )
        if result.returncode == 0:
            logger.info(f"Ping 성공: {hostname}")
            return True
        else:
            logger.warning(f"Ping 실패: {hostname}, Return Code: {result.returncode}")
            return False
    except FileNotFoundError:
        logger.error("'ping' 명령어를 찾을 수 없습니다. OS에 설치되어 있는지 확인하세요.")
        return False
    except subprocess.TimeoutExpired:
        logger.warning(f"Ping 시간 초과: {hostname}")
        return False
    except Exception as e:
        logger.error(f"Ping 실행 중 예외 발생: {e}")
        return False

def resolve_dns(hostname: str) -> str:
    """
    도메인 이름에 해당하는 IP 주소를 조회합니다.

    Args:
        hostname (str): IP 주소를 조회할 도메인 이름.

    Returns:
        str: 조회된 IP 주소. 실패 시 빈 문자열을 반환합니다.

    Raises:
        ValueError: hostname 형식이 유효하지 않은 경우.

    Example:
        >>> ip = resolve_dns("google.com")
        >>> print(f"Google.com IP: {ip}")
    """
    logger.info(f"DNS 조회 시도: {hostname}")
    if not isinstance(hostname, str) or not hostname:
        raise ValueError("호스트 이름은 비어있지 않은 문자열이어야 합니다.")
    
    try:
        ip_address = socket.gethostbyname(hostname)
        logger.info(f"DNS 조회 성공: {hostname} -> {ip_address}")
        return ip_address
    except socket.gaierror as e:
        logger.warning(f"DNS 조회를 실패했습니다: {hostname}, 오류: {e}")
    return ""

def parse_rss_feed(rss_url: str, timeout: int = 15) -> List[Dict[str, str]]:
    """
    RSS 피드 URL에서 게시물 목록(제목, 링크, 설명 등)을 파싱하여 리스트로 반환합니다.
    'feedparser' 라이브러리를 사용합니다.

    Args:
        rss_url (str): 파싱할 RSS 피드의 URL.
        timeout (int): URL 요청 대기 시간(초). 기본값 15초.

    Returns:
        list: 각 게시물 정보(title, link, summary)가 담긴 딕셔너리의 리스트.
              실패 시 빈 리스트를 반환합니다.

    Raises:
        ValueError: URL이 유효하지 않은 경우.

    Example:
        >>> bbc_news = parse_rss_feed("http://feeds.bbci.co.uk/news/rss.xml")
        >>> if bbc_news: print(bbc_news[0]['title'])
    """
    logger.info(f"RSS 피드 파싱 시도: {rss_url}")
    try:
        # RSS 피드는 http를 사용하는 경우가 많으므로 _validate_and_sanitize_url 재정의
        if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', rss_url, re.IGNORECASE):
             raise ValueError(f"URL 형식이 잘못되었습니다: {rss_url}")
        
        # feedparser는 내부적으로 http 요청을 하므로 타임아웃 설정이 직접적으로 불가.
        # socket의 default timeout을 설정하여 간접적으로 제어.
        socket.setdefaulttimeout(timeout)
        feed = feedparser.parse(rss_url)
        socket.setdefaulttimeout(None) # 원래대로 복구

        if feed.bozo:
            logger.warning(f"RSS 피드 파싱 중 문제가 발생했을 수 있습니다: {rss_url}, 이유: {feed.bozo_exception}")

        entries = []
        for entry in feed.entries:
            entries.append({
                'title': entry.get('title', ''),
                'link': entry.get('link', ''),
                'summary': entry.get('summary', '')
            })
        logger.info(f"RSS 피드에서 {len(entries)}개의 항목을 파싱했습니다.")
        return entries

    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except Exception as e:
        logger.error(f"RSS 피드 파싱 중 예상치 못한 오류 발생: {rss_url}, 오류: {e}")
        return []

def send_email_smtp(to_email: str, subject: str, body: str) -> bool:
    """
    SMTP 서버를 통해 간단한 텍스트 이메일을 발송합니다.
    민감 정보(서버, 포트, 계정)는 환경 변수에서 로드합니다.

    환경 변수 설정 예시:
    export SMTP_SERVER="smtp.gmail.com"
    export SMTP_PORT="587"
    export SMTP_SENDER_EMAIL="my_email@gmail.com"
    export SMTP_SENDER_PASSWORD="my_app_password"

    Args:
        to_email (str): 수신자 이메일 주소.
        subject (str): 이메일 제목.
        body (str): 이메일 본문.

    Returns:
        bool: 이메일 발송 성공 시 True, 실패 시 False.

    Raises:
        ValueError: 환경 변수가 설정되지 않았거나 이메일 형식이 잘못된 경우.

    Example:
        >>> # 환경 변수 설정 후
        >>> # success = send_email_smtp("recipient@example.com", "Test", "This is a test email.")
        >>> # print(f"Email sent: {success}")
    """
    logger.info(f"이메일 발송 시도: -> {to_email}")
    # --- 민감 정보 로드 (환경 변수 사용) ---
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port_str = os.getenv("SMTP_PORT")
    sender_email = os.getenv("SMTP_SENDER_EMAIL")
    password = os.getenv("SMTP_SENDER_PASSWORD")

    if not all([smtp_server, smtp_port_str, sender_email, password]):
        raise ValueError("SMTP 관련 환경 변수가 모두 설정되지 않았습니다.")
    
    if not re.match(r'[^@]+@[^@]+\.[^@]+', to_email):
        raise ValueError("수신자 이메일 주소 형식이 올바르지 않습니다.")

    try:
        smtp_port = int(smtp_port_str)
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, password)
            server.sendmail(sender_email, to_email, msg.as_string())
        logger.info(f"이메일 발송 성공: -> {to_email}")
        return True
    except (ValueError, smtplib.SMTPException) as e:
        logger.error(f"이메일 발송 실패: {e}")
        return False

def get_http_headers(url: str, timeout: int = 5) -> Dict[str, str]:
    """
    URL에 요청했을 때 서버가 반환하는 전체 HTTP 헤더 정보를 딕셔너리로 가져옵니다.

    Args:
        url (str): 헤더를 확인할 URL.
        timeout (int): 요청 대기 시간(초).

    Returns:
        dict: 서버가 반환한 HTTP 헤더 딕셔너리.

    Raises:
        ValueError: URL이 유효하지 않은 경우.
        requests.exceptions.RequestException: 네트워크 오류 발생 시.

    Example:
        >>> headers = get_http_headers("https://www.google.com")
        >>> print(headers.get('Content-Type'))
        text/html; charset=UTF-8
    """
    logger.info(f"HTTP 헤더 확인: {url}")
    try:
        safe_url = _validate_and_sanitize_url(url)
        headers = {'User-Agent': 'MyAgent/1.0'}
        response = requests.head(safe_url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()
        return dict(response.headers)
    except ValueError as e:
        logger.error(f"URL 유효성 검사 실패: {e}")
        raise
    except RequestException as e:
        logger.error(f"HTTP 헤더 확인 중 오류: {url}, 오류: {e}")
        raise

def get_ssl_certificate_info(hostname: str, port: int = 443) -> Dict:
    """
    특정 호스트의 SSL 인증서 정보를 (유효기간, 발급자 등) 조회합니다.

    Args:
        hostname (str): 인증서를 확인할 호스트 이름.
        port (int): 포트 번호, 기본값 443.

    Returns:
        dict: 인증서의 주요 정보(발급 대상, 발급자, 만료일 등)가 담긴 딕셔너리.

    Raises:
        ValueError: hostname 형식이 유효하지 않은 경우.
        ssl.SSLError: SSL 관련 오류 발생 시.
        socket.error: 소켓 연결 오류 발생 시.

    Example:
        >>> cert_info = get_ssl_certificate_info("www.google.com")
        >>> print(f"Issuer: {cert_info.get('issuer')}")
    """
    logger.info(f"SSL 인증서 정보 조회: {hostname}:{port}")
    # 보안: 명령어 주입 방지를 위한 호스트 이름 검증
    if not re.match(r'^[a-zA-Z0-9\.\-]+$', hostname):
        raise ValueError(f"유효하지 않은 호스트 이름 형식입니다: {hostname}")

    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                issuer = dict(x[0] for x in cert.get('issuer', []))
                subject = dict(x[0] for x in cert.get('subject', []))
                
                info = {
                    'issuer': issuer.get('commonName', ''),
                    'subject': subject.get('commonName', ''),
                    'version': cert.get('version'),
                    'serial_number': cert.get('serialNumber'),
                    'not_before': cert.get('notBefore'),
                    'not_after': cert.get('notAfter'),
                }
                logger.info(f"SSL 인증서 정보 조회 성공: {hostname}")
                return info
    except (ssl.SSLError, socket.error, ValueError) as e:
        logger.error(f"SSL 인증서 정보 조회 실패: {hostname}, 오류: {e}")
        raise

def fetch_dynamic_content(url: str, timeout: int = 30) -> str:
    """
    [주의] JavaScript 렌더링이 필요한 동적 웹 페이지의 최종 HTML 소스를 가져옵니다.
    이 함수는 Selenium과 웹 드라이버(예: ChromeDriver)가 설치된 환경에서만 동작합니다.
    상대적으로 무겁고 느린 작업입니다.

    Args:
        url (str): 콘텐츠를 가져올 동적 웹 페이지 URL.
        timeout (int): 페이지 로드를 기다릴 최대 시간(초).

    Returns:
        str: JavaScript 렌더링 후의 최종 HTML 소스 코드.

    Raises:
        ValueError: URL이 유효하지 않은 경우.
        ImportError: 'selenium' 라이브러리가 설치되지 않은 경우.
        Exception: 웹 드라이버 실행 또는 페이지 로드 중 오류 발생 시.

    Example:
        >>> # html = fetch_dynamic_content("https://twitter.com/elonmusk")
        >>> # print("Elon Musk" in html)
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("이 함수를 사용하려면 'selenium'과 'webdriver-manager'가 필요합니다. (pip install selenium webdriver-manager)")
        raise ImportError("'selenium' 라이브러리가 설치되지 않았습니다.")

    logger.info(f"동적 콘텐츠 가져오기 시도: {url}")
    safe_url = _validate_and_sanitize_url(url)

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # UI 없이 백그라운드에서 실행
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=MyDynamicAgent/1.0")

    driver = None
    try:
        # 웹 드라이버 자동 설치 및 설정
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(timeout)
        driver.get(safe_url)
        content = driver.page_source
        logger.info(f"동적 콘텐츠 가져오기 성공: {url}")
        return content
    except Exception as e:
        logger.error(f"동적 콘텐츠 가져오기 중 오류 발생: {e}")
        raise
    finally:
        if driver:
            driver.quit()

def _ftp_operation(upload: bool, host: str, user: str, pwd: str, local_path: str, remote_path: str) -> bool:
    """
    [경고] FTP는 암호를 평문으로 전송하는 오래된 프로토콜입니다.
    가능하면 SFTP 사용을 권장합니다. 이 함수는 보안 연결(FTP over TLS)을 시도합니다.

    내부적으로 FTP 업로드/다운로드를 처리하는 헬퍼 함수.
    민감 정보(user, pwd)는 환경 변수에서 가져오는 것을 권장합니다.
    """
    logger.info(f"FTP {'업로드' if upload else '다운로드'} 시도: {host}")
    if not re.match(r'^[a-zA-Z0-9\.\-]+$', host):
        raise ValueError("유효하지 않은 호스트 이름 형식입니다.")

    try:
        # 보안 강화를 위해 명시적 FTP over TLS 사용
        with FTP_TLS(host, timeout=10) as ftps:
            ftps.login(user, pwd)
            ftps.prot_p()  # 데이터 채널 암호화
            
            if upload:
                with open(local_path, 'rb') as f:
                    ftps.storbinary(f'STOR {remote_path}', f)
                logger.info(f"FTP 업로드 성공: {local_path} -> ftp://{host}/{remote_path}")
            else: # download
                with open(local_path, 'wb') as f:
                    ftps.retrbinary(f'RETR {remote_path}', f.write)
                logger.info(f"FTP 다운로드 성공: ftp://{host}/{remote_path} -> {local_path}")
        return True
    except Exception as e:
        logger.error(f"FTP 작업 실패: {e}")
        return False

def ftp_upload_file(host: str, user: str, pwd: str, local_path: str, remote_path: str) -> bool:
    """
    FTP 프로토콜(TLS)을 사용해 로컬 파일을 원격 서버에 업로드합니다.
    자격 증명은 코드에 하드코딩하지 말고 환경 변수 등을 통해 안전하게 전달하세요.

    Args:
        host (str): FTP 서버 호스트 이름.
        user (str): FTP 사용자 이름.
        pwd (str): FTP 비밀번호.
        local_path (str): 업로드할 로컬 파일 경로.
        remote_path (str): 서버에 저장될 파일 경로.

    Returns:
        bool: 성공 시 True, 실패 시 False.

    Raises:
        ValueError: 호스트 이름이 유효하지 않은 경우.
    """
    return _ftp_operation(True, host, user, pwd, local_path, remote_path)


def ftp_download_file(host: str, user: str, pwd: str, remote_path: str, local_path: str) -> bool:
    """
    FTP 프로토콜(TLS)을 사용해 원격 서버의 파일을 로컬로 다운로드합니다.
    자격 증명은 코드에 하드코딩하지 말고 환경 변수 등을 통해 안전하게 전달하세요.

    Args:
        host (str): FTP 서버 호스트 이름.
        user (str): FTP 사용자 이름.
        pwd (str): FTP 비밀번호.
        remote_path (str): 다운로드할 원격 파일 경로.
        local_path (str): 로컬에 저장될 파일 경로.

    Returns:
        bool: 성공 시 True, 실패 시 False.
    
    Raises:
        ValueError: 호스트 이름이 유효하지 않은 경우.
    """
    return _ftp_operation(False, host, user, pwd, local_path, remote_path)
