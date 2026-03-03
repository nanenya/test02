# test02 프로젝트 분석 보고서

---
---

## 0. 요구사항 추적 (Requirements Tracker)

> **이 섹션은 매 작업 요청 시 갱신됩니다.**
> 마지막 갱신: 2026-03-01 (4층 파이프라인 Phase 1-4 구현 완료 + GitHub push)

### 0.1 완료된 요구사항 (Completed)

> DB 관리: `history/conversations.db` → `requirements` 테이블
> 조회: `python -m claude_tools tracker requirements`

### 0.2 진행 중인 요구사항 (In Progress)

> DB 관리: `history/conversations.db` → `requirements` 테이블 (`status = 'IN_PROGRESS'`)
> 조회: `python -m claude_tools tracker inprogress`
> 상태 변경: `python -m claude_tools req move <번호> inprogress`

### 0.3 미구현 / 예정 요구사항 (Pending / Backlog)

> DB 관리: `history/conversations.db` → `requirements` 테이블 (`status = 'PENDING'`)
> 조회: `python -m claude_tools tracker pending`
> 상태 변경: `python -m claude_tools req move <번호> pending`

### 0.4 변경 이력 (Change Log)

> DB 관리: `history/conversations.db` → `change_log` 테이블
> 조회: `python -m claude_tools tracker changes`

---
---

## 1. 프로젝트 개요

**프로젝트명**: Multi-Provider Agent Orchestrator
**언어/런타임**: Python 3.12
**아키텍처**: ReAct (Reasoning + Acting) 기반 AI 에이전트 오케스트레이터
**LLM 백엔드**: Google Gemini / Anthropic Claude / Ollama (로컬) — llm_client.py가 활성 프로바이더로 라우팅
**핵심 프레임워크**: FastAPI (서버), Typer (CLI), MCP (Model Context Protocol)

이 프로젝트는 사용자의 자연어 명령을 받아, LLM이 실행 계획을 수립하고, 등록된 도구(MCP)를 순차적으로 실행하여 작업을 완수하는 AI 에이전트 시스템입니다.

---

## 2. 디렉토리 구조

```
test02/
├── main.py                      # CLI 진입점 (Typer 앱)
├── requirements.txt             # Python 의존성
├── start.sh                     # venv 활성화 스크립트
├── pytest.ini                   # pytest 설정
├── mcp_servers.json             # MCP 서버 레지스트리 (mcp_manager)
├── model_config.json            # LLM 프로바이더/모델 설정 (model_manager)
├── .gitignore
├── orchestrator/                # 핵심 오케스트레이터 패키지
│   ├── __init__.py              # 패키지 초기화 (로깅 설정)
│   ├── config.py                # MCP 서버 및 로컬 모듈 설정
│   ├── models.py                # Pydantic 데이터 모델 정의
│   ├── api.py                   # FastAPI 엔드포인트 (핵심 ReAct 루프)
│   ├── web_router.py            # 웹 UI용 /api/v1 REST API (16개 엔드포인트)
│   ├── llm_client.py            # LLM 라우터 (활성 프로바이더로 위임)
│   ├── gemini_client.py         # Gemini API 통신 (플래너, 답변 생성)
│   ├── claude_client.py         # Anthropic Claude API (gemini_client와 동일 인터페이스)
│   ├── ollama_client.py         # Ollama 로컬 LLM 통신
│   ├── history_manager.py       # 얇은 어댑터 — graph_manager에 위임
│   ├── graph_manager.py         # SQLite 대화/그룹/토픽/키워드 관리
│   ├── tool_registry.py         # 도구 등록소 (로컬 + MCP 서버)
│   ├── mcp_manager.py           # MCP 서버 레지스트리 (mcp_servers.json)
│   ├── mcp_db_manager.py        # MCP 함수 DB 관리 (버전/테스트/exec)
│   ├── model_manager.py         # LLM 프로바이더/모델 설정 관리
│   ├── agent_config_manager.py  # 시스템 프롬프트/스킬/매크로/워크플로우/페르소나
│   ├── issue_tracker.py         # 런타임 에러 자동 저장
│   ├── token_tracker.py         # ContextVar 기반 토큰/비용 누적 추적
│   ├── constants.py             # 전역 상수 (MAX_HISTORY_ENTRIES, HISTORY_MAX_CHARS, utcnow)
│   ├── pipeline_db.py           # 4층 파이프라인 DB (7개 테이블: designs/tasks/task_plans/templates/cache/gap/cursor)
│   ├── pipeline_manager.py      # 파이프라인 상태머신 (Design→Task→Plan→ExecGroup)
│   ├── template_engine.py       # 실행 템플릿 스코어링 + LLM 인자 적응
│   ├── tool_discoverer.py       # 도구 발견 (로컬→npm MCP→Python 자동구현) + 보안 검증
│   ├── llm_router.py            # 단계별 LLM 티어 자동 라우팅 (high/standard + 예산 강등)
│   └── test_*.py                # 각 모듈 단위 테스트 (17개 파일, 343개 통과)
├── mcp_modules/                 # MCP Python 모듈
│   ├── __init__.py
│   └── hashline_editor.py       # Hashline 파일 편집 모듈
│                                # ※ 이전 Python 구현체는 #34에서 SQLite DB로 이전 후 삭제됨
│                                # 현재 모듈은 tool_registry.py의 DB 우선 로드(mcp_db_manager)로 메모리에 로드
├── mcp_cache/                   # MCP 서버 캐시 (index.html 등)
├── static/                      # 웹 UI 정적 파일 (index.html)
├── claude_tools/                # 프로젝트 분석 자동화 도구 (토큰 절약용)
│   ├── __init__.py
│   ├── __main__.py              # CLI 진입점 (python -m claude_tools <cmd>)
│   ├── project_scanner.py       # 프로젝트 구조/함수 스냅샷 생성
│   ├── change_tracker.py        # 이전 스냅샷 대비 변경 감지
│   ├── report_updater.py        # PROJECT_ANALYSIS.md 섹션 11,12 자동 갱신
│   ├── report_validator.py      # 섹션 2/6/7 자동 검증 (불일치 경고)
│   └── project_tracker.py       # MD 정적 섹션 → SQLite DB 관리 (requirements/change_log/deleted_files/test_status)
├── venv/                        # Python 가상환경
├── system_prompts/              # 시스템 프롬프트 파일 (자동 생성)
└── history/                     # SQLite DB (conversations.db) + JSON 마이그레이션 이력
```

---

## 3. 핵심 아키텍처 흐름

### 3.1 ReAct 루프 (기존 엔드포인트 — `/agent/decide_and_act`)

```
사용자 CLI 입력
  → main.py (Typer CLI)
    → POST /agent/decide_and_act (api.py)
      → llm_client.generate_execution_plan()  (활성 프로바이더로 라우팅)
        → LLM이 "다음 1개 실행 그룹" 생성
      → 사용자에게 PLAN_CONFIRMATION 반환
    → 사용자 승인
    → POST /agent/execute_group (api.py)
      → tool_registry.get_tool() → 도구 실행
      → STEP_EXECUTED 반환
    → POST /agent/decide_and_act (재진입: user_input=None)
      → 이전 결과 기반 "다음 단계" 계획
      → ...반복...
    → Gemini가 빈 리스트 [] 반환 시
      → generate_final_answer()로 최종 답변 생성
      → FINAL_ANSWER 반환 → 루프 종료
```

### 3.2 4층 파이프라인 (신규 엔드포인트 — `/agent/pipeline`)

```
사용자 쿼리
  → POST /agent/pipeline (api.py)
      → [Layer 1] 설계 생성 (llm_router: high tier)
          → llm_client.generate_design()
          → pipeline_db.create_design()
          → DESIGN_CONFIRMATION 반환 → 사용자 확인
      → pipeline_action="confirm_design"
          → [Layer 2] 태스크 분해 (standard tier)
              → llm_client.decompose_tasks()
              → pipeline_db.create_tasks()
          → [Layer 3] 계획 매핑 (캐시 우선)
              → _make_task_signature() → task_plan_cache 히트 시 LLM 호출 없음
              → 캐시 미스: llm_client.map_plans()
          → [Layer 4] 실행 그룹 빌드
              → template_engine.find_and_adapt(): 기존 템플릿 스코어링
              → 템플릿 없으면: llm_client.build_execution_group_for_step()
              → tool_discoverer.discover_and_resolve(): 누락 도구 발견
          → PLAN_CONFIRMATION 반환
  → POST /agent/pipeline/execute (api.py)
      → tool_registry.get_tool() → 도구 실행
      → pipeline_db.save_execution_template() (성공 시 템플릿 저장)
      → pipeline_db.increment_template_fail() (실패 시 자동 비활성화)
      → STEP_EXECUTED 반환
```

### 3.3 상태 흐름

| 상태 | 의미 |
|------|------|
| `PLAN_CONFIRMATION` | 다음 실행 그룹에 대한 사용자 승인 요청 |
| `DESIGN_CONFIRMATION` | 설계안 사용자 확인 요청 (4층 파이프라인) |
| `STEP_EXECUTED` | 그룹 실행 완료, 다음 계획 수립 트리거 |
| `FINAL_ANSWER` | 모든 작업 완료, 최종 답변 제공 |
| `ERROR` | 오류 발생 |

---

## 4. 핵심 모듈 상세 분석

### 4.1 orchestrator/config.py
- `LOCAL_MODULES`: DB 우선 로드 대상 모듈 이름 목록 (10개)
  - 파일이 삭제된 이후에도 목록을 유지해 tool_registry의 DB 조회 키로 사용
  - `mcp_modules/` 디렉토리는 비어 있음. 파일 fallback은 DB 미등록 시에만 시도
- `MCP_SERVERS`: 3개 외부 MCP 서버 연동
  - **filesystem** (@modelcontextprotocol/server-filesystem via npx)
  - **git** (mcp-server-git)
  - **fetch** (mcp-server-fetch)
- `TOOL_NAME_ALIASES`: 기존 도구명 → MCP 도구명 매핑 (하위 호환성)

### 4.2 orchestrator/models.py (Pydantic 모델)
- `AgentRequest`: CLI→서버 요청 (conversation_id, history, user_input, requirement_paths, model_preference, system_prompts)
- `GeminiToolCall`: 단일 도구 호출 정의 (tool_name, arguments, model_preference)
- `ExecutionGroup`: 여러 태스크의 논리적 그룹 (group_id, description, tasks)
- `AgentResponse`: 서버→CLI 응답 (status, history, message, execution_group)

### 4.3 orchestrator/gemini_client.py
- Gemini API (google-genai) 클라이언트
- API 키: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 환경변수 지원
- 모델 선택: `HIGH_PERF_MODEL` (기본: gemini-2.0-flash) / `STANDARD_MODEL` (기본: gemini-2.0-flash-lite)
  - 환경변수 `GEMINI_HIGH_PERF_MODEL`, `GEMINI_STANDARD_MODEL`로 오버라이드 가능
  - `_get_model_name()` 헬퍼로 preference/default_type에 따라 모델 결정
- `generate_execution_plan()`: ReAct 플래너 — `_truncate_history()`로 문자 예산(HISTORY_MAX_CHARS=6000) 기반 히스토리 제한, 다음 1개 ExecutionGroup 생성 또는 빈 리스트(완료)
- `generate_final_answer()`: 전체 작업 이력 기반 최종 답변 생성 — `_truncate_history()`로 최신부터 역순 누적, 예산 초과 시 중단
- `generate_title_for_conversation()`: 대화 제목 자동 생성 (5단어 이내, history 처음 2개만 사용)
- `_truncate_history()`: 문자 예산 기반 히스토리 잘라내기 — 최신 메시지부터 역순으로 누적, HISTORY_MAX_CHARS 초과 시 중단
- JSON 응답 모드 사용 (`response_mime_type="application/json"`)

### 4.4 orchestrator/api.py (FastAPI 엔드포인트)
- **`POST /agent/decide_and_act`**: ReAct 핵심 엔드포인트
  - user_input 있으면: 첫 계획 수립
  - user_input 없으면(STEP_EXECUTED 후): history 기반 다음 계획 또는 최종 답변
- **`POST /agent/execute_group`**: 저장된 단일 그룹 실행
  - 각 task의 tool 함수를 tool_registry에서 가져와 실행
  - async/sync 함수 자동 처리
- **web_router.py include_router** → `/api/v1/*` (16개 엔드포인트) 마운트

### 4.5 orchestrator/tool_registry.py
- **로컬 도구**: `_load_local_modules()` — DB 우선 로드 후 파일 fallback
  1. `mcp_db_manager.load_module_in_memory(module_name)` → DB에 활성 함수 있으면 exec()으로 메모리 로드
  2. DB 없거나 실패 시 `mcp_modules/{module_name}.py` 파일 import 시도 (현재 파일 없어 ERROR 로그 후 skip)
- **MCP 도구**: `_connect_mcp_server()` - StdioServerParameters로 MCP 서버 연결
- `get_tool()`: 도구명으로 함수 반환 (로컬 → 별칭 → MCP 순서로 검색)
- MCP 도구는 `session.call_tool()`을 감싸는 async wrapper로 제공

### 4.6 orchestrator/history_manager.py
- **얇은 어댑터 레이어** — `graph_manager`(SQLite DB)에 모든 기능 위임
- 기존 함수 시그니처 유지 (하위 호환): `save_history()`, `load_history()`, `list_histories()` 등
- JSON 파일 없음 (모든 이력은 `history/conversations.db`에 저장)
- UUID 파일명 / `_sanitize_title()` / 타임스탬프 변환 등 구 아키텍처 코드 제거됨

### 4.7 main.py (CLI)
- `server` 명령: FastAPI 서버 실행 (uvicorn, 포트 충돌 자동 처리)
- `run` 명령: 에이전트 상호작용 루프 (--query, --continue, --req, --model-pref, --gem)
- `list` 명령: 저장된 대화 목록 표시
- httpx 클라이언트로 오케스트레이터 서버와 통신 (timeout=120s)

### 4.8 orchestrator/llm_client.py
- **LLM 라우터** — `model_manager`에서 활성 프로바이더를 읽어 해당 클라이언트에 위임
- 지원 프로바이더: `gemini` → gemini_client, `claude` → claude_client, `ollama` → ollama_client
- 기존 공통 인터페이스: `generate_execution_plan()`, `generate_final_answer()`, `generate_title_for_conversation()`, `extract_keywords()`, `separate_topics()`
- **파이프라인 전용 추가** (Phase 1-2): `generate_design()`, `decompose_tasks()`, `map_plans()`, `build_execution_group_for_step()`, `adapt_template_arguments()`

### 4.9 orchestrator/claude_client.py
- Anthropic Claude API 클라이언트 (`anthropic` SDK)
- API 키: `ANTHROPIC_API_KEY` 환경변수
- `gemini_client.py`와 동일한 함수 인터페이스 구현

### 4.10 orchestrator/ollama_client.py
- Ollama 로컬 LLM 통신 (httpx, `OLLAMA_BASE_URL` 환경변수)
- `gemini_client.py`와 동일한 함수 인터페이스 구현
- 인터넷 연결 없이 오프라인 실행 가능

### 4.11 orchestrator/model_manager.py
- 5종 프로바이더(gemini/claude/openai/grok/ollama) 설정 관리
- 활성 프로바이더/모델을 `model_config.json`에 저장
- `fetch_models()`: 각 프로바이더 API 호출로 사용 가능한 모델 목록 조회

### 4.12 orchestrator/graph_manager.py
- **SQLite 기반** 대화/그룹/토픽/키워드 CRUD (`history/conversations.db`)
- 대화 UUID, 제목, 타임스탬프, 그룹/토픽 관계, 키워드 태깅
- `_fetch_keywords()` 헬퍼로 SQL 중복 제거

### 4.13 orchestrator/mcp_db_manager.py
- MCP 함수 버전관리 (등록/활성화/롤백), `ast.parse()` 사전 검증 후 `exec()`
- 함수 테스트 코드 저장 및 실행, 실행 통계/세션 추적
- `MAX_FUNC_NAMES_PER_SESSION=1000` 상한

### 4.14 orchestrator/mcp_manager.py
- MCP 서버 레지스트리 — `mcp_servers.json` 기반 CRUD
- 서버 활성화/비활성화, npm/PyPI 검색 지원

### 4.15 orchestrator/agent_config_manager.py
- 시스템 프롬프트 / 스킬 / 매크로 / 워크플로우 / 페르소나 CRUD (SQLite)
- `sync_skills()`: 로컬 모듈에서 스킬 자동 동기화 (added/updated/total 로깅)

