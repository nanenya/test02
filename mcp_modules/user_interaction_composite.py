#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용자 상호작용(User Interaction)을 위한 복합 MCP(Mission Control Primitives) 모음.

이 모듈은 AI 에이전트가 터미널 환경에서 사용자와 효과적으로 상호작용할 수 있도록
돕는 고수준 함수들을 제공합니다. 선택지 제공, 경로 입력, 중요 작업 확인 등
다양한 시나리오를 처리합니다.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import difflib
import questionary
from questionary import ValidationError, Validator

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Validator Classes for questionary ---

class PathValidator(Validator):
    """파일 또는 디렉토리 경로의 유효성을 검증하는 Validator 클래스."""
    def __init__(self, is_file: bool, must_exist: bool):
        self._is_file = is_file
        self._must_exist = must_exist
        self._type = "파일" if is_file else "디렉토리"

    def validate(self, document):
        path_str = document.text.strip()
        if not path_str and not self._must_exist:
            return # 경로가 비어있어도 되고, 존재하지 않아도 되면 통과
        
        path = Path(path_str).expanduser()
        
        if self._must_exist and not path.exists():
            raise ValidationError(
                message=f"경로가 존재하지 않습니다: {path}",
                cursor_position=len(document.text))
        
        if self._is_file and path.exists() and not path.is_file():
            raise ValidationError(
                message=f"경로는 {self._type}이어야 합니다.",
                cursor_position=len(document.text))
            
        if not self._is_file and path.exists() and not path.is_dir():
             raise ValidationError(
                message=f"경로는 {self._type}이어야 합니다.",
                cursor_position=len(document.text))

# --- MCP Functions ---

def present_options_and_get_choice(prompt: str, options: List[str]) -> Optional[str]:
    """
    사용자에게 번호가 매겨진 선택지 목록을 보여주고, 하나를 선택하게 합니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문 메시지.
        options (List[str]): 사용자에게 제공할 선택지 문자열 리스트.

    Returns:
        Optional[str]: 사용자가 선택한 항목의 문자열. 사용자가 선택을 취소(Ctrl+C)하면 None을 반환합니다.
    
    Raises:
        ValueError: 선택지(options) 리스트가 비어 있을 경우 발생합니다.

    Example:
        >>> selected_framework = present_options_and_get_choice(
        ...     "어떤 웹 프레임워크를 사용하시겠습니까?",
        ...     ["Django", "FastAPI", "Flask"]
        ... )
        >>> print(f"선택: {selected_framework}")
    """
    if not options:
        logger.error("선택지 목록(options)이 비어 있습니다.")
        raise ValueError("선택지 목록은 비어 있을 수 없습니다.")
    
    logger.info(f"사용자에게 선택지 제시: {prompt}")
    try:
        choice = questionary.select(prompt, choices=options).ask()
        logger.info(f"사용자 선택: {choice}")
        return choice
    except KeyboardInterrupt:
        logger.warning("사용자가 선택을 취소했습니다.")
        return None

def present_checkbox_and_get_choices(prompt: str, options: List[str]) -> List[str]:
    """
    여러 선택지를 체크박스 형태로 보여주고, 사용자가 다중 선택한 항목들의 리스트를 반환합니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문 메시지.
        options (List[str]): 사용자에게 제공할 선택지 문자열 리스트.

    Returns:
        List[str]: 사용자가 선택한 모든 항목의 문자열 리스트. 아무것도 선택하지 않거나 취소하면 빈 리스트를 반환합니다.

    Example:
        >>> selected_libs = present_checkbox_and_get_choices(
        ...     "설치할 라이브러리를 모두 선택하세요:",
        ...     ["pandas", "numpy", "matplotlib"]
        ... )
        >>> print(f"선택된 라이브러리: {selected_libs}")
    """
    if not options:
        logger.warning("선택지 목록(options)이 비어 있어 빈 리스트를 반환합니다.")
        return []

    logger.info(f"사용자에게 체크박스 선택지 제시: {prompt}")
    try:
        choices = questionary.checkbox(prompt, choices=options).ask()
        # 사용자가 Ctrl+C로 취소하면 ask()는 None을 반환하므로 빈 리스트로 통일
        result = choices or []
        logger.info(f"사용자 선택: {result}")
        return result
    except KeyboardInterrupt:
        logger.warning("사용자가 선택을 취소했습니다.")
        return []

