#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/agent_config_manager.py
"""에이전트 설정 관리 모듈 — 시스템 프롬프트, 스킬, 매크로, 워크플로우, 페르소나."""

import json
import logging
import re
from datetime import datetime
from .constants import utcnow
from pathlib import Path
from typing import Any, Dict, List, Optional

from .graph_manager import DB_PATH, get_db


# ── 인메모리 프롬프트 캐시 ────────────────────────────────────────
_PROMPT_CACHE: dict[str, str] = {}

# 매크로 변수 패턴 {{var}}
_MACRO_VAR_RE = re.compile(r'\{\{(\w+)\}\}')


def _apply_update(conn, table: str, name: str, now: str, **fields) -> None:
    """동적 UPDATE 쿼리를 빌드하여 실행합니다.

    fields에 포함된 None 값은 무시됩니다.
    """
    clauses = ["updated_at=?"]
    params: List[Any] = [now]
    for col, val in fields.items():
        if val is not None:
            clauses.append(f"{col}=?")
            params.append(val)
    params.append(name)
    conn.execute(f"UPDATE {table} SET {', '.join(clauses)} WHERE name=?", params)


# ── DB 초기화 ─────────────────────────────────────────────────────

def init_db(path: Path = DB_PATH) -> None:
    """에이전트 설정 5개 테이블을 IF NOT EXISTS로 생성."""
    with get_db(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS system_prompts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            content     TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            is_default  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );
        """)
        # prompt_type 컬럼 마이그레이션 (이미 존재하면 무시)
        try:
            conn.execute(
                "ALTER TABLE system_prompts ADD COLUMN prompt_type TEXT NOT NULL DEFAULT 'system'"
            )
        except Exception:
            pass
        conn.executescript("""

        CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            source      TEXT    NOT NULL DEFAULT 'local',
            description TEXT    NOT NULL DEFAULT '',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL,
            synced_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_macros (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL DEFAULT '',
            template    TEXT    NOT NULL,
            variables   TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflows (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL DEFAULT '',
            steps       TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS personas (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL UNIQUE,
            display_name      TEXT    NOT NULL DEFAULT '',
            system_prompt     TEXT    NOT NULL,
            system_prompt_ref TEXT    DEFAULT NULL,
            allowed_skills    TEXT    NOT NULL DEFAULT '[]',
            keywords          TEXT    NOT NULL DEFAULT '[]',
            description       TEXT    NOT NULL DEFAULT '',
            is_default        INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT    NOT NULL,
            updated_at        TEXT    NOT NULL
        );
        """)


# ── 프롬프트 시드 데이터 ─────────────────────────────────────────

_DEFAULT_PROMPTS: List[tuple] = [
    # (name, prompt_type, description, content)
    (
        "react_planner_system",
        "system",
        "ReAct 플래너 시스템 지시사항",
        "당신은 사용자의 목표를 달성하기 위해, '이전 대화'를 분석하여 '다음 1단계'의 계획을 수립하는 'ReAct 플래너'입니다.\n반드시 유효한 JSON만 응답하세요. 다른 텍스트는 포함하지 마세요.",
    ),
    (
        "react_planner_instruction",
        "template",
        "ReAct 플래너 사용자 메시지 템플릿 (변수: user_query, requirements_content, tool_descriptions, formatted_history)",
        """## 최종 목표 (사용자 최초 요청):
{user_query}

## 사용자가 제공한 추가 요구사항 및 컨텍스트:
{requirements_content}

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

## 다음 실행 계획 (JSON):""",
    ),
    (
        "final_answer_system",
        "system",
        "최종 답변 생성 시스템 프롬프트",
        "당신은 AI 에이전트입니다. 작업 기록을 바탕으로 사용자에게 최종 답변을 한국어로 생성합니다.",
    ),
    (
        "final_answer_user",
        "template",
        "최종 답변 생성 사용자 메시지 템플릿 (변수: history_str)",
        """다음은 AI 에이전트와 사용자의 작업 기록 요약입니다.
모든 작업이 완료되었습니다.
전체 '실행 결과'와 '사용자 목표'를 바탕으로 사용자에게 제공할 최종적이고 종합적인 답변을 한국어로 생성해주세요.

--- 작업 기록 요약 ---
{history_str}
---

최종 답변:""",
    ),
    (
        "extract_keywords_system",
        "system",
        "키워드 추출 시스템 프롬프트",
        "당신은 텍스트에서 핵심 키워드를 추출하는 전문가입니다. 반드시 JSON 배열만 응답하세요.",
    ),
    (
        "extract_keywords_user",
        "template",
        "키워드 추출 사용자 메시지 템플릿 (변수: history_str)",
        """다음 대화에서 핵심 키워드를 5~10개 추출해주세요.
명사 위주로, 한국어/영어 혼용 가능합니다.

--- 대화 내용 ---
{history_str}
---

JSON 배열로만 응답하세요. 예: ["FastAPI", "SQLite", "ReAct", "Python"]""",
    ),
    (
        "detect_topic_split_system",
        "system",
        "주제 분리 감지 시스템 프롬프트",
        "당신은 대화 분석 전문가입니다. 반드시 JSON 형식만 응답하세요.",
    ),
    (
        "detect_topic_split_user",
        "template",
        "주제 분리 감지 사용자 메시지 템플릿 (변수: history_str)",
        """다음 대화에서 주제가 크게 전환된 지점이 있는지 분석해주세요.

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
주제 전환이 없으면 detected를 false로 응답하세요.""",
    ),
    (
        "generate_title_system",
        "system",
        "대화 제목 생성 시스템 프롬프트",
        "당신은 대화를 간결하게 요약하는 전문가입니다.",
    ),
    (
        "generate_title_user",
        "template",
        "대화 제목 생성 사용자 메시지 템플릿 (변수: msg0, msg1)",
        """다음 대화 내용을 바탕으로, 어떤 작업을 수행했는지 알 수 있도록 5단어 이내의 간결한 '요약'을 한국어로 만들어줘.

--- 대화 내용 (초반 2개) ---
{msg0}
{msg1}
---

요약:""",
    ),
    (
        "clarifying_questions_user",
        "template",
        "명확화 질문 생성 템플릿 (변수: user_query)",
        """사용자가 다음 작업을 요청했습니다:

"{user_query}"

실행하기 전에 범위, 모호한 부분, 전제 조건을 명확히 하기 위해 사용자에게 물어봐야 할 핵심 질문 3~5개를 JSON 배열 형식으로만 반환하세요.
예시: ["질문1", "질문2", "질문3"]
질문이 불필요하면 빈 배열 []을 반환하세요.""",
    ),
    (
        "summarize_history_user",
        "template",
        "히스토리 요약 템플릿 (변수: excerpt)",
        "다음은 AI 에이전트와의 대화 이력입니다. 핵심 작업 내용, 완료된 항목, 미완료 항목, 중요한 결정 사항만 3~5문장으로 간결하게 요약하세요:\n\n{excerpt}",
    ),
    (
        "classify_intent_user",
        "template",
        "의도 분류 템플릿 (변수: user_query)",
        """사용자 요청: "{user_query}"

위 요청이 단순 질문/대화('chat')인지, 파일·코드·시스템 도구 사용이 필요한 작업('task')인지 한 단어로만 답하세요: chat 또는 task""",
    ),
    (
        "classify_intent_full_user",
        "template",
        "5-카테고리 의도 분류 템플릿 (변수: user_query)",
        """사용자 요청을 아래 5개 카테고리 중 하나로 분류하세요.

카테고리:
- dialogue: 단순 질문, 설명 요청, 대화 (도구 불필요)
- code_write: 코드 작성/수정/리팩터링/버그 수정
- file_ops: 파일/디렉토리 생성/읽기/수정/삭제
- web_search: 정보 검색, 웹 조회, 문서 조회
- analysis: 코드/데이터/로그 분석, 리뷰, 설명

요청: {user_query}

응답은 카테고리 이름 하나만 출력하세요 (다른 내용 없이).""",
    ),
    (
        "intent_code_write_system",
        "system",
        "코드 작성 의도 시스템 프롬프트",
        "당신은 전문 소프트웨어 엔지니어입니다. 코드 품질, 가독성, 유지보수성을 최우선으로 합니다. 기존 코드 스타일을 유지하고 테스트 가능한 코드를 작성합니다.",
    ),
    (
        "intent_file_ops_system",
        "system",
        "파일 조작 의도 시스템 프롬프트",
        "당신은 파일 및 디렉토리 조작 전문가입니다. 안전한 파일 처리, 원자적 쓰기, 백업 전략을 우선합니다. 삭제·덮어쓰기 전 반드시 확인합니다.",
    ),
    (
        "intent_search_system",
        "system",
        "웹 검색 의도 시스템 프롬프트",
        "당신은 정보 검색 전문가입니다. 정확한 출처를 명시하고, 여러 소스를 교차 검증합니다. 검색 결과를 구조화하여 제공합니다.",
    ),
    (
        "intent_analysis_system",
        "system",
        "분석 의도 시스템 프롬프트",
        "당신은 코드 분석 전문가입니다. 데이터를 읽고 패턴을 발견하며 구체적인 개선점을 제시합니다. 분석 근거를 명확히 설명합니다.",
    ),
    (
        "intent_dialogue_system",
        "system",
        "대화 의도 시스템 프롬프트",
        "당신은 친절하고 전문적인 AI 어시스턴트입니다. 명확하고 간결하게 답변합니다.",
    ),
    (
        "design_user",
        "template",
        "설계 생성 템플릿 (변수: system_ctx, history_ctx, user_query)",
        """{system_ctx}{history_ctx}사용자 요청:
"{user_query}"

위 요청을 분석하여 아래 JSON 형식으로 설계를 반환하세요. 반드시 JSON만 반환하고 다른 텍스트는 포함하지 마세요.

{{
  "goal": "최종 목표 한 줄 요약",
  "approach": "접근 방법 2-3문장",
  "constraints": ["제약사항1", "제약사항2"],
  "expected_outputs": ["결과물1", "결과물2"],
  "complexity": "simple 또는 medium 또는 complex"
}}""",
    ),
    (
        "decompose_tasks_user",
        "template",
        "태스크 분해 템플릿 (변수: design_text, user_query)",
        """설계 내용:
{design_text}

사용자 원래 요청: "{user_query}"

위 설계를 독립적으로 실행 가능한 태스크로 분해하세요. 최대 10개, JSON 배열만 반환하세요.

[{{"title": "태스크 제목", "description": "무엇을 해야 하는지 구체적 설명"}}, ...]""",
    ),
    (
        "map_plans_user",
        "template",
        "계획 매핑 템플릿 (변수: task_title, task_description, tools_str)",
        """태스크: {task_title}
설명: {task_description}

사용 가능한 도구 목록: {tools_str}

위 태스크를 실행 순서대로 분해하세요. 각 단계는 하나의 도구 호출로 처리 가능해야 합니다. 최대 8단계, JSON 배열만 반환하세요.

[{{"action": "무엇을 할 것인지 설명", "tool_hints": ["도구명1", "도구명2"]}}, ...]""",
    ),
    (
        "build_execution_group_user",
        "template",
        "실행 그룹 생성 템플릿 (변수: history_ctx, goal, task_title, step_action, tool_hints, tools_desc)",
        """{history_ctx}전체 목표: {goal}
현재 태스크: {task_title}
현재 단계: {step_action}
예상 도구 힌트: {tool_hints}

사용 가능한 도구:
{tools_desc}

위 단계를 실행하기 위한 도구 호출을 JSON으로 반환하세요. 반드시 아래 형식만 반환하고, 도구가 필요 없으면 tasks를 빈 배열로 하세요.

{{
  "group_id": "group_1",
  "description": "이 단계에서 하는 일 설명",
  "tasks": [
    {{"tool_name": "도구이름", "arguments": {{"인자명": "값"}}, "model_preference": "standard"}}
  ]
}}""",
    ),
    (
        "adapt_template_user",
        "template",
        "템플릿 인자 적응 템플릿 (변수: history_ctx, goal, task_title, step_action, template_json)",
        """{history_ctx}현재 목표: {goal}
현재 태스크: {task_title}
현재 단계: {step_action}

아래는 이전에 성공한 실행 템플릿입니다:
{template_json}

위 템플릿의 arguments 값만 현재 컨텍스트에 맞게 수정하세요.
반드시 지켜야 할 규칙:
  1. tool_name은 절대 변경하지 마세요.
  2. tasks 배열의 길이와 순서를 유지하세요.
  3. arguments의 키(key)는 변경하지 마세요, 값(value)만 수정하세요.
  4. 수정이 불필요한 arguments는 그대로 유지하세요.
수정된 전체 JSON만 반환하세요 (설명 없이).""",
    ),
    (
        "role_planner",
        "system",
        "Planner 역할 시스템 프롬프트",
        (
            "당신은 계획 수립 전문가(Planner)입니다. "
            "주어진 작업을 명확하고 실행 가능한 단계별 계획으로 분해하세요. "
            "병렬 실행 가능한 단계는 같은 그룹에 배치하고, "
            "각 그룹은 독립적으로 완료될 수 있어야 합니다."
        ),
    ),
    (
        "role_reviewer",
        "system",
        "Reviewer 역할 시스템 프롬프트",
        (
            "당신은 결과 검토 전문가(Reviewer)입니다. "
            "이전 실행 결과를 면밀히 검토하고, 작업이 완전히 완료되었는지 확인하세요. "
            "미완료 항목이 있으면 다음 실행 단계를 계획하고, "
            "모든 작업이 완료되었으면 반드시 빈 계획([])을 반환하세요."
        ),
    ),
    (
        "extract_wisdom_user",
        "template",
        "도구 실행 결과 학습 추출 템플릿 (변수: tool_results, context)",
        """다음 도구 실행 결과에서 재사용 가능한 학습 사항을 추출하세요.

[실행 결과]
{tool_results}

[작업 맥락]
{context}

JSON 배열로 반환 (학습 가치 있는 항목만, 없으면 []):
[{{"category":"conventions|successes|failures|gotchas|commands","content":"내용","source_tool":"도구명"}}]

category 의미: conventions=코딩규칙, successes=성공패턴, failures=실패/오류, gotchas=주의사항, commands=유용한명령어""",
    ),
    (
        "react_planner_parallel_note",
        "system",
        "병렬 플래닝 모드 추가 지시사항 (react_planner_system에 덧붙임)",
        """[병렬 실행 모드 활성화]
여러 그룹 반환이 허용됩니다. 다음 기준으로 그룹을 분리하세요:
- 서로 입출력 의존이 없는 태스크 → 별도 그룹, "can_parallel": true
- 이전 그룹 결과가 필요한 태스크 → 별도 그룹, "can_parallel": false
- 단, 진정 독립적인 경우만 can_parallel: true로 설정 (의존성 있는데 병렬로 표시 금지)

완료 시 빈 리스트 []를 반환하세요.""",
    ),
    (
        "classify_intent_and_category_user",
        "template",
        "의도 + 복잡도 통합 분류 템플릿 (변수: user_query)",
        """사용자 요청을 분석하여 아래 두 값을 반환하세요.

요청: {user_query}

[intent] 다음 중 하나:
- dialogue: 단순 질문, 설명, 대화 (도구 불필요)
- code_write: 코드 작성/수정/리팩터링
- file_ops: 파일/디렉토리 생성/수정/삭제
- web_search: 정보 검색, 웹 조회
- analysis: 코드/데이터/로그 분석

[complexity] 다음 중 하나:
- quick: 단순 작업 (5단어 이내 또는 사소한 변경)
- deep: 일반 작업
- ultrabrain: 전체 아키텍처/설계/대규모 리팩터링
- visual: UI/CSS/화면/디자인 관련

두 값만 아래 형식으로 출력 (다른 내용 없이):
intent: <값>
complexity: <값>""",
    ),
    (
        "validate_plan_user",
        "template",
        "실행 계획 검증 템플릿 (변수: available_tools, plan_json)",
        """다음 실행 계획의 품질을 검증하세요.

[사용 가능한 도구]
{available_tools}

[실행 계획 JSON]
{plan_json}

JSON으로 반환:
{{"valid":true,"score":0.0~1.0,"issues":["문제점"],"suggestions":["개선안"]}}

검증 기준 (각 위반시 점수 감점):
- tool_name이 사용 가능 목록에 없음: -0.4/개
- 필수 인자 누락 의심: -0.1/개
- 논리적 흐름 불명확: -0.2
- 완료 조건 없음: -0.1
score < 0.6이면 valid=false""",
    ),
    (
        "tool_implementation_user",
        "template",
        "도구 구현 생성 템플릿 (변수: tool_hint, context)",
        """다음 기능을 수행하는 Python 함수를 작성하세요:

함수 이름: {tool_hint}
컨텍스트: {context}

요구사항:
  1. 함수 이름은 정확히 위에서 지정한 이름으로 작성하세요.
  2. 적절한 타입 힌트와 docstring을 포함하세요.
  3. os, subprocess, eval, exec는 절대 사용하지 마세요.
  4. 파일 쓰기/삭제 작업은 하지 마세요 (읽기만 허용).
  5. 표준 라이브러리만 사용하세요 (json, re, pathlib, typing 등).
  6. 함수 코드만 반환하세요 (import문 포함 가능, 주석 허용).

Python 코드만 반환하세요:""",
    ),
]


