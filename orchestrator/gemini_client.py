#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/gemini_client.py

import google.generativeai as genai
import os
import json
import logging 
from dotenv import load_dotenv
from .tool_registry import get_all_tool_descriptions, MCP_DIRECTORY
from .models import GeminiToolCall, ExecutionGroup
from typing import List, Dict, Any, Literal
from pathlib import Path

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ... (기존 모델 설정 및 get_model 함수) ...
HIGH_PERF_MODEL_NAME = os.getenv("GEMINI_HIGH_PERF_MODEL", "gemini-1.5-pro-latest")
STANDARD_MODEL_NAME = os.getenv("GEMINI_STANDARD_MODEL", "gemini-1.5-flash-latest")
ModelPreference = Literal["auto", "standard", "high"]

try:
    high_perf_model = genai.GenerativeModel(
        HIGH_PERF_MODEL_NAME,
        generation_config={"response_mime_type": "application/json"}
    )
    standard_model = genai.GenerativeModel(STANDARD_MODEL_NAME)
    standard_model_json = genai.GenerativeModel(
        STANDARD_MODEL_NAME,
        generation_config={"response_mime_type": "application/json"}
    )
except Exception as e:
    print(f"모델 초기화 오류: {e}. 기본 모델로 폴백합니다.")
    high_perf_model = genai.GenerativeModel('gemini-pro', generation_config={"response_mime_type": "application/json"})
    standard_model = genai.GenerativeModel('gemini-pro')
    standard_model_json = genai.GenerativeModel('gemini-pro', generation_config={"response_mime_type": "application/json"})


def get_model(
    model_preference: ModelPreference = "auto",
    default_type: Literal["high", "standard"] = "standard",
    needs_json: bool = False
) -> genai.GenerativeModel:
    if model_preference == "high":
        return high_perf_model if needs_json else genai.GenerativeModel(HIGH_PERF_MODEL_NAME)
    
    if model_preference == "standard":
        return standard_model_json if needs_json else standard_model
    
    if default_type == "high":
        return high_perf_model if needs_json else genai.GenerativeModel(HIGH_PERF_MODEL_NAME)
    else: 
        return standard_model_json if needs_json else standard_model
# ... (여기까지 기존과 동일) ...