def ask_for_file_path(prompt: str, default_path: str = "", must_exist: bool = True) -> Optional[str]:
    """
    사용자에게 파일 경로를 입력하도록 요청하고, 경로의 유효성을 검증합니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문 메시지.
        default_path (str, optional): 기본으로 보여줄 경로. Defaults to "".
        must_exist (bool, optional): 파일이 반드시 존재해야 하는지 여부. Defaults to True.

    Returns:
        Optional[str]: 사용자가 입력한 유효한 파일의 전체 경로 문자열. 취소 시 None.
    
    Example:
        >>> config_path = ask_for_file_path("설정 파일의 경로를 입력하세요:", default_path="./config.json")
    """
    logger.info(f"사용자에게 파일 경로 입력 요청: {prompt}")
    try:
        path = questionary.path(
            prompt,
            default=default_path,
            validate=PathValidator(is_file=True, must_exist=must_exist)
        ).ask()
        
        if path:
            full_path = str(Path(path).expanduser().resolve())
            logger.info(f"사용자 입력 경로: {full_path}")
            return full_path
        else:
            logger.warning("사용자가 경로 입력을 취소했습니다.")
            return None
            
    except KeyboardInterrupt:
        logger.warning("사용자가 경로 입력을 취소했습니다.")
        return None

def ask_for_directory_path(prompt: str, default_path: str = "", must_exist: bool = True) -> Optional[str]:
    """
    사용자에게 디렉토리 경로를 입력하도록 요청하고, 경로의 유효성을 검증합니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문 메시지.
        default_path (str, optional): 기본으로 보여줄 경로. Defaults to "".
        must_exist (bool, optional): 디렉토리가 반드시 존재해야 하는지 여부. Defaults to True.

    Returns:
        Optional[str]: 사용자가 입력한 유효한 디렉토리의 전체 경로 문자열. 취소 시 None.
        
    Example:
        >>> project_dir = ask_for_directory_path("프로젝트 디렉토리 경로를 입력하세요:", default_path="~/projects/")
    """
    logger.info(f"사용자에게 디렉토리 경로 입력 요청: {prompt}")
    try:
        path = questionary.path(
            prompt,
            default=default_path,
            validate=PathValidator(is_file=False, must_exist=must_exist),
            only_directories=True
        ).ask()

        if path:
            full_path = str(Path(path).expanduser().resolve())
            logger.info(f"사용자 입력 경로: {full_path}")
            return full_path
        else:
            logger.warning("사용자가 경로 입력을 취소했습니다.")
            return None

    except KeyboardInterrupt:
        logger.warning("사용자가 경로 입력을 취소했습니다.")
        return None

def confirm_critical_action(action_description: str, details_to_show: Optional[str] = None) -> bool:
    """
    중요한 작업을 실행하기 전, 상세 내용을 보여주고 사용자에게 재확인받습니다.

    Args:
        action_description (str): 수행할 작업에 대한 간결한 설명. (예: "총 5개의 파일을 영구적으로 삭제합니다.")
        details_to_show (Optional[str], optional): 사용자에게 보여줄 추가적인 상세 정보. (예: 삭제될 파일 목록). Defaults to None.

    Returns:
        bool: 사용자가 'Yes'를 선택하면 True, 'No'를 선택하거나 취소하면 False.

    Example:
        >>> files_to_delete = ["a.txt", "b.txt"]
        >>> if confirm_critical_action(
        ...     f"총 {len(files_to_delete)}개의 파일을 삭제합니다.",
        ...     details_to_show="\\n".join(files_to_delete)
        ... ):
        ...     print("삭제 작업 실행")
        ... else:
        ...     print("삭제 작업 취소")
    """
    logger.warning(f"중요 작업 확인 요청: {action_description}")
    
    if details_to_show:
        print("\n--- 작업 상세 내용 ---")
        print(details_to_show)
        print("---------------------\n")
    
    try:
        # questionary는 기본적으로 안전을 위해 'No'를 기본값으로 하도록 'default=False'를 권장
        confirmed = questionary.confirm(f"{action_description} 계속하시겠습니까?", default=False).ask()
        result = confirmed or False
        if result:
            logger.info("사용자가 중요 작업을 승인했습니다.")
        else:
            logger.warning("사용자가 중요 작업을 거부했습니다.")
        return result
    except KeyboardInterrupt:
        logger.warning("사용자가 중요 작업 확인을 취소했습니다.")
        return False

