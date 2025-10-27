#!/usr/bin/env python3

import google.generativeai as genai
import os
import json
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions
from .models import GeminiToolCall

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
#model = genai.GenerativeModel('gemini-2.5-pro')
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))

# 함수 이름을 get_next_action -> get_next_action_with_history 로 변경하고 history 인자 추가
def get_next_action_with_history(user_query: str, history: list) -> GeminiToolCall | str:
    """
    사용자 쿼리와 대화 기록을 바탕으로 Gemini에게 다음 행동을 결정하도록 요청합니다.
    """
    tool_descriptions = get_all_tool_descriptions()

    # 대화 기록을 프롬프트에 포함시켜 맥락을 유지하도록 함
    formatted_history = "\n".join(history)

    prompt = f"""
    당신은 사용자의 목표를 달성하기 위해 주어진 도구를 사용하는 AI 에이전트입니다.
    사용자의 목표와 이전 행동 기록을 분석하여, 목표 달성을 위해 어떤 도구를 어떤 인자로 호출해야 할지 결정하세요.

    ## 사용 가능한 도구 목록:
    {tool_descriptions}

    ## 이전 행동 기록:
    {formatted_history}

    ## 출력 형식:
    반드시 아래 두 가지 형식 중 하나로만 답변해야 합니다.
    1. 도구를 사용해야 할 경우, 다음 JSON 형식으로만 응답하세요:
       {{ "tool_name": "사용할_도구_이름", "arguments": {{"인자1": "값1", "인자2": "값2"}} }}
    2. 모든 작업이 완료되어 최종 답변을 할 수 있는 경우, 일반 텍스트로 답변하세요.

    ## 사용자의 최종 목표:
    {user_query}

    ## 당신의 결정:
    """

    response = model.generate_content(prompt)

    try:
        # 응답이 JSON 형식인지 먼저 시도
        # Gemini가 ```json ... ``` 으로 응답하는 경우가 많아, 마크다운을 제거하는 로직 추가
        cleaned_text = response.text.strip().removeprefix("```json").removesuffix("```")
        decision_json = json.loads(cleaned_text)
        return GeminiToolCall(**decision_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        # JSON 파싱 실패 시 일반 텍스트 답변으로 간주
        return response.text