### 4.16 orchestrator/issue_tracker.py
- 런타임 에러 자동 캡처 — FastAPI 전역 exception handler 연동
- 이슈 상태: open / resolved / ignored

### 4.17 orchestrator/web_router.py
- 웹 UI용 `/api/v1/*` REST API — FastAPIRouter, 총 16개 엔드포인트
- 대화/그룹/토픽/키워드/설정 조회·수정 API 제공

### 4.18 orchestrator/constants.py
- 전역 상수 중앙화: `MAX_HISTORY_ENTRIES=200`, `HISTORY_MAX_CHARS=6000`
- `utcnow()` 헬퍼: 시간대 일관성 보장 (UTC)

### 4.19 orchestrator/pipeline_db.py (Phase 1-2 신규)
- **7개 테이블**: designs, tasks, task_plans, execution_templates (is_active), task_plan_cache, tool_gap_log, pipeline_cursors
- 설계 CRUD: `create_design()`, `confirm_design()`, `get_active_design()`
- 태스크/계획: `create_tasks()`, `get_next_pending_task()`, `create_task_plans()`, `get_next_pending_plan()`
- 템플릿 관리: `save_execution_template()`, `find_best_template()`, `list_templates()`, `get_template()`, `disable_template()`, `enable_template()`, `delete_template()`, `get_template_stats()`, `auto_disable_failing_templates()`, `increment_template_fail()`
  - 자동 비활성화 조건: fail_rate ≥ 60% AND total_uses ≥ 3
- 캐시: `get_task_plan_cache()`, `save_task_plan_cache()` (SHA-256 시그니처 기반, use_count 추적)
- 도구 갭 로그: `log_tool_gap()`
- 파이프라인 커서: `set_cursor()`, `get_cursor()`, `clear_cursor()` (UPSERT)

### 4.20 orchestrator/pipeline_manager.py (Phase 1-2 신규)
- 4층 파이프라인 상태머신 — `start_design_phase()`, `proceed_after_design_confirm()`, `advance_after_execution()`, `record_execution_success()`
- `_make_task_signature(title, desc)` → 공백 정규화 → SHA-256[:24]
- `_map_plans_with_cache()` → task_plan_cache 히트 시 LLM 호출 생략
- `_build_and_return_step()` → template_engine 우선, LLM 폴백, 누락 도구 → tool_gap_log

### 4.21 orchestrator/template_engine.py (Phase 2 신규)
- 향상된 스코어링: `keyword_overlap + tool_match_bonus(+1.5/개) + success_rate_bonus(×3.0) - recency_penalty(30일당 -0.5, 최대 -3.0)`
- `SCORE_THRESHOLD = 4.0` 미만이면 None 반환 (새 LLM 호출로 대체)
- `find_best_template_scored()`, `adapt_template()` (도구명 변조 방지), `find_and_adapt()` (통합 진입점)

### 4.22 orchestrator/tool_discoverer.py (Phase 3 신규)
- **3단계 도구 발견**: registered_tools → npm MCP search → Python 자동 구현
- `_ALLOWED_COMMANDS = frozenset({"npm","npx","pip","pip3","uvx"})` — 화이트리스트
- `_DANGEROUS_PATTERNS` — os.system/subprocess/eval/exec/__import__/write-mode open/shutil.rmtree 정적 검사
- `_run_safe()`: 화이트리스트 + 인젝션 문자 차단 + `shell=False` 강제
- `_is_code_safe()`: 정규식 + `ast.parse()` 이중 검증
- 자동 생성 코드: `mcp_db_manager.add_function()` 비활성 상태로 저장 (사용자 검토 후 활성화)

### 4.23 orchestrator/llm_router.py (Phase 4 신규)
- 단계별 기본 티어: `design_generation=high`, `task_decomposition=standard`, `tool_implementation=high`, 나머지 `standard`
- 복잡도 오버라이드: standard 단계 + complex → high 상향
- 예산 기반 자동 강등: 누적 비용 ≥ $0.10 → high 금지 (standard 유지)
- `get_tier(stage, complexity, budget_usd, force)`, `route(stage, complexity, force)` — token_tracker 자동 연동
- `infer_complexity_from_query()` — 단어 수 + 복잡 키워드 휴리스틱 (≤5단어→simple, ≥20단어/복잡키워드→complex)

---

## 5. MCP 도구 모듈 현황

> **`mcp_modules/` 디렉토리**: `__init__.py` + `hashline_editor.py` (신규 추가됨)
> DB 우선 로드: SQLite DB(`history/conversations.db`)의 `mcp_functions` 테이블 → `mcp_db_manager.load_module_in_memory()`
> 자동 구현 도구: `tool_discoverer.generate_tool_implementation()` → 비활성 상태로 DB 저장 → 사용자 활성화 후 로드

### 5.1 이력 (삭제된 파일)

> DB 관리: `history/conversations.db` → `deleted_files` 테이블
> 조회: `python -m claude_tools tracker deleted`

### 5.2 현재 도구 로드 경로

```
tool_registry._load_local_modules()
  └─ DB 우선: mcp_db_manager.load_module_in_memory(module_name)
       ├─ 성공: exec() → TOOLS 딕셔너리에 등록
       └─ 실패/빈 DB: mcp_modules/{module_name}.py import 시도
            └─ 파일 없음 → ERROR 로그 후 skip (현재 상태)
```

---

## 6. 테스트 현황

> DB 관리: `history/conversations.db` → `test_status` 테이블 (validate 실행 시 자동 갱신)
> 조회: `python -m claude_tools tracker tests`
> 실행: `pytest` (pytest.ini: `pythonpath = .`)

---

## 7. 의존성 (requirements.txt)

| 패키지 | 용도 |
|--------|------|
| fastapi | 오케스트레이터 API 서버 |
| uvicorn[standard] | ASGI 서버 |
| python-multipart | FastAPI 파일 업로드 지원 |
| typer[all] | CLI 인터페이스 |
| rich | 터미널 UI (Rich 출력) |
| questionary | 대화형 사용자 입력 UI |
| pydantic | 데이터 모델 검증 |
| python-dotenv | .env 파일 로드 |
| google-genai | Gemini API 클라이언트 |
| anthropic | Claude API 클라이언트 |
| openai | OpenAI API 클라이언트 |
| mcp>=1.0.0 | MCP Python SDK |
| mcp-server-git | Git MCP 서버 |
| mcp-server-fetch | Fetch MCP 서버 |
| httpx | 비동기 HTTP 클라이언트 |
| requests_mock | 테스트용 HTTP 모킹 |
| feedparser | RSS 피드 파싱 |
| beautifulsoup4 | HTML 파싱 |
| aiosqlite | 비동기 SQLite 지원 |
| pytest-mock | 테스트용 모킹 |
| pytest-asyncio | async 테스트 지원 |

---

## 8. 보안 설계

> **참고**: mcp_modules/ 파일들(code_execution_atomic.py 등)은 변경 #34에서 DB 마이그레이션으로 삭제됨.
> 아래는 현재 활성 코드(orchestrator/)의 보안 설계.

- **입력 모델 검증** (`models.py`): `tool_name`/`group_id` 최대 100자, `description` 최대 500자, `arguments` 10KB 상한, `tasks` 50개 상한 (Pydantic field_validator)
- **히스토리 상한** (`api.py` + `constants.py`): `MAX_HISTORY_ENTRIES=200`으로 이력 폭증 방지 (`_prune_history()`)
- **도구 결과 잘림** (`api.py`): 1000자 초과 시 경고 로그 + 자동 truncate
- **DB 코드 실행 검증** (`mcp_db_manager.py`): `ast.parse()` 사전 검증 후 `exec()`, `func_names` 상한 `MAX_FUNC_NAMES_PER_SESSION=1000`
- **MCP 서버 화이트리스트** (`config.py`): `ALLOWED_MCP_COMMANDS`로 허용 명령어 제한
- **경로 검증** (`api.py`): `requirements_path` 파일 존재 여부 확인
- **SQL**: 파라미터화 쿼리 강제 (모든 DB 모듈)
- **UTC 타임스탬프** (`constants.py`): `utcnow()` 헬퍼로 시간대 일관성 보장
- **도구 발견 보안** (`tool_discoverer.py`, Phase 3 신규):
  - `_ALLOWED_COMMANDS` 화이트리스트: npm/npx/pip/pip3/uvx 외 모든 명령 차단
  - `_SHELL_INJECT_CHARS` (`;|&$\`(){}`) 포함 인자 즉시 차단
  - `shell=False` 강제 — 셸 인젝션 원천 차단
  - `_DANGEROUS_PATTERNS` + `ast.parse()` 이중 정적 검사 (os.system/subprocess/eval/exec/__import__/write-mode-open/shutil.rmtree)
  - 자동 생성 코드: 비활성(inactive) 상태로만 저장 — 사용자 수동 활성화 필요

---

## 9. 설정 및 실행 방법

```bash
# 가상환경 활성화
source venv/bin/activate

# .env 파일에 GEMINI_API_KEY 설정 필요
# GEMINI_API_KEY=your_api_key

# 서버 실행
python main.py server

# 새 쿼리 실행 (다른 터미널)
python main.py run --query "파일 목록을 조회해줘"

# 대화 이어가기
python main.py list
python main.py run --continue <대화ID>

# 시스템 프롬프트(Gem) 사용
python main.py run --query "..." --gem default

# 테스트 실행
pytest

# 4층 파이프라인 (신규)
python main.py run --query "..." --pipeline          # 파이프라인 모드 실행

# 실행 템플릿 관리
python main.py template list                          # 템플릿 목록
python main.py template show <id>                    # 상세 조회
python main.py template stats                        # 통계
python main.py template disable <id>                 # 비활성화
python main.py template enable <id>                  # 활성화
python main.py template delete <id>                  # 삭제

# 도구 갭 관리
python main.py gap report                            # 갭 보고서 조회
python main.py gap discover "<tool_hint>"            # 도구 발견 실행
```

---

## 10. 알려진 이슈 및 개선 포인트

> DB 관리: `history/conversations.db` → `issues` 테이블 (orchestrator/issue_tracker.py)
> 조회: `python -m claude_tools tracker issues`

---

## 11. 파일별 상세 카탈로그 (자동 생성)

> 자동 생성 시각: 2026-03-03T18:13:29
> Python 파일: 52개 | 함수: 495개 | 클래스: 111개 | 총 라인: 18744줄

### ./

#### `OMO_COMPARISON.md` (361줄, 18,415B)

#### `PROJECT_ANALYSIS.md` (2172줄, 126,131B)