async def generate_execution_plan(
    user_query: str, 
    requirements_content: str, 
    history: list,
    model_preference: ModelPreference = "auto",
    system_prompts: List[str] = None
) -> List[ExecutionGroup]:
    """
    (수정) Planner 프롬프트. JSON 스키마를 매우 엄격하게 강조하여 AI의 오류(group_name)를 방지.
    """
    
    model_to_use = get_model(model_preference, default_type="high", needs_json=True)

    tool_descriptions = get_all_tool_descriptions()
    formatted_history = "\n".join(history[-10:]) 
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
    
    ## (특수 명령)
    - reload_tools: 새로 생성된 MCP 파일을 mcp_modules에서 다시 로드하여 즉시 사용할 수 있게 합니다. MCP 파일 작성(write_file) 직후에 이 도구를 호출해야 합니다.

    ## 이전 대화 요약 (참고용):
    {formatted_history}

    ## [매우 중요] 지시사항:
    1. 사용자의 '최종 목표'와 '이전 대화'를 분석하여, 목표 달성에 필요한 모든 작업을 식별합니다. (오류가 발생했다면, 오류를 수정하는 계획을 수립합니다.)
    2. 작업들을 논리적인 순서에 따라 '실행 그룹(ExecutionGroup)' 단위로 묶어주세요.
    3. (중요) 한 태스크가 이전 그룹의 결과(예: 'find_files'의 결과)를 인자로 사용해야 한다면, `arguments` 값에 `"$LAST_RESULT"` (가장 마지막 실행 결과) 또는 `"$MERGED_RESULTS"` (모든 이전 결과 결합) 플레이스홀더를 사용해야 합니다.
    
    ## [절대 규칙] 출력 형식:
    반드시 다음 JSON 스키마를 '정확하게' 따르는 'ExecutionGroup' 객체의 리스트(배열) 형식으로만 응답해야 합니다.
    'thought', 'group_name', 'args' 같은 임의의 키를 절대 사용하지 마세요.
    오직 'group_id', 'description', 'tasks', 'tool_name', 'arguments', 'model_preference' 만 사용하세요.

    [
      {{
        "group_id": "group_1",
        "description": "첫 번째 실행 그룹에 대한 사용자 친화적 설명",
        "tasks": [
          {{ 
            "tool_name": "사용할_도구_이름_1", 
            "arguments": {{"인자1": "값1"}},
            "model_preference": "standard" 
          }}
        ]
      }},
      {{
        "group_id": "group_2",
        "description": "두 번째 실행 그룹에 대한 설명 (예: 이전 결과 사용)",
        "tasks": [
          {{ 
            "tool_name": "사용할_도구_이름_2", 
            "arguments": {{"content": "$LAST_RESULT", "path": "./output.txt"}},
            "model_preference": "high"
          }}
        ]
      }}
    ]

    ## 실행 계획 (JSON):
    """

    try:
        response = await model_to_use.generate_content_async(prompt)
        # (신규) AI가 생성한 JSON에서 불필요한 마크다운 래퍼 제거 (예: ```json ... ```)
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        parsed_json = json.loads(cleaned_text)
        
        plan = [ExecutionGroup(**group) for group in parsed_json]
        return plan
        
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"오류 복구 JSON 파싱 오류: {e}\n받은 응답: {response.text}")
        raise ValueError(f"Planner 모델이 유효한 JSON 계획을 생성하지 못했습니다: {e}")
    except Exception as e:
        print(f"Planner 모델 호출 오류: {e}")
        raise e

# (신규) 요청사항 1, 2: 신규 MCP 생성을 위한 함수
async def generate_new_mcp_code(
    user_instruction: str,
    history: list,
    model_preference: ModelPreference = "auto"
) -> str:
    """
    'Agent Developer' 페르소나를 사용하여, 기존 MCP 스타일을 따른
    새로운 MCP 모듈 코드를 생성합니다. (RAG 활용)
    """
    
    # 고성능 모델 (텍스트 생성용, non-JSON)
    model_to_use = get_model(model_preference, default_type="high", needs_json=False)

    # RAG: 기존 MCP 파일 중 하나를 '스타일 가이드'로 읽어옵니다.
    style_guide_path = Path(MCP_DIRECTORY) / "file_content_operations.py"
    style_guide_code = ""
    try:
        if style_guide_path.exists():
            style_guide_code = style_guide_path.read_text(encoding='utf-8')
    except Exception as e:
        logging.warning(f"MCP 스타일 가이드 로드 실패: {e}")

    formatted_history = "\n".join(history[-10:]) 

    prompt = f"""
    당신은 'AI Agent Developer'입니다. 
    사용자가 '위험한 작업' (execute_shell_command 등)을 실행하는 대신, 
    더 안전하고 재사용 가능한 Python MCP(Mission Control Primitive) 모듈 생성을 요청했습니다.

    ## 사용자의 요청:
    {user_instruction}

    ## 현재 대화 및 오류 맥락:
    {formatted_history}

    ## [매우 중요] 코딩 스타일 가이드:
    새로 생성하는 MCP 코드는 반드시 다음 '예시 코드'의 스타일을 따라야 합니다.
    - `logging`을 사용해야 합니다.
    - `pathlib.Path`를 사용해야 합니다.
    - `typing` (List, Union, Optional 등)을 사용해야 합니다.
    - 명확한 Docstring을 포함해야 합니다. (Planner가 인식하는 데 필수)
    - 강력한 예외 처리(try...except, raise)를 포함해야 합니다.

    ## 예시 코드 (file_content_operations.py):
    ```python
    #!/usr/bin/env python3
    # -*- coding: utf-8 -*-
    import logging
    from pathlib import Path
    from typing import Union, List, ByteString

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    def _prepare_write_path(path: Union[str, Path]) -> Path:
        # ... (헬퍼 함수 예시) ...
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_file(path: Union[str, Path], encoding: str = 'utf-8') -> str:
        \"\"\"지정된 경로의 텍스트 파일 내용을 전부 읽어 문자열로 반환합니다.
        (Docstring 예시)
        \"\"\"
        logger.info(f"Attempting to read text file: {path}")
        try:
            p = Path(path).resolve(strict=True)
            if not p.is_file():
                raise IsADirectoryError(f"해당 경로는 파일이 아닙니다: {p}")
            return p.read_text(encoding=encoding)
        except FileNotFoundError as e:
            logger.error(f"Failed to read file {path}: {e}")
            raise
    ```

    ## 지시사항:
    사용자의 요청({user_instruction})을 해결할 수 있는 **단일 Python 함수**를 포함한 **완전한 MCP 모듈 파일 코드**를 생성하세요.
    - 다른 설명이나 대답, 마크다운 래퍼 없이 **오직 Python 코드**만 반환하세요.
    - 함수 이름은 작업 내용에 맞게 명확하게 (예: `combine_files`, `analyze_code_dependencies`) 지어주세요.
    
    # --- (*** 여기 ***) ---
    # (수정) f-string 오류를 피하기 위해 이중 중괄호 사용
    - 로그에서 실패한 `{{file_paths = $LAST_RESULT}}`와 같은 코드가 있다면, `file_paths: List[str]`를 인자로 받는 함수로 만들어야 합니다.
    # -----------------------

    ## 신규 MCP 모듈 코드:
    """

    try:
        response = await model_to_use.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"MCP 생성 AI 호출 실패: {e}")
        raise

# ... (기존 generate_final_answer, generate_title_for_conversation 함수) ...
async def generate_final_answer(
    history: list, 
    model_preference: ModelPreference = "auto"
) -> str:
    # ... (기존 코드와 동일) ...
    model_to_use = get_model(model_preference, default_type="standard", needs_json=False)
    # ... (기존 프롬프트 및 로직) ...
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
                raise ValueError("모델이 빈 응답을 반환했습니다.")
        return response.text.strip()
    except Exception as e:
        logging.error(f"Executor (generate_final_answer) 오류: {e}", exc_info=True)
        last_result = next((item for item in reversed(history) if item.startswith("  - 실행 결과:")), "N/A")
        return f"최종 요약 생성에 실패했습니다. 마지막 실행 결과입니다:\n{last_result}"

async def generate_title_for_conversation(
    history: list, 
    model_preference: ModelPreference = "auto"
) -> str:
    # ... (기존 코드와 동일) ...
    model_to_use = get_model(model_preference, default_type="standard", needs_json=False)
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
        response = await model_to_use.generate_content_async(summary_prompt)
        if not response.parts:
                return "요약_실패"
        return response.text.strip().replace("*", "").replace("`", "").replace("\"", "")
    except Exception:
        return "Untitled_Conversation"
