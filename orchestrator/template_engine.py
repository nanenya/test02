#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/template_engine.py
"""Phase 2 — 실행 템플릿 엔진.

기능:
  1. 향상된 유사도 스코어링 (키워드 겹침 + 도구명 매칭 + 성공률 가중치)
  2. LLM(local/standard) 기반 템플릿 인자 적응 — 구조 재사용, 값만 교체
  3. 실패율 초과 템플릿 자동 비활성화 (auto_disable_failing_templates 위임)

템플릿 재사용 판단 임계값:
  SCORE_THRESHOLD = 4  (키워드 기준 최소 스코어)
  성공률 보너스:  success_rate * 3.0
  도구명 일치 보너스: 일치 도구당 +1.5
  최근성 패널티: 30일마다 -0.5 (최대 -3.0)
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import pipeline_db

logger = logging.getLogger(__name__)

# ── 스코어링 파라미터 ──────────────────────────────────────────────────────────
_SCORE_THRESHOLD = 4.0          # 이 이상이어야 템플릿 채택
_TOOL_MATCH_BONUS = 1.5         # 도구명 정확 일치당 보너스
_SUCCESS_RATE_WEIGHT = 3.0      # 성공률 × 가중치
_RECENCY_PENALTY_PER_30D = 0.5  # 30일 경과당 패널티
_MAX_RECENCY_PENALTY = 3.0


def _score_template(
    template: Dict[str, Any],
    query_keywords: set,
    tool_hints: List[str],
    now_ts: float,
) -> float:
    """단일 템플릿의 유사도 스코어를 계산합니다.

    score = keyword_overlap
            + tool_match_bonus
            + success_rate_bonus
            - recency_penalty
    """
    raw_kw = template.get("keywords") or []
    kw_list = raw_kw if isinstance(raw_kw, list) else json.loads(raw_kw)
    t_keywords = set(k.lower() for k in kw_list)
    overlap = len(query_keywords & t_keywords)
    if overlap == 0:
        return 0.0

    # 도구명 일치 보너스
    t_tools = set()
    for task in template.get("execution_group", {}).get("tasks", []):
        t_tools.add(task.get("tool_name", "").lower())
    hint_set = set(h.lower() for h in tool_hints)
    tool_bonus = len(t_tools & hint_set) * _TOOL_MATCH_BONUS

    # 성공률 보너스
    success = template.get("success_count", 0)
    fail = template.get("fail_count", 0)
    total = success + fail
    success_bonus = (success / total * _SUCCESS_RATE_WEIGHT) if total > 0 else 0.0

    # 최근성 패널티
    last_used = template.get("last_used_at")
    penalty = 0.0
    if last_used:
        try:
            lu_ts = datetime.fromisoformat(last_used).replace(
                tzinfo=timezone.utc
            ).timestamp()
            days_elapsed = (now_ts - lu_ts) / 86400
            penalty = min(
                (days_elapsed / 30) * _RECENCY_PENALTY_PER_30D,
                _MAX_RECENCY_PENALTY,
            )
        except Exception:
            pass

    return overlap + tool_bonus + success_bonus - penalty


def find_best_template_scored(
    keywords: List[str],
    tool_hints: List[str],
    path=None,
) -> Optional[Dict[str, Any]]:
    """향상된 스코어링으로 가장 적합한 활성 템플릿을 반환합니다.

    SCORE_THRESHOLD 미만이면 None을 반환합니다.
    """
    if not keywords and not tool_hints:
        return None

    kw_set = set(k.lower() for k in keywords)
    now_ts = datetime.now(timezone.utc).timestamp()

    kwargs = {"path": path} if path else {}
    templates = pipeline_db.list_templates(active_only=True, limit=200, **kwargs)

    best_score = 0.0
    best = None

    for t in templates:
        # execution_group이 dict로 역직렬화된 상태여야 함
        full = pipeline_db.get_template(t["id"], **kwargs)
        if not full:
            continue
        score = _score_template(full, kw_set, tool_hints, now_ts)
        if score > best_score:
            best_score = score
            best = full

    if best_score < _SCORE_THRESHOLD:
        return None

    logger.info(
        f"[TemplateEngine] 템플릿 채택: id={best['id']} name={best['name']!r} "
        f"score={best_score:.2f}"
    )
    return best


# ── 인자 적응(Argument Adaptation) ───────────────────────────────────────────

async def adapt_template(
    template_group: Dict[str, Any],
    plan_step: Dict[str, Any],
    task: Dict[str, Any],
    design: Dict[str, Any],
    history: List[str],
    model_preference: str = "standard",
) -> Dict[str, Any]:
    """템플릿 ExecutionGroup을 현재 컨텍스트에 맞게 인자만 교체합니다.

    - tool_name은 절대 변경하지 않습니다.
    - LLM이 실패하면 원본 템플릿을 그대로 반환합니다 (안전 fallback).
    - 인자 적응은 standard 티어 이하로 처리합니다 (비용 최소화).
    """
    from .llm_client import adapt_template_arguments

    try:
        adapted = await adapt_template_arguments(
            template_group=template_group,
            plan_step=plan_step,
            task=task,
            design=design,
            history=history[-4:],        # 최근 4항목만 (토큰 절약)
            model_preference=model_preference,
        )
        # tool_name 변조 방지: 원본 도구명 강제 복원
        orig_tools = {t["tool_name"]: t for t in template_group.get("tasks", [])}
        for adapted_task in adapted.get("tasks", []):
            if adapted_task.get("tool_name") not in orig_tools:
                logger.warning(
                    f"[TemplateEngine] 도구명 변조 감지, 원복: "
                    f"{adapted_task.get('tool_name')} → 원본 목록과 불일치"
                )
                # 순서 기준으로 원본 도구명 복원
                orig_list = list(orig_tools.keys())
                idx = adapted.get("tasks", []).index(adapted_task)
                if idx < len(orig_list):
                    adapted_task["tool_name"] = orig_list[idx]
        return adapted
    except Exception as e:
        logger.warning(f"[TemplateEngine] 인자 적응 실패, 원본 사용: {e}")
        return template_group


# ── 통합 진입점 ───────────────────────────────────────────────────────────────

async def find_and_adapt(
    plan_step: Dict[str, Any],
    task: Dict[str, Any],
    design: Dict[str, Any],
    history: List[str],
    model_preference: str = "standard",
    path=None,
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """템플릿 검색 → 인자 적응 → (adapted_group, template_id) 반환.

    적합한 템플릿이 없으면 (None, None)을 반환합니다.
    """
    keywords = (
        plan_step.get("tool_hints", [])
        + plan_step.get("action", "").split()[:6]
        + task.get("title", "").split()[:4]
    )
    tool_hints = plan_step.get("tool_hints", [])

    template = find_best_template_scored(keywords, tool_hints, path=path)
    if not template:
        return None, None

    adapted = await adapt_template(
        template_group=template["execution_group"],
        plan_step=plan_step,
        task=task,
        design=design,
        history=history,
        model_preference=model_preference,
    )
    return adapted, template["id"]
