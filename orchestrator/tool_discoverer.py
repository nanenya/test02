#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/tool_discoverer.py
"""Phase 3 — 도구 발견 및 자동 구현 모듈.

우선순위:
  1. 로컬 TOOLS / MCP 등록 도구에서 검색 (즉시)
  2. npm/pip MCP 서버 탐색 (subprocess 기반)
  3. LLM(high 티어)으로 Python 함수 자동 생성 → mcp_db_manager 저장 → 즉시 활성화

보안:
  - npm/pip 명령 화이트리스트 (_ALLOWED_COMMANDS)
  - LLM 생성 코드 정적 위험 패턴 검사 후 저장 거부
  - tool_gap_log에 모든 시도를 기록
"""

import ast
import logging
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from . import pipeline_db
from . import mcp_db_manager
from . import tool_registry
from . import agent_config_manager as _acm
from .constants import utcnow

logger = logging.getLogger(__name__)

# ── 보안: 허용된 패키지 관리자 명령 화이트리스트 ──────────────────────────────
_ALLOWED_COMMANDS: frozenset = frozenset({"npm", "npx", "pip", "pip3", "uvx"})

# LLM 생성 코드에서 거부할 위험 패턴 (정적 분석)
_DANGEROUS_PATTERNS: List[str] = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\s*\(",
    r"\bopen\s*\(.*['\"]w['\"]",   # 쓰기 모드 파일 오픈
    r"\bshutil\.rmtree\b",
    r"\bos\.remove\b",
    r"\bos\.unlink\b",
    r"rm\s+-rf",
    r"\bimport\s+subprocess\b",
    r"\bimport\s+os\b",
]
_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


# ── 1단계: 로컬/MCP 도구 검색 ────────────────────────────────────────────────

def find_in_registered_tools(tool_hint: str) -> Optional[str]:
    """등록된 도구 중 tool_hint와 이름이 일치하거나 포함된 것을 반환합니다."""
    hint_lower = tool_hint.lower()

    # 정확히 일치
    all_tools = list(tool_registry.TOOLS.keys()) + list(tool_registry._mcp_tools.keys())
    for name in all_tools:
        if name.lower() == hint_lower:
            return name

    # 부분 포함 (hints가 도구명 일부인 경우)
    for name in all_tools:
        if hint_lower in name.lower() or name.lower() in hint_lower:
            return name

    return None


def find_tools_for_step(tool_hints: List[str]) -> Dict[str, Optional[str]]:
    """tool_hints 목록에 대해 등록 도구 매핑을 반환합니다.

    Returns: {hint: matched_tool_name or None}
    """
    return {hint: find_in_registered_tools(hint) for hint in tool_hints}


# ── 2단계: npm/pip MCP 서버 탐색 ─────────────────────────────────────────────

def _run_safe(cmd: List[str], timeout: int = 20) -> Optional[str]:
    """화이트리스트 검증 후 subprocess를 실행합니다."""
    if not cmd or cmd[0] not in _ALLOWED_COMMANDS:
        logger.warning(f"[Discoverer] 허용되지 않은 명령: {cmd[0]!r}")
        return None
    # args에 셸 인젝션 문자 거부
    inject_chars = set(";|&`$><")
    for arg in cmd[1:]:
        if any(c in str(arg) for c in inject_chars):
            logger.warning(f"[Discoverer] 위험 문자 포함 인자: {arg!r}")
            return None
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # 절대 shell=True 사용 금지
        )
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        logger.debug(f"[Discoverer] subprocess 실패: {e}")
        return None


def search_npm_mcp(tool_hint: str) -> List[Dict[str, str]]:
    """npm에서 MCP 서버 패키지를 검색합니다."""
    import json
    raw = _run_safe(["npm", "search", "--json", f"mcp-server {tool_hint}"])
    if not raw:
        return []
    try:
        packages = json.loads(raw)
        return [
            {"name": p.get("name", ""), "description": p.get("description", "")}
            for p in packages[:5]
            if "mcp" in p.get("name", "").lower()
        ]
    except Exception:
        return []


# ── 3단계: LLM Python 구현 자동 생성 ─────────────────────────────────────────

def _is_code_safe(code: str) -> Tuple[bool, str]:
    """LLM 생성 코드의 위험 패턴을 정적으로 검사합니다.

    Returns: (is_safe, reason)
    """
    # 정규식 기반 패턴 검사
    match = _DANGEROUS_RE.search(code)
    if match:
        return False, f"위험 패턴 감지: {match.group()!r}"

    # AST 파싱 가능 여부 (구문 오류 방지)
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"구문 오류: {e}"

    return True, ""


