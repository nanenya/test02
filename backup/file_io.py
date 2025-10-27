#!/usr/bin/env python3

from typing import List

def save_file(content: str, filename: str) -> str:
    """
    주어진 내용을 지정된 파일 이름으로 저장합니다. 파일이 이미 존재하면 덮어씁니다.

    Args:
        content (str): 파일에 저장할 텍스트 내용.
        filename (str): 저장할 파일의 이름 (경로 포함 가능).

    Returns:
        str: 파일 저장 성공 메시지.
    """
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"'{filename}' 파일에 성공적으로 저장되었습니다."

def read_file(filename: str) -> str:
    """
    지정된 파일을 읽어 그 내용을 반환합니다.

    Args:
        filename (str): 읽을 파일의 이름.

    Returns:
        str: 파일의 전체 내용.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

def list_files(directory: str = '.') -> List[str]:
    """
    지정된 디렉토리의 파일 및 폴더 목록을 반환합니다.

    Args:
        directory (str): 목록을 조회할 디렉토리 경로. 기본값은 현재 디렉토리입니다.

    Returns:
        List[str]: 해당 디렉토리의 파일 및 폴더 이름 리스트.
    """
    import os
    return os.listdir(directory)
