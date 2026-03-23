#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_api_helpers.py — api.py에서 추출한 내부 헬퍼 함수

import inspect
import logging
import os
import time

from .models import AgentResponse
from .llm_client import (
    generate_execution_plan,
    validate_execution_plan,
    summarize_history,
    _get_model_for_category,
)
from .constants import (
    HISTORY_AUTO_SUMMARIZE_THRESHOLD,
    HISTORY_KEEP_RECENT,
    HISTORY_SUMMARY_MARKER,
    MAX_HISTORY_ENTRIES,
    MAX_TOOL_RESULT_LENGTH,
    MAX_REQUIREMENT_FILE_SIZE,
    TOOL_RESULT_TRUNCATED_SUFFIX,
    USER_REQUEST_PREFIX,
)
from . import tool_registry, agent_config_manager, mcp_db_manager, token_tracker


def _resp(**kwargs) -> AgentResponse:
    """token_usage를 자동으로 포함한 AgentResponse를 생성합니다."""
    kwargs.setdefault("token_usage", token_tracker.get_accumulated())
    return AgentResponse(**kwargs)


def _apply_category_preference(plan_list: list) -> None:
    """[D] 각 그룹의 category → task.model_preference 자동 적용."""
    for group in plan_list:
        if group.category:
            mp = _get_model_for_category(group.category)
            for task in group.tasks:
                if task.model_preference == "auto":
                    task.model_preference = mp


async def _validate_and_replan(
    plan_list: list,
    query: str,
    requirements_content: str,
    history: list,
    model_preference: str,
    system_prompts: list,
    allowed_skills,
) -> list:
    """[E] 계획 검증 게이트: 실패 시 1회 재계획."""
    try:
        available = list(tool_registry.get_all_tool_descriptions().keys())
        validation = await validate_execution_plan(plan_list, available)
        if not validation.valid:
            logging.warning(f"[E-PlanGate] score={validation.score:.2f}: {validation.issues}")
            history.append(
                f"[계획 검증 실패 score={validation.score:.2f}]: {'; '.join(validation.issues)}"
                f" → 개선 필요: {'; '.join(validation.suggestions)}"
            )
            plan_list = await generate_execution_plan(
                user_query=query,
                requirements_content=requirements_content,
                history=history,
                model_preference=model_preference,
                system_prompts=system_prompts,
                allowed_skills=allowed_skills,
            )
    except Exception as val_e:
        logging.debug(f"[E-PlanGate] 검증 생략: {val_e}")
    return plan_list


def _resolve_persona(
    provided_prompts: list,
    provided_skills,
    query: str,
    persona_name,
) -> tuple:
    """페르소나에서 system_prompts·allowed_skills를 해석합니다."""
    if provided_prompts:
        return provided_prompts, provided_skills
    persona = agent_config_manager.get_effective_persona(
        query=query, explicit_name=persona_name
    )
    if persona:
        return [persona["system_prompt"]], provided_skills or persona.get("allowed_skills")
    return [], provided_skills


def _format_wisdom(entries: list) -> str:
    """지식 항목을 카테고리별로 포맷팅하여 시스템 프롬프트용 문자열로 반환합니다."""
    if not entries:
        return ""
    by_cat: dict = {}
    for e in entries:
        cat = e.get("category", "misc")
        by_cat.setdefault(cat, []).append(e.get("content", ""))
    lines = ["[이전 학습 지식 - 참고하여 더 나은 계획 수립]"]
    for cat, contents in by_cat.items():
        for c in contents[:3]:
            lines.append(f"  [{cat}] {c}")
    return "\n".join(lines)


async def _maybe_auto_summarize(history: list) -> list:
    """임계값 초과 시 히스토리를 자동 요약합니다. 실패 시 원본 반환."""
    if len(history) <= HISTORY_AUTO_SUMMARIZE_THRESHOLD:
        return history
    recent = history[-HISTORY_KEEP_RECENT:]
    if any(HISTORY_SUMMARY_MARKER in h for h in recent if isinstance(h, str)):
        return history
    to_summarize = history[:-HISTORY_KEEP_RECENT]
    try:
        summary = await summarize_history(to_summarize, model_preference="standard")
    except Exception:
        summary = ""
    if not summary:
        return history
    logging.info(
        f"[AutoSummarize] {len(history)}개 → {1 + HISTORY_KEEP_RECENT}개로 압축"
    )
    return [f"{HISTORY_SUMMARY_MARKER}\n{summary}"] + history[-HISTORY_KEEP_RECENT:]