def _seed_default_prompts(db_path: Path = DB_PATH) -> None:
    """기본 프롬프트 22개를 INSERT OR IGNORE로 삽입합니다 (멱등성 보장)."""
    now = utcnow()
    with get_db(db_path) as conn:
        for name, prompt_type, description, content in _DEFAULT_PROMPTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO system_prompts
                    (name, content, description, is_default, prompt_type, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (name, content, description, prompt_type, now, now),
            )


def get_prompt(name: str, db_path: Path = DB_PATH) -> str:
    """캐시 우선으로 프롬프트 내용을 반환합니다. 없으면 KeyError 발생."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    row = get_system_prompt(name, db_path)
    if row is None:
        raise KeyError(f"프롬프트 '{name}'을 찾을 수 없습니다.")
    _PROMPT_CACHE[name] = row["content"]
    return row["content"]


def render_prompt(name: str, db_path: Path = DB_PATH, **kwargs) -> str:
    """프롬프트 템플릿을 로드하여 변수를 치환합니다 (format_map 사용)."""
    content = get_prompt(name, db_path)
    return content.format_map(kwargs)


# ── 자동 초기화 ──────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    logging.warning(f"agent_config_manager DB 자동 초기화 실패: {_e}")

try:
    _seed_default_prompts()
except Exception as _e:
    logging.warning(f"agent_config_manager 프롬프트 시드 실패: {_e}")


# ── 시스템 프롬프트 CRUD ─────────────────────────────────────────

def create_system_prompt(
    name: str,
    content: str,
    description: str = "",
    is_default: bool = False,
    db_path: Path = DB_PATH,
) -> int:
    """시스템 프롬프트 생성. is_default=True면 기존 기본값 해제 후 설정."""
    now = utcnow()
    with get_db(db_path) as conn:
        if is_default:
            conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
        cur = conn.execute(
            """
            INSERT INTO system_prompts (name, content, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, content, description, int(is_default), now, now),
        )
        return cur.lastrowid