#### `main.py` (2686줄, 117,327B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `list_conversations_cmd` | `group: Annotated[Optional[int], typer.Option("-...` | `-` | 저장된 대화 목록을 표시합니다. |
| `run` | `query: Annotated[str, typer.Option("--query", "...` | `-` | AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다. |
| `is_port_in_use` | `port: int, host: str` | `bool` | - |
| `run_server` | `host: Annotated[str, typer.Option(help="서버가 바인딩...` | `-` | FastAPI 오케스트레이터 서버를 실행합니다. |
| `graph_cmd` | `center: Annotated[Optional[str], typer.Option("...` | `-` | 대화 관계 그래프를 Rich 뷰로 출력합니다. |
| `migrate_cmd` | `dry_run: Annotated[bool, typer.Option("--dry-ru...` | `-` | 기존 JSON 히스토리를 SQLite로 마이그레이션합니다. |
| `group_list` | `` | `-` | 그룹 목록 표시. |
| `group_create` | `name: Annotated[str, typer.Argument(help="그룹 이름...` | `-` | 새 그룹 생성. |
| `group_delete` | `group_id: Annotated[int, typer.Argument(help="그...` | `-` | 그룹 삭제. |
| `group_add_convo` | `group_id: Annotated[int, typer.Argument(help="그...` | `-` | 대화를 그룹에 추가. |
| `group_remove_convo` | `group_id: Annotated[int, typer.Argument(help="그...` | `-` | 대화를 그룹에서 제거. |
| `topic_list` | `` | `-` | 토픽 목록 표시. |
| `topic_create` | `name: Annotated[str, typer.Argument(help="토픽 이름...` | `-` | 새 토픽 생성. |
| `topic_delete` | `topic_id: Annotated[int, typer.Argument(help="토...` | `-` | 토픽 삭제. |
| `topic_link` | `id_a: Annotated[int, typer.Argument(help="토픽 ID...` | `-` | 두 토픽을 양방향 연결. |
| `topic_add_convo` | `topic_id: Annotated[int, typer.Argument(help="토...` | `-` | 대화를 토픽에 추가. |
| `keyword_list` | `convo_id: Annotated[Optional[str], typer.Argume...` | `-` | 키워드 목록 표시. 대화 UUID를 지정하면 해당 대화의 키워드만 표시. |
| `keyword_edit` | `convo_id: Annotated[str, typer.Argument(help="대...` | `-` | 대화의 키워드를 수동으로 편집합니다. |
| `keyword_search` | `keyword: Annotated[str, typer.Argument(help="검색...` | `-` | 키워드로 대화를 검색합니다. |
| `mcp_list` | `all_servers: Annotated[bool, typer.Option("--al...` | `-` | 등록된 MCP 서버 목록을 표시합니다. |
| `mcp_add` | `name: Annotated[str, typer.Argument(help="서버 이름...` | `-` | MCP 서버를 레지스트리에 추가합니다. |
| `mcp_remove` | `name: Annotated[str, typer.Argument(help="제거할 서...` | `-` | MCP 서버를 레지스트리에서 제거합니다. |
| `mcp_search` | `query: Annotated[str, typer.Argument(help="검색 키...` | `-` | npm/PyPI에서 MCP 서버 패키지를 검색합니다. |
| `mcp_enable` | `name: Annotated[str, typer.Argument(help="활성화할 ...` | `-` | MCP 서버를 활성화합니다. |
| `mcp_disable` | `name: Annotated[str, typer.Argument(help="비활성화할...` | `-` | MCP 서버를 비활성화합니다. |
| `func_add` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 함수를 DB에 등록합니다. |
| `func_list` | `group: Annotated[Optional[str], typer.Option("-...` | `-` | 등록된 함수 목록을 표시합니다. |
| `func_versions` | `name: Annotated[str, typer.Argument(help="함수 이름")]` | `-` | 함수의 버전 이력을 표시합니다. |
| `func_show` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 함수 상세 정보 및 코드를 출력합니다. |
| `func_test` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 함수 테스트를 실행합니다. |
| `func_import` | `file: Annotated[str, typer.Argument(help="임포트할 ...` | `-` | Python 파일의 함수들을 DB로 일괄 임포트합니다. |
| `func_update` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 함수 코드를 업데이트합니다 (새 버전으로 등록). |
| `func_edit_test` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 함수의 테스트 코드를 업데이트하고 테스트를 실행합니다. |
| `func_activate` | `name: Annotated[str, typer.Argument(help="함수 이름...` | `-` | 특정 버전을 수동으로 활성화합니다 (롤백/롤포워드). |
| `func_template` | `name: Annotated[Optional[str], typer.Argument(h...` | `-` | 독립 실행형 테스트 코드 작성 가이드를 출력합니다. |
| `mcp_stats` | `func: Annotated[Optional[str], typer.Option("--...` | `-` | MCP 함수 실행 통계를 표시합니다. |
| `model_status` | `` | `-` | 현재 활성 프로바이더와 모델을 표시합니다. |
| `model_list` | `provider: Annotated[Optional[str], typer.Option...` | `-` | 프로바이더별 사용 가능한 모델 목록을 조회합니다. |
| `model_set` | `provider: Annotated[str, typer.Argument(help="프...` | `-` | 활성 프로바이더와 모델을 변경합니다. |
| `prompt_list` | `` | `-` | 등록된 시스템 프롬프트 목록 표시. |
| `prompt_show` | `name: Annotated[str, typer.Argument(help="프롬프트 ...` | `-` | 시스템 프롬프트 내용 출력. |
| `prompt_create` | `name: Annotated[str, typer.Argument(help="프롬프트 ...` | `-` | 새 시스템 프롬프트 생성. |
| `prompt_edit` | `name: Annotated[str, typer.Argument(help="프롬프트 ...` | `-` | 시스템 프롬프트 수정. |
| `prompt_delete` | `name: Annotated[str, typer.Argument(help="프롬프트 ...` | `-` | 시스템 프롬프트 삭제. |
| `prompt_import` | `directory: Annotated[str, typer.Option("--dir",...` | `-` | system_prompts/*.txt 파일을 DB로 임포트합니다. |
| `skill_list` | `all_skills: Annotated[bool, typer.Option("--all...` | `-` | 등록된 스킬 목록 표시. |
| `skill_sync` | `` | `-` | 로컬 모듈에서 스킬을 동기화합니다. |
| `skill_enable` | `name: Annotated[str, typer.Argument(help="스킬 이름")]` | `-` | 스킬 활성화. |
| `skill_disable` | `name: Annotated[str, typer.Argument(help="스킬 이름")]` | `-` | 스킬 비활성화. |
| `skill_show` | `name: Annotated[str, typer.Argument(help="스킬 이름")]` | `-` | 스킬 상세 정보 출력. |
| `macro_list` | `` | `-` | 등록된 스킬 매크로 목록 표시. |
| `macro_show` | `name: Annotated[str, typer.Argument(help="매크로 이...` | `-` | 매크로 상세 정보 출력. |
| `macro_create` | `name: Annotated[str, typer.Argument(help="매크로 이...` | `-` | 새 스킬 매크로 생성. |
| `macro_edit` | `name: Annotated[str, typer.Argument(help="매크로 이...` | `-` | 매크로 수정. |
| `macro_delete` | `name: Annotated[str, typer.Argument(help="매크로 이...` | `-` | 매크로 삭제. |
| `macro_render` | `name: Annotated[str, typer.Argument(help="매크로 이...` | `-` | 매크로 렌더링 (변수 치환). |
| `workflow_list` | `` | `-` | 등록된 워크플로우 목록 표시. |
| `workflow_show` | `name: Annotated[str, typer.Argument(help="워크플로우...` | `-` | 워크플로우 상세 정보 출력. |
| `workflow_create` | `name: Annotated[str, typer.Argument(help="워크플로우...` | `-` | 새 빈 워크플로우 생성. |
| `workflow_add_step` | `name: Annotated[str, typer.Argument(help="워크플로우...` | `-` | 워크플로우에 스텝 추가. |
| `workflow_delete` | `name: Annotated[str, typer.Argument(help="워크플로우...` | `-` | 워크플로우 삭제. |
| `persona_list` | `` | `-` | 등록된 페르소나 목록 표시. |
| `persona_show` | `name: Annotated[str, typer.Argument(help="페르소나 ...` | `-` | 페르소나 상세 정보 출력. |
| `persona_create` | `name: Annotated[str, typer.Argument(help="페르소나 ...` | `-` | 새 페르소나 생성. |
| `persona_edit` | `name: Annotated[str, typer.Argument(help="페르소나 ...` | `-` | 페르소나 수정. |
| `persona_delete` | `name: Annotated[str, typer.Argument(help="페르소나 ...` | `-` | 페르소나 삭제. |
| `persona_set_default` | `name: Annotated[str, typer.Argument(help="페르소나 ...` | `-` | 페르소나를 기본값으로 설정. |
| `persona_detect` | `query: Annotated[str, typer.Argument(help="자동 감...` | `-` | 쿼리에 대해 자동 감지되는 페르소나를 출력합니다. |
| `issue_list` | `status: Optional[str], source: Optional[str], l...` | `-` | 이슈 목록을 출력합니다. |
| `issue_show` | `issue_id: int` | `-` | 이슈 상세 정보를 출력합니다. |
| `issue_resolve` | `issue_id: int, note: str` | `-` | 이슈를 resolved 상태로 변경합니다. |
| `issue_ignore` | `issue_id: int` | `-` | 이슈를 ignored 상태로 변경합니다. |
| `test_import` | `file_path: str` | `-` | 단일 테스트 파일을 DB에 저장합니다. |
| `test_import_all` | `` | `-` | orchestrator/ 디렉토리의 test_*.py 파일을 모두 DB에 저장합니다. |
| `test_list` | `` | `-` | DB에 저장된 테스트 목록을 표시합니다. |
| `test_show` | `name: str` | `-` | 저장된 테스트 코드를 출력합니다. |
| `test_run` | `name: str` | `-` | 특정 테스트를 실행합니다. |
| `test_run_all` | `` | `-` | 저장된 모든 테스트를 실행하고 요약을 출력합니다. |
| `template_list` | `active_only: bool, limit: int` | `None` | 실행 템플릿 목록을 조회합니다. |
| `template_show` | `template_id: int` | `None` | 템플릿 상세 정보를 출력합니다. |
| `template_stats` | `` | `None` | 템플릿 통계를 출력합니다. |
| `template_disable` | `template_id: int` | `None` | 템플릿을 비활성화합니다. |
| `template_enable` | `template_id: int` | `None` | 템플릿을 활성화합니다. |
| `template_delete` | `template_id: int, yes: bool` | `None` | 템플릿을 삭제합니다. |
| `gap_report` | `limit: int` | `None` | 도구 부재 이력을 조회합니다. |
| `gap_discover` | `tool: str, context: str` | `None` | 특정 도구를 MCP 탐색 → Python 자동 구현 순으로 해결합니다. |

의존성: `asyncio`, `click`, `dotenv`, `httpx`, `json`, `orchestrator`, `os`, `pathlib`, `rich`, `shutil`

#### `mcp_servers.json` (211줄, 7,511B)

#### `model_config.json` (38줄, 996B)

#### `pytest.ini` (4줄, 57B)

#### `requirements.txt` (36줄, 1,816B)

#### `start.sh` (3줄, 81B)

### claude_tools/

#### `__init__.py` (2줄, 128B)

#### `__main__.py` (435줄, 17,512B)
> claude_tools CLI 진입점  사용법:     python -m claude_tools scan              # 프로젝트 스캔 (스냅샷 생성)     python -m claude_tools changes           # 변경 사항 감지     python -m claude_tools update            # 분석 보고서

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `main` | `` | `-` | - |

의존성: `change_tracker`, `json`, `os`, `project_scanner`, `project_tracker`, `report_updater`, `report_validator`, `sqlite3`, `sys`

#### `change_tracker.py` (231줄, 7,824B)
> change_tracker.py - 이전 스냅샷 대비 변경 사항 감지  이 스크립트의 출력만 읽으면 Claude가 "무엇이 변했는지"를 즉시 파악할 수 있습니다. 개별 파일을 읽을 필요가 없어 토큰 소모를 대폭 줄입니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `detect_changes` | `project_root: str` | `Dict[str, Any]` | 이전 스냅샷과 현재 상태를 비교하여 변경 사항을 반환. |
| `save_changes` | `project_root: str` | `Tuple[str, Dict]` | 변경 사항을 감지하고 JSON으로 저장한 뒤, 새 스냅샷으로 갱신. |
| `print_changes_summary` | `changes: Dict` | `-` | 변경 사항을 사람이 읽기 좋은 형태로 출력. |

의존성: `ast`, `datetime`, `json`, `os`, `pathlib`, `project_scanner`, `sys`, `typing`

#### `project_scanner.py` (245줄, 8,229B)
> project_scanner.py - 프로젝트 구조 및 코드 스냅샷 생성기  이 스크립트가 생성하는 .snapshot.json을 읽으면 Claude가 개별 소스 파일을 읽지 않아도 프로젝트를 파악할 수 있습니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `scan_project` | `project_root: str` | `Dict[str, Any]` | 프로젝트 전체를 스캔하여 스냅샷 딕셔너리를 반환. |
| `save_snapshot` | `project_root: str` | `str` | 프로젝트를 스캔하고 결과를 JSON으로 저장. |
| `load_snapshot` | `project_root: str` | `Optional[Dict]` | 저장된 스냅샷을 로드. |

의존성: `ast`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `sys`, `typing`

#### `project_tracker.py` (788줄, 35,144B)
> project_tracker.py - PROJECT_ANALYSIS.md 정적 섹션 → SQLite DB 관리  관리 테이블:   requirements  — 요구사항 전체 (섹션 0.1/0.2/0.3 통합, status로 구분)                   status: 'DONE' | 'IN_PROGRESS' | 'PENDING'   change_l

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `get_db_path` | `` | `str` | 프로젝트 루트 기준 DB 경로를 반환합니다. |
| `init_tables` | `db_path: Optional[str]` | `None` | 4개 테이블을 생성합니다 (이미 있으면 무시). requirements에 issue_id 컬럼 보장. |
| `add_requirement` | `number: int, title: str, applied_files: str, st...` | `int` | 요구사항을 DB에 추가합니다. |
| `update_requirement_status` | `number: int, new_status: str, note: str, applie...` | `bool` | 요구사항 상태를 변경합니다 (PENDING→IN_PROGRESS→DONE 등). |
| `list_requirements` | `status: Optional[str], db_path: Optional[str]` | `List[Dict]` | 요구사항 목록을 반환합니다. |
| `get_next_req_number` | `db_path: Optional[str]` | `int` | requirements 테이블의 현재 최대 number + 1을 반환합니다. |
| `auto_create_from_issues` | `db_path: Optional[str], severity_filter: Option...` | `List[Dict]` | open 이슈를 스캔해 아직 요구사항이 없는 그룹마다 PENDING 요구사항을 자동 생성합니다. |
| `auto_resolve_issues` | `db_path: Optional[str]` | `int` | DONE 처리된 이슈 기반 요구사항의 연결 이슈를 모두 resolved 처리합니다. |
| `sync_issues` | `db_path: Optional[str], dry_run: bool` | `Dict` | 이슈 → 요구사항 동기화를 실행합니다 (create + resolve). |
| `get_issue_detail` | `issue_id: int, db_path: Optional[str]` | `Optional[Dict]` | 단일 이슈의 전체 상세 정보를 반환합니다 (traceback, context 포함). |
| `list_bug_requirements` | `db_path: Optional[str]` | `List[Dict]` | 이슈 기반(issue_id 있는) 요구사항 중 미완료 항목을 이슈 상세 포함하여 반환합니다. |
| `add_change` | `date: str, description: str, changed_files: str...` | `int` | - |
| `list_changes` | `limit: int, db_path: Optional[str]` | `List[Dict]` | - |
| `add_deleted_file` | `module_name: str, level: str, note: str, delete...` | `int` | - |
| `list_deleted_files` | `db_path: Optional[str]` | `List[Dict]` | - |
| `upsert_test_status` | `test_file: str, target_module: str, note: str, ...` | `None` | - |
| `list_test_status` | `db_path: Optional[str]` | `List[Dict]` | - |
| `migrate_from_md` | `db_path: Optional[str], force: bool` | `None` | PROJECT_ANALYSIS.md 5개 섹션 데이터를 DB로 마이그레이션합니다 (1회성). |

의존성: `contextlib`, `datetime`, `pathlib`, `sqlite3`, `typing`

#### `report_updater.py` (183줄, 7,122B)
> report_updater.py - PROJECT_ANALYSIS.md 자동 갱신  스냅샷과 변경 사항 데이터를 기반으로 분석 보고서의 특정 섹션을 자동 갱신합니다. Claude가 이 보고서만 읽으면 전체 프로젝트를 파악할 수 있도록 합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `update_report` | `project_root: str` | `str` | PROJECT_ANALYSIS.md의 자동 생성 섹션(11, 12)을 갱신. |

의존성: `datetime`, `json`, `os`, `pathlib`, `project_scanner`, `re`, `sys`, `typing`

#### `report_validator.py` (324줄, 12,802B)
> report_validator.py - PROJECT_ANALYSIS.md 자동 검증  섹션 2(디렉토리), 섹션 6(테스트), 섹션 7(의존성)을 실제 파일/스냅샷과 비교하여 불일치를 경고합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `validate_dependencies` | `project_root: Path` | `ValidationResult` | requirements.txt의 패키지를 섹션 7 테이블과 비교. |
| `validate_directory_structure` | `project_root: Path, snapshot: Optional[dict]` | `ValidationResult` | 실제 디렉토리 목록과 섹션 2 표기를 비교. |
| `validate_test_section` | `project_root: Path, snapshot: Optional[dict]` | `ValidationResult` | 실제 테스트 파일 목록과 섹션 6 테이블을 비교. pytest 개수도 대조. |
| `validate_all` | `project_root: str` | `List[ValidationResult]` | - |

**class `ValidationResult`** (line 24)

의존성: `dataclasses`, `json`, `pathlib`, `project_tracker`, `re`, `subprocess`, `sys`, `typing`

### history/

#### `conversations.db` (?줄, 946,176B)

### mcp_modules/

#### `__init__.py` (1줄, 26B)

#### `hashline_editor.py` (199줄, 7,826B)
> Hashline 편집 도구 — LLM이 라인 해시로 파일을 안전하게 편집할 수 있게 합니다.  파일 읽기 시 각 라인에 {n}#{hash}| 접두사를 붙이고, 편집 시 해시를 검증하여 스테일 라인 충돌을 방지합니다.  OMO(Oh My OpenCode) 알고리즘 포팅:   성공률 6.7% → 68.3% 향상 (원본 벤치마크 기준)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `read_file_with_hashes` | `path: str` | `str` | 파일을 읽고 각 라인에 {n}#{hash}| 접두사를 추가하여 반환합니다. |
| `hashline_edit` | `path: str, edits: str` | `str` | 해시 참조로 파일을 안전하게 편집합니다. |

의존성: `json`, `re`, `typing`, `zlib`

#### `test_hashline_editor.py` (203줄, 6,741B)
> Hashline 편집 도구 단위 테스트.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `test_read_file_with_hashes_format` | `` | `-` | - |
| `test_hash_deterministic` | `` | `-` | - |
| `test_hash_whitespace_insensitive` | `` | `-` | - |
| `test_replace_single_line` | `` | `-` | - |
| `test_replace_range` | `` | `-` | - |
| `test_append_to_end` | `` | `-` | - |
| `test_prepend_to_start` | `` | `-` | - |
| `test_append_after_line` | `` | `-` | - |
| `test_hash_mismatch_returns_error` | `` | `-` | - |
| `test_mismatch_shows_correct_hash` | `` | `-` | - |
| `test_multiple_edits_applied` | `` | `-` | - |
| `test_nonexistent_file_raises` | `` | `-` | - |
| `test_invalid_json_raises` | `` | `-` | - |

의존성: `json`, `os`, `pytest`, `re`, `tempfile`

### orchestrator/

#### `__init__.py` (8줄, 274B)

의존성: `logging`

#### `agent_config_manager.py` (1013줄, 36,959B)
> 에이전트 설정 관리 모듈 — 시스템 프롬프트, 스킬, 매크로, 워크플로우, 페르소나.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `init_db` | `path: Path` | `None` | 에이전트 설정 5개 테이블을 IF NOT EXISTS로 생성. |
| `get_prompt` | `name: str, db_path: Path` | `str` | 캐시 우선으로 프롬프트 내용을 반환합니다. 없으면 KeyError 발생. |
| `render_prompt` | `name: str, db_path: Path` | `str` | 프롬프트 템플릿을 로드하여 변수를 치환합니다 (format_map 사용). |
| `create_system_prompt` | `name: str, content: str, description: str, is_d...` | `int` | 시스템 프롬프트 생성. is_default=True면 기존 기본값 해제 후 설정. |
| `get_system_prompt` | `name: str, db_path: Path` | `Optional[Dict]` | - |
| `get_default_system_prompt` | `db_path: Path` | `Optional[Dict]` | - |
| `list_system_prompts` | `db_path: Path` | `List[Dict]` | - |
| `update_system_prompt` | `name: str, content: Optional[str], description:...` | `bool` | - |
| `delete_system_prompt` | `name: str, db_path: Path` | `bool` | - |
| `migrate_prompts_from_files` | `prompts_dir: str, db_path: Path` | `int` | system_prompts/*.txt → system_prompts 테이블. INSERT OR IGNORE (멱등). 마이그레이션 수 반환. |
| `sync_skills_from_registry` | `db_path: Path` | `int` | tool_registry의 로컬 모듈을 로드하고 skills 테이블과 동기화. 신규 추가 수 반환. |
| `list_skills` | `active_only: bool, db_path: Path` | `List[Dict]` | - |
| `get_skill` | `name: str, db_path: Path` | `Optional[Dict]` | - |
| `set_skill_active` | `name: str, active: bool, db_path: Path` | `bool` | - |
| `create_macro` | `name: str, template: str, description: str, var...` | `int` | 스킬 매크로 생성. variables 미제공 시 {{var}} 패턴으로 자동 추출. |
| `get_macro` | `name: str, db_path: Path` | `Optional[Dict]` | - |
| `list_macros` | `db_path: Path` | `List[Dict]` | - |
| `update_macro` | `name: str, template: Optional[str], description...` | `bool` | - |
| `delete_macro` | `name: str, db_path: Path` | `bool` | - |
| `render_macro` | `name: str, bindings: Dict[str, str], db_path: Path` | `str` | 매크로 템플릿에 변수 바인딩 적용. 누락된 변수는 KeyError 발생. |
| `create_workflow` | `name: str, steps: List[Dict], description: str,...` | `int` | - |
| `get_workflow` | `name: str, db_path: Path` | `Optional[Dict]` | - |
| `list_workflows` | `db_path: Path` | `List[Dict]` | - |
| `update_workflow` | `name: str, steps: Optional[List[Dict]], descrip...` | `bool` | - |
| `delete_workflow` | `name: str, db_path: Path` | `bool` | - |
| `create_persona` | `name: str, system_prompt: str, allowed_skills: ...` | `int` | - |
| `get_persona` | `name: str, db_path: Path` | `Optional[Dict]` | - |
| `list_personas` | `db_path: Path` | `List[Dict]` | - |
| `update_persona` | `name: str, system_prompt: Optional[str], allowe...` | `bool` | - |
| `delete_persona` | `name: str, db_path: Path` | `bool` | - |
| `get_effective_persona` | `query: str, explicit_name: Optional[str], db_pa...` | `Optional[Dict]` | 페르소나 자동 감지 알고리즘: |

의존성: `constants`, `datetime`, `graph_manager`, `json`, `logging`, `pathlib`, `re`, `tool_registry`, `typing`

#### `api.py` (891줄, 37,884B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async lifespan` | `app: FastAPI` | `-` | - |
| `async decide_and_act` | `request: AgentRequest` | `-` | (수정) ReAct 루프의 핵심. |
| `async execute_group` | `request: AgentRequest` | `-` | 저장된 그룹을 실행합니다. can_parallel=True 그룹은 병렬 실행 [A]. |
| `async pipeline_endpoint` | `request: AgentRequest` | `-` | 4층 파이프라인 통합 엔드포인트. |
| `async pipeline_execute` | `request: AgentRequest` | `-` | 파이프라인 전용 그룹 실행 엔드포인트. |

의존성: `asyncio`, `constants`, `contextlib`, `datetime`, `fastapi`, `inspect`, `llm_client`, `logging`, `models`, `os`

#### `claude_client.py` (290줄, 10,150B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async generate_execution_plan` | `user_query: str, requirements_content: str, his...` | `List[ExecutionGroup]` | ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다. |
| `async generate_final_answer` | `history: list, model_preference: ModelPreference` | `str` | - |
| `async extract_keywords` | `history: list, model_preference: ModelPreference` | `List[str]` | Claude로 키워드 5~10개 추출. 실패 시 [] 반환 (예외 전파 안 함). |
| `async detect_topic_split` | `history: list, model_preference: ModelPreference` | `Optional[Dict[str, Any]]` | Claude로 주제 전환 지점 감지. 실패 시 None 반환. |
| `async generate_title_for_conversation` | `history: list, model_preference: ModelPreference` | `str` | - |

의존성: `constants`, `dotenv`, `httpx`, `json`, `logging`, `models`, `os`, `re`, `tool_registry`, `typing`

#### `config.py` (266줄, 8,313B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `load_mcp_config` | `` | `tuple` | MCP 서버 설정을 로드합니다. |
| `load_model_config` | `` | `tuple` | model_config.json에서 현재 활성 프로바이더/모델을 읽습니다. |
| `get_env_with_fallback` | `primary: str, fallback: str` | `str` | 환경변수를 primary → fallback 순서로 조회합니다. |
| `get_mcp_servers` | `` | `List[Dict]` | MCP 서버 설정을 캐시하여 반환합니다. |
| `get_tool_aliases` | `` | `Dict` | 도구 이름 별칭 맵을 캐시하여 반환합니다. |
| `get_model_config` | `` | `tuple` | 활성 모델 설정(provider, model)을 캐시하여 반환합니다. |

의존성: `json`, `logging`, `model_manager`, `os`, `sys`, `typing`

#### `constants.py` (62줄, 1,982B)
> 프로젝트 전역 상수 정의.  이 파일에 정의된 상수들은 여러 모듈에서 공유됩니다. 값 변경 시 이 파일만 수정하면 됩니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `utcnow` | `` | `str` | 현재 UTC 시각을 'YYYY-MM-DDTHH:MM:SS' 형식 문자열로 반환합니다. |
| `utcnow_timestamp` | `` | `float` | 현재 UTC 시각을 Unix timestamp(float)로 반환합니다. |

의존성: `datetime`, `typing`

#### `gemini_client.py` (282줄, 9,672B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async generate_execution_plan` | `user_query: str, requirements_content: str, his...` | `List[ExecutionGroup]` | ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다. |
| `async generate_final_answer` | `history: list, model_preference: ModelPreference` | `str` | - |
| `async extract_keywords` | `history: list, model_preference: ModelPreference` | `List[str]` | Gemini로 키워드 5~10개 추출. 실패 시 [] 반환 (예외 전파 안 함). |
| `async detect_topic_split` | `history: list, model_preference: ModelPreference` | `Optional[Dict[str, Any]]` | Gemini로 주제 전환 지점 감지. 실패 시 None 반환. |
| `async generate_title_for_conversation` | `history: list, model_preference: ModelPreference` | `str` | - |

의존성: `constants`, `dotenv`, `google`, `json`, `logging`, `model_manager`, `models`, `os`, `tool_registry`, `typing`

#### `graph_manager.py` (942줄, 33,336B)
> SQLite 기반 대화 지식 그래프 관리 모듈.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `get_db` | `path: Path` | `-` | - |
| `init_db` | `path: Path` | `None` | 모든 테이블을 IF NOT EXISTS로 생성. |
| `migrate_json_to_sqlite` | `history_dir: Path, db_path: Path` | `int` | history/*.json → conversations 테이블. 파일은 보존. 마이그레이션된 수 반환. |
| `create_conversation` | `convo_id: str, db_path: Path` | `None` | - |
| `save_conversation` | `convo_id: str, history: List[str], title: str, ...` | `str` | Upsert 대화. UUID 그대로 유지. convo_id 반환. |
| `load_conversation` | `convo_id: str, db_path: Path` | `Optional[Dict[str, Any]]` | - |
| `list_conversations` | `group_id: Optional[int], keyword: Optional[str]...` | `List[Dict[str, Any]]` | - |
| `delete_conversation` | `convo_id: str, db_path: Path` | `bool` | - |
| `create_group` | `name: str, description: str, db_path: Path` | `int` | - |
| `list_groups` | `db_path: Path` | `List[Dict]` | - |
| `assign_conversation_to_group` | `convo_id: str, group_id: int, db_path: Path` | `None` | - |
| `remove_conversation_from_group` | `convo_id: str, group_id: int, db_path: Path` | `None` | - |
| `delete_group` | `group_id: int, db_path: Path` | `bool` | - |
| `create_topic` | `name: str, description: str, db_path: Path` | `int` | - |
| `list_topics` | `db_path: Path` | `List[Dict]` | - |
| `assign_conversation_to_topic` | `convo_id: str, topic_id: int, db_path: Path` | `None` | - |
| `link_topics` | `topic_id_a: int, topic_id_b: int, relation: str...` | `None` | 양방향 INSERT OR IGNORE. |
| `delete_topic` | `topic_id: int, db_path: Path` | `bool` | - |
| `get_or_create_keyword` | `name: str, db_path: Path` | `int` | - |
| `assign_keywords_to_conversation` | `convo_id: str, keyword_names: List[str], db_pat...` | `None` | - |
| `list_keywords` | `convo_id: Optional[str], db_path: Path` | `List[Dict]` | - |
| `update_conversation_keywords` | `convo_id: str, keyword_names: List[str], db_pat...` | `None` | 기존 키워드 연결 삭제 후 재연결. |
| `link_conversations` | `convo_id_a: str, convo_id_b: str, link_type: st...` | `None` | - |
| `get_linked_conversations` | `convo_id: str, link_type: Optional[str], db_pat...` | `List[Dict]` | - |
| `split_conversation` | `original_id: str, split_point_index: int, db_pa...` | `Tuple[str, str]` | history[:idx] → 원본 유지 (status='split') |
| `get_graph_data` | `center_id: Optional[str], depth: int, db_path: ...` | `Dict` | nodes/edges 딕셔너리 반환. |
| `render_graph` | `graph_data: Dict, center_id: Optional[str]` | `None` | Rich Panel로 그래프 출력. |
| `save_wisdom` | `convo_id: str, entries: List[dict], db_path: Path` | `None` | 실행 결과에서 추출한 지식 항목을 저장합니다. |
| `load_wisdom` | `convo_id: str, limit: int, db_path: Path` | `List[dict]` | 대화에 저장된 지식 항목을 반환합니다 (최신순). |

의존성: `constants`, `contextlib`, `datetime`, `json`, `logging`, `pathlib`, `rich`, `sqlite3`, `typing`, `uuid`

#### `history_manager.py` (55줄, 1,726B)
> 얇은 어댑터 레이어 — graph_manager에 모든 기능을 위임한다. 기존 함수 시그니처 100% 유지.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `new_conversation` | `` | `Tuple[str, List]` | 새 대화 ID(UUID)와 초기 히스토리를 반환합니다. |
| `save_conversation` | `convo_id: str, history: List[str], title: str, ...` | `str` | 대화를 SQLite에 저장합니다. convo_id(UUID) 그대로 반환. |
| `load_conversation` | `convo_id: str` | `Optional[Dict[str, Any]]` | SQLite에서 대화를 불러옵니다. |
| `list_conversations` | `group_id: Optional[int], keyword: Optional[str]...` | `List[Dict[str, Any]]` | 저장된 대화 목록을 반환합니다. |
| `split_conversation` | `original_id: str, split_point_index: int` | `Tuple[str, str]` | 대화를 두 개로 분리합니다. (original_id, new_id) 반환. |

의존성: `typing`, `uuid`

#### `issue_tracker.py` (181줄, 6,513B)
> 런타임 이슈 자동 저장 모듈.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `init_db` | `path` | `None` | issues 테이블을 생성합니다. |
| `capture` | `error_message: str, error_type: str, traceback:...` | `Optional[int]` | 이슈를 DB에 저장합니다. 예외는 절대 re-raise 하지 않습니다. |
| `capture_exception` | `exc: Exception, context: str, source: str, seve...` | `Optional[int]` | except 블록 안에서 호출하면 traceback을 자동 캡처합니다. |
| `list_issues` | `status: Optional[str], source: Optional[str], l...` | `List[Dict]` | 이슈 목록을 반환합니다. ORDER BY created_at DESC. |
| `get_issue` | `issue_id: int, db_path` | `Optional[Dict]` | 단일 이슈를 반환합니다. 없으면 None. |
| `update_status` | `issue_id: int, status: str, resolution_note: st...` | `bool` | 이슈 상태를 갱신합니다. 성공 시 True 반환. |

의존성: `datetime`, `graph_manager`, `logging`, `traceback`, `typing`

#### `llm_client.py` (628줄, 21,802B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async generate_execution_plan` | `user_query: str, requirements_content: str, his...` | `-` | - |
| `async generate_final_answer` | `history: list, model_preference: ModelPreference` | `str` | - |
| `async extract_keywords` | `history: list, model_preference: ModelPreference` | `List[str]` | - |
| `async detect_topic_split` | `history: list, model_preference: ModelPreference` | `Optional[Dict[str, Any]]` | - |
| `async generate_title_for_conversation` | `history: list, model_preference: ModelPreference` | `str` | - |
| `async generate_clarifying_questions` | `user_query: str, model_preference: ModelPreference` | `List[str]` | 사용자 쿼리를 분석해 실행 전 확인이 필요한 질문 목록을 반환합니다. |
| `async summarize_history` | `history: list, model_preference: ModelPreference` | `str` | 긴 히스토리를 핵심 내용 위주로 요약한 문자열을 반환합니다. |
| `async classify_intent` | `user_query: str, model_preference: ModelPreference` | `str` | 사용자 쿼리를 'chat' 또는 'task'로 분류합니다. |
| `async generate_design` | `user_query: str, persona_prompt: str, history: ...` | `Dict[str, Any]` | 사용자 쿼리를 분석해 고수준 설계를 생성합니다 (Design Phase). |
| `async decompose_tasks` | `design: Dict[str, Any], user_query: str, model_...` | `List[Dict[str, str]]` | 설계를 실행 가능한 태스크 목록으로 분해합니다 (Task Decomposition Phase). |
| `async map_plans` | `task: Dict[str, str], available_tools: List[str...` | `List[Dict[str, Any]]` | 태스크를 순서 있는 계획 단계(Plan Steps)로 매핑합니다 (Plan Mapping Phase). |
| `async build_execution_group_for_step` | `plan_step: Dict[str, Any], task: Dict[str, str]...` | `Dict[str, Any]` | 계획 단계 1개에 대한 ExecutionGroup을 생성합니다. |
| `async extract_wisdom` | `tool_results: List[str], context: str` | `List[dict]` | 도구 실행 결과에서 재사용 가능한 학습 사항을 추출합니다. |
| `async validate_execution_plan` | `plan_list, available_tools: List[str]` | `PlanValidation` | 실행 계획의 도구 유효성·인자 충실도·완료 조건을 검증합니다. |
| `async classify_task_category` | `user_query: str` | `str` | 사용자 쿼리를 태스크 카테고리로 분류합니다 (LLM 없이 휴리스틱). |
| `async adapt_template_arguments` | `template_group: Dict[str, Any], plan_step: Dict...` | `Dict[str, Any]` | 기존 템플릿의 구조를 유지하면서 arguments만 현재 컨텍스트에 맞게 교체합니다. |

의존성: `constants`, `json`, `logging`, `model_manager`, `models`, `re`, `typing`

#### `llm_router.py` (157줄, 6,105B)
> Phase 4 — 파이프라인 단계별 LLM 티어 자동 라우팅.  각 파이프라인 단계의 복잡도를 분석해 high/standard/local 티어를 자동 결정합니다.  티어 정의:   high     : cloud LLM (claude-opus / gemini-2.5-pro 등) — 창의적 판단, 코드 생성   standard : cloud LLM (claud

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `get_tier` | `stage: str, complexity: str, budget_usd: Option...` | `str` | 파이프라인 단계와 복잡도를 기반으로 LLM 티어를 결정합니다. |
| `get_current_budget` | `` | `float` | 현재 요청의 누적 비용 USD를 반환합니다 (token_tracker 연동). |
| `route` | `stage: str, complexity: str, force: Optional[str]` | `str` | token_tracker 비용을 자동으로 반영한 LLM 티어를 반환합니다. |
| `infer_complexity_from_design` | `design: dict` | `str` | 설계 dict에서 complexity 필드를 추출합니다. 없으면 'medium'. |
| `infer_complexity_from_query` | `query: str` | `str` | 쿼리 길이·키워드 기반으로 복잡도를 추정합니다 (빠른 휴리스틱). |

의존성: `logging`, `token_tracker`, `typing`

#### `mcp_db_manager.py` (724줄, 26,981B)
> SQLite DB 기반 MCP 함수 관리 모듈.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `init_db` | `path` | `None` | MCP 관련 테이블 4개를 생성합니다. |
| `register_function` | `func_name: str, module_group: str, code: str, t...` | `Dict` | 함수를 DB에 새 버전으로 등록합니다. |
| `run_function_tests` | `func_name: str, version: int, db_path` | `Dict` | pytest를 subprocess로 실행하여 함수 테스트를 수행합니다. |
| `generate_temp_module` | `module_group: str, db_path` | `Path` | 활성 함수들을 조합하여 mcp_cache/{module_group}.py 를 생성합니다. |
| `load_module_in_memory` | `module_group: str, db_path` | `dict` | DB 활성 함수들을 exec()으로 메모리에 로드. {func_name: callable} 반환. |
| `get_active_function` | `func_name: str, db_path` | `Optional[Dict]` | 활성 버전의 함수 정보를 반환합니다. |
| `list_functions` | `module_group: Optional[str], active_only: bool,...` | `List[Dict]` | 함수 목록을 반환합니다. |
| `get_function_versions` | `func_name: str, db_path` | `List[Dict]` | 함수의 모든 버전 이력을 반환합니다. |
| `start_session` | `conversation_id: Optional[str], group_id: str, ...` | `str` | 실행 세션을 시작하고 session_id(UUID)를 반환합니다. |
| `end_session` | `session_id: str, overall_success: bool, db_path` | `None` | 실행 세션을 종료합니다. |
| `log_usage` | `func_name: str, success: bool, session_id: Opti...` | `None` | 함수 실행 로그를 기록합니다. |
| `get_usage_stats` | `func_name: Optional[str], module_group: Optiona...` | `Dict` | 사용 통계를 집계합니다. |
| `import_from_file` | `file_path: str, module_group: Optional[str], te...` | `Dict` | 기존 Python 파일에서 공개 함수를 DB로 임포트합니다. |
| `update_function_test_code` | `func_name: str, test_code: str, version: Option...` | `Dict` | 기존 버전의 test_code를 업데이트하고 선택적으로 테스트를 실행합니다. |
| `activate_function` | `func_name: str, version: int, db_path` | `None` | 특정 버전을 수동으로 활성화합니다. |
| `set_module_preamble` | `module_group: str, preamble_code: str, descript...` | `None` | 모듈 그룹의 preamble 코드를 직접 설정합니다. |

의존성: `ast`, `constants`, `datetime`, `graph_manager`, `json`, `logging`, `pathlib`, `re`, `subprocess`, `sys`

#### `mcp_manager.py` (267줄, 8,889B)
> MCP 서버 레지스트리 관리 모듈.  서버 등록/제거/검색, 도구 중복 분석, 하드코딩 마이그레이션 등을 담당합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `load_registry` | `path: Optional[str]` | `Dict[str, Any]` | JSON 레지스트리 파일을 읽어 반환합니다. |
| `save_registry` | `registry: Dict[str, Any], path: Optional[str]` | `None` | 레지스트리를 JSON 파일에 저장합니다. |
| `get_servers` | `registry: Dict[str, Any], enabled_only: bool` | `List[Dict[str, Any]]` | 서버 목록을 반환합니다. |
| `add_server` | `registry: Dict[str, Any], name: str, package: s...` | `Dict[str, Any]` | 서버를 레지스트리에 추가합니다. 이름 중복 시 ValueError. |
| `remove_server` | `registry: Dict[str, Any], name: str` | `bool` | 서버를 레지스트리에서 제거합니다. 제거 성공 시 True. |
| `enable_server` | `registry: Dict[str, Any], name: str, enabled: bool` | `bool` | 서버를 활성/비활성 전환합니다. 성공 시 True. |
| `search_npm` | `query: str` | `List[Dict[str, str]]` | npm에서 MCP 서버 패키지를 검색합니다. |
| `search_pip` | `query: str` | `List[Dict[str, str]]` | PyPI JSON API로 패키지를 검색합니다. |
| `search_packages` | `query: str, manager: str` | `Dict[str, List[Dict[str, str]]]` | npm/pip 통합 검색 결과를 반환합니다. |
| `async probe_server_tools` | `server_config: Dict[str, Any]` | `List[Dict[str, str]]` | 서버에 임시 연결하여 도구 목록을 조회합니다. |
| `get_tool_overlap_report` | `new_tools: List[Dict[str, str]], existing_tools...` | `List[Dict[str, str]]` | 새 도구와 기존 도구의 중복을 분석합니다. |
| `migrate_from_hardcoded` | `path: Optional[str]` | `Dict[str, Any]` | 하드코딩된 config 값을 JSON 레지스트리로 변환합니다. |

의존성: `contextlib`, `datetime`, `httpx`, `json`, `logging`, `mcp`, `os`, `subprocess`, `typing`

#### `model_manager.py` (273줄, 9,381B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `load_config` | `path: str` | `Dict[str, Any]` | - |
| `save_config` | `config: Dict[str, Any], path: str` | `None` | - |
| `get_active_model` | `config: Optional[Dict[str, Any]]` | `tuple` | - |
| `set_active_model` | `provider: str, model: str, config: Optional[Dic...` | `Dict[str, Any]` | - |
| `list_providers` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, Any]]` | - |
| `async fetch_models_gemini` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | - |
| `async fetch_models_claude` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | - |
| `async fetch_models_openai` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | - |
| `async fetch_models_grok` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | - |
| `async fetch_models_ollama` | `config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | Ollama /api/tags 엔드포인트에서 설치된 모델 목록을 조회합니다. |
| `async fetch_models` | `provider: str, config: Optional[Dict[str, Any]]` | `List[Dict[str, str]]` | - |

의존성: `google`, `httpx`, `json`, `logging`, `os`, `typing`

#### `models.py` (113줄, 4,570B)

**class `TaskCategory`** (line 10)

**class `AgentRequest`** (line 17)
> CLI가 서버로 보내는 요청 모델

**class `ToolCall`** (line 38)
> 단일 도구 호출(MCP)을 정의하는 모델

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `validate_tool_name` | `cls, v: str` | 도구 이름에 위험 문자가 없는지 검증합니다. |
| `validate_arguments_size` | `cls, v: Dict[str, Any]` | arguments 직렬화 크기를 10KB로 제한합니다. |

**class `ExecutionGroup`** (line 69)
> 여러 태스크를 묶는 실행 그룹 모델

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `validate_tasks_count` | `cls, v: List[ToolCall]` | 태스크 수를 50개로 제한합니다. |

**class `WisdomEntry`** (line 85)

**class `PlanValidation`** (line 91)

**class `AgentResponse`** (line 98)
> 서버가 CLI로 보내는 응답 모델

의존성: `json`, `pydantic`, `typing`

#### `ollama_client.py` (264줄, 9,874B)
> Ollama 로컬 LLM 클라이언트.  8GB RAM 환경 기준 모델:   HIGH    : qwen2.5-coder:7b  (~4.5GB, 코딩 고성능)   STANDARD: qwen2.5-coder:3b  (~2.0GB, 코딩 경량/균형)  Gemini/Claude 클라이언트와 동일한 함수 인터페이스를 제공합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async generate_execution_plan` | `user_query: str, requirements_content: str, his...` | `List[ExecutionGroup]` | ReAct 플래너: 다음 1개 실행 그룹을 생성합니다. 완료 시 [] 반환. |
| `async generate_final_answer` | `history: list, model_preference: ModelPreference` | `str` | 작업 완료 후 최종 답변을 생성합니다. |
| `async extract_keywords` | `history: list, model_preference: ModelPreference` | `List[str]` | 대화에서 핵심 키워드 5~10개를 추출합니다. 실패 시 [] 반환. |
| `async detect_topic_split` | `history: list, model_preference: ModelPreference` | `Optional[Dict[str, Any]]` | 대화에서 주제 전환 지점을 감지합니다. 실패 시 None 반환. |
| `async generate_title_for_conversation` | `history: list, model_preference: ModelPreference` | `str` | 대화 내용을 요약한 5단어 이내 제목을 생성합니다. |

의존성: `constants`, `dotenv`, `httpx`, `json`, `logging`, `models`, `os`, `tool_registry`, `typing`

#### `pipeline_db.py` (615줄, 23,761B)
> 4층 파이프라인 DB 관리 모듈.  테이블:   - designs           : 설계 결과 (사용자 확인 포함)   - tasks             : 태스크 분해 결과   - task_plans        : 태스크별 계획 단계   - execution_templates : 실행 그룹 템플릿 (재사용 핵심)   - task_plan_cache

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `init_db` | `path` | `None` | 파이프라인 관련 테이블을 IF NOT EXISTS로 생성하고 마이그레이션합니다. |
| `create_design` | `conversation_id: str, query_text: str, design_t...` | `int` | 설계를 DB에 저장하고 design_id를 반환합니다. |
| `confirm_design` | `design_id: int, path` | `None` | 설계를 confirmed 상태로 변경합니다. |
| `reject_design` | `design_id: int, path` | `None` | 설계를 rejected 상태로 변경합니다. |
| `get_design` | `design_id: int, path` | `Optional[Dict[str, Any]]` | design_id로 설계를 조회합니다. |
| `get_active_design` | `conversation_id: str, path` | `Optional[Dict[str, Any]]` | 대화의 현재 활성 설계(pending_confirm 또는 confirmed)를 반환합니다. |
| `create_tasks` | `design_id: int, tasks: List[Dict[str, str]], path` | `List[int]` | 태스크 목록을 DB에 저장하고 task_id 리스트를 반환합니다. |
| `get_tasks` | `design_id: int, path` | `List[Dict[str, Any]]` | design_id에 속한 모든 태스크를 반환합니다. |
| `get_next_pending_task` | `design_id: int, path` | `Optional[Dict[str, Any]]` | 다음 실행 대기 중인 태스크를 반환합니다. |
| `update_task_status` | `task_id: int, status: str, path` | `None` | - |
| `create_task_plans` | `task_id: int, plans: List[Dict[str, Any]], path` | `List[int]` | 계획 단계 목록을 DB에 저장하고 plan_id 리스트를 반환합니다. |
| `get_task_plans` | `task_id: int, path` | `List[Dict[str, Any]]` | task_id에 속한 모든 계획 단계를 반환합니다. |
| `get_next_pending_plan` | `task_id: int, path` | `Optional[Dict[str, Any]]` | 다음 실행 대기 중인 계획 단계를 반환합니다. |
| `update_plan_status` | `plan_id: int, status: str, result: str, templat...` | `None` | - |
| `save_execution_template` | `name: str, description: str, keywords: List[str...` | `int` | 실행 그룹 템플릿을 저장하고 template_id를 반환합니다. |
| `find_best_template` | `keywords: List[str], path` | `Optional[Dict[str, Any]]` | 키워드 중복 수로 가장 유사한 활성 템플릿을 반환합니다 (기본 조회용). |
| `list_templates` | `active_only: bool, limit: int, offset: int, path` | `List[Dict[str, Any]]` | 템플릿 목록을 반환합니다 (success_count 내림차순). |
| `get_template` | `template_id: int, path` | `Optional[Dict[str, Any]]` | 단일 템플릿 전체 정보를 반환합니다. |
| `disable_template` | `template_id: int, path` | `None` | 템플릿을 비활성화합니다. |
| `enable_template` | `template_id: int, path` | `None` | 템플릿을 활성화합니다. |
| `delete_template` | `template_id: int, path` | `None` | 템플릿을 삭제합니다. |
| `get_template_stats` | `path` | `Dict[str, Any]` | 템플릿 전체 통계를 반환합니다. |
| `auto_disable_failing_templates` | `fail_rate_threshold: float, min_uses: int, path` | `List[int]` | 실패율이 임계값을 초과한 템플릿을 자동 비활성화합니다. |
| `increment_template_fail` | `template_id: int, path` | `None` | - |
| `get_task_plan_cache` | `task_signature: str, path` | `Optional[List[Dict[str, Any]]]` | 태스크 시그니처로 캐시된 계획 단계를 반환하고 use_count를 증가시킵니다. |
| `save_task_plan_cache` | `task_signature: str, keywords: List[str], plans...` | `None` | 태스크 계획 매핑 결과를 캐시에 저장합니다 (UPSERT). |
| `log_tool_gap` | `required_tool: str, resolution_type: str, mcp_s...` | `None` | 도구 부재 이벤트를 기록합니다. 예외는 절대 발생시키지 않습니다. |
| `set_cursor` | `conversation_id: str, phase: str, design_id: Op...` | `None` | 현재 파이프라인 위치를 저장합니다 (UPSERT). |
| `get_cursor` | `conversation_id: str, path` | `Optional[Dict[str, Any]]` | 대화의 현재 파이프라인 커서를 반환합니다. |
| `clear_cursor` | `conversation_id: str, path` | `None` | 파이프라인 커서를 idle 상태로 초기화합니다. |

의존성: `constants`, `datetime`, `graph_manager`, `json`, `logging`, `typing`

#### `pipeline_manager.py` (585줄, 21,636B)
> 4층 파이프라인 오케스트레이터.  흐름:   1. [DESIGN]   사용자 쿼리 → LLM(high) → 설계 생성 → DESIGN_CONFIRMATION   2. [TASKS]    설계 확인 → LLM(standard) → 태스크 분해   3. [PLANS]    각 태스크 → LLM(standard) → 계획 단계 매핑   4. [EXEC]     

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async start_design_phase` | `conversation_id: str, query: str, history: List...` | `AgentResponse` | 사용자 쿼리로부터 설계를 생성하고 DESIGN_CONFIRMATION을 반환합니다. |
| `async proceed_after_design_confirm` | `conversation_id: str, design_id: int, history: ...` | `AgentResponse` | 설계 확인 후 태스크 분해 → 첫 번째 실행 그룹을 반환합니다. |
| `async advance_after_execution` | `conversation_id: str, execution_result: str, hi...` | `AgentResponse` | 현재 계획 단계 완료 처리 후 다음 단계/태스크/완료를 반환합니다. |
| `record_execution_success` | `plan_id: int, execution_group_dict: Dict[str, Any]` | `None` | 실행 성공 후 템플릿을 저장/업데이트합니다. |

의존성: `graph_manager`, `hashlib`, `json`, `llm_client`, `logging`, `models`, `re`, `typing`

#### `template_engine.py` (208줄, 7,437B)
> Phase 2 — 실행 템플릿 엔진.  기능:   1. 향상된 유사도 스코어링 (키워드 겹침 + 도구명 매칭 + 성공률 가중치)   2. LLM(local/standard) 기반 템플릿 인자 적응 — 구조 재사용, 값만 교체   3. 실패율 초과 템플릿 자동 비활성화 (auto_disable_failing_templates 위임)  템플릿 재사용 판단 임계

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `find_best_template_scored` | `keywords: List[str], tool_hints: List[str], path` | `Optional[Dict[str, Any]]` | 향상된 스코어링으로 가장 적합한 활성 템플릿을 반환합니다. |
| `async adapt_template` | `template_group: Dict[str, Any], plan_step: Dict...` | `Dict[str, Any]` | 템플릿 ExecutionGroup을 현재 컨텍스트에 맞게 인자만 교체합니다. |
| `async find_and_adapt` | `plan_step: Dict[str, Any], task: Dict[str, Any]...` | `Tuple[Optional[Dict[str, Any]], Optional[int]]` | 템플릿 검색 → 인자 적응 → (adapted_group, template_id) 반환. |

의존성: `datetime`, `json`, `llm_client`, `logging`, `re`, `typing`

#### `test_agent_config_manager.py` (416줄, 18,922B)
> agent_config_manager 단위 테스트.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `tmp_db` | `tmp_path` | `-` | 임시 DB 경로 픽스처. |

**class `TestSystemPrompts`** (line 25)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_get` | `self, tmp_db` | - |
| `test_create_default` | `self, tmp_db` | - |
| `test_only_one_default` | `self, tmp_db` | - |
| `test_list` | `self, tmp_db` | - |
| `test_update` | `self, tmp_db` | - |
| `test_update_nonexistent` | `self, tmp_db` | - |
| `test_delete` | `self, tmp_db` | - |
| `test_delete_nonexistent` | `self, tmp_db` | - |
| `test_migrate_from_files` | `self, tmp_db, tmp_path` | - |
| `test_migrate_idempotent` | `self, tmp_db, tmp_path` | - |

**class `TestSkills`** (line 106)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_sync_skills` | `self, tmp_db` | - |
| `test_sync_idempotent` | `self, tmp_db` | - |
| `test_list_skills_active_only` | `self, tmp_db` | - |
| `test_set_skill_active` | `self, tmp_db` | - |
| `test_get_nonexistent_skill` | `self, tmp_db` | - |

**class `TestSkillMacros`** (line 159)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_get` | `self, tmp_db` | - |
| `test_auto_extract_variables` | `self, tmp_db` | - |
| `test_explicit_variables` | `self, tmp_db` | - |
| `test_list_macros` | `self, tmp_db` | - |
| `test_update_macro` | `self, tmp_db` | - |
| `test_delete_macro` | `self, tmp_db` | - |
| `test_render_macro` | `self, tmp_db` | - |
| `test_render_macro_missing_var` | `self, tmp_db` | - |
| `test_render_nonexistent_macro` | `self, tmp_db` | - |

**class `TestWorkflows`** (line 219)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_get` | `self, tmp_db` | - |
| `test_list_workflows` | `self, tmp_db` | - |
| `test_update_workflow` | `self, tmp_db` | - |
| `test_delete_workflow` | `self, tmp_db` | - |
| `test_update_nonexistent` | `self, tmp_db` | - |

**class `TestPersonas`** (line 259)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_get` | `self, tmp_db` | - |
| `test_create_default_persona` | `self, tmp_db` | - |
| `test_only_one_default_persona` | `self, tmp_db` | - |
| `test_list_personas` | `self, tmp_db` | - |
| `test_update_persona` | `self, tmp_db` | - |
| `test_delete_persona` | `self, tmp_db` | - |

**class `TestGetEffectivePersona`** (line 314)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_explicit_name` | `self, tmp_db` | - |
| `test_explicit_name_not_found_falls_back` | `self, tmp_db` | - |
| `test_keyword_detection` | `self, tmp_db` | - |
| `test_keyword_specificity_tiebreak` | `self, tmp_db` | - |
| `test_no_match_returns_default` | `self, tmp_db` | - |
| `test_no_match_no_default_returns_none` | `self, tmp_db` | - |
| `test_empty_query_returns_default` | `self, tmp_db` | - |
| `test_no_personas_returns_none` | `self, tmp_db` | - |

**class `TestSyncSkillsLogging`** (line 368)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_sync_logs_info` | `self, tmp_db, caplog` | sync_skills_from_registry가 INFO 로그를 기록한다. |
| `test_sync_logs_added_and_updated` | `self, tmp_db, caplog` | 신규/갱신 수가 로그 메시지에 포함된다. |

의존성: `datetime`, `graph_manager`, `json`, `logging`, `orchestrator`, `pathlib`, `pytest`, `tempfile`, `unittest`

#### `test_api.py` (383줄, 15,862B)
> orchestrator/api.py에 대한 단위 테스트

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `sample_group` | `` | `-` | - |

**class `TestDecideAndAct`** (line 31)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_new_request_returns_plan_confirmation` | `self, sample_group` | 신규 사용자 입력 시 PLAN_CONFIRMATION 반환 |
| `test_empty_plan_returns_final_answer` | `self` | 플래너가 빈 계획 반환 시 FINAL_ANSWER |

**class `TestExecuteGroup`** (line 83)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_conversation_returns_404` | `self` | 존재하지 않는 대화 ID는 404 |
| `test_successful_execution_returns_step_executed` | `self, sample_group` | 정상 실행 시 STEP_EXECUTED 반환 |
| `test_missing_tool_returns_error` | `self, sample_group` | 도구를 찾을 수 없을 때 ERROR 반환 |
| `test_empty_plan_returns_400` | `self` | 실행할 계획이 없으면 400 |

**class `TestValidateRequirementPath`** (line 182)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_valid_file_returns_realpath` | `self, tmp_path` | - |
| `test_nonexistent_raises` | `self, tmp_path` | - |
| `test_directory_raises` | `self, tmp_path` | - |
| `test_symlink_resolved` | `self, tmp_path` | - |
| `test_oversized_file_raises` | `self, tmp_path` | - |
| `test_exactly_1mb_passes` | `self, tmp_path` | - |

**class `TestValidateToolArguments`** (line 221)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_valid_args_pass` | `self` | - |
| `test_unknown_arg_raises` | `self` | - |
| `test_empty_args_pass` | `self` | - |
| `test_all_params_allowed` | `self` | - |
| `test_invalid_args_blocked_in_execute_group` | `self, sample_group` | execute_group에서 허용되지 않은 인자 사용 시 ERROR 반환 |

**class `TestPruneHistory`** (line 290)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_pruning_when_under_limit` | `self` | - |
| `test_prunes_oldest_when_over_limit` | `self` | - |
| `test_empty_history_unchanged` | `self` | - |
| `test_one_over_limit_removes_oldest` | `self` | - |

**class `TestExtractFirstQuery`** (line 316)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_extracts_first_user_request` | `self` | - |
| `test_returns_default_when_not_found` | `self` | - |
| `test_empty_history_returns_default` | `self` | - |
| `test_colon_in_content_preserved` | `self` | - |
| `test_finds_first_not_second` | `self` | - |
| `test_non_string_entries_skipped` | `self` | - |

**class `TestResultTruncationWarning`** (line 343)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_truncation_logs_warning` | `self, sample_group, caplog` | 도구 결과가 1000자 초과 시 WARNING 로그 발생 |

의존성: `api`, `asyncio`, `constants`, `httpx`, `logging`, `models`, `os`, `pytest`, `unittest`

#### `test_config.py` (66줄, 2,762B)

**class `TestValidateServerConfig`** (line 13)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_allowed_command_passes` | `self` | - |
| `test_disallowed_command_returns_false` | `self, caplog` | - |
| `test_shell_inject_char_in_args_returns_false` | `self, caplog` | - |
| `test_all_allowed_commands_pass` | `self` | - |
| `test_pipe_char_blocked` | `self` | - |
| `test_backtick_char_blocked` | `self` | - |
| `test_empty_args_passes` | `self` | - |
| `test_invalid_server_skipped_in_load` | `self, tmp_path, monkeypatch` | load_mcp_config에서 검증 실패 서버는 결과 목록에서 제외된다. |

의존성: `config`, `json`, `logging`, `pytest`

#### `test_gemini_client.py` (115줄, 4,829B)
> orchestrator/gemini_client.py에 대한 단위 테스트

**class `TestTruncateHistory`** (line 13)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_history` | `self` | 빈 history는 빈 문자열 반환 |
| `test_normal_history` | `self` | 정상 history는 줄바꿈으로 연결 |
| `test_truncation_over_max_chars` | `self` | max_chars 초과 시 최신 항목 우선 보존, 생략 표시 포함 |
| `test_single_item_exceeds_max` | `self` | 단일 항목이 max_chars를 초과해도 최소 1개는 포함 |
| `test_default_max_chars_is_constant` | `self` | 기본 max_chars가 DEFAULT_HISTORY_MAX_CHARS 상수와 일치 |

**class `TestGetModelName`** (line 42)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_high_preference` | `self` | model_preference='high'이면 HIGH_PERF_MODEL_NAME 반환 |
| `test_standard_preference` | `self` | model_preference='standard'이면 STANDARD_MODEL_NAME 반환 |
| `test_auto_uses_config_active_model` | `self` | auto 모드는 model_config.json의 active_model 우선 반환 |
| `test_auto_with_high_default_fallback` | `self` | auto + active_model 비어있을 때 default_type='high'이면 HIGH_PERF_MODEL_NAME 폴백 |
| `test_auto_with_standard_default_fallback` | `self` | auto + active_model 비어있을 때 default_type='standard'이면 STANDARD_MODEL_NAME 폴백 |
| `test_auto_fallback_on_exception` | `self` | auto + model_manager 오류 시 default_type 폴백 |

**class `TestGenerateExecutionPlan`** (line 84)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_raises_runtime_error` | `self` | client=None일 때 RuntimeError 발생 |

**class `TestGenerateFinalAnswer`** (line 93)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_raises_runtime_error` | `self` | client=None일 때 RuntimeError 발생 |

**class `TestGenerateTitleForConversation`** (line 102)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_returns_default` | `self` | client=None일 때 기본 제목 반환 |
| `test_short_history_returns_new_conversation` | `self` | history가 2개 미만이면 '새로운_대화' 반환 |

의존성: `json`, `models`, `pytest`, `unittest`

#### `test_graph_manager.py` (467줄, 18,415B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `db` | `tmp_path` | `-` | 각 테스트마다 격리된 임시 DB. |

**class `TestInitDb`** (line 48)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_all_tables_exist` | `self, db` | - |

**class `TestConversationCRUD`** (line 76)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_load` | `self, db` | - |
| `test_save_new_conversation` | `self, db` | - |
| `test_save_updates_existing` | `self, db` | - |
| `test_is_final_sets_status` | `self, db` | - |
| `test_load_nonexistent_returns_none` | `self, db` | - |
| `test_list_conversations` | `self, db` | - |
| `test_list_filter_by_status` | `self, db` | - |
| `test_list_filter_by_group` | `self, db` | - |
| `test_list_filter_by_keyword` | `self, db` | - |
| `test_delete_conversation` | `self, db` | - |
| `test_delete_nonexistent_returns_false` | `self, db` | - |

**class `TestGroupCRUD`** (line 149)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_list` | `self, db` | - |
| `test_assign_and_list_with_count` | `self, db` | - |
| `test_remove_conversation_from_group` | `self, db` | - |
| `test_duplicate_group_name_raises` | `self, db` | - |
| `test_delete_group` | `self, db` | - |

**class `TestKeywordCRUD`** (line 187)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_get_or_create_idempotent` | `self, db` | - |
| `test_assign_and_list` | `self, db` | - |
| `test_update_replaces_keywords` | `self, db` | - |
| `test_list_all_keywords_usage_count` | `self, db` | - |

**class `TestTopicCRUD`** (line 220)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_and_list` | `self, db` | - |
| `test_assign_convo_to_topic` | `self, db` | - |
| `test_link_topics_bidirectional` | `self, db` | - |
| `test_delete_topic` | `self, db` | - |

**class `TestSplitConversation`** (line 255)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_split_creates_new_uuid` | `self, db` | - |
| `test_split_histories` | `self, db` | - |
| `test_split_registers_link` | `self, db` | - |
| `test_split_original_status` | `self, db` | - |
| `test_split_copies_keywords` | `self, db` | - |
| `test_split_copies_group` | `self, db` | - |
| `test_split_nonexistent_raises` | `self, db` | - |

**class `TestConversationLinks`** (line 305)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_link_and_get` | `self, db` | - |
| `test_get_linked_with_type_filter` | `self, db` | - |

**class `TestMigrateJson`** (line 323)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_migrates_json_to_db` | `self, db, tmp_path` | - |
| `test_migrates_duplicate_skipped` | `self, db, tmp_path` | - |
| `test_skips_invalid_json` | `self, db, tmp_path` | - |

**class `TestExtractKeywords`** (line 370)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_client_none_returns_empty` | `self, monkeypatch` | - |

**class `TestDetectTopicSplit`** (line 382)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_client_none_returns_none` | `self, monkeypatch` | - |

**class `TestFetchKeywordsHelper`** (line 396)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_keywords` | `self, db` | - |
| `test_returns_empty_for_no_keywords` | `self, db` | - |
| `test_load_conversation_uses_helper` | `self, db` | load_conversation이 _fetch_keywords를 통해 키워드를 올바르게 반환한다. |
| `test_list_conversations_uses_helper` | `self, db` | list_conversations가 _fetch_keywords를 통해 키워드를 올바르게 반환한다. |

**class `TestUtcTimestamps`** (line 440)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_create_conversation_uses_utc` | `self, db` | create_conversation이 UTC 타임스탬프를 저장한다. |
| `test_save_conversation_uses_utc` | `self, db` | - |

의존성: `json`, `orchestrator`, `pytest`, `sqlite3`, `uuid`

#### `test_issue_tracker.py` (186줄, 6,613B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `db` | `tmp_path` | `-` | 각 테스트마다 격리된 임시 DB. |

**class `TestInitDb`** (line 30)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_table_exists` | `self, db` | - |
| `test_idempotent` | `self, db` | 두 번 호출해도 오류 없이 동일 테이블. |

**class `TestCapture`** (line 55)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_basic_capture` | `self, db` | - |
| `test_all_fields_stored` | `self, db` | - |
| `test_db_failure_returns_none` | `self, tmp_path` | - |
| `test_capture_exception_includes_traceback` | `self, db` | - |

**class `TestListIssues`** (line 105)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_list` | `self, db` | - |
| `test_source_filter` | `self, db` | - |
| `test_limit` | `self, db` | - |
| `test_status_filter_after_update` | `self, db` | - |

**class `TestGetIssue`** (line 142)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_get_existing_issue` | `self, db` | - |
| `test_get_nonexistent_returns_none` | `self, db` | - |

**class `TestUpdateStatus`** (line 158)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_resolve_with_note` | `self, db` | - |
| `test_ignore` | `self, db` | - |
| `test_nonexistent_id_returns_false` | `self, db` | - |
| `test_in_progress_resolved_at_is_none` | `self, db` | - |

의존성: `orchestrator`, `pathlib`, `pytest`, `sqlite3`

#### `test_mcp_db_manager.py` (591줄, 23,976B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `db` | `tmp_path` | `-` | 각 테스트마다 격리된 임시 DB. |
| `cache_dir` | `tmp_path, monkeypatch` | `-` | 격리된 임시 캐시 디렉토리. |

**class `TestInitDb`** (line 56)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_all_tables_exist` | `self, db` | - |
| `test_idempotent` | `self, db` | 두 번 호출해도 오류 없음. |

**class `TestRegisterFunction`** (line 82)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_basic_register` | `self, db` | - |
| `test_version_increments` | `self, db` | - |
| `test_active_flag_switches_to_latest` | `self, db` | - |
| `test_test_code_passes` | `self, db` | - |
| `test_test_code_fails_no_activation` | `self, db` | - |
| `test_no_test_code_activates_immediately` | `self, db` | - |

**class `TestListFunctions`** (line 141)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_active_only_default` | `self, db` | - |
| `test_filter_by_group` | `self, db` | - |
| `test_all_versions` | `self, db` | - |

**class `TestGetFunctionVersions`** (line 165)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_all_versions_descending` | `self, db` | - |
| `test_empty_for_unknown_func` | `self, db` | - |

**class `TestGetActiveFunction`** (line 180)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_active_version` | `self, db` | - |
| `test_returns_none_for_unknown` | `self, db` | - |

**class `TestGenerateTempModule`** (line 195)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_file_created` | `self, db, tmp_path, monkeypatch` | - |
| `test_file_contains_auto_header` | `self, db, tmp_path, monkeypatch` | - |
| `test_includes_preamble` | `self, db, tmp_path, monkeypatch` | - |

**class `TestSessionLogging`** (line 231)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_start_and_end_session` | `self, db` | - |
| `test_session_failure` | `self, db` | - |

**class `TestLogUsage`** (line 261)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_log_recorded` | `self, db` | - |
| `test_session_func_names_updated` | `self, db` | - |
| `test_no_duplicate_in_func_names` | `self, db` | - |

**class `TestGetUsageStats`** (line 304)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_stats` | `self, db` | - |
| `test_basic_stats` | `self, db` | - |
| `test_filter_by_module_group` | `self, db` | - |

**class `TestExtractPreamble`** (line 333)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_extracts_imports` | `self` | - |
| `test_excludes_public_functions` | `self` | - |
| `test_empty_source` | `self` | - |

**class `TestExtractTestMap`** (line 359)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_camel_to_snake` | `self` | - |
| `test_fixture_included` | `self` | - |
| `test_non_test_class_ignored` | `self` | - |

**class `TestImportFromFile`** (line 398)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_basic_import` | `self, db, tmp_path` | - |
| `test_file_not_found` | `self, db` | - |
| `test_module_group_inferred_from_filename` | `self, db, tmp_path` | - |
| `test_preamble_saved` | `self, db, tmp_path` | - |

**class `TestUpdateFunctionTestCode`** (line 446)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_update_and_pass` | `self, db` | - |
| `test_update_and_fail` | `self, db` | - |
| `test_update_without_run` | `self, db` | - |
| `test_error_on_unknown_func` | `self, db` | - |
| `test_specific_version` | `self, db` | - |
| `test_error_on_unknown_version` | `self, db` | - |

**class `TestActivateFunction`** (line 500)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_activate_older_version` | `self, db` | - |
| `test_activate_unknown_version_raises` | `self, db` | - |

**class `TestValidateCodeSyntax`** (line 520)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_valid_code_passes` | `self` | - |
| `test_invalid_syntax_raises_value_error` | `self` | - |
| `test_label_included_in_error_message` | `self` | - |
| `test_empty_code_passes` | `self` | - |
| `test_preamble_validated_before_exec` | `self, db` | 구문 오류가 있는 preamble이 있으면 load_module_in_memory가 ValueError를 발생시킨다. |
| `test_function_code_validated_before_exec` | `self, db` | 구문 오류가 있는 함수 코드가 있으면 load_module_in_memory가 ValueError를 발생시킨다. |

**class `TestFuncNamesLimit`** (line 561)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_func_names_does_not_exceed_limit` | `self, db, monkeypatch` | func_names 리스트가 MAX_FUNC_NAMES_PER_SESSION을 초과하지 않는다. |
| `test_func_names_warns_at_limit` | `self, db, monkeypatch, caplog` | 한도 초과 시 WARNING 로그가 기록된다. |

의존성: `ast`, `json`, `logging`, `orchestrator`, `pathlib`, `pytest`, `sqlite3`

#### `test_mcp_manager.py` (193줄, 7,356B)
> orchestrator/mcp_manager.py에 대한 단위 테스트

**class `TestRegistryIO`** (line 15)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_load_nonexistent_returns_empty` | `self` | 존재하지 않는 파일 로드 시 빈 레지스트리 반환 |
| `test_save_and_load_roundtrip` | `self` | 저장 후 로드하면 동일한 데이터 반환 |

**class `TestAddRemoveServer`** (line 46)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_add_server` | `self` | 서버 추가 성공 |
| `test_add_duplicate_raises` | `self` | 중복 이름 추가 시 ValueError |
| `test_remove_server` | `self` | 서버 제거 성공 |
| `test_remove_nonexistent` | `self` | 존재하지 않는 서버 제거 시 False |
| `test_enable_disable` | `self` | 활성/비활성 토글 |
| `test_enable_nonexistent` | `self` | 존재하지 않는 서버 활성화 시 False |
| `test_get_servers_enabled_only` | `self` | enabled_only=True 시 비활성 서버 제외 |
| `test_get_servers_all` | `self` | enabled_only=False 시 모든 서버 반환 |

**class `TestSearchPackages`** (line 110)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_search_npm_only` | `self, mock_npm` | manager='npm'이면 npm만 검색 |
| `test_search_pip_only` | `self, mock_pip` | manager='pip'이면 pip만 검색 |
| `test_search_all` | `self, mock_pip, mock_npm` | manager='all'이면 둘 다 검색 |

**class `TestToolOverlap`** (line 139)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_overlap_found` | `self` | 중복 도구가 있으면 리포트에 포함 |
| `test_no_overlap` | `self` | 중복이 없으면 빈 리스트 |

**class `TestMigration`** (line 159)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_migrate_creates_json` | `self` | 마이그레이션 시 JSON 파일 생성 |

**class `TestResolveArgs`** (line 179)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_dot_replaced` | `self` | '.'가 cwd로 치환됨 |
| `test_cwd_replaced` | `self` | '$CWD'가 cwd로 치환됨 |
| `test_other_args_unchanged` | `self` | 다른 인자는 변경 없음 |

의존성: `json`, `os`, `pytest`, `tempfile`, `unittest`

#### `test_model_manager.py` (303줄, 12,302B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `tmp_config` | `tmp_path` | `-` | 임시 model_config.json 경로를 반환합니다. |

**class `TestConfigIO`** (line 59)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_load_config_from_file` | `self, tmp_config` | - |
| `test_load_config_default_when_missing` | `self, tmp_path` | - |
| `test_save_and_reload` | `self, tmp_path` | - |

**class `TestSetActiveModel`** (line 81)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_set_active_model` | `self, tmp_config` | - |
| `test_set_unknown_provider_raises` | `self, tmp_config` | - |
| `test_get_active_model` | `self, tmp_config` | - |

**class `TestListProviders`** (line 104)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_providers_with_keys` | `self, tmp_config` | - |
| `test_list_providers_without_keys` | `self, tmp_config` | - |
| `test_list_providers_ollama_no_api_key_required` | `self, tmp_config` | - |

**class `TestFetchModels`** (line 137)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_fetch_models_gemini_mock` | `self, tmp_config` | - |
| `test_fetch_models_claude_mock` | `self, tmp_config` | - |
| `test_fetch_models_openai_mock` | `self, tmp_config` | - |
| `test_fetch_models_grok_mock` | `self, tmp_config` | - |
| `test_fetch_models_ollama_mock` | `self, tmp_config` | - |
| `test_fetch_models_dispatcher` | `self, tmp_config` | - |
| `test_fetch_models_unknown_provider` | `self` | - |

**class `TestFetchModelsNoApiKey`** (line 276)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_gemini_no_key` | `self, tmp_config` | - |
| `test_claude_no_key` | `self, tmp_config` | - |
| `test_openai_no_key` | `self, tmp_config` | - |
| `test_grok_no_key` | `self, tmp_config` | - |

의존성: `json`, `os`, `pytest`, `pytest_asyncio`, `unittest`

#### `test_models.py` (78줄, 2,834B)

**class `TestGeminiToolCallValidation`** (line 12)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_valid_tool_call` | `self` | - |
| `test_tool_name_too_long_raises` | `self` | - |
| `test_tool_name_exactly_100_passes` | `self` | - |
| `test_arguments_over_10kb_raises` | `self` | - |
| `test_arguments_exactly_at_limit_passes` | `self` | - |

**class `TestExecutionGroupValidation`** (line 36)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_valid_group` | `self` | - |
| `test_group_id_too_long_raises` | `self` | - |
| `test_description_too_long_raises` | `self` | - |
| `test_description_exactly_500_passes` | `self` | - |
| `test_tasks_over_50_raises` | `self` | - |
| `test_tasks_exactly_50_passes` | `self` | - |

의존성: `models`, `pydantic`, `pytest`

#### `test_ollama_client.py` (181줄, 7,692B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|

**class `TestGenerateExecutionPlan`** (line 23)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_execution_group` | `self` | - |
| `test_returns_empty_when_done` | `self` | - |
| `test_dict_with_tasks_field_converted` | `self` | {"tasks": [...]} 형태 응답을 ExecutionGroup으로 자동 변환합니다. |
| `test_connect_error_raises_runtime` | `self` | - |
| `test_invalid_json_raises_value_error` | `self` | - |

**class `TestGenerateFinalAnswer`** (line 77)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_stripped_answer` | `self` | - |
| `test_connect_error_raises_runtime` | `self` | - |
| `test_error_fallback_returns_last_result` | `self` | - |
| `test_error_fallback_no_result_in_history` | `self` | - |

**class `TestExtractKeywords`** (line 107)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_response` | `self` | - |
| `test_dict_response` | `self` | - |
| `test_failure_returns_empty` | `self` | - |

**class `TestDetectTopicSplit`** (line 130)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_detected_split` | `self` | - |
| `test_no_split` | `self` | - |
| `test_failure_returns_none` | `self` | - |

**class `TestGenerateTitleForConversation`** (line 161)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_cleaned_title` | `self` | - |
| `test_short_history_returns_default` | `self` | - |
| `test_exception_returns_fallback` | `self` | - |

의존성: `httpx`, `json`, `pytest`, `unittest`

#### `test_omo_features.py` (528줄, 22,786B)
> OMO P1~P3 기능 단위 테스트.  P1-A: Ralph Loop 헬퍼 (_check_dangerous_tools, _DANGEROUS_TOOLS) P1-B: 카테고리 모델 라우팅 (_CATEGORY_TO_MODEL_PREF) P1-C: 컨텍스트 파일 자동 주입 (_load_context_files) P2-A: Todo Enforcer (_scan_in

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `main_mod` | `` | `-` | - |

**class `TestCheckDangerousTools`** (line 53)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_safe_group_returns_empty` | `self, main_mod` | - |
| `test_delete_file_detected` | `self, main_mod` | - |
| `test_multiple_dangerous_tools` | `self, main_mod` | - |
| `test_empty_group` | `self, main_mod` | - |
| `test_dangerous_tools_set_contains_expected` | `self, main_mod` | - |
| `test_case_insensitive_check` | `self, main_mod` | tool_name이 소문자로 비교되어 대소문자 구분 없이 감지. |

**class `TestCategoryToModelPref`** (line 94)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_all_expected_categories_exist` | `self, main_mod` | - |
| `test_quick_is_standard` | `self, main_mod` | - |
| `test_code_and_analysis_are_high` | `self, main_mod` | - |
| `test_unknown_category_not_in_map` | `self, main_mod` | - |

**class `TestLoadContextFiles`** (line 116)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_empty_when_no_context_files` | `self, tmp_path, main_mod` | - |
| `test_loads_agents_md` | `self, tmp_path, main_mod` | - |
| `test_loads_readme_md` | `self, tmp_path, main_mod` | - |
| `test_loads_both_files` | `self, tmp_path, main_mod` | - |
| `test_file_content_truncated_at_8kb` | `self, tmp_path, main_mod` | - |
| `test_searches_parent_directories` | `self, tmp_path, main_mod` | - |

**class `TestScanIncompleteMarkers`** (line 157)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_history_returns_empty` | `self, main_mod` | - |
| `test_detects_todo` | `self, main_mod` | - |
| `test_detects_markdown_checkbox` | `self, main_mod` | - |
| `test_detects_korean_markers` | `self, main_mod` | - |
| `test_completed_items_not_detected` | `self, main_mod` | - |
| `test_only_checks_last_10_entries` | `self, main_mod` | - |
| `test_result_lines_max_200_chars` | `self, main_mod` | - |
| `test_detects_fixme_and_hack` | `self, main_mod` | - |

**class `TestFallbackChain`** (line 203)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_active_provider_when_no_chain` | `self` | - |
| `test_returns_configured_chain` | `self` | - |
| `test_call_with_fallback_succeeds_on_second_provider` | `self` | 첫 번째 provider 실패 → 두 번째 provider 성공. |
| `test_call_with_fallback_raises_when_all_fail` | `self` | 모든 provider 실패 시 마지막 예외 re-raise. |

**class `TestSummarizeHistory`** (line 273)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_history_returns_empty` | `self` | - |
| `test_returns_empty_on_all_provider_failure` | `self` | - |
| `test_history_truncated_to_8000_chars_in_prompt` | `self` | 매우 긴 히스토리도 LLM 호출 시 8000자로 제한. |

**class `TestRolePrompts`** (line 324)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_planner_and_reviewer_roles_defined` | `self` | - |
| `test_planner_prompt_not_empty` | `self` | - |
| `test_reviewer_prompt_mentions_completion` | `self` | - |
| `test_planner_prompt_mentions_plan` | `self` | - |

**class `TestClassifyIntent`** (line 349)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_task_on_provider_failure` | `self` | 모든 provider 실패 시 보수적 기본값 'task' 반환. |
| `test_chat_response_returns_chat` | `self` | 'chat'이 포함된 응답을 받으면 'chat' 반환. |
| `test_task_response_returns_task` | `self` | 'task'가 포함된 응답을 받으면 'task' 반환. |
| `test_ambiguous_response_defaults_to_task` | `self` | 'chat'이 없는 응답은 모두 'task' 처리. |

**class `TestOnDemandMcp`** (line 421)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_on_demand_config_registered_without_connecting` | `self` | on_demand=true 서버는 _on_demand_configs에 등록되고 즉시 연결하지 않습니다. |
| `test_on_demand_tool_map_lookup` | `self` | _on_demand_tool_map으로 도구 → 서버 역인덱스 조회가 동작합니다. |
| `test_clear_resets_on_demand_state` | `self` | shutdown() 호출 시 on-demand 캐시도 초기화됩니다. |

**class `TestParallelExecution`** (line 477)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_asyncio_gather_used_in_execute_group` | `self` | api.py execute_group이 asyncio.gather를 호출하는지 소스 검사. |
| `test_return_exceptions_true_in_gather` | `self` | asyncio.gather에 return_exceptions=True가 설정되어 있는지 확인. |

**class `TestFmtUsage`** (line 513)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_dict_returns_empty` | `self, main_mod` | - |
| `test_formats_tokens` | `self, main_mod` | - |
| `test_formats_cost_usd` | `self, main_mod` | - |
| `test_ollama_shows_free` | `self, main_mod` | - |

의존성: `ast`, `asyncio`, `importlib`, `json`, `orchestrator`, `pathlib`, `pytest`, `sys`, `types`, `unittest`

#### `test_pipeline.py` (297줄, 12,013B)
> 4층 파이프라인 신규 모듈 테스트.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `tmp_db` | `tmp_path` | `-` | - |
| `test_pipeline_db_init` | `tmp_db` | `-` | DB 초기화 후 기본 통계가 0인지 확인합니다. |
| `test_design_crud` | `tmp_db` | `-` | 설계 생성 → 확인 → 조회 흐름을 검증합니다. |
| `test_task_plan_cache` | `tmp_db` | `-` | 계획 캐시 저장 → 조회 → use_count 증가를 검증합니다. |
| `test_execution_template_lifecycle` | `tmp_db` | `-` | 템플릿 저장 → 조회 → 비활성화 → 자동 비활성화 임계값 테스트. |
| `test_tool_gap_log` | `tmp_db` | `-` | 도구 부재 로그 기록을 검증합니다. |
| `test_pipeline_cursor` | `tmp_db` | `-` | 파이프라인 커서 UPSERT를 검증합니다. |
| `test_llm_router_tiers` | `` | `-` | 단계별 기본 티어와 복잡도 오버라이드를 검증합니다. |
| `test_llm_router_budget_downgrade` | `` | `-` | 예산 초과 시 high → standard 강등을 검증합니다. |
| `test_llm_router_force_override` | `` | `-` | force 파라미터가 모든 로직을 override함을 검증합니다. |
| `test_llm_router_complexity_inference` | `` | `-` | 쿼리 기반 복잡도 추정을 검증합니다. |
| `test_is_code_safe` | `` | `-` | 위험 코드 패턴 정적 검사를 검증합니다. |
| `test_run_safe_whitelist` | `` | `-` | 화이트리스트 외 명령 차단을 검증합니다. |
| `test_run_safe_injection` | `` | `-` | 셸 인젝션 문자가 포함된 인자를 차단합니다. |
| `test_find_tools_for_step` | `` | `-` | 등록된 도구 검색을 검증합니다. |
| `test_template_engine_empty_db` | `tmp_db` | `-` | 빈 DB에서 템플릿 검색 시 None을 반환합니다. |
| `test_template_engine_scoring` | `tmp_db` | `-` | 스코어링이 올바르게 동작하는지 검증합니다. |
| `test_make_task_signature` | `` | `-` | 같은 태스크 제목+설명은 같은 시그니처를 반환합니다. |

의존성: `json`, `orchestrator`, `pathlib`, `pytest`, `tempfile`

#### `test_registry.py` (151줄, 5,413B)
> orchestrator 테스트 파일 DB 저장 및 실행 모듈.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `init_db` | `path` | `None` | orchestrator_tests 테이블을 생성합니다. |
| `import_test_file` | `file_path, db_path` | `Dict` | 파일을 읽어 DB에 upsert합니다. |
| `import_all` | `directory, db_path` | `List[Dict]` | orchestrator/ 디렉토리의 test_*.py 파일을 모두 임포트합니다. |
| `list_tests` | `db_path` | `List[Dict]` | 저장된 테스트 목록을 반환합니다. |
| `get_test` | `name, db_path` | `Optional[Dict]` | 이름으로 테스트를 조회합니다. |
| `run_test` | `name, db_path` | `Dict` | DB에서 코드를 꺼내 임시 파일로 pytest를 실행합니다. |
| `run_all` | `db_path` | `List[Dict]` | 저장된 모든 테스트를 순차 실행합니다. |

의존성: `datetime`, `graph_manager`, `pathlib`, `subprocess`, `sys`, `typing`

#### `test_test_registry.py` (160줄, 6,280B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `db` | `tmp_path` | `-` | 각 테스트마다 격리된 임시 DB. |

**class `TestInitDb`** (line 30)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_table_exists` | `self, db` | - |
| `test_idempotent` | `self, db` | 두 번 호출해도 오류 없이 동일 테이블. |

**class `TestImportTestFile`** (line 55)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_new_import` | `self, db, tmp_path` | 신규 파일 임포트 시 created=True. |
| `test_reimport_updates` | `self, db, tmp_path` | 재임포트 시 created=False, 코드가 갱신됨. |
| `test_missing_file_raises` | `self, db, tmp_path` | 존재하지 않는 파일은 FileNotFoundError. |

**class `TestImportAll`** (line 85)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_import_multiple_files` | `self, db, tmp_path` | test_*.py 파일 2개가 있으면 2개 임포트. |
| `test_import_all_result_names` | `self, db, tmp_path` | 임포트된 이름이 파일 stem과 일치. |

**class `TestListTests`** (line 103)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_empty_list` | `self, db` | 임포트 전에는 빈 목록. |
| `test_list_after_import` | `self, db, tmp_path` | 임포트 후 목록에 포함됨. |

**class `TestGetTest`** (line 121)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_get_existing` | `self, db, tmp_path` | 존재하는 이름으로 조회 시 dict 반환. |
| `test_get_nonexistent_returns_none` | `self, db` | 존재하지 않는 이름은 None 반환. |

**class `TestRunTest`** (line 139)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_run_passing_test` | `self, db, tmp_path` | 간단한 통과 테스트 코드를 저장하고 실행. |
| `test_run_failing_test` | `self, db, tmp_path` | 실패하는 테스트 코드를 저장하고 실행. |
| `test_run_nonexistent_returns_error` | `self, db` | 존재하지 않는 이름은 error 키 반환. |

의존성: `orchestrator`, `pathlib`, `pytest`, `sqlite3`

#### `test_tool_registry.py` (159줄, 5,741B)
> orchestrator/tool_registry.py에 대한 단위 테스트

**class `TestLoadLocalModules`** (line 13)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `setup_method` | `self` | 각 테스트 전 TOOLS/TOOL_DESCRIPTIONS 초기화 |
| `test_successful_load` | `self` | 정상 모듈 로드 시 TOOLS에 함수가 등록됨 |
| `test_failed_module_logged` | `self` | 존재하지 않는 모듈 로드 시 에러 로깅 후 계속 진행 |
| `test_all_tools_have_descriptions` | `self` | 로드된 모든 도구에 설명이 있음 |

**class `TestGetTool`** (line 43)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `setup_method` | `self` | - |
| `test_local_tool` | `self` | 로컬 도구 이름으로 함수 반환 |
| `test_alias_resolution` | `self` | 별칭으로 MCP 도구 검색 |
| `test_nonexistent_tool` | `self` | 존재하지 않는 도구는 None 반환 |

**class `TestToolProviders`** (line 74)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `setup_method` | `self` | - |
| `test_get_tool_providers_empty` | `self` | 제공자가 없으면 빈 리스트 |
| `test_get_tool_providers_single` | `self` | 단일 제공자 반환 |
| `test_get_tool_providers_multiple` | `self` | 다중 제공자 반환 |
| `test_set_tool_preference_valid` | `self` | 유효한 서버로 선호 설정 성공 |
| `test_set_tool_preference_invalid_server` | `self` | 존재하지 않는 서버로 선호 설정 실패 |
| `test_get_duplicate_tools` | `self` | 2개 이상 서버가 제공하는 도구만 반환 |
| `test_get_tool_uses_preference` | `self` | 선호 서버가 설정되면 해당 세션 사용 |

**class `TestGetAllToolDescriptions`** (line 155)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_dict` | `self` | 반환 타입이 dict |

의존성: `importlib`, `pytest`, `unittest`

#### `test_web_router.py` (341줄, 15,963B)
> orchestrator/web_router.py에 대한 단위 테스트

**class `TestConversations`** (line 14)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_conversations_empty` | `self` | - |
| `test_list_conversations_with_keyword_filter` | `self` | - |
| `test_get_conversation_found` | `self` | - |
| `test_get_conversation_not_found` | `self` | - |
| `test_delete_conversation_found` | `self` | - |
| `test_delete_conversation_not_found` | `self` | - |

**class `TestFunctions`** (line 106)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_functions` | `self` | - |
| `test_get_function_found` | `self` | - |
| `test_get_function_not_found` | `self` | - |

**class `TestSettingsPrompts`** (line 155)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_prompts` | `self` | - |
| `test_create_prompt` | `self` | - |
| `test_update_prompt_found` | `self` | - |
| `test_update_prompt_not_found` | `self` | - |
| `test_delete_prompt_found` | `self` | - |

**class `TestSettingsSkills`** (line 236)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_skills` | `self` | - |
| `test_toggle_skill_found` | `self` | - |
| `test_toggle_skill_not_found` | `self` | - |

**class `TestSettingsPersonas`** (line 283)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_list_personas` | `self` | - |
| `test_create_persona` | `self` | - |
| `test_delete_persona_found` | `self` | - |
| `test_delete_persona_not_found` | `self` | - |

의존성: `api`, `httpx`, `pytest`, `unittest`

#### `token_tracker.py` (128줄, 4,877B)
> 요청별 LLM 토큰 사용량 추적.  ContextVar 기반으로 async 요청 단위로 격리됩니다. 각 LLM 클라이언트가 record()를 호출하고, api.py가 get_accumulated()로 수집합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `calculate_cost` | `model: str, input_tokens: int, output_tokens: int` | `float` | 모델명 + 토큰 수로 USD 비용을 계산합니다. 미등록 모델은 0.0 반환. |
| `begin_tracking` | `` | `None` | 현재 async 컨텍스트에서 토큰 추적을 시작합니다 (요청 핸들러 진입 시 호출). |
| `record` | `provider: str, model: str, input_tokens: int, o...` | `None` | 토큰 사용 1건을 현재 컨텍스트에 기록합니다. begin_tracking() 이후에만 동작합니다. |
| `get_accumulated` | `` | `Optional[dict]` | 수집된 토큰 사용량을 집계하여 dict로 반환합니다. 기록이 없으면 None. |

**class `_Entry`** (line 67)

의존성: `contextvars`, `dataclasses`, `typing`

#### `tool_discoverer.py` (289줄, 10,567B)
> Phase 3 — 도구 발견 및 자동 구현 모듈.  우선순위:   1. 로컬 TOOLS / MCP 등록 도구에서 검색 (즉시)   2. npm/pip MCP 서버 탐색 (subprocess 기반)   3. LLM(high 티어)으로 Python 함수 자동 생성 → mcp_db_manager 저장 → 즉시 활성화  보안:   - npm/pip 명령 화이트리스

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `find_in_registered_tools` | `tool_hint: str` | `Optional[str]` | 등록된 도구 중 tool_hint와 이름이 일치하거나 포함된 것을 반환합니다. |
| `find_tools_for_step` | `tool_hints: List[str]` | `Dict[str, Optional[str]]` | tool_hints 목록에 대해 등록 도구 매핑을 반환합니다. |
| `search_npm_mcp` | `tool_hint: str` | `List[Dict[str, str]]` | npm에서 MCP 서버 패키지를 검색합니다. |
| `async generate_tool_implementation` | `tool_hint: str, context: str, model_preference:...` | `Optional[int]` | LLM으로 Python 도구 함수를 생성하고 mcp_db_manager에 저장합니다. |
| `async discover_and_resolve` | `missing_tools: List[str], context: str, model_p...` | `Dict[str, Dict[str, Any]]` | 누락 도구 목록에 대해 발견/구현을 시도합니다. |
| `get_gap_report` | `limit: int` | `List[Dict[str, Any]]` | 최근 tool_gap_log를 조회합니다. |

의존성: `ast`, `constants`, `json`, `llm_client`, `logging`, `re`, `subprocess`, `typing`

#### `tool_registry.py` (301줄, 11,452B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async initialize` | `` | `-` | 모든 로컬 모듈과 MCP 서버를 초기화합니다. |
| `async shutdown` | `` | `-` | MCP 서버 연결을 정리합니다. |
| `async ensure_tool_server_connected` | `tool_name: str` | `None` | P3-D: on-demand 서버의 도구가 요청될 때 지연 연결합니다. |
| `get_tool` | `name: str` | `Optional[Callable]` | 이름으로 도구 함수를 가져옵니다. |
| `get_tool_providers` | `name: str` | `List[dict]` | 해당 도구를 제공하는 모든 서버 정보를 반환합니다. |
| `set_tool_preference` | `tool_name: str, server_name: str` | `bool` | 특정 도구의 선호 서버를 설정합니다. |
| `get_duplicate_tools` | `` | `Dict[str, List[str]]` | 2개 이상의 서버가 제공하는 도구 목록을 반환합니다. |
| `get_all_tool_descriptions` | `` | `Dict[str, str]` | 모든 도구(로컬 + MCP)의 이름과 설명을 반환합니다. |
| `get_filtered_tool_descriptions` | `allowed_skills` | `Dict[str, str]` | allowed_skills 필터를 적용한 도구 이름/설명 딕셔너리 반환. |

의존성: `contextlib`, `importlib`, `inspect`, `logging`, `mcp`, `os`, `typing`

#### `web_router.py` (290줄, 9,413B)
> 웹 UI용 REST API 라우터 — /api/v1 prefix.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `list_conversations` | `keyword: Optional[str], status: Optional[str], ...` | `-` | - |
| `get_conversation` | `convo_id: str` | `-` | - |
| `delete_conversation` | `convo_id: str` | `-` | - |
| `list_groups` | `` | `-` | - |
| `get_function_stats` | `` | `-` | - |
| `list_functions` | `module_group: Optional[str], active_only: bool` | `-` | - |
| `get_function_versions` | `func_name: str` | `-` | - |
| `get_function` | `func_name: str` | `-` | - |
| `list_prompts` | `` | `-` | - |
| `create_prompt` | `body: SystemPromptCreate` | `-` | - |
| `update_prompt` | `name: str, body: SystemPromptUpdate` | `-` | - |
| `delete_prompt` | `name: str` | `-` | - |
| `list_skills` | `` | `-` | - |
| `toggle_skill` | `name: str, body: SkillToggle` | `-` | - |
| `list_personas` | `` | `-` | - |
| `create_persona` | `body: PersonaCreate` | `-` | - |
| `update_persona` | `name: str, body: PersonaUpdate` | `-` | - |
| `delete_persona` | `name: str` | `-` | - |
| `list_macros` | `` | `-` | - |
| `list_workflows` | `` | `-` | - |

**class `SystemPromptCreate`** (line 19)

**class `SystemPromptUpdate`** (line 26)

**class `PersonaCreate`** (line 32)

**class `PersonaUpdate`** (line 42)

**class `SkillToggle`** (line 51)

의존성: `fastapi`, `pydantic`, `typing`

### static/

#### `index.html` (?줄, 38,394B)

### system_prompts/

#### `default.txt` (1줄, 48B)

---

## 12. 모듈 간 의존성 맵 (자동 생성)

```
  main.py → orchestrator.agent_config_manager, orchestrator.graph_manager, orchestrator.history_manager.list_conversations, orchestrator.history_manager.load_conversation, orchestrator.history_manager.new_conversation, orchestrator.history_manager.split_conversation, orchestrator.issue_tracker, orchestrator.llm_client.generate_clarifying_questions, orchestrator.llm_client.summarize_history, orchestrator.mcp_db_manager, orchestrator.mcp_manager, orchestrator.model_manager.fetch_models, orchestrator.model_manager.get_active_model, orchestrator.model_manager.list_providers, orchestrator.model_manager.load_config, orchestrator.model_manager.set_active_model, orchestrator.pipeline_db.delete_template, orchestrator.pipeline_db.disable_template, orchestrator.pipeline_db.enable_template, orchestrator.pipeline_db.get_template, orchestrator.pipeline_db.get_template_stats, orchestrator.pipeline_db.init_db, orchestrator.pipeline_db.list_templates, orchestrator.test_registry, orchestrator.tool_discoverer.discover_and_resolve, orchestrator.tool_discoverer.get_gap_report, orchestrator.tool_registry.TOOL_DESCRIPTIONS
  test_hashline_editor.py → mcp_modules.hashline_editor._compute_line_hash, mcp_modules.hashline_editor.hashline_edit, mcp_modules.hashline_editor.read_file_with_hashes
  api.py → .agent_config_manager, .graph_manager, .history_manager, .issue_tracker, .mcp_db_manager, .pipeline_db, .pipeline_manager, .token_tracker, .tool_registry
  claude_client.py → .agent_config_manager, .token_tracker
  gemini_client.py → .agent_config_manager, .token_tracker
  history_manager.py → .graph_manager
  llm_client.py → .agent_config_manager, .claude_client, .gemini_client, .ollama_client
  mcp_manager.py → .config
  ollama_client.py → .agent_config_manager, .token_tracker
  pipeline_manager.py → .graph_manager, .history_manager, .llm_router, .pipeline_db, .template_engine, .token_tracker, .tool_registry
  template_engine.py → .pipeline_db
  test_agent_config_manager.py → .agent_config_manager, orchestrator.agent_config_manager
  test_config.py → .config
  test_gemini_client.py → .gemini_client
  test_graph_manager.py → orchestrator.gemini_client, orchestrator.gemini_client.detect_topic_split, orchestrator.gemini_client.extract_keywords, orchestrator.graph_manager._fetch_keywords, orchestrator.graph_manager.assign_conversation_to_group, orchestrator.graph_manager.assign_conversation_to_topic, orchestrator.graph_manager.assign_keywords_to_conversation, orchestrator.graph_manager.create_conversation, orchestrator.graph_manager.create_group, orchestrator.graph_manager.create_topic, orchestrator.graph_manager.delete_conversation, orchestrator.graph_manager.delete_group, orchestrator.graph_manager.delete_topic, orchestrator.graph_manager.get_db, orchestrator.graph_manager.get_linked_conversations, orchestrator.graph_manager.get_or_create_keyword, orchestrator.graph_manager.init_db, orchestrator.graph_manager.link_conversations, orchestrator.graph_manager.link_topics, orchestrator.graph_manager.list_conversations, orchestrator.graph_manager.list_groups, orchestrator.graph_manager.list_keywords, orchestrator.graph_manager.list_topics, orchestrator.graph_manager.load_conversation, orchestrator.graph_manager.migrate_json_to_sqlite, orchestrator.graph_manager.remove_conversation_from_group, orchestrator.graph_manager.save_conversation, orchestrator.graph_manager.split_conversation, orchestrator.graph_manager.update_conversation_keywords
  test_issue_tracker.py → orchestrator.issue_tracker.capture, orchestrator.issue_tracker.capture_exception, orchestrator.issue_tracker.get_issue, orchestrator.issue_tracker.init_db, orchestrator.issue_tracker.list_issues, orchestrator.issue_tracker.update_status
  test_mcp_db_manager.py → orchestrator.constants.MAX_FUNC_NAMES_PER_SESSION, orchestrator.graph_manager.get_db, orchestrator.mcp_db_manager, orchestrator.mcp_db_manager.MCP_CACHE_DIR, orchestrator.mcp_db_manager._extract_preamble, orchestrator.mcp_db_manager._extract_test_map, orchestrator.mcp_db_manager._validate_code_syntax, orchestrator.mcp_db_manager.activate_function, orchestrator.mcp_db_manager.end_session, orchestrator.mcp_db_manager.generate_temp_module, orchestrator.mcp_db_manager.get_active_function, orchestrator.mcp_db_manager.get_function_versions, orchestrator.mcp_db_manager.get_usage_stats, orchestrator.mcp_db_manager.import_from_file, orchestrator.mcp_db_manager.init_db, orchestrator.mcp_db_manager.list_functions, orchestrator.mcp_db_manager.load_module_in_memory, orchestrator.mcp_db_manager.log_usage, orchestrator.mcp_db_manager.register_function, orchestrator.mcp_db_manager.run_function_tests, orchestrator.mcp_db_manager.set_module_preamble, orchestrator.mcp_db_manager.start_session, orchestrator.mcp_db_manager.update_function_test_code
  test_mcp_manager.py → .mcp_manager
  test_model_manager.py → .model_manager
  test_ollama_client.py → .ollama_client
  test_omo_features.py → orchestrator.agent_config_manager, orchestrator.llm_client._call_with_fallback, orchestrator.llm_client._get_fallback_chain, orchestrator.llm_client.classify_intent, orchestrator.llm_client.summarize_history, orchestrator.tool_registry
  test_pipeline.py → orchestrator.llm_router.get_tier, orchestrator.llm_router.infer_complexity_from_query, orchestrator.pipeline_db.auto_disable_failing_templates, orchestrator.pipeline_db.clear_cursor, orchestrator.pipeline_db.confirm_design, orchestrator.pipeline_db.create_design, orchestrator.pipeline_db.disable_template, orchestrator.pipeline_db.enable_template, orchestrator.pipeline_db.find_best_template, orchestrator.pipeline_db.get_active_design, orchestrator.pipeline_db.get_cursor, orchestrator.pipeline_db.get_db, orchestrator.pipeline_db.get_design, orchestrator.pipeline_db.get_task_plan_cache, orchestrator.pipeline_db.get_template_stats, orchestrator.pipeline_db.increment_template_fail, orchestrator.pipeline_db.init_db, orchestrator.pipeline_db.list_templates, orchestrator.pipeline_db.log_tool_gap, orchestrator.pipeline_db.save_execution_template, orchestrator.pipeline_db.save_task_plan_cache, orchestrator.pipeline_db.set_cursor, orchestrator.pipeline_manager._make_task_signature, orchestrator.template_engine.find_best_template_scored, orchestrator.tool_discoverer._is_code_safe, orchestrator.tool_discoverer._run_safe, orchestrator.tool_discoverer.find_tools_for_step, orchestrator.tool_discoverer.get_gap_report, orchestrator.tool_registry
  test_test_registry.py → orchestrator.test_registry.get_test, orchestrator.test_registry.import_all, orchestrator.test_registry.import_test_file, orchestrator.test_registry.init_db, orchestrator.test_registry.list_tests, orchestrator.test_registry.run_test
  test_tool_registry.py → .config, .tool_registry
  tool_discoverer.py → .agent_config_manager, .mcp_db_manager, .pipeline_db, .tool_registry
  tool_registry.py → .config, .mcp_db_manager
  web_router.py → .agent_config_manager, .graph_manager, .mcp_db_manager
```
