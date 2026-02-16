#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

from google import genai
from google.genai import types
import os
import json
import logging
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions
from .models import GeminiToolCall, ExecutionGroup
from typing import List, Dict, Any, Literal

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if _api_key:
    client = genai.Client(api_key=_api_key)
else:
    logging.warning("GEMINI_API_KEY 환경변수가 설정되지 않았습니다. Gemini API 호출 시 오류가 발생합니다.")
    client = None

HIGH_PERF_MODEL_NAME = os.getenv("GEMINI_HIGH_PERF_MODEL", "gemini-2.0-flash")
STANDARD_MODEL_NAME = os.getenv("GEMINI_STANDARD_MODEL", "gemini-2.0-flash-lite")

ModelPreference = Literal["auto", "standard", "high"]

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
    if default_type == "high":
        return HIGH_PERF_MODEL_NAME
    return STANDARD_MODEL_NAME


async def generate_execution_plan(
    user_query: str,
    requirements_content: str,
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None
) -> List[ExecutionGroup]:
    """
    ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다.
    목표가 완료되면 빈 리스트 []를 반환합니다.
    """

    if not client:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 설정해주세요.")

    model_name = _get_model_name(model_preference, default_type="high")

    tool_descriptions = get_all_tool_descriptions()
    formatted_history = "\n".join(history[-10:])

    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."

    prompt = f"""
    {custom_system_prompt}

    당신은 사용자의 목표를 달성하기 위해, '이전 대화'를 분석하여 '다음 1단계'의 계획을 수립하는 'ReAct 플래너'입니다.

    ## 최종 목표 (사용자 최초 요청):
    {user_query}

    ## 사용자가 제공한 추가 요구사항 및 컨텍스트:
    {requirements_content if requirements_content else "없음"}

    ## 사용 가능한 도구 목록:
    {tool_descriptions}

    ## 이전 대화 요약 (매우 중요!):
    {formatted_history}

    ## 지시사항 (필독!):
    1. '최종 목표'와 '이전 대화 요약'을 면밀히 분석합니다.
    2. '이전 대화 요약'에 "실행 결과"가 있다면, 그 결과를 **입력으로 사용**하여 **다음에 실행할 논리적인 1개의 '실행 그룹(ExecutionGroup)'**을 만드세요.
       (예: "실행 결과: ['a.txt']"가 있다면, 다음 그룹은 'read_file(path="a.txt")' 태스크를 포함해야 합니다.)
    3. 만약 '이전 대화 요약'을 분석했을 때 모든 '최종 목표'가 완료되었다고 판단되면, 반드시 빈 리스트( `[]` )를 반환하세요.
    4. 만약 '이전 대화 요약'이 비어있거나 "실행 결과"가 없다면(첫 단계), '최종 목표' 달성을 위한 **첫 번째 1개의 '실행 그룹'**을 만드세요.
    5. 각 'task' 객체 내에 'model_preference' 필드를 포함해야 합니다 ('high', 'standard', 'auto').

    ## 출력 형식:
    반드시 'ExecutionGroup' 객체의 리스트(배열) 형식으로만 응답해야 합니다.
    **다음 1개 그룹만** 포함하거나, **완료 시 빈 리스트 `[]`**를 반환해야 합니다.

    # 예시 1: 다음 단계가 남은 경우 (1개 그룹만 포함)
    [
      {{
        "group_id": "group_N",
        "description": "다음에 실행할 단일 그룹에 대한 설명",
        "tasks": [
          {{
            "tool_name": "도구_이름",
            "arguments": {{"이전_결과_활용": "값"}},
            "model_preference": "standard"
          }}
        ]
      }}
    ]

    # 예시 2: 모든 작업 완료 시
    []

    ## 다음 실행 계획 (JSON):
    """

    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=JSON_CONFIG,
        )
        parsed_json = json.loads(response.text)

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]

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

    if len(history) > 15:
        truncated_history_list = history[:2] + ["... (중간 기록 생략) ..."] + history[-13:]
        history_str = '\n'.join(truncated_history_list)
    else:
        history_str = '\n'.join(history)

    summary_prompt = f"""
    다음은 AI 에이전트와 사용자의 작업 기록 요약입니다.
    모든 작업이 완료되었습니다.
    전체 '실행 결과'와 '사용자 목표'를 바탕으로 사용자에게 제공할 최종적이고 종합적인 답변을 한국어로 생성해주세요.

    --- 작업 기록 요약 ---
    {history_str}
    ---

    최종 답변:
    """
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=summary_prompt,
        )

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


async def generate_title_for_conversation(
    history: list,
    model_preference: ModelPreference = "auto"
) -> str:

    if not client:
        return "Untitled_Conversation"

    model_name = _get_model_name(model_preference, default_type="standard")

    if len(history) < 2:
        return "새로운_대화"

    summary_prompt = f"""
    다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 '요약'을 한국어로 만들어줘.

    --- 대화 내용 (초반 2개) ---
    {history[0]}
    {history[1] if len(history) > 1 else ""}
    ---

    요약:
    """
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=summary_prompt,
        )

        if not response.text:
            return "요약_실패"

        return response.text.strip().replace("*", "").replace("`", "").replace("\"", "")
    except Exception:
        return "Untitled_Conversation"