async def generate_tool_implementation(
    tool_hint: str,
    context: str = "",
    model_preference: str = "high",
    module_group: str = "auto_generated",
) -> Optional[int]:
    """LLM으로 Python 도구 함수를 생성하고 mcp_db_manager에 저장합니다.

    성공 시 func_id(mcp_functions.id)를 반환합니다.
    보안 검사 실패 또는 LLM 오류 시 None을 반환합니다.
    """
    from .llm_client import _get_fallback_chain, _get_client_module

    prompt = _acm.render_prompt(
        "tool_implementation_user",
        tool_hint=tool_hint,
        context=context or "일반적인 도구 함수",
    )

    chain = _get_fallback_chain()
    for provider in chain:
        try:
            module = _get_client_module(provider)
            raw = await module.generate_final_answer(
                history=[f"TOOL_IMPL_GEN: {prompt}"],
                model_preference=model_preference,
            )
            # 코드 블록 추출
            code_match = re.search(r"```python\s*(.*?)```", raw, re.DOTALL)
            code = code_match.group(1).strip() if code_match else raw.strip()

            # 보안 검사
            is_safe, reason = _is_code_safe(code)
            if not is_safe:
                logger.warning(f"[Discoverer] 생성 코드 보안 검사 실패: {reason}")
                pipeline_db.log_tool_gap(
                    required_tool=tool_hint,
                    resolution_type="security_rejected",
                    note=reason,
                )
                return None

            # mcp_db_manager에 저장 (비활성 상태로 저장, 사용자 검토 후 활성화)
            func_id = mcp_db_manager.add_function(
                func_name=tool_hint,
                module_group=module_group,
                code=code,
                description=f"자동 생성: {context or tool_hint}",
                source_type="auto_generated",
                source_desc=f"LLM 자동 생성 (provider={provider})",
            )

            pipeline_db.log_tool_gap(
                required_tool=tool_hint,
                resolution_type="python_impl",
                func_id=func_id,
                note=f"provider={provider}, module={module_group}",
            )
            logger.info(f"[Discoverer] 도구 생성 완료: {tool_hint} (func_id={func_id})")
            return func_id

        except Exception as e:
            logger.warning(f"[Discoverer] 도구 생성 실패 provider={provider}: {e}")

    return None


# ── 통합 진입점 ───────────────────────────────────────────────────────────────

async def discover_and_resolve(
    missing_tools: List[str],
    context: str = "",
    model_preference: str = "high",
) -> Dict[str, Dict[str, Any]]:
    """누락 도구 목록에 대해 발견/구현을 시도합니다.

    Returns:
        {tool_hint: {"status": "found"|"npm_found"|"python_impl"|"failed",
                     "resolved_name": str or None,
                     "func_id": int or None}}
    """
    results: Dict[str, Dict[str, Any]] = {}

    for hint in missing_tools:
        # 1단계: 이미 등록된 도구 재탐색 (동의어 등)
        matched = find_in_registered_tools(hint)
        if matched:
            results[hint] = {"status": "found", "resolved_name": matched, "func_id": None}
            pipeline_db.log_tool_gap(
                required_tool=hint,
                resolution_type="found_in_registry",
                note=f"matched={matched}",
            )
            continue

        # 2단계: npm MCP 서버 탐색 (발견 시 사용자에게 알리고 자동 등록은 하지 않음)
        npm_results = search_npm_mcp(hint)
        if npm_results:
            best = npm_results[0]
            logger.info(
                f"[Discoverer] npm 탐색 결과: {hint} → {best['name']}"
            )
            pipeline_db.log_tool_gap(
                required_tool=hint,
                resolution_type="mcp_found",
                mcp_server_name=best["name"],
                note=best.get("description", ""),
            )
            results[hint] = {
                "status": "npm_found",
                "resolved_name": best["name"],
                "func_id": None,
                "npm_package": best["name"],
                "description": best.get("description", ""),
            }
            continue

        # 3단계: Python 함수 자동 생성
        func_id = await generate_tool_implementation(
            tool_hint=hint,
            context=context,
            model_preference=model_preference,
        )
        if func_id is not None:
            results[hint] = {"status": "python_impl", "resolved_name": hint, "func_id": func_id}
        else:
            results[hint] = {"status": "failed", "resolved_name": None, "func_id": None}
            pipeline_db.log_tool_gap(
                required_tool=hint,
                resolution_type="not_found",
                note="all_resolution_failed",
            )

    return results


def get_gap_report(limit: int = 20) -> List[Dict[str, Any]]:
    """최근 tool_gap_log를 조회합니다."""
    with pipeline_db.get_db() as conn:
        rows = conn.execute(
            """SELECT required_tool, resolution_type, mcp_server_name, func_id, note, created_at
               FROM tool_gap_log ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