def get_form_input(form_fields: Dict[str, str]) -> Dict[str, Any]:
    """
    정의된 여러 필드에 대해 순차적으로 질문하여, 폼(Form)처럼 사용자 입력을 받습니다.

    Args:
        form_fields (Dict[str, str]): 딕셔너리. key는 결과 딕셔너리의 키가 되고, value는 사용자에게 보여줄 질문이 됩니다.

    Returns:
        Dict[str, Any]: 사용자가 각 필드에 대해 입력한 값을 담은 딕셔너리.

    Example:
        >>> user_info = get_form_input({
        ...     "name": "이름을 입력하세요:",
        ...     "email": "이메일을 입력하세요:",
        ...     "age": "나이를 입력하세요:"
        ... })
        >>> print(user_info)
    """
    logger.info("폼 입력 시작.")
    results = {}
    try:
        for key, question in form_fields.items():
            answer = questionary.text(question).ask()
            if answer is None: # 사용자가 Ctrl+C 로 중단한 경우
                raise KeyboardInterrupt
            results[key] = answer
            logger.debug(f"폼 필드 '{key}' 입력 완료: {answer}")
        
        logger.info("폼 입력 완료.")
        return results
    except KeyboardInterrupt:
        logger.warning("사용자가 폼 입력을 중단했습니다.")
        return {} # 중단 시 빈 딕셔너리 반환

def ask_for_validated_input(question: str, validation_rule: Dict[str, str]) -> Optional[str]:
    """
    정규식을 기반으로 입력값의 유효성을 검증하며 사용자 입력을 받습니다.

    Args:
        question (str): 사용자에게 보여줄 질문.
        validation_rule (Dict[str, str]): 검증 규칙.
            - "regex" (str): 입력값을 검증할 정규식 패턴.
            - "message" (str): 검증 실패 시 보여줄 오류 메시지.

    Returns:
        Optional[str]: 유효성 검증을 통과한 사용자 입력 문자열. 취소 시 None.

    Raises:
        KeyError: validation_rule 딕셔너리에 'regex'나 'message' 키가 없을 경우.

    Example:
        >>> email_rule = {"regex": r"^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$", "message": "유효한 이메일 주소를 입력해주세요."}
        >>> user_email = ask_for_validated_input("이메일 주소를 입력하세요:", email_rule)
    """
    logger.info(f"유효성 검증이 필요한 입력 요청: {question}")
    
    class RegexValidator(Validator):
        def validate(self, document):
            if not re.match(validation_rule["regex"], document.text):
                raise ValidationError(
                    message=validation_rule["message"],
                    cursor_position=len(document.text))

    try:
        answer = questionary.text(question, validate=RegexValidator).ask()
        if answer:
            logger.info("유효성 검증 통과.")
        else:
            logger.warning("사용자가 입력을 취소했습니다.")
        return answer
    except KeyboardInterrupt:
        logger.warning("사용자가 입력을 취소했습니다.")
        return None

