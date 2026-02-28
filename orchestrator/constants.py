#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/constants.py
"""프로젝트 전역 상수 정의.

이 파일에 정의된 상수들은 여러 모듈에서 공유됩니다.
값 변경 시 이 파일만 수정하면 됩니다.
"""

from datetime import datetime, timezone
from typing import Final

# LLM에 전달하는 대화 이력 최대 문자 수 (gemini/claude/ollama 공통)
HISTORY_MAX_CHARS: Final[int] = 6000

# 단일 대화의 최대 이력 항목 수 (이를 초과하면 오래된 항목 제거)
MAX_HISTORY_ENTRIES: Final[int] = 200

# 단일 세션에서 기록 가능한 최대 도구 호출 함수 이름 수
MAX_FUNC_NAMES_PER_SESSION: Final[int] = 1000

# 도구 실행 결과 최대 문자 수 (초과 시 잘림 처리)
MAX_TOOL_RESULT_LENGTH: Final[int] = 1000

# 요구사항 파일 최대 크기 (1 MB)
MAX_REQUIREMENT_FILE_SIZE: Final[int] = 1 * 1024 * 1024

# API 서버 기본 바인딩 주소/포트
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8000


def utcnow() -> str:
    """현재 UTC 시각을 'YYYY-MM-DDTHH:MM:SS' 형식 문자열로 반환합니다.

    issue_tracker.py 등 전 모듈에서 일관된 UTC 타임스탬프를 사용하기 위한
    중앙 헬퍼 함수입니다. naive datetime(timezone 없음) 대신 UTC 기준을 사용합니다.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def utcnow_timestamp() -> float:
    """현재 UTC 시각을 Unix timestamp(float)로 반환합니다."""
    return datetime.now(timezone.utc).timestamp()
