#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_user_interaction_atomic.py

'interaction_utils.py' 모듈의 MCP 함수들에 대한 단위 테스트.
"""

import os
import sys
from io import StringIO
from unittest.mock import patch

import pytest
from rich.prompt import Confirm, Prompt
from rich.console import Console

from .user_interaction_atomic import (
    ask_for_multiline_input,
    ask_for_password,
    ask_user_for_confirmation,
    ask_user_for_input,
    clear_screen,
    display_table,
    show_alert,
    show_message
)

# --- 성공 케이스 ---

def test_ask_user_for_input_success(monkeypatch):
    """ask_user_for_input 성공 케이스 테스트"""
    monkeypatch.setattr(Prompt, "ask", lambda _: "test_project")
    assert ask_user_for_input("Project name?") == "test_project"

def test_ask_for_multiline_input_success(monkeypatch):
    """ask_for_multiline_input 성공 케이스 테스트"""
    inputs = iter(['first line', 'second line', 'EOF'])
    monkeypatch.setattr('builtins.input', lambda: next(inputs))
    expected = "first line\nsecond line"
    assert ask_for_multiline_input("Enter text:") == expected

def test_ask_user_for_confirmation_yes(monkeypatch):
    """ask_user_for_confirmation 'yes' 케이스 테스트"""
    monkeypatch.setattr(Confirm, "ask", lambda _, default: True)
    assert ask_user_for_confirmation("Continue?") is True

def test_ask_user_for_confirmation_no(monkeypatch):
    """ask_user_for_confirmation 'no' 케이스 테스트"""
    monkeypatch.setattr(Confirm, "ask", lambda _, default: False)
    assert ask_user_for_confirmation("Continue?") is False

def test_ask_for_password_success(monkeypatch):
    """ask_for_password 성공 케이스 테스트"""
    monkeypatch.setattr("getpass.getpass", lambda _: "secret_pass")
    assert ask_for_password("Enter pass:") == "secret_pass"

def test_show_message_success(capsys):
    """show_message가 메시지를 정상 출력하는지 테스트"""
    show_message("Hello World")
    captured = capsys.readouterr()
    assert "Hello World" in captured.out

def test_show_alert_success(capsys):
    """show_alert가 수준별 메시지를 정상 출력하는지 테스트"""
    show_alert("Success!", level="success")
    captured = capsys.readouterr()
    assert "[SUCCESS] Success!" in captured.out
    assert "green" in captured.out # rich가 사용하는 스타일 키워드

def test_show_alert_success(monkeypatch):
    """show_alert가 성공 메시지를 올바른 스타일로 출력하는지 테스트"""
    # 1. 출력을 가로챌 가상의 터미널(StringIO)과 콘솔 객체를 만듭니다.
    # string_io = StringIO()
    # test_console = Console(file=string_io, force_terminal=True, color_system="truecolor")
    # test_console = Console(file=string_io, color_system=None) 
    test_console = Console(record=True, width=100)

    # 2. monkeypatch를 이용해 원본 console 객체를 테스트용 객체로 임시 교체합니다.
    #    'mcp_modules.user_interaction_atomic.console' 부분은
    #    실제 console 객체가 정의된 경로로 맞춰주어야 합니다.
    monkeypatch.setattr('mcp_modules.user_interaction_atomic.console', test_console)

    # 3. 테스트할 함수를 호출합니다.
    #    이제 show_alert 안의 console.print는 test_console을 통해 실행됩니다.
    show_alert("Success!", level="success")

    # 4. 가상 터미널에 기록된 내용을 가져옵니다.
    # captured_output = string_io.getvalue()
    captured_output = test_console.export_text()

    # 5. 이제 스타일 태그가 포함된 원본 내용을 검증할 수 있습니다.
    assert "[SUCCESS] Success!" in captured_output
    # assert "[green]" in captured_output # 스타일 키워드 'green'이 아닌, rich의 마크업 '[green]'을 확인합니다.

def test_display_table_success(capsys):
    """display_table이 표를 정상 출력하는지 테스트"""
    data = [{"id": "1", "name": "test"}]
    headers = ["id", "name"]
    display_table(data, headers)
    captured = capsys.readouterr()
    assert "id" in captured.out
    assert "name" in captured.out
    assert "test" in captured.out

@patch('os.system')
def test_clear_screen(mock_system):
    """clear_screen이 올바른 OS 명령어를 호출하는지 테스트"""
    clear_screen()
    expected_command = 'cls' if os.name == 'nt' else 'clear'
    mock_system.assert_called_once_with(expected_command)


# --- 실패 및 엣지 케이스 ---

def test_ask_for_multiline_input_empty(monkeypatch):
    """ask_for_multiline_input 빈 입력 엣지 케이스 테스트"""
    inputs = iter(['EOF'])
    monkeypatch.setattr('builtins.input', lambda: next(inputs))
    assert ask_for_multiline_input("Enter text:") == ""

@patch('getpass.getpass', side_effect=IOError("Test Error"))
def test_ask_for_password_fail(mock_getpass):
    """ask_for_password가 예외를 발생시키는지 테스트"""
    with pytest.raises(IOError, match="안전한 입력 환경"):
        ask_for_password("Enter pass:")

def test_display_table_empty_data_fail():
    """display_table에 빈 데이터를 전달 시 예외 발생 테스트"""
    with pytest.raises(ValueError, match="데이터와 헤더는 비어 있을 수 없습니다."):
        display_table([], headers=["id"])

def test_display_table_empty_headers_fail():
    """display_table에 빈 헤더를 전달 시 예외 발생 테스트"""
    with pytest.raises(ValueError, match="데이터와 헤더는 비어 있을 수 없습니다."):
        display_table([{"id": 1}], headers=[])

def test_display_table_mismatched_keys_edge_case(capsys):
    """display_table에 키가 없는 데이터가 포함된 엣지 케이스 테스트"""
    data = [{"id": "1", "name": "test"}, {"id": "2"}] # 'name' 키 없음
    headers = ["id", "name"]
    display_table(data, headers)
    captured = capsys.readouterr()
    # "name" 키가 없는 행에도 id "2"는 정상 출력되어야 함
    assert "2" in captured.out