def select_file_from_directory(prompt: str, directory_path: str) -> Optional[str]:
    """
    특정 디렉토리의 파일 목록을 보여주고, 사용자가 그중 하나를 선택하게 합니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문 메시지.
        directory_path (str): 파일을 검색할 디렉토리 경로.

    Returns:
        Optional[str]: 사용자가 선택한 파일의 전체 경로. 디렉토리가 없거나 파일이 없거나, 선택 취소 시 None.
        
    Raises:
        NotADirectoryError: 주어진 directory_path가 디렉토리가 아닐 경우 발생.
        FileNotFoundError: 주어진 directory_path가 존재하지 않을 경우 발생.

    Example:
        >>> selected_file = select_file_from_directory("설정 파일을 선택하세요:", "./configs")
    """
    logger.info(f"'{directory_path}' 디렉토리에서 파일 선택 요청.")
    
    path = Path(directory_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {directory_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"주어진 경로는 디렉토리가 아닙니다: {directory_path}")
        
    try:
        files = sorted([f.name for f in path.iterdir() if f.is_file()])
        
        if not files:
            logger.warning(f"'{directory_path}' 디렉토리에 파일이 없습니다.")
            return None
        
        # 파일 목록과 함께 '취소' 옵션 추가
        files_with_cancel = files + ["[ 취소 ]"]
        
        selected_file = present_options_and_get_choice(prompt, files_with_cancel)
        
        if selected_file and selected_file != "[ 취소 ]":
            full_path = str(path / selected_file)
            logger.info(f"사용자가 '{full_path}' 파일을 선택했습니다.")
            return full_path
        else:
            logger.info("사용자가 파일 선택을 취소했거나 선택하지 않았습니다.")
            return None
            
    except Exception as e:
        logger.error(f"파일 선택 중 오류 발생: {e}")
        return None

def show_diff(text1: str, text2: str, fromfile: str = '원본', tofile: str = '수정본'):
    """
    두 텍스트를 비교하여 차이점(diff)을 터미널에 시각적으로 강조하여 보여줍니다.

    Args:
        text1 (str): 비교할 첫 번째 텍스트 (원본).
        text2 (str): 비교할 두 번째 텍스트 (수정본).
        fromfile (str, optional): 원본 파일명으로 표시될 이름. Defaults to '원본'.
        tofile (str, optional): 수정본 파일명으로 표시될 이름. Defaults to '수정본'.

    Returns:
        None: 결과를 직접 print() 함수로 출력합니다.

    Example:
        >>> original_code = "def hello():\\n    print('Hello World')"
        >>> modified_code = "def hello_user(name):\\n    print(f'Hello {name}')"
        >>> show_diff(original_code, modified_code)
    """
    logger.info("두 텍스트의 차이점(diff)을 출력합니다.")
    diff = difflib.unified_diff(
        text1.splitlines(keepends=True),
        text2.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
    )
    print("--- 텍스트 비교 결과 ---")
    for line in diff:
        print(line, end="")
    print("------------------------")


def prompt_with_autocomplete(prompt: str, choices: List[str]) -> Optional[str]:
    """
    사용자 입력을 시작하면, 제공된 선택지 목록을 기반으로 자동 완성 제안을 보여줍니다.

    Args:
        prompt (str): 사용자에게 보여줄 질문.
        choices (List[str]): 자동 완성 제안에 사용할 문자열 리스트.

    Returns:
        Optional[str]: 사용자가 선택하거나 입력한 최종 문자열. 취소 시 None.

    Example:
        >>> city_list = ["Seoul", "New York", "London", "Paris", "Tokyo"]
        >>> selected_city = prompt_with_autocomplete("도시를 선택하세요:", city_list)
    """
    if not choices:
        logger.warning("자동 완성 목록(choices)이 비어 있어 일반 텍스트 입력을 사용합니다.")
        return questionary.text(prompt).ask()

    logger.info(f"자동 완성 프롬프트 제시: {prompt}")
    try:
        result = questionary.autocomplete(
            prompt,
            choices=choices
        ).ask()
        logger.info(f"사용자 선택/입력: {result}")
        return result
    except KeyboardInterrupt:
        logger.warning("사용자가 입력을 취소했습니다.")
        return None
