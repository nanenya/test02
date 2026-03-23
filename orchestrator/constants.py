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


# 카테고리 → model_preference 매핑 [D]
CATEGORY_MODEL_MAP: dict = {
    "quick":      "standard",
    "deep":       "high",
    "ultrabrain": "high",
    "visual":     "auto",
    "code":       "high",
    "analysis":   "high",
    "creative":   "auto",
}

# 계획 검증 점수 임계값 [E]
PLAN_VALIDATION_MIN_SCORE: float = 0.6

# 누적 지식 최대 항목 수 (대화당) [B]
WISDOM_MAX_ENTRIES: int = 50

# decide_and_act history 슬라이스 크기
RECENT_HISTORY_ITEMS: Final[int] = 6

# LLM 프롬프트에 전달하는 도구 목록 최대 개수
MAX_TOOLS_IN_PROMPT: Final[int] = 30

# summarize_history 히스토리 발췌 최대 문자
HISTORY_EXCERPT_MAX_CHARS: Final[int] = 8000

# API 서버 자동 히스토리 요약 임계값
HISTORY_AUTO_SUMMARIZE_THRESHOLD: int = 40   # 이 이상이면 자동 요약
HISTORY_KEEP_RECENT: int = 10                # 요약 후 최신 N개 보존
HISTORY_SUMMARY_MARKER: str = "[이전 대화 요약]"  # 중복 요약 방지 마커

# extract_wisdom 결과 슬라이스 크기
RESULT_HISTORY_ITEMS: Final[int] = 20

# api.py 매직 문자열
USER_REQUEST_PREFIX: Final[str] = "사용자 요청:"
TOOL_RESULT_TRUNCATED_SUFFIX: Final[str] = "... (결과가 너무 길어 잘림)"

# llm_client.py 매직 숫자
_DAY_SECONDS: Final[int] = 24 * 3600
_GEMINI_RATE_LIMIT_SECONDS: Final[int] = 60


def truncate_history(history: list, max_chars: int = HISTORY_MAX_CHARS) -> str:
    """최근 대화 우선 보존하는 캐릭터 예산 기반 히스토리 truncation.

    gemini_client / claude_client / ollama_client 공유용.
    뒤(최신)부터 역순으로 항목을 추가하되, max_chars를 초과하면 중단합니다.
    """
    if not history:
        return ""
    # 비문자열 항목은 str()로 변환 (None, dict 등 방어)
    history = [item if isinstance(item, str) else str(item) for item in history]
    selected = []
    total = 0
    for item in reversed(history):
        item_len = len(item)
        if total + item_len > max_chars and selected:
            break
        selected.append(item)
        total += item_len
    selected.reverse()
    if len(selected) < len(history):
        return "... (이전 기록 생략) ...\n" + "\n".join(selected)
    return "\n".join(selected)
