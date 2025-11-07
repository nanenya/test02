#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

import google.generativeai as genai
import os
import json
import logging 
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions
from .models import GeminiToolCall, ExecutionGroup
from typing import List, Dict, Any, Literal

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# (요청사항 1) 고성능 모델과 일반 모델 분리
HIGH_PERF_MODEL_NAME = os.getenv("GEMINI_HIGH_PERF_MODEL", "gemini-1.5-pro-latest")
STANDARD_MODEL_NAME = os.getenv("GEMINI_STANDARD_MODEL", "gemini-1.5-flash-latest")

ModelPreference = Literal["auto", "standard", "high"]

# (요청사항 1) 모델 인스턴스 초기화
try:
    # 'Planner' 및 고성능 작업용
    high_perf_model = genai.GenerativeModel(
        HIGH_PERF_MODEL_NAME,
        # JSON 출력을 강제하기 위해 generation_config 설정
        generation_config={"response_mime_type": "application/json"}
    )
    
    # 'Executor' 및 일반 작업용 (JSON 출력이 필요할 수 있으므로 2개 만듦)
    standard_model = genai.GenerativeModel(STANDARD_MODEL_NAME)
    standard_model_json = genai.GenerativeModel(
        STANDARD_MODEL_NAME,
        generation_config={"response_mime_type": "application/json"}
    )
except Exception as e:
    print(f"모델 초기화 오류: {e}")
    print("경고: 모델 로드 실패. 기본 모델(gemini-pro)로 폴백합니다.")
    high_perf_model = genai.GenerativeModel('gemini-pro', generation_config={"response_mime_type": "application/json"})
    standard_model = genai.GenerativeModel('gemini-pro')
    standard_model_json = genai.GenerativeModel('gemini-pro', generation_config={"response_mime_type": "application/json"})


def get_model(
    model_preference: ModelPreference = "auto",
    default_type: Literal["high", "standard"] = "standard",
    needs_json: bool = False
) -> genai.GenerativeModel:
    """
    (요청사항 1) 사용자의 선호도와 작업 유형에 따라 적절한 모델 인스턴스를 반환합니다.
    """
    if model_preference == "high":
        return high_perf_model if needs_json else genai.GenerativeModel(HIGH_PERF_MODEL_NAME) # JSON 아닌 high
    
    if model_preference == "standard":
        return standard_model_json if needs_json else standard_model
    
    # 'auto'인 경우
    if default_type == "high":
        return high_perf_model if needs_json else genai.GenerativeModel(HIGH_PERF_MODEL_NAME)
    else: # 'standard'
        return standard_model_json if needs_json else standard_model