def get_system_prompt(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM system_prompts WHERE name=?", (name,)
        ).fetchone()
        return dict(row) if row else None


def get_default_system_prompt(db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM system_prompts WHERE is_default=1 LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def list_system_prompts(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM system_prompts ORDER BY is_default DESC, name"
        ).fetchall()
        return [dict(r) for r in rows]


def update_system_prompt(
    name: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    is_default: Optional[bool] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM system_prompts WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if is_default is True:
            conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
        try:
            _apply_update(
                conn, "system_prompts", name, now,
                content=content,
                description=description,
                is_default=int(is_default) if is_default is not None else None,
            )
        finally:
            _PROMPT_CACHE.pop(name, None)
        return True


def delete_system_prompt(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM system_prompts WHERE name=?", (name,))
        _PROMPT_CACHE.pop(name, None)
        return cur.rowcount > 0


def migrate_prompts_from_files(
    prompts_dir: str,
    db_path: Path = DB_PATH,
) -> int:
    """system_prompts/*.txt → system_prompts 테이블. INSERT OR IGNORE (멱등). 마이그레이션 수 반환."""
    imported = 0
    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        logging.warning(f"프롬프트 디렉토리가 없습니다: {prompts_dir}")
        return 0

    for txt_file in sorted(prompts_path.glob("*.txt")):
        name = txt_file.stem
        try:
            content = txt_file.read_text(encoding="utf-8")
        except Exception as e:
            logging.warning(f"파일 읽기 실패 {txt_file}: {e}")
            continue

        is_default = name == "default"
        now = utcnow()
        with get_db(db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM system_prompts WHERE name=?", (name,)
            ).fetchone()
            if existing:
                continue
            if is_default:
                conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
            conn.execute(
                """
                INSERT INTO system_prompts (name, content, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, content, f"파일에서 임포트: {txt_file.name}", int(is_default), now, now),
            )
        imported += 1

    return imported


# ── 스킬 CRUD ────────────────────────────────────────────────────

def sync_skills_from_registry(db_path: Path = DB_PATH) -> int:
    """tool_registry의 로컬 모듈을 로드하고 skills 테이블과 동기화. 신규 추가 수 반환."""
    from .tool_registry import _load_local_modules, TOOL_DESCRIPTIONS

    _load_local_modules()

    now = utcnow()
    added = 0
    updated = 0

    for tool_name, description in TOOL_DESCRIPTIONS.items():
        with get_db(db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM skills WHERE name=?", (tool_name,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE skills SET description=?, synced_at=? WHERE name=?",
                    (description, now, tool_name),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO skills (name, source, description, is_active, created_at, synced_at)
                    VALUES (?, 'local', ?, 1, ?, ?)
                    """,
                    (tool_name, description, now, now),
                )
                added += 1

    total = len(TOOL_DESCRIPTIONS)
    logging.info(
        f"스킬 동기화 완료: 신규 {added}개 추가, 기존 {updated}개 갱신 "
        f"(전체 {total}개 처리)"
    )
    return added


def list_skills(active_only: bool = True, db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM skills WHERE is_active=1 ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]


def get_skill(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None


def set_skill_active(name: str, active: bool, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute(
            "UPDATE skills SET is_active=? WHERE name=?", (int(active), name)
        )
        return cur.rowcount > 0


# ── 스킬 매크로 CRUD ─────────────────────────────────────────────

def create_macro(
    name: str,
    template: str,
    description: str = "",
    variables: Optional[List[str]] = None,
    db_path: Path = DB_PATH,
) -> int:
    """스킬 매크로 생성. variables 미제공 시 {{var}} 패턴으로 자동 추출."""
    if variables is None:
        variables = _MACRO_VAR_RE.findall(template)
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO skill_macros (name, description, template, variables, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, template, json.dumps(variables, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def get_macro(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM skill_macros WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["variables"] = json.loads(d["variables"])
        return d


def list_macros(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM skill_macros ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["variables"] = json.loads(d["variables"])
            result.append(d)
        return result


def update_macro(
    name: str,
    template: Optional[str] = None,
    description: Optional[str] = None,
    variables: Optional[List[str]] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id, template FROM skill_macros WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if template is not None and variables is None:
            variables = _MACRO_VAR_RE.findall(template)
        _apply_update(
            conn, "skill_macros", name, now,
            template=template,
            description=description,
            variables=json.dumps(variables, ensure_ascii=False) if variables is not None else None,
        )
        return True


def delete_macro(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM skill_macros WHERE name=?", (name,))
        return cur.rowcount > 0


def render_macro(name: str, bindings: Dict[str, str], db_path: Path = DB_PATH) -> str:
    """매크로 템플릿에 변수 바인딩 적용. 누락된 변수는 KeyError 발생."""
    macro = get_macro(name, db_path)
    if not macro:
        raise KeyError(f"매크로 '{name}'을 찾을 수 없습니다.")
    template = macro["template"]
    variables = macro["variables"]
    for var in variables:
        if var not in bindings:
            raise KeyError(f"매크로 '{name}': 변수 '{var}'가 bindings에 없습니다.")
    result = template
    for key, value in bindings.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# ── 워크플로우 CRUD ──────────────────────────────────────────────

def create_workflow(
    name: str,
    steps: List[Dict],
    description: str = "",
    db_path: Path = DB_PATH,
) -> int:
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO workflows (name, description, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, json.dumps(steps, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def get_workflow(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM workflows WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["steps"] = json.loads(d["steps"])
        return d


def list_workflows(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d["steps"])
            result.append(d)
        return result


def update_workflow(
    name: str,
    steps: Optional[List[Dict]] = None,
    description: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM workflows WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        _apply_update(
            conn, "workflows", name, now,
            steps=json.dumps(steps, ensure_ascii=False) if steps is not None else None,
            description=description,
        )
        return True


def delete_workflow(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM workflows WHERE name=?", (name,))
        return cur.rowcount > 0


# ── 페르소나 CRUD ────────────────────────────────────────────────

def create_persona(
    name: str,
    system_prompt: str,
    allowed_skills: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    description: str = "",
    display_name: str = "",
    system_prompt_ref: Optional[str] = None,
    is_default: bool = False,
    db_path: Path = DB_PATH,
) -> int:
    now = utcnow()
    if allowed_skills is None:
        allowed_skills = []
    if keywords is None:
        keywords = []
    with get_db(db_path) as conn:
        if is_default:
            conn.execute("UPDATE personas SET is_default=0 WHERE is_default=1")
        cur = conn.execute(
            """
            INSERT INTO personas
                (name, display_name, system_prompt, system_prompt_ref,
                 allowed_skills, keywords, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                display_name,
                system_prompt,
                system_prompt_ref,
                json.dumps(allowed_skills, ensure_ascii=False),
                json.dumps(keywords, ensure_ascii=False),
                description,
                int(is_default),
                now,
                now,
            ),
        )
        return cur.lastrowid


def _parse_persona_row(row) -> Dict:
    d = dict(row)
    d["allowed_skills"] = json.loads(d["allowed_skills"])
    d["keywords"] = json.loads(d["keywords"])
    return d


def get_persona(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM personas WHERE name=?", (name,)).fetchone()
        return _parse_persona_row(row) if row else None


def list_personas(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM personas ORDER BY is_default DESC, name"
        ).fetchall()
        return [_parse_persona_row(r) for r in rows]


def update_persona(
    name: str,
    system_prompt: Optional[str] = None,
    allowed_skills: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    description: Optional[str] = None,
    display_name: Optional[str] = None,
    system_prompt_ref: Optional[str] = None,
    is_default: Optional[bool] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM personas WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if is_default is True:
            conn.execute("UPDATE personas SET is_default=0 WHERE is_default=1")
        _apply_update(
            conn, "personas", name, now,
            system_prompt=system_prompt,
            allowed_skills=json.dumps(allowed_skills, ensure_ascii=False) if allowed_skills is not None else None,
            keywords=json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
            description=description,
            display_name=display_name,
            system_prompt_ref=system_prompt_ref,
            is_default=int(is_default) if is_default is not None else None,
        )
        return True


def delete_persona(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM personas WHERE name=?", (name,))
        return cur.rowcount > 0


def get_effective_persona(
    query: str = "",
    explicit_name: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> Optional[Dict]:
    """
    페르소나 자동 감지 알고리즘:
    1. explicit_name 있음 → get_persona(explicit_name). 없으면 WARNING 후 Step 2로
    2. 모든 페르소나 로드 → keywords 있는 것만 스코어링
       score = sum(1 for kw in keywords if kw.lower() in query.lower())
       동점 → keywords 개수 많은 쪽(더 구체적) 우선
    3. best_score >= 1 → 해당 페르소나 반환
    4. 매치 없음 → is_default=1인 페르소나 반환
    5. 기본도 없음 → None 반환
    """
    if explicit_name:
        persona = get_persona(explicit_name, db_path)
        if persona:
            return persona
        logging.warning(f"페르소나 '{explicit_name}'을 찾을 수 없습니다. 자동 감지로 대체합니다.")

    personas = list_personas(db_path)
    query_lower = query.lower()

    best_persona = None
    best_score = 0
    best_kw_count = 0

    for persona in personas:
        keywords = persona.get("keywords", [])
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw.lower() in query_lower)
        kw_count = len(keywords)
        if score > best_score or (score == best_score and score >= 1 and kw_count > best_kw_count):
            best_score = score
            best_kw_count = kw_count
            best_persona = persona

    if best_score >= 1:
        return best_persona

    # is_default 페르소나 반환
    for persona in personas:
        if persona.get("is_default"):
            return persona

    return None
