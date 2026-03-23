#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_llm_utils.py
"""LLM 클라이언트 공통 유틸리티.

모든 LLM 클라이언트(gemini/claude/openai/grok/ollama)에서 동일하게 사용하는
헬퍼 함수를 한 곳에 정의합니다.

call_fn 통합 시그니처: async (system, user, model, json_mode) -> str
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .constants import truncate_history as _truncate_history
from . import agent_config_manager as _acm


def _extract_json_block(text: str) -> str:
    """```json...``` 블록에서 JSON 문자열을 추출합니다."""
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            return m.group(1).strip()
    return text.strip()


async def generate_execution_plan_with_caller(
    call_fn: Callable,
    user_query: str,
    requirements_content: str,
    history: list,
    model_name: str,
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> list:
    """공통 실행 계획 생성 로직 (ReAct 플래너). call_fn만 프로바이더별로 다름.

    반환: List[ExecutionGroup] — ReAct 방식으로 1개만 반환.
    완료 시 빈 리스트 [].
    """
    from .models import ExecutionGroup
    from .tool_registry import get_filtered_tool_descriptions

    tool_descriptions = get_filtered_tool_descriptions(allowed_skills)
    formatted_history = _truncate_history(history)
    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."
    system = custom_system_prompt + "\n\n" + _acm.get_prompt("react_planner_system")
    user = _acm.render_prompt(
        "react_planner_instruction",
        user_query=user_query,
        requirements_content=requirements_content if requirements_content else "없음",
        tool_descriptions=tool_descriptions,
        formatted_history=formatted_history,
    )

    text = ""
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=True)
        text = _extract_json_block(text)
        parsed_json = json.loads(text)

        # dict → list 정규화 (일부 모델이 dict로 감싸서 반환)
        if isinstance(parsed_json, dict):
            if "tasks" in parsed_json and isinstance(parsed_json["tasks"], list):
                parsed_json = [{
                    "group_id": "group_1",
                    "description": "자동 생성된 실행 그룹",
                    "tasks": parsed_json["tasks"],
                }]
            else:
                for v in parsed_json.values():
                    if isinstance(v, list):
                        parsed_json = v
                        break
                else:
                    raise ValueError("응답 dict에서 실행 계획 리스트를 찾을 수 없습니다.")

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan[:1]

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logging.error(f"JSON 파싱 오류: {e}\n받은 응답: {text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        logging.error(f"Planner 모델 호출 오류: {e}")
        raise


async def generate_final_answer_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> str:
    """공통 최종 답변 생성 로직. 실패 시 마지막 실행 결과로 폴백."""
    history_str = _truncate_history(history)
    system = _acm.get_prompt("final_answer_system")
    user = _acm.render_prompt("final_answer_user", history_str=history_str)
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=False)
        return text.strip()
    except Exception as e:
        logging.error(f"generate_final_answer 오류: {e}", exc_info=True)
        last_result = next(
            (item for item in reversed(history) if item.startswith("  - 실행 결과:")), None
        )
        if last_result:
            return f"최종 요약 생성에 실패했습니다 (서버 로그 참조). 마지막 실행 결과입니다:\n{last_result}"
        return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다. 서버 로그를 확인해주세요."


async def extract_keywords_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> List[str]:
    """공통 키워드 추출 로직. call_fn만 프로바이더별로 다름."""
    history_str = _truncate_history(history)
    system = _acm.get_prompt("extract_keywords_system")
    user = _acm.render_prompt("extract_keywords_user", history_str=history_str)
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=True)
        parsed = json.loads(_extract_json_block(text))
        if isinstance(parsed, list):
            return [str(k) for k in parsed if isinstance(k, str)]
        # {"keywords": [...]} 형태 처리
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return [str(k) for k in v if isinstance(k, str)]
        return []
    except Exception as e:
        logging.warning(f"키워드 추출 실패: {e}")
        return []


async def detect_topic_split_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> Optional[Dict[str, Any]]:
    """공통 주제 분리 감지 로직. call_fn만 프로바이더별로 다름."""
    history_str = _truncate_history(history)
    system = _acm.get_prompt("detect_topic_split_system")
    user = _acm.render_prompt("detect_topic_split_user", history_str=history_str)
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=True)
        parsed = json.loads(_extract_json_block(text))
        if isinstance(parsed, dict) and "detected" in parsed:
            return parsed
        return None
    except Exception as e:
        logging.warning(f"주제 분리 감지 실패: {e}")
        return None


async def generate_title_with_caller(
    call_fn: Callable,
    history: list,
    model_name: str,
) -> str:
    """공통 대화 제목 생성 로직. call_fn만 프로바이더별로 다름."""
    if len(history) < 2:
        return "새로운_대화"
    system = _acm.get_prompt("generate_title_system")
    user = _acm.render_prompt(
        "generate_title_user",
        msg0=history[0],
        msg1=history[1] if len(history) > 1 else "",
    )
    try:
        text = await call_fn(system=system, user=user, model=model_name, json_mode=False)
        return text.strip().replace("*", "").replace("`", "").replace('"', "")
    except Exception:
        return "Untitled_Conversation"
