#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
user_interaction_atomic.py

사용자 상호작용을 위한 원자적(Atomic) MCP(Mission Control Primitives) 모음.
이 모듈은 터미널 환경에서 사용자로부터 입력을 받거나 정보를 표시하는
다양한 유틸리티 함수를 제공합니다.
"""

import getpass
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.progress import Progress
from rich.prompt import Confirm, Prompt
from rich.spinner import Spinner
from rich.table import Table

# --- 초기 설정 ---
# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rich 콘솔 객체 초기화
console = Console()


# --- MCP 함수 정의 ---

def ask_user_for_input(question: str) -> str:
    """사용자에게 단일 텍스트 라인 질문을 던지고, 문자열 입력을 받아 반환합니다.

    'rich' 라이브러리의 Prompt를 사용하여 사용자에게 명확한 질문을 제시합니다.

    Args:
        question (str): 사용자에게 표시할 질문 문자열.

    Returns:
        str: 사용자가 입력한 텍스트.

    Example:
        >>> project_name = ask_user_for_input("프로젝트 이름을 입력하세요:")
        >>> print(f"프로젝트 이름: {project_name}")
    """
    logger.info(f"사용자에게 질문 요청: '{question}'")
    # 보안: Rich 라이브러리는 기본적인 입력 처리를 수행합니다.
    # 추가적인 정제(sanitization)가 필요하다면 이 단계 이후에 수행해야 합니다.
    response = Prompt.ask(question)
    logger.info(f"사용자로부터 입력 받음: '{response}'")
    return response

def ask_for_multiline_input(prompt: str) -> str:
    """사용자에게 여러 줄의 텍스트 입력을 요청하고 반환합니다.

    사용자는 입력을 마친 후, 새 줄에 'EOF'를 입력하여 종료 신호를 보냅니다.

    Args:
        prompt (str): 사용자에게 표시할 안내 메시지.

    Returns:
        str: 사용자가 입력한 여러 줄의 텍스트.

    Example:
        >>> commit_message = ask_for_multiline_input("커밋 메시지를 입력하세요 (종료하려면 EOF 입력):")
        >>> print(commit_message)
    """
    logger.info(f"사용자에게 여러 줄 입력 요청: '{prompt}'")
    console.print(f"{prompt} (종료하려면 새 줄에 'EOF'를 입력하세요)")
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == 'EOF':
                break
            lines.append(line)
        except EOFError:  # Ctrl+D / Ctrl+Z
            break
    result = "\n".join(lines)
    logger.info("사용자로부터 여러 줄 입력 완료.")
    return result

def ask_user_for_confirmation(question: str) -> bool:
    """사용자에게 예(Yes)/아니오(No) 질문을 하고, True/False 불리언 값을 반환합니다.

    Args:
        question (str): 사용자에게 표시할 확인 질문.

    Returns:
        bool: 사용자가 '예'를 선택하면 True, '아니오'를 선택하면 False.

    Example:
        >>> if ask_user_for_confirmation("정말로 파일을 삭제하시겠습니까?"):
        ...     print("파일을 삭제했습니다.")
        ... else:
        ...     print("삭제를 취소했습니다.")
    """
    logger.info(f"사용자에게 확인 요청: '{question}'")
    response = Confirm.ask(question, default=False)
    logger.info(f"사용자 확인 응답: {response}")
    return response

def ask_for_password(prompt: str) -> str:
    """사용자에게 민감한 정보(비밀번호 등)를 입력받습니다. 입력 내용은 화면에 표시되지 않습니다.

    Args:
        prompt (str): 사용자에게 표시할 안내 메시지.

    Returns:
        str: 사용자가 입력한 비밀번호 문자열.

    Raises:
        IOError: 터미널이 없어 getpass를 사용할 수 없는 환경일 경우 발생.

    Example:
        >>> api_key = ask_for_password("API 키를 입력하세요:")
    """
    logger.info(f"사용자에게 비밀번호 입력 요청: '{prompt}'")
    try:
        # 보안: getpass는 표준 라이브러리에서 제공하는 안전한 비밀번호 입력 방식입니다.
        password = getpass.getpass(prompt + " ")
        logger.info("사용자로부터 비밀번호 입력 완료.")
        return password
    except Exception as e:
        logger.error(f"비밀번호 입력 중 오류 발생: {e}", exc_info=True)
        raise IOError("안전한 입력 환경(터미널)이 아니므로 비밀번호를 입력할 수 없습니다.") from e

def show_message(message: str):
    """사용자에게 단순 정보성 메시지를 보여줍니다.

    Args:
        message (str): 출력할 메시지.

    Example:
        >>> show_message("스크립트 실행을 완료했습니다.")
    """
    logger.info(f"메시지 표시: '{message}'")
    console.print(message)

def display_table(data: List[Dict[str, Any]], headers: List[str]):
    """구조화된 데이터를 표(Table) 형식으로 깔끔하게 출력합니다.

    Args:
        data (List[Dict[str, Any]]): 표로 만들 데이터. 각 딕셔너리가 행(row)이 됩니다.
        headers (List[str]): 표의 헤더(열 제목) 리스트. 딕셔너리의 키와 일치해야 합니다.

    Raises:
        ValueError: 데이터나 헤더가 비어있거나 형식이 맞지 않을 경우 발생.

    Example:
        >>> users = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        >>> display_table(users, headers=["id", "name"])
    """
    if not headers or not data:
        logger.warning("테이블 데이터나 헤더가 비어 있어 표시할 수 없습니다.")
        raise ValueError("데이터와 헤더는 비어 있을 수 없습니다.")

    logger.info(f"{len(data)}개 행의 테이블 표시.")
    table = Table(show_header=True, header_style="bold magenta")
    for header in headers:
        table.add_column(header)

    try:
        for item in data:
            # 모든 헤더 키가 데이터에 있는지 확인하고, 없으면 빈 문자열로 처리
            row_values = [str(item.get(h, "")) for h in headers]
            table.add_row(*row_values)
        console.print(table)
    except Exception as e:
        logger.error(f"테이블 생성 중 오류 발생: {e}", exc_info=True)
        raise ValueError("테이블 데이터 형식이 잘못되었습니다.") from e

def show_progress_bar(total: int, description: str = "Processing..."):
    """전체 작업량에 대한 진행률 표시줄(Progress Bar)을 보여줍니다.

    이 함수는 진행 상황을 시뮬레이션하며 보여주는 예제입니다.
    실제 사용 시에는 'with' 구문과 함께 progress 객체를 사용하여 작업을 감싸야 합니다.

    Args:
        total (int): 전체 작업량 (예: 100).
        description (str, optional): 진행률 표시줄에 표시될 설명. 기본값은 "Processing...".

    Example:
        >>> show_progress_bar(100, "파일 다운로드 중")
    """
    logger.info(f"'{description}' 작업에 대한 진행률 표시줄 시작 (총 {total}).")
    with Progress(console=console) as progress:
        task = progress.add_task(f"[cyan]{description}", total=total)
        while not progress.finished:
            progress.update(task, advance=1)
            time.sleep(0.02)
    logger.info("진행률 표시줄 완료.")

def clear_screen():
    """터미널이나 콘솔 화면을 깨끗하게 지웁니다.

    운영체제에 따라 적절한 명령어를 사용합니다.

    Example:
        >>> show_message("이 메시지는 곧 사라집니다.")
        >>> time.sleep(2)
        >>> clear_screen()
    """
    logger.info("화면 지우기 실행.")
    # 멱등성: 여러 번 실행해도 화면이 깨끗한 상태는 동일합니다.
    command = 'cls' if os.name == 'nt' else 'clear'
    os.system(command)

def show_alert(message: str, level: str = "info"):
    """심각도 수준에 따라 다른 스타일의 경고 메시지를 보여줍니다.

    Args:
        message (str): 표시할 경고 메시지.
        level (str, optional): 경고 수준. 'info', 'success', 'warning', 'error' 중 하나.
                               기본값은 'info'.

    Example:
        >>> show_alert("설정이 성공적으로 저장되었습니다.", level="success")
        >>> show_alert("API 키가 유효하지 않습니다.", level="error")
    """
    level = level.lower()
    styles = {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red"
    }
    style = styles.get(level, "default")
    prefix = f"[{level.upper()}]"
    logger.info(f"'{level}' 수준의 경고 표시: '{message}'")
    console.print(f"[{style}]{prefix} {message}[/]")

def render_markdown(markdown_text: str):
    """마크다운 형식의 텍스트를 서식이 적용된 형태로 터미널에 출력합니다.

    Args:
        markdown_text (str): 렌더링할 마크다운 텍스트.

    Example:
        >>> doc = "# 제목\\n* 항목 1\\n* 항목 2"
        >>> render_markdown(doc)
    """
    logger.info("마크다운 텍스트 렌더링.")
    md = Markdown(markdown_text)
    console.print(md)

def show_spinner(message: str, duration_sec: float = 2.0):
    """작업이 진행 중임을 알리는 애니메이션 스피너를 일정 시간 동안 보여줍니다.

    이 함수는 스피너를 보여주는 예제입니다. 실제로는 오래 걸리는 작업과 함께
    'with console.status(...) as status:' 구문을 사용하는 것이 좋습니다.

    Args:
        message (str): 스피너와 함께 표시될 메시지.
        duration_sec (float, optional): 스피너를 보여줄 시간(초). 기본값은 2.0.

    Example:
        >>> show_spinner("데이터를 분석하는 중...", duration_sec=3)
    """
    logger.info(f"스피너 시작: '{message}'")
    with console.status(f"[bold green]{message}"):
        time.sleep(duration_sec)
    logger.info("스피너 종료.")

def update_last_line(message: str):
    """콘솔의 마지막 라인에 출력된 메시지를 새로운 메시지로 덮어씁니다.

    줄바꿈 문자 없이 캐리지 리턴('\\r')을 사용하여 커서를 줄의 시작으로
    이동시킨 후 메시지를 출력합니다.

    Args:
        message (str): 덮어쓸 새로운 메시지.

    Example:
        >>> update_last_line("파일 처리 중... 10%")
        >>> time.sleep(1)
        >>> update_last_line("파일 처리 중... 50%")
    """
    # 로깅은 파일에 기록되므로 이 함수의 시각적 효과와는 무관합니다.
    # 따라서 이 함수에서는 로깅을 생략하여 중복을 피합니다.
    sys.stdout.write(f"\r{message}")
    sys.stdout.flush()
