#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
user_interaction_composite 모듈에 대한 단위 테스트.

`pytest`와 `unittest.mock`을 사용하여 대화형 프롬프트를 시뮬레이션하고
각 MCP 함수의 동작을 검증합니다.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# 테스트 대상 모듈 임포트
from mcp_modules import user_interaction_composite as ui

# --- Fixtures ---

@pytest.fixture
def mock_questionary():
    """questionary 라이브러리의 함수들을 모킹(Mocking)합니다."""
    with patch('questionary.select') as mock_select, \
         patch('questionary.checkbox') as mock_checkbox, \
         patch('questionary.path') as mock_path, \
         patch('questionary.confirm') as mock_confirm, \
         patch('questionary.text') as mock_text, \
         patch('questionary.autocomplete') as mock_autocomplete:
        
        yield {
            "select": mock_select,
            "checkbox": mock_checkbox,
            "path": mock_path,
            "confirm": mock_confirm,
            "text": mock_text,
            "autocomplete": mock_autocomplete
        }

# --- Test Cases ---

class TestUserInteractionComposite:

    # 1. present_options_and_get_choice
    def test_present_options_and_get_choice_success(self, mock_questionary):
        """성공 케이스: 사용자가 옵션 중 하나를 선택"""
        mock_questionary["select"].return_value.ask.return_value = "FastAPI"
        result = ui.present_options_and_get_choice("프레임워크 선택", ["Django", "FastAPI"])
        assert result == "FastAPI"
        mock_questionary["select"].assert_called_once()

    def test_present_options_and_get_choice_empty_options(self):
        """실패 케이스: 옵션 리스트가 비어있을 때 ValueError 발생"""
        with pytest.raises(ValueError):
            ui.present_options_and_get_choice("프레임워크 선택", [])
            
    def test_present_options_and_get_choice_cancel(self, mock_questionary):
        """엣지 케이스: 사용자가 선택을 취소(Ctrl+C)했을 때 None 반환"""
        mock_questionary["select"].return_value.ask.return_value = None
        result = ui.present_options_and_get_choice("프레임워크 선택", ["Django", "FastAPI"])
        assert result is None

    # 2. present_checkbox_and_get_choices
    def test_present_checkbox_and_get_choices_success(self, mock_questionary):
        """성공 케이스: 사용자가 여러 옵션을 선택"""
        mock_questionary["checkbox"].return_value.ask.return_value = ["pandas", "numpy"]
        result = ui.present_checkbox_and_get_choices("라이브러리 선택", ["pandas", "numpy"])
        assert result == ["pandas", "numpy"]

    def test_present_checkbox_and_get_choices_empty_options(self, mock_questionary):
        """엣지 케이스: 옵션이 비어있을 때 빈 리스트 반환"""
        result = ui.present_checkbox_and_get_choices("라이브러리 선택", [])
        assert result == []
        mock_questionary["checkbox"].assert_not_called()

    # 3. ask_for_file_path
    def test_ask_for_file_path_success(self, mock_questionary, tmp_path):
        """성공 케이스: 존재하는 파일 경로 입력"""
        dummy_file = tmp_path / "test.txt"
        dummy_file.touch()
        mock_questionary["path"].return_value.ask.return_value = str(dummy_file)
        
        result = ui.ask_for_file_path("파일 경로 입력")
        assert result == str(dummy_file.resolve())

    def test_ask_for_file_path_must_exist_false(self, mock_questionary, tmp_path):
        """엣지 케이스: 존재하지 않아도 되는 파일 경로 입력"""
        non_existent_file = tmp_path / "new_file.txt"
        mock_questionary["path"].return_value.ask.return_value = str(non_existent_file)
        
        result = ui.ask_for_file_path("파일 경로 입력", must_exist=False)
        assert result == str(non_existent_file.resolve())

    # 4. ask_for_directory_path
    def test_ask_for_directory_path_success(self, mock_questionary, tmp_path):
        """성공 케이스: 존재하는 디렉토리 경로 입력"""
        mock_questionary["path"].return_value.ask.return_value = str(tmp_path)
        result = ui.ask_for_directory_path("디렉토리 경로 입력")
        assert result == str(tmp_path.resolve())

    # 5. confirm_critical_action
    def test_confirm_critical_action_yes(self, mock_questionary):
        """성공 케이스: 사용자가 'Yes'를 선택"""
        mock_questionary["confirm"].return_value.ask.return_value = True
        assert ui.confirm_critical_action("파일 삭제") is True

    def test_confirm_critical_action_no(self, mock_questionary):
        """실패 케이스: 사용자가 'No'를 선택"""
        mock_questionary["confirm"].return_value.ask.return_value = False
        assert ui.confirm_critical_action("파일 삭제") is False

    # 6. get_form_input
    def test_get_form_input_success(self, mock_questionary):
        """성공 케이스: 모든 폼 필드를 정상적으로 입력"""
        mock_questionary["text"].return_value.ask.side_effect = ["John Doe", "johndoe@email.com"]
        form = {"name": "이름:", "email": "이메일:"}
        result = ui.get_form_input(form)
        assert result == {"name": "John Doe", "email": "johndoe@email.com"}
    
    def test_get_form_input_cancel(self, mock_questionary):
        """엣지 케이스: 사용자가 중간에 입력을 취소"""
        mock_questionary["text"].return_value.ask.side_effect = ["John Doe", KeyboardInterrupt]
        form = {"name": "이름:", "email": "이메일:", "age": "나이:"}
        result = ui.get_form_input(form)
        assert result == {} # 취소 시 빈 딕셔너리 반환

    # 7. ask_for_validated_input
    def test_ask_for_validated_input_success(self, mock_questionary):
        """성공 케이스: 유효한 이메일 입력"""
        rule = {"regex": r".+@.+\..+", "message": "Invalid email"}
        mock_questionary["text"].return_value.ask.return_value = "test@example.com"
        result = ui.ask_for_validated_input("이메일 입력", rule)
        assert result == "test@example.com"

    # 8. select_file_from_directory
    def test_select_file_from_directory_success(self, mock_questionary, tmp_path):
        """성공 케이스: 디렉토리 내 파일 선택"""
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.log").touch()
        (tmp_path / "subdir").mkdir()
        
        mock_questionary["select"].return_value.ask.return_value = "b.log"
        result = ui.select_file_from_directory("파일 선택", str(tmp_path))
        assert result == str(tmp_path / "b.log")
        
        # 호출된 `choices` 인자가 파일만 포함하는지 확인
        call_args = mock_questionary["select"].call_args[1]
        assert "choices" in call_args
        assert sorted(call_args["choices"]) == ["[ 취소 ]", "a.txt", "b.log"]

    def test_select_file_from_directory_no_files(self, mock_questionary, tmp_path):
        """엣지 케이스: 디렉토리에 파일이 없을 때 None 반환"""
        (tmp_path / "subdir").mkdir()
        result = ui.select_file_from_directory("파일 선택", str(tmp_path))
        assert result is None
        mock_questionary["select"].assert_not_called()

    def test_select_file_from_directory_not_found(self):
        """실패 케이스: 존재하지 않는 디렉토리 경로"""
        with pytest.raises(FileNotFoundError):
            ui.select_file_from_directory("파일 선택", "./non_existent_dir_12345")

    # 9. show_diff
    def test_show_diff_captures_output(self, capsys):
        """성공 케이스: diff 출력이 정상적으로 생성되는지 확인"""
        text1 = "hello\nworld"
        text2 = "hello\npython"
        ui.show_diff(text1, text2)
        captured = capsys.readouterr()
        assert "-world" in captured.out
        assert "+python" in captured.out
        assert "--- 원본" in captured.out
        assert "+++ 수정본" in captured.out

    # 10. prompt_with_autocomplete
    def test_prompt_with_autocomplete_success(self, mock_questionary):
        """성공 케이스: 자동 완성 목록에서 선택"""
        choices = ["Seoul", "New York", "London"]
        mock_questionary["autocomplete"].return_value.ask.return_value = "Seoul"
        result = ui.prompt_with_autocomplete("도시 선택", choices)
        assert result == "Seoul"
        mock_questionary["autocomplete"].assert_called_once()
