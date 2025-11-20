#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# shared/prompt_manager.py

import os
from pathlib import Path
from typing import Dict, Optional

class PromptManager:
    """
    시스템 프롬프트를 파일 시스템에서 로드하고 관리하는 싱글톤/유틸리티 클래스.
    CLI, Orchestrator, MCP 어디서든 사용 가능합니다.
    """
    def __init__(self, prompts_dir: str = "system_prompts"):
        # 프로젝트 루트 기준으로 경로 설정
        self.base_dir = Path(os.getcwd()) / prompts_dir
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self._create_defaults()

    def _create_defaults(self):
        """기본 프롬프트 파일 생성"""
        defaults = {
            "default.txt": "당신은 유능한 AI 어시스턴트입니다.",
            "planner.txt": "당신은 복잡한 작업을 단계별로 계획하는 마스터 플래너입니다.",
            "developer.txt": "당신은 Python 코드를 작성하는 AI 개발자입니다.",
            "summarizer.txt": "다음 텍스트를 간결하게 요약해주세요."
        }
        for filename, content in defaults.items():
            (self.base_dir / filename).write_text(content, encoding="utf-8")

    def load(self, name: str, **kwargs) -> str:
        """
        프롬프트 파일을 읽어옵니다. **kwargs가 있으면 {key} 포맷팅을 수행합니다.
        
        Args:
            name (str): 파일명 (확장자 포함 또는 제외, 예: 'planner' or 'planner.txt')
            **kwargs: 프롬프트 내의 플레이스홀더를 채울 변수들.
            
        Returns:
            str: 로드된 (그리고 포맷팅된) 프롬프트 문자열.
        """
        if not name.endswith(".txt"):
            name += ".txt"
            
        file_path = self.base_dir / name
        
        if not file_path.exists():
            # 파일이 없으면 단순히 이름이나 빈 문자열 반환보다는 경고성 텍스트 반환
            return f"[System Warning: Prompt file '{name}' not found]"
            
        try:
            content = file_path.read_text(encoding="utf-8")
            if kwargs:
                try:
                    return content.format(**kwargs)
                except KeyError as e:
                    return f"{content}\n\n[System Warning: Missing format key {e}]"
            return content
        except Exception as e:
            return f"[System Error: Failed to load prompt '{name}': {e}]"

# 전역 인스턴스 (필요시 사용)
prompt_manager = PromptManager()