async def generate_execution_plan(
    user_query: str, 
    requirements_content: str, 
    history: list,
    model_preference: ModelPreference = "auto", # (요청사항 1)
    system_prompts: List[str] = None # (요청사항 4)
) -> List[ExecutionGroup]:
    """
    (요청사항 1 - Planner)
    사용자 쿼리, 요구사항, 대화 기록을 바탕으로 'Planner' 모델을 사용해
    'ExecutionGroup'의 리스트로 구성된 전체 실행 계획을 생성합니다.
    (요청사항 2) 태스크별 모델 선호도를 지정하도록 프롬프트 수정.
    (요청사항 4) 시스템 프롬프트(Gem) 주입.
    """
    
    # (요청사항 1) 계획 수립(Priority 2)은 'high'를 기본으로 함
    model_to_use = get_model(model_preference, default_type="high", needs_json=True)

    tool_descriptions = get_all_tool_descriptions()
    formatted_history = "\n".join(history[-10:]) # 최근 10개 기록만 사용

    # (요청사항 4) 시스템 프롬프트 결합
    custom_system_prompt = "\n".join(system_prompts) if system_prompts else "당신은 유능한 AI 어시스턴트입니다."

    prompt = f"""
    {custom_system_prompt}
    
    당신은 사용자의 복잡한 목표를 달성하기 위해, 주어진 도구들을 활용하여 체계적인 실행 계획을 수립하는 '마스터 플래너'입니다.

    ## 최종 목표:
    {user_query}

    ## 사용자가 제공한 추가 요구사항 및 컨텍스트:
    {requirements_content if requirements_content else "없음"}

    ## 사용 가능한 도구 목록:
    {tool_descriptions}

    ## 이전 대화 요약 (참고용):
    {formatted_history}

    ## 지시사항:
    1. 사용자의 '최종 목표'와 '추가 요구사항'을 분석하여, 목표 달성에 필요한 모든 작업을 식별합니다.
    2. 작업들을 논리적인 순서에 따라 '실행 그룹(ExecutionGroup)' 단위로 묶어주세요.
    3. 각 그룹은 사용자가 이해하고 승인할 수 있는 독립적인 작업 단위여야 합니다. (예: "파일 읽기", "데이터 분석", "보고서 작성")
    4. 각 그룹은 하나 이상의 '태스크(도구 호출)'를 포함해야 합니다.
    5. (요청사항 2) 각 'task' 객체 내에 'model_preference' 필드를 포함해야 합니다.
       - 복잡한 추론, 코드 생성, 심층 분석이 필요한 태스크에는 'high'를 할당합니다.
       - 파일 IO, 단순 요약, 데이터 변환 등 간단한 태스크에는 'standard'를 할당합니다.
       - 판단이 어려우면 'auto'를 사용합니다.
       - (참고: 현재 아키텍처는 로컬 도구만 실행하므로 이 설정은 미래 확장을 위한 것입니다. 하지만 반드시 포함해주세요.)
    6. (매우 중요) 한 태스크(예: 'write_file')가 이전 그룹의 실행 결과(예: 'read_file'의 내용)를 인자로 사용해야 한다면, `arguments` 값에 `"$MERGED_RESULTS"` (모든 이전 결과들을 하나의 문자열로 결합) 또는 `"$LAST_RESULT"` (가장 마지막 실행 결과) 같은 특수 플레이스홀더 문자열을 사용해야 합니다.
           (예: 여러 파일을 읽은 후 하나의 파일로 합치는 경우, `write_file`의 `content` 인자는 `"$MERGED_RESULTS"`가 되어야 합니다.)

    ## 출력 형식:
    반드시 다음 JSON 스키마를 따르는 'ExecutionGroup' 객체의 리스트(배열) 형식으로만 응답해야 합니다.
    다른 텍스트나 설명은 절대 포함하지 마세요.

    [
      {{
        "group_id": "group_1",
        "description": "첫 번째 실행 그룹에 대한 사용자 친화적 설명",
        "tasks": [
          {{ 
            "tool_name": "사용할_도구_이름_1", 
            "arguments": {{"인자1": "값1"}},
            "model_preference": "standard" 
          }},
          {{ 
            "tool_name": "사용할_도구_이름_2", 
            "arguments": {{"인자1": "값1", "인자2": "값2"}},
            "model_preference": "high"
          }}
        ]
      }},
      {{
        "group_id": "group_2",
        "description": "두 번째 실행 그룹에 대한 설명",
        "tasks": [
          {{ 
            "tool_name": "사용할_도구_이름_3", 
            "arguments": {{}},
            "model_preference": "auto"
          }}
        ]
      }}
    ]

    ## 실행 계획 (JSON):
    """

    try:
        response = await model_to_use.generate_content_async(prompt)
        parsed_json = json.loads(response.text)
        
        # Pydantic 모델로 변환하여 유효성 검사
        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan
        
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"JSON 파싱 오류: {e}\n받은 응답: {response.text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        print(f"Planner 모델 호출 오류: {e}")
        raise e

async def generate_final_answer(
    history: list, 
    model_preference: ModelPreference = "auto" # (요청사항 1)
) -> str:
    """
    (요청사항 1 - Executor)
    모든 계획 실행이 완료된 후, 전체 대화 기록을 바탕으로 모델을 사용해
    사용자에게 제공할 최종 답변을 생성합니다. (기본 'standard' 모델)
    """
    
    # (요청사항 1) 최종 답변 생성은 'standard'를 기본으로 함
    model_to_use = get_model(model_preference, default_type="standard", needs_json=False)

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
        response = await model_to_use.generate_content_async(summary_prompt)
        
        if not response.parts:
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
    model_preference: ModelPreference = "auto" # (요청사항 1)
) -> str:
    """
    (요청사항 1 - Executor)
    대화 내용을 요약하여 모델을 사용해 짧은 제목을 생성합니다. (기본 'standard' 모델)
    (요청사항 3) 파일명에 사용될 '요약'을 생성합니다.
    """
    
    # (요청사항 1) 제목 생성은 'standard'를 기본으로 함
    model_to_use = get_model(model_preference, default_type="standard", needs_json=False)

    if len(history) < 2:
        return "새로운_대화"

    # (요청사항 3) 프롬프트 수정 (제목 -> 요약)
    summary_prompt = f"""
    다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 '요약'을 한국어로 만들어줘.

    --- 대화 내용 (초반 2개) ---
    {history[0]}
    {history[1] if len(history) > 1 else ""}
    ---

    요약:
    """
    try:
        response = await model_to_use.generate_content_async(summary_prompt)
        
        if not response.parts:
             return "요약_실패"

        # Gemini가 생성할 수 있는 불필요한 마크다운 제거
        return response.text.strip().replace("*", "").replace("`", "").replace("\"", "")
    except Exception:
        return "Untitled_Conversation"
