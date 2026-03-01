#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/token_tracker.py
"""요청별 LLM 토큰 사용량 추적.

ContextVar 기반으로 async 요청 단위로 격리됩니다.
각 LLM 클라이언트가 record()를 호출하고, api.py가 get_accumulated()로 수집합니다.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# ── 모델별 가격표 (USD / 1M 토큰) ─────────────────────────────────────────────
# (input_per_1M, output_per_1M)
_PRICING: Dict[str, Tuple[float, float]] = {
    # Gemini
    "gemini-2.0-flash":                   (0.10,   0.40),
    "gemini-2.0-flash-001":               (0.10,   0.40),
    "gemini-2.0-flash-lite":              (0.075,  0.30),
    "gemini-2.0-flash-lite-001":          (0.075,  0.30),
    "gemini-1.5-flash":                   (0.075,  0.30),
    "gemini-1.5-pro":                     (1.25,   5.00),
    "gemini-2.5-pro":                     (1.25,  10.00),
    "gemini-2.5-flash":                   (0.15,   0.60),
    "gemini-3.1-pro-preview":             (1.25,  10.00),
    # models/ prefix variants
    "models/gemini-2.0-flash":            (0.10,   0.40),
    "models/gemini-2.0-flash-001":        (0.10,   0.40),
    "models/gemini-2.0-flash-lite":       (0.075,  0.30),
    "models/gemini-2.0-flash-lite-001":   (0.075,  0.30),
    "models/gemini-1.5-flash":            (0.075,  0.30),
    "models/gemini-1.5-pro":              (1.25,   5.00),
    "models/gemini-2.5-pro":              (1.25,  10.00),
    "models/gemini-2.5-flash":            (0.15,   0.60),
    "models/gemini-3.1-pro-preview":      (1.25,  10.00),
    # Claude
    "claude-opus-4-6":                    (15.0,  75.0),
    "claude-sonnet-4-6":                  (3.0,   15.0),
    "claude-haiku-4-5-20251001":          (0.80,   4.0),
    "claude-haiku-4-5":                   (0.80,   4.0),
    "claude-3-5-haiku-20241022":          (0.80,   4.0),
    # Ollama: 로컬/무료 — 항목 없으면 cost 0
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """모델명 + 토큰 수로 USD 비용을 계산합니다. 미등록 모델은 0.0 반환."""
    pricing = _PRICING.get(model)
    if not pricing:
        # 부분 매칭 (prefix 포함 모델명 등 대응)
        ml = model.lower()
        for key, price in _PRICING.items():
            kl = key.lower()
            if kl in ml or ml in kl:
                pricing = price
                break
    if not pricing:
        return 0.0
    in_price, out_price = pricing
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


# ── ContextVar 기반 요청별 추적 ────────────────────────────────────────────────

@dataclass
class _Entry:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    rate_limit_limit: Optional[int] = None
    rate_limit_remaining: Optional[int] = None


_collector: ContextVar[Optional[list]] = ContextVar("_token_collector", default=None)


def begin_tracking() -> None:
    """현재 async 컨텍스트에서 토큰 추적을 시작합니다 (요청 핸들러 진입 시 호출)."""
    _collector.set([])


def record(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    rate_limit_limit: Optional[int] = None,
    rate_limit_remaining: Optional[int] = None,
) -> None:
    """토큰 사용 1건을 현재 컨텍스트에 기록합니다. begin_tracking() 이후에만 동작합니다."""
    bucket = _collector.get()
    if bucket is None:
        return
    cost = calculate_cost(model, input_tokens, output_tokens)
    bucket.append(_Entry(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        rate_limit_limit=rate_limit_limit,
        rate_limit_remaining=rate_limit_remaining,
    ))


def get_accumulated() -> Optional[dict]:
    """수집된 토큰 사용량을 집계하여 dict로 반환합니다. 기록이 없으면 None."""
    bucket = _collector.get()
    if not bucket:
        return None
    total_in = sum(e.input_tokens for e in bucket)
    total_out = sum(e.output_tokens for e in bucket)
    total_cost = sum(e.cost_usd for e in bucket)
    last = bucket[-1]
    first = bucket[0]
    return {
        "provider": first.provider,
        "model": first.model,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": round(total_cost, 8),
        "rate_limit_limit": last.rate_limit_limit,
        "rate_limit_remaining": last.rate_limit_remaining,
        "call_count": len(bucket),
    }
