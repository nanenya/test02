#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/llm_router.py
"""Phase 4 — 파이프라인 단계별 LLM 티어 자동 라우팅.

각 파이프라인 단계의 복잡도를 분석해 high/standard/local 티어를 자동 결정합니다.

티어 정의:
  high     : cloud LLM (claude-opus / gemini-2.5-pro 등) — 창의적 판단, 코드 생성
  standard : cloud LLM (claude-sonnet / gemini-flash 등) — 구조적 출력, 분류
  local    : Ollama 로컬 모델 — 단순 분류, 키워드 추출, 간단한 변환

라우팅 규칙:
  PIPELINE_STAGE → 기본 티어 (complexity override 허용)

피드백 루프:
  token_tracker에서 누적 비용을 읽어 예산 초과 시 자동으로 낮은 티어로 강등.
  budget_usd=None이면 비용 제한 없음.
"""

import logging
from typing import Literal, Optional

from .token_tracker import get_accumulated

logger = logging.getLogger(__name__)

ModelPreference = Literal["auto", "standard", "high"]

# ── 단계별 기본 티어 정의 ──────────────────────────────────────────────────────
_STAGE_DEFAULT_TIER: dict = {
    # [설계] 창의적 판단 → high
    "design_generation":         "high",
    # [태스크 분해] 구조적 출력 → standard
    "task_decomposition":        "standard",
    # [계획 매핑] 도구 목록 기반 매핑 → standard (캐시 히트 시 호출 자체 없음)
    "plan_mapping":              "standard",
    # [실행 그룹 빌드] 단일 단계 집중 → standard
    "exec_group_build":          "standard",
    # [템플릿 인자 적응] 값 교체만 → standard (간단하면 local 가능)
    "template_adaptation":       "standard",
    # [의도 분류] 단순 분류 → standard (local Ollama 우선)
    "intent_classification":     "standard",
    # [Python 도구 생성] 코드 품질 중요 → high
    "tool_implementation":       "high",
    # [최종 답변] 복잡도에 따라 다름
    "final_answer_simple":       "standard",
    "final_answer_complex":      "standard",
    # [키워드 추출] 단순 → standard
    "keyword_extraction":        "standard",
    # [제목 생성] 단순 → standard
    "title_generation":          "standard",
    # [요약] 압축 → standard
    "history_summarization":     "standard",
}

# 복잡도 → 티어 오버라이드 맵
_COMPLEXITY_TIER: dict = {
    "simple":  "standard",
    "medium":  "standard",
    "complex": "high",
}

# 비용 예산 임계값 — 초과 시 티어 강등
_BUDGET_DOWNGRADE_TIERS: list = [
    # (예산 USD, 강등 후 최대 티어)
    (0.10, "standard"),   # 10센트 초과 → high 금지
    (0.50, "standard"),   # 50센트 초과 → standard 유지 (local은 미도입)
]


def get_tier(
    stage: str,
    complexity: str = "medium",
    budget_usd: Optional[float] = None,
    force: Optional[str] = None,
) -> str:
    """파이프라인 단계와 복잡도를 기반으로 LLM 티어를 결정합니다.

    Args:
        stage:      파이프라인 단계 식별자 (_STAGE_DEFAULT_TIER 키)
        complexity: 설계에서 분류된 복잡도 (simple/medium/complex)
        budget_usd: 현재까지 누적 비용 USD (None=제한 없음)
        force:      강제 티어 (None=자동)

    Returns:
        "high" | "standard" — 현재 model_preference 호환 문자열
    """
    if force in ("high", "standard", "auto"):
        return force

    # 단계별 기본 티어
    base = _STAGE_DEFAULT_TIER.get(stage, "standard")

    # 복잡도 오버라이드 (기본 티어가 standard이고 complex이면 high로 상향)
    if base == "standard" and complexity == "complex":
        base = _COMPLEXITY_TIER.get(complexity, base)

    # 비용 예산 초과 시 티어 강등
    if budget_usd is not None:
        for threshold, max_tier in _BUDGET_DOWNGRADE_TIERS:
            if budget_usd >= threshold and base == "high":
                logger.info(
                    f"[LLMRouter] 예산 초과 강등: {base} → {max_tier} "
                    f"(누적=${budget_usd:.4f}, 임계=${threshold})"
                )
                base = max_tier
                break

    logger.debug(f"[LLMRouter] stage={stage} complexity={complexity} → tier={base}")
    return base


def get_current_budget() -> float:
    """현재 요청의 누적 비용 USD를 반환합니다 (token_tracker 연동)."""
    usage = get_accumulated()
    return usage.get("cost_usd", 0.0) if usage else 0.0


def route(
    stage: str,
    complexity: str = "medium",
    force: Optional[str] = None,
) -> str:
    """token_tracker 비용을 자동으로 반영한 LLM 티어를 반환합니다.

    파이프라인 매니저에서 model_preference 인자 대신 이 함수를 호출합니다.
    """
    budget = get_current_budget()
    return get_tier(stage=stage, complexity=complexity, budget_usd=budget, force=force)


# ── 복잡도 추론 헬퍼 ──────────────────────────────────────────────────────────

def infer_complexity_from_design(design: dict) -> str:
    """설계 dict에서 complexity 필드를 추출합니다. 없으면 'medium'."""
    return design.get("complexity", "medium")


def infer_complexity_from_query(query: str) -> str:
    """쿼리 길이·키워드 기반으로 복잡도를 추정합니다 (빠른 휴리스틱).

    - 단어 수 >= 20 또는 복잡 키워드 포함 → complex
    - 단어 수 <= 5 → simple
    - 나머지 → medium
    """
    words = query.split()
    complex_keywords = {
        "통합", "마이그레이션", "리팩토링", "아키텍처", "설계",
        "migrate", "refactor", "architecture", "integration", "pipeline",
        "분석", "자동화", "최적화", "구현",
    }
    if len(words) >= 20 or any(k in query for k in complex_keywords):
        return "complex"
    if len(words) <= 5:
        return "simple"
    return "medium"