def _validate_requirement_path(path: str) -> str:
    """요구사항 파일 경로를 검증합니다."""
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise ValueError(f"요구사항 경로가 일반 파일이 아닙니다: {path}")
    if os.path.getsize(real) > MAX_REQUIREMENT_FILE_SIZE:
        raise ValueError(f"요구사항 파일이 너무 큽니다 (최대 1MB): {path}")
    return real


def _prune_history(history: list) -> list:
    """대화 이력이 MAX_HISTORY_ENTRIES를 초과하면 오래된 항목을 제거합니다."""
    if len(history) > MAX_HISTORY_ENTRIES:
        logging.info(
            f"대화 이력이 {MAX_HISTORY_ENTRIES}개를 초과하여 오래된 항목을 제거합니다. "
            f"(현재: {len(history)}개)"
        )
        return history[-MAX_HISTORY_ENTRIES:]
    return history


def _extract_first_query(history: list) -> str:
    """대화 이력에서 첫 번째 사용자 요청을 추출합니다."""
    for entry in history:
        if isinstance(entry, str) and entry.startswith(USER_REQUEST_PREFIX):
            return entry[len(USER_REQUEST_PREFIX):].strip()
    return "이전 작업을 계속하세요."


def _validate_tool_arguments(tool_function, tool_name: str, arguments: dict) -> None:
    """LLM이 생성한 tool 인자를 함수 서명과 대조하여 검증합니다."""
    try:
        sig = inspect.signature(tool_function)
    except (ValueError, TypeError):
        return
    if any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    ):
        return
    allowed = set(sig.parameters.keys())
    unknown = set(arguments.keys()) - allowed
    if unknown:
        raise ValueError(
            f"도구 '{tool_name}'에 허용되지 않은 인자: {unknown}. 허용된 인자: {allowed}"
        )


async def _execute_single_task(task, session_id) -> tuple:
    """단일 태스크를 실행하고 (tool_name, result_str, exc | None) 튜플을 반환."""
    from . import mcp_db_manager as _mdb
    t_start = time.monotonic()
    try:
        await tool_registry.ensure_tool_server_connected(task.tool_name)

        tool_function = tool_registry.get_tool(task.tool_name)
        if not tool_function:
            try:
                from . import tool_discoverer
                discovery = await tool_discoverer.discover_and_resolve([task.tool_name])
                result_info = discovery.get(task.tool_name, {})
                if result_info.get("status") in ("found", "python_impl"):
                    tool_function = tool_registry.get_tool(task.tool_name)
            except Exception as _disc_err:
                logging.warning(f"on-demand discover 실패: {_disc_err}")
        if not tool_function:
            raise ValueError(f"'{task.tool_name}' 도구를 찾을 수 없습니다.")

        providers = tool_registry.get_tool_providers(task.tool_name)
        if len(providers) >= 2:
            server_names = [p["server"] for p in providers]
            logging.info(f"Tool '{task.tool_name}' has multiple providers: {server_names}")

        _validate_tool_arguments(tool_function, task.tool_name, task.arguments)

        if inspect.iscoroutinefunction(tool_function):
            result = await tool_function(**task.arguments)
        else:
            result = tool_function(**task.arguments)
        duration_ms = int((time.monotonic() - t_start) * 1000)
        try:
            _mdb.log_usage(
                task.tool_name, success=True, session_id=session_id,
                duration_ms=duration_ms, args_summary=",".join(task.arguments.keys()),
            )
        except Exception as log_err:
            logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
        result_str = str(result)
        if len(result_str) > MAX_TOOL_RESULT_LENGTH:
            logging.warning(
                f"도구 '{task.tool_name}' 결과가 {MAX_TOOL_RESULT_LENGTH}자를 초과하여 잘렸습니다. "
                f"(원래 길이: {len(result_str)}자)"
            )
            result_str = result_str[:MAX_TOOL_RESULT_LENGTH] + TOOL_RESULT_TRUNCATED_SUFFIX
        return task.tool_name, result_str, None
    except Exception as tool_err:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        try:
            mcp_db_manager.log_usage(
                task.tool_name, success=False, session_id=session_id,
                duration_ms=duration_ms, error_message=str(tool_err),
                args_summary=",".join(task.arguments.keys()),
            )
        except Exception as log_err:
            logging.warning(f"mcp_db_manager.log_usage 실패: {log_err}")
        return task.tool_name, "", tool_err
