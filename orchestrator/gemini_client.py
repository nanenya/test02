#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

from google import genai
from google.genai import types
import os
import json
import logging
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions, get_filtered_tool_descriptions
from .models import ToolCall, ExecutionGroup
from .constants import HISTORY_MAX_CHARS
from . import agent_config_manager as _acm
from typing import Dict, Any, List, Literal, Optional

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if _api_key:
    client = genai.Client(api_key=_api_key)
else:
    logging.warning("GEMINI_API_KEY 환경변수가 설정되지 않았습니다. Gemini API 호출 시 오류가 발생합니다.")
    client = None

HIGH_PERF_MODEL_NAME = os.getenv("GEMINI_HIGH_PERF_MODEL", "gemini-2.0-flash-001")
STANDARD_MODEL_NAME = os.getenv("GEMINI_STANDARD_MODEL", "gemini-2.0-flash-lite-001")

ModelPreference = Literal["auto", "standard", "high"]


DEFAULT_HISTORY_MAX_CHARS = HISTORY_MAX_CHARS  # constants.py에서 중앙 관리


def _record_usage(response, model_name: str) -> None:
    """Gemini 응답의 usage_metadata를 token_tracker에 기록합니다. 실패는 무시."""
    try:
        from . import token_tracker
        um = response.usage_metadata
        token_tracker.record(
            provider="gemini",
            model=model_name,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
        )
    except Exception:
        pass


def _truncate_history(history: list, max_chars: int = DEFAULT_HISTORY_MAX_CHARS) -> str:
    """최근 대화 우선 보존하는 캐릭터 예산 기반 히스토리 truncation.

    뒤(최신)부터 역순으로 항목을 추가하되, max_chars를 초과하면 중단합니다.
    """
    if not history:
        return ""

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

JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
)


def _get_model_name(
    model_preference: ModelPreference = "auto",
    default_type: Literal["high", "standard"] = "standard",
) -> str:
    if model_preference == "high":
        return HIGH_PERF_MODEL_NAME
    if model_preference == "standard":
        return STANDARD_MODEL_NAME
    # "auto": model_config.json에 설정된 활성 모델 우선 사용
    try:
        from .model_manager import load_config, get_active_model
        _, active_model = get_active_model(load_config())
        if active_model:
            return active_model
    except Exception:
        pass
    # 폴백: default_type에 따라 상수 사용
    if default_type == "high":
        return HIGH_PERF_MODEL_NAME
    return STANDARD_MODEL_NAME


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None,
    allowed_skills: Optional[List[str]] = None,
) -> List[ExecutionGroup]:
    """
    ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다.
    목표가 완료되면 빈 리스트 []를 반환합니다.
    """

    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 설정해주세요.")

    model_name = _get_model_name(model_preference, default_type="high")

    tool_descriptions = get_filtered_tool_descriptions(allowed_skills)
    formatted_history = _truncate_history(history)

    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."

    react_system = _acm.get_prompt("react_planner_system")
    instruction = _acm.render_prompt(
        "react_planner_instruction",
        user_query=user_query,
        requirements_content=requirements_content if requirements_content else "없음",
        tool_descriptions=tool_descriptions,
        formatted_history=formatted_history,
    )
    prompt = f"{custom_system_prompt}\n\n{react_system}\n\n{instruction}"

    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=JSON_CONFIG,
        )
        _record_usage(response, model_name)
        parsed_json = json.loads(response.text)

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]

        # ReAct: LLM이 여러 그룹을 반환해도 1개만 사용 (1-step 계획/실행/재계획 루프)
        return plan[:1]

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"JSON 파싱 오류: {e}\n받은 응답: {response.text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        print(f"Planner 모델 호출 오류: {e}")
        raise e


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto"
) -> str:

    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    model_name = _get_model_name(model_preference, default_type="standard")

    history_str = _truncate_history(history)

    summary_prompt = _acm.render_prompt("final_answer_user", history_str=history_str)
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=summary_prompt,
        )
        _record_usage(response, model_name)

        if not response.text:
            raise ValueError("모델이 빈 응답을 반환했습니다 (내용 필터링 가능성).")

        return response.text.strip()

    except Exception as e:
        logging.error(f"Executor (generate_final_answer) 오류: {e}", exc_info=True)

        last_result = next((item for item in reversed(history) if item.startswith("  - 실행 결과:")), None)

        if last_result:
            return f"최종 요약 생성에 실패했습니다 (서버 로그 참조). 마지막 실행 결과입니다:\n{last_result}"
        else:
            return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다. 서버 로그를 확인해주세요."


async def extract_keywords(
    history: list,
    model_preference: ModelPreference = "auto",
) -> List[str]:
    """Gemini로 키워드 5~10개 추출. 실패 시 [] 반환 (예외 전파 안 함).
    JSON_CONFIG + _truncate_history() 적용. 명사 위주, 한국어/영어 혼용."""
    if not client:
        return []

    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    prompt = _acm.render_prompt("extract_keywords_user", history_str=history_str)
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=JSON_CONFIG,
        )
        _record_usage(response, model_name)
        parsed = json.loads(response.text)
        if isinstance(parsed, list):
            return [str(k) for k in parsed if isinstance(k, str)]
        return []
    except Exception as e:
        logging.warning(f"키워드 추출 실패: {e}")
        return []


async def detect_topic_split(
    history: list,
    model_preference: ModelPreference = "auto",
) -> Optional[Dict[str, Any]]:
    """Gemini로 주제 전환 지점 감지. 실패 시 None 반환.
    반환: {"detected": bool, "split_index": int, "reason": str,
           "topic_a": str, "topic_b": str}"""
    if not client:
        return None

    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    prompt = _acm.render_prompt("detect_topic_split_user", history_str=history_str)
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=JSON_CONFIG,
        )
        _record_usage(response, model_name)
        parsed = json.loads(response.text)
        if isinstance(parsed, dict) and "detected" in parsed:
            return parsed
        return None
    except Exception as e:
        logging.warning(f"주제 분리 감지 실패: {e}")
        return None


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto"
) -> str:

    if not client:
        return "Untitled_Conversation"

    model_name = _get_model_name(model_preference, default_type="standard")

    if len(history) < 2:
        return "새로운_대화"

    summary_prompt = _acm.render_prompt("generate_title_user", msg0=history[0], msg1=history[1] if len(history) > 1 else "")
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=summary_prompt,
        )
        _record_usage(response, model_name)

        if not response.text:
            return "요약_실패"

        return response.text.strip().replace("*", "").replace("`", "").replace("\"", "")
    except Exception:
        return "Untitled_Conversation"
