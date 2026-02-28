#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/claude_client.py

import httpx
import os
import json
import logging
from dotenv import load_dotenv
from .tool_registry import get_filtered_tool_descriptions
from .models import ExecutionGroup
from .constants import HISTORY_MAX_CHARS
from typing import Dict, Any, List, Literal, Optional

load_dotenv()

_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    logging.warning("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. Claude API 호출 시 오류가 발생합니다.")

HIGH_PERF_MODEL_NAME = os.getenv("CLAUDE_HIGH_PERF_MODEL", "claude-sonnet-4-6")
STANDARD_MODEL_NAME = os.getenv("CLAUDE_STANDARD_MODEL", "claude-haiku-4-5-20251001")

ModelPreference = Literal["auto", "standard", "high"]

DEFAULT_HISTORY_MAX_CHARS = HISTORY_MAX_CHARS  # constants.py에서 중앙 관리


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


async def _call_claude(
    system: str,
    user: str,
    model: str,
    json_mode: bool = False,
) -> str:
    """Claude Messages API 호출 내부 헬퍼."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일에 ANTHROPIC_API_KEY를 설정해주세요.")

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    # 토큰 사용량 기록
    try:
        from . import token_tracker
        _usage = data.get("usage", {})
        def _to_int(v):
            try:
                return int(v)
            except Exception:
                return None
        token_tracker.record(
            provider="claude",
            model=model,
            input_tokens=_usage.get("input_tokens", 0) or 0,
            output_tokens=_usage.get("output_tokens", 0) or 0,
            rate_limit_limit=_to_int(resp.headers.get("anthropic-ratelimit-tokens-limit")),
            rate_limit_remaining=_to_int(resp.headers.get("anthropic-ratelimit-tokens-remaining")),
        )
    except Exception:
        pass

    content_blocks = data.get("content", [])
    if not content_blocks:
        raise ValueError("Claude API가 빈 content를 반환했습니다.")

    text = content_blocks[0].get("text", "")
    if not text:
        raise ValueError("Claude API가 빈 텍스트를 반환했습니다.")

    return text


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
    model_name = _get_model_name(model_preference, default_type="high")
    tool_descriptions = get_filtered_tool_descriptions(allowed_skills)
    formatted_history = _truncate_history(history)
    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."

    system = f"""{custom_system_prompt}

당신은 사용자의 목표를 달성하기 위해, '이전 대화'를 분석하여 '다음 1단계'의 계획을 수립하는 'ReAct 플래너'입니다.
반드시 유효한 JSON만 응답하세요. 다른 텍스트는 포함하지 마세요."""

    user = f"""## 최종 목표 (사용자 최초 요청):
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

## 다음 실행 계획 (JSON):"""

    try:
        text = await _call_claude(system=system, user=user, model=model_name, json_mode=True)

        # JSON 블록 추출 (```json ... ``` 감싸진 경우 처리)
        if "```" in text:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()

        parsed_json = json.loads(text)

        if not isinstance(parsed_json, list):
            raise ValueError("응답이 리스트 형식이 아닙니다.")

        if not parsed_json:
            return []

        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan[:1]

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"JSON 파싱 오류: {e}\n받은 응답: {text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        print(f"Planner 모델 호출 오류: {e}")
        raise e


async def generate_final_answer(
    history: list,
    model_preference: ModelPreference = "auto"
) -> str:
    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    system = "당신은 AI 에이전트입니다. 작업 기록을 바탕으로 사용자에게 최종 답변을 한국어로 생성합니다."
    user = f"""다음은 AI 에이전트와 사용자의 작업 기록 요약입니다.
모든 작업이 완료되었습니다.
전체 '실행 결과'와 '사용자 목표'를 바탕으로 사용자에게 제공할 최종적이고 종합적인 답변을 한국어로 생성해주세요.

--- 작업 기록 요약 ---
{history_str}
---

최종 답변:"""

    try:
        text = await _call_claude(system=system, user=user, model=model_name, json_mode=False)
        return text.strip()
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
    """Claude로 키워드 5~10개 추출. 실패 시 [] 반환 (예외 전파 안 함)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return []

    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    system = "당신은 텍스트에서 핵심 키워드를 추출하는 전문가입니다. 반드시 JSON 배열만 응답하세요."
    user = f"""다음 대화에서 핵심 키워드를 5~10개 추출해주세요.
명사 위주로, 한국어/영어 혼용 가능합니다.

--- 대화 내용 ---
{history_str}
---

JSON 배열로만 응답하세요. 예: ["FastAPI", "SQLite", "ReAct", "Python"]"""

    try:
        text = await _call_claude(system=system, user=user, model=model_name, json_mode=True)
        if "```" in text:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()
        parsed = json.loads(text)
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
    """Claude로 주제 전환 지점 감지. 실패 시 None 반환.
    반환: {"detected": bool, "split_index": int, "reason": str,
           "topic_a": str, "topic_b": str}"""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None

    model_name = _get_model_name(model_preference, default_type="standard")
    history_str = _truncate_history(history)

    system = "당신은 대화 분석 전문가입니다. 반드시 JSON 형식만 응답하세요."
    user = f"""다음 대화에서 주제가 크게 전환된 지점이 있는지 분석해주세요.

--- 대화 내용 (인덱스 포함) ---
{history_str}
---

JSON 형식으로만 응답하세요:
{{
  "detected": true또는false,
  "split_index": 정수(주제 전환이 시작되는 메시지 인덱스),
  "reason": "전환 이유 설명",
  "topic_a": "첫 번째 주제 이름",
  "topic_b": "두 번째 주제 이름"
}}
주제 전환이 없으면 detected를 false로 응답하세요."""

    try:
        text = await _call_claude(system=system, user=user, model=model_name, json_mode=True)
        if "```" in text:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()
        parsed = json.loads(text)
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
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "Untitled_Conversation"

    model_name = _get_model_name(model_preference, default_type="standard")

    if len(history) < 2:
        return "새로운_대화"

    system = "당신은 대화를 간결하게 요약하는 전문가입니다."
    user = f"""다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 '요약'을 한국어로 만들어줘.

--- 대화 내용 (초반 2개) ---
{history[0]}
{history[1] if len(history) > 1 else ""}
---

요약:"""

    try:
        text = await _call_claude(system=system, user=user, model=model_name, json_mode=False)
        return text.strip().replace("*", "").replace("`", "").replace('"', "")
    except Exception:
        return "Untitled_Conversation"
