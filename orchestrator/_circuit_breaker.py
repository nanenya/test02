#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_circuit_breaker.py — Circuit Breaker + 프로바이더 폴백 체인

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from .constants import _DAY_SECONDS, _GEMINI_RATE_LIMIT_SECONDS

logger = logging.getLogger(__name__)

# {provider: {"until": float(unix_ts), "reason": str}}
_circuit_breaker: Dict[str, Dict] = {}

_VALID_PROVIDERS = {"gemini", "claude", "ollama", "openai", "grok"}


def _fmt_duration(seconds: float) -> str:
    """초를 사람이 읽기 쉬운 형식으로 변환."""
    if seconds < 120:
        return f"{int(seconds)}초"
    if seconds < 7200:
        return f"{int(seconds / 60)}분"
    return f"{int(seconds / 3600)}시간"


def _next_pt_midnight_seconds() -> float:
    """다음 PT 자정(UTC 변환) 까지 남은 초.

    Gemini 일일 quota 리셋 기준:
      - PST (11월~3월): UTC 08:00
      - PDT (3월~11월, DST): UTC 07:00
    현재 월로 간략 판정. 최소 5분 버퍼 포함.
    """
    now = datetime.now(timezone.utc)
    pt_offset = 7 if 3 <= now.month <= 10 else 8
    reset = now.replace(hour=pt_offset, minute=5, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    return max(300.0, (reset - now).total_seconds())


def _detect_circuit_trip(exc: Exception, provider: str) -> Optional[Tuple[float, str]]:
    """에러 분석 → (스킵 초, 사유) 반환. 해당 없으면 None."""
    try:
        import httpx
        body = exc.response.text.lower() if isinstance(exc, httpx.HTTPStatusError) else str(exc).lower()
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    except Exception:
        body = str(exc).lower()
        status = None

    if "credit balance is too low" in body:
        return (_DAY_SECONDS, "크레딧 소진 — Plans & Billing에서 충전 필요 (24시간 후 재시도)")

    if provider == "gemini" and (
        "resource_exhausted" in body or "resource has been exhausted" in body
    ):
        secs = _next_pt_midnight_seconds()
        eta = datetime.now(timezone.utc) + timedelta(seconds=secs)
        return (
            secs,
            f"일일 quota 초과 — UTC {eta.strftime('%H:%M')}에 자동 리셋 ({_fmt_duration(secs)} 후)",
        )

    if "insufficient_quota" in body or "exceeded your current quota" in body:
        return (
            _DAY_SECONDS,
            "billing quota 초과 — OpenAI 대시보드에서 한도 증액 필요 (24시간 후 재시도)",
        )

    if status == 429 or "rate limit" in body or "rate_limit_exceeded" in body:
        return _GEMINI_RATE_LIMIT_SECONDS, "분당 요청 한도 초과 (60초 후 재시도)"

    return None


def _trip(provider: str, duration: float, reason: str) -> None:
    """Circuit Breaker 차단 설정 및 로그."""
    _circuit_breaker[provider] = {"until": time.time() + duration, "reason": reason}
    logger.warning(
        f"[CircuitBreaker] ⛔ {provider} 차단 ({_fmt_duration(duration)}): {reason}"
    )


def _is_tripped(provider: str) -> Tuple[bool, str]:
    """(차단 여부, 사유+남은시간) 반환. 만료 항목 자동 제거."""
    entry = _circuit_breaker.get(provider)
    if not entry:
        return False, ""
    remaining = entry["until"] - time.time()
    if remaining <= 0:
        del _circuit_breaker[provider]
        return False, ""
    return True, f"{entry['reason']} (남은 시간: {_fmt_duration(remaining)})"


def get_provider_status() -> Dict[str, Dict]:
    """현재 프로바이더 Circuit Breaker 상태를 반환."""
    chain = _get_fallback_chain()
    result = {}
    for p in _VALID_PROVIDERS:
        tripped, reason = _is_tripped(p)
        result[p] = {
            "available": not tripped,
            "in_fallback_chain": p in chain,
            "reason": reason if tripped else "",
        }
    return result


def _get_client_module(provider: str):
    """프로바이더 이름으로 클라이언트 모듈을 반환."""
    if provider == "claude":
        from . import claude_client
        return claude_client
    if provider == "ollama":
        from . import ollama_client
        return ollama_client
    if provider == "openai":
        from . import openai_client
        return openai_client
    if provider == "grok":
        from . import grok_client
        return grok_client
    from . import gemini_client
    return gemini_client


def _get_active_client_module():
    """현재 활성 프로바이더에 맞는 클라이언트 모듈을 반환."""
    from .model_manager import load_config, get_active_model
    provider, _ = get_active_model(load_config())
    return _get_client_module(provider)


def _get_fallback_chain() -> List[str]:
    """model_config.json의 fallback_chain을 반환. 없으면 active_provider만."""
    from .model_manager import load_config, get_active_model
    config = load_config()
    chain = config.get("fallback_chain", [])
    if not chain:
        provider, _ = get_active_model(config)
        chain = [provider]

    seen: set = set()
    result: List[str] = []
    for p in chain:
        if p in _VALID_PROVIDERS and p not in seen:
            seen.add(p)
            result.append(p)
    return result or ["gemini"]


async def _call_with_fallback(fn_name: str, **kwargs):
    """폴백 체인 순서대로 provider를 시도해 첫 성공 결과를 반환.

    Circuit Breaker: quota/크레딧 소진 프로바이더는 리셋 시각까지 자동 스킵.
    모든 provider가 실패/스킵되면 마지막 예외를 re-raise 합니다.
    """
    chain = _get_fallback_chain()
    last_exc: Exception = RuntimeError("폴백 체인이 비어 있습니다.")

    for provider in chain:
        tripped, trip_reason = _is_tripped(provider)
        if tripped:
            logger.info(f"[CircuitBreaker] ⏭ {provider} 스킵: {trip_reason}")
            last_exc = RuntimeError(f"{provider} 사용 불가 — {trip_reason}")
            continue

        try:
            module = _get_client_module(provider)
            fn = getattr(module, fn_name)
            return await fn(**kwargs)
        except Exception as exc:
            trip = _detect_circuit_trip(exc, provider)
            if trip:
                duration, reason = trip
                _trip(provider, duration, reason)
            logger.warning(
                f"[폴백] provider={provider} fn={fn_name} 실패: {exc}",
                exc_info=True,
            )
            last_exc = exc

    raise last_exc
