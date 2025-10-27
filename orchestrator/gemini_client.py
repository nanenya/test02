#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

import google.generativeai as genai
import os
import json
import logging  # (수정 1) 로깅 모듈 임포트
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions
from .models import GeminiToolCall, ExecutionGroup
from typing import List, Dict, Any

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- (요청사항 1) Planner와 Executor 모델 분리 ---
# PLANNER_MODEL: 복잡한 계획 수립을 위한 고성능 모델 (예: gemini-1.5-pro-latest)
PLANNER_MODEL_NAME = os.getenv("GEMINI_PLANNER_MODEL", "gemini-1.5-pro-latest")
# EXECUTOR_MODEL: 단순 요약, 제목 생성을 위한 경량 모델 (예: gemini-1.5-flash-latest)
EXECUTOR_MODEL_NAME = os.getenv("GEMINI_EXECUTOR_MODEL", "gemini-1.5-flash-latest")

try:
    planner_model = genai.GenerativeModel(
        PLANNER_MODEL_NAME,
        # JSON 출력을 강제하기 위해 generation_config 설정
        generation_config={"response_mime_type": "application/json"}
    )
    executor_model = genai.GenerativeModel(EXECUTOR_MODEL_NAME)
except Exception as e:
    print(f"모델 초기화 오류: {e}")
    # 하나라도 실패하면 둘 다 기본 모델로 폴백 (예시)
    print("경고: 모델 로드 실패. 기본 모델(gemini-pro)로 폴백합니다.")
    planner_model = genai.GenerativeModel('gemini-pro')
    executor_model = genai.GenerativeModel('gemini-pro')
# -------------------------------------------------


async def generate_execution_plan(
    user_query: str, 
    requirements_content: str, 
    history: list
) -> List[ExecutionGroup]:
    """
    (요청사항 1 - Planner)
    사용자 쿼리, 요구사항, 대화 기록을 바탕으로 'Planner' 모델을 사용해
    'ExecutionGroup'의 리스트로 구성된 전체 실행 계획을 생성합니다.
    """
    tool_descriptions = get_all_tool_descriptions()
    formatted_history = "\n".join(history[-10:]) # 최근 10개 기록만 사용

    prompt = f"""
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
    5. 사용자가 중간에 결과를 확인할 필요가 없는 간단한 작업(예: 파일 읽고 바로 내용 분석)은 하나의 그룹으로 묶으세요.
    
    ## 출력 형식:
    반드시 다음 JSON 스키마를 따르는 'ExecutionGroup' 객체의 리스트(배열) 형식으로만 응답해야 합니다.
    다른 텍스트나 설명은 절대 포함하지 마세요.

    [
      {{
        "group_id": "group_1",
        "description": "첫 번째 실행 그룹에 대한 사용자 친화적 설명",
        "tasks": [
          {{ "tool_name": "사용할_도구_이름_1", "arguments": {{"인자1": "값1"}} }},
          {{ "tool_name": "사용할_도구_이름_2", "arguments": {{"인자1": "값1", "인자2": "값2"}} }}
        ]
      }},
      {{
        "group_id": "group_2",
        "description": "두 번째 실행 그룹에 대한 설명",
        "tasks": [
          {{ "tool_name": "사용할_도구_이름_3", "arguments": {{}} }}
        ]
      }}
    ]

    ## 실행 계획 (JSON):
    """

    try:
        response = await planner_model.generate_content_async(prompt)
        # response_mime_type을 사용하면 response.text가 순수 JSON 문자열임
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

async def generate_final_answer(history: list) -> str:
    """
    (요청사항 1 - Executor)
    모든 계획 실행이 완료된 후, 전체 대화 기록을 바탕으로 'Executor' 모델을 사용해
    사용자에게 제공할 최종 답변을 생성합니다.
    """
    
    # (수정 2) 컨텍스트 길이 초과 및 필터링 방지를 위해 history 축소
    # 초기 목표(최대 2개) + 최근 실행 내역(최대 13개)만 요약에 사용
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
        response = await executor_model.generate_content_async(summary_prompt)
        
        # (수정 4) 모델이 빈 응답을 반환했는지 확인 (안전 필터링 등)
        if not response.text or not response.text.strip():
            raise ValueError("모델이 빈 응답을 반환했습니다 (내용 필터링 가능성).")
            
        return response.text.strip()
        
    except Exception as e:
        # (수정 1) 실패 시 실제 오류를 서버 로그에 기록
        logging.error(f"Executor (generate_final_answer) 오류: {e}", exc_info=True)
        
        # (수정 3) 최종 요약에 실패하더라도, 사용자가 원했던 마지막 실행 결과를 찾아서 반환
        last_result = next((item for item in reversed(history) if item.startswith("  - 실행 결과:")), None)
        
        if last_result:
            return f"최종 요약 생성에 실패했습니다 (서버 로그 참조). 마지막 실행 결과입니다:\n{last_result}"
        else:
            # (기존 메시지)
            return "작업이 완료되었지만, 최종 답변을 생성하는 데 실패했습니다. 서버 로그를 확인해주세요."

async def generate_title_for_conversation(history: list) -> str:
    """
    (요청사항 1 - Executor)
    대화 내용을 요약하여 'Executor' 모델을 사용해 짧은 제목을 생성합니다.
    """
    if len(history) < 2:
        return "새로운 대화"

    summary_prompt = f"""
    다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 제목을 한국어로 만들어줘.

    --- 대화 내용 (초반 2개) ---
    {history[0]}
    {history[1] if len(history) > 1 else ""}
    ---

    제목:
    """
    try:
        response = await executor_model.generate_content_async(summary_prompt)
        # Gemini가 생성할 수 있는 불필요한 마크다운 제거
        return response.text.strip().replace("*", "").replace("`", "").replace("\"", "")
    except Exception:
        return "Untitled Conversation"
