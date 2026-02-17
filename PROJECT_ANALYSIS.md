# test02 프로젝트 분석 보고서

---
---

## 0. 요구사항 추적 (Requirements Tracker)

> **이 섹션은 매 작업 요청 시 갱신됩니다.**
> 마지막 갱신: 2026-02-17 (5가지 개선점 + 테스트 추가 반영)

### 0.1 완료된 요구사항 (Completed)

| # | 요구사항 | 적용 파일 | 상태 | 비고 |
|---|---------|-----------|------|------|
| 22 | MCP 연결 실패 graceful handling | tool_registry.py | DONE | 실패 카운트 + 실패 서버명 warning 로그 |
| 23 | ALLOWED_BASE_PATH 보안 개선 | code_execution_atomic.py | DONE | 모듈 위치 기반 + 환경변수 오버라이드 |
| 24 | orchestrator 테스트 추가 (26개) | test_api.py, test_gemini_client.py, test_tool_registry.py | DONE | pytest-asyncio 의존성 추가 |
| 25 | history truncation max_chars 보수적 조정 | gemini_client.py | DONE | 8000→6000, DEFAULT_HISTORY_MAX_CHARS 상수 추출 |
| 26 | pytest-asyncio를 requirements.txt에 추가, 로그성 목록 최근 5개 유지 정책 적용 | requirements.txt, PROJECT_ANALYSIS.md | DONE | 완료 요구사항/변경이력 최근 5개만 보존 |

> *#1~#21은 이전 작업으로 정리 완료 (최근 5개만 표시)*

### 0.2 진행 중인 요구사항 (In Progress)

| # | 요구사항 | 관련 파일 | 상태 | 비고 |
|---|---------|-----------|------|------|
| - | 현재 없음 | - | - | - |

### 0.3 미구현 / 예정 요구사항 (Pending / Backlog)

| # | 요구사항 | 관련 스펙 | 우선순위 | 비고 |
|---|---------|-----------|----------|------|
| P1 | file_management 모듈 Python 구현 | file_management.spec.yaml | Medium | MCP 서버로 위임 중이지만 로컬 fallback 필요할 수 있음 |
| P2 | file_content_operations 모듈 Python 구현 | file_content_operations.spec.yaml | Medium | 동일 |
| P3 | file_attributes 모듈 Python 구현 | file_attributes.spec.yaml | Low | MCP filesystem 서버가 커버 |
| P4 | file_system_composite 모듈 Python 구현 | file_system_composite.spec.yaml | Medium | move, find, replace 등 고수준 기능 |
| P5 | git_version_control 모듈 Python 구현 | git_version_control.spec.yaml | Low | MCP git 서버가 커버 |
| P6 | web_network_atomic 모듈 Python 구현 | web_network_atomic.spec.yaml | Medium | fetch, API 호출, DNS, SSL 등 |

### 0.4 변경 이력 (Change Log)

| 날짜 | 작업 내용 | 변경 파일 |
|------|-----------|-----------|
| 2026-02-17 | 알려진 이슈 해결: python_history.txt 삭제, history truncation 통합, plan[:1] 주석, exec()→subprocess 격리 | gemini_client.py, code_execution_atomic.py, test_code_execution_atomic.py, PROJECT_ANALYSIS.md |
| 2026-02-17 | 보고서 정리: 완료 요구사항/변경이력 축약, 해결된 이슈 제거 | PROJECT_ANALYSIS.md |
| 2026-02-17 | 5가지 개선: 보고서 정리, MCP graceful handling, ALLOWED_BASE_PATH 보안, orchestrator 테스트 26개 추가, history max_chars 조정 | PROJECT_ANALYSIS.md, tool_registry.py, code_execution_atomic.py, gemini_client.py, test_api.py, test_gemini_client.py, test_tool_registry.py |
| 2026-02-17 | pytest-asyncio requirements.txt 추가, 로그성 목록 최근 5개 유지 정책 적용 | requirements.txt, PROJECT_ANALYSIS.md |

> *최근 5개만 표시, 이전 이력은 정리 완료*

---
---

## 1. 프로젝트 개요

**프로젝트명**: Gemini Agent Orchestrator
**언어/런타임**: Python 3.12
**아키텍처**: ReAct (Reasoning + Acting) 기반 AI 에이전트 오케스트레이터
**LLM 백엔드**: Google Gemini API (gemini-2.0-flash / gemini-2.0-flash-lite)
**핵심 프레임워크**: FastAPI (서버), Typer (CLI), MCP (Model Context Protocol)

이 프로젝트는 사용자의 자연어 명령을 받아, Gemini LLM이 실행 계획을 수립하고, 등록된 도구(MCP)를 순차적으로 실행하여 작업을 완수하는 AI 에이전트 시스템입니다.

---

## 2. 디렉토리 구조

```
test02/
├── main.py                      # CLI 진입점 (Typer 앱)
├── requirements.txt             # Python 의존성
├── start.sh                     # venv 활성화 스크립트
├── pytest.ini                   # pytest 설정
├── .gitignore
├── orchestrator/                # 핵심 오케스트레이터 패키지
│   ├── __init__.py              # 패키지 초기화 (로깅 설정)
│   ├── config.py                # MCP 서버 및 로컬 모듈 설정
│   ├── models.py                # Pydantic 데이터 모델 정의
│   ├── api.py                   # FastAPI 엔드포인트 (핵심 ReAct 루프)
│   ├── gemini_client.py         # Gemini API 통신 (플래너, 답변 생성)
│   ├── history_manager.py       # 대화 이력 JSON 저장/로드
│   └── tool_registry.py         # 도구 등록소 (로컬 + MCP 서버)
├── mcp_modules/                 # MCP 도구 모듈 (로컬 구현체 + 스펙)
│   ├── code_execution_atomic.py       # 셸 실행, 파일 읽기, 환경변수 등
│   ├── code_execution_composite.py    # 스크립트 실행, 패키지 관리, Git, Docker
│   ├── user_interaction_atomic.py     # 사용자 입력, 메시지 출력, 테이블 등
│   ├── user_interaction_composite.py  # 선택지, 파일 경로, 폼 입력, diff 등
│   ├── test_code_execution_atomic.py  # 단위 테스트
│   ├── test_code_execution_composite.py
│   ├── test_user_interaction_atomic.py
│   ├── test_user_interaction_composite.py
│   └── *.spec.yaml / *.atomic.yaml   # MCP 스펙 정의 파일들
├── claude_tools/                 # 프로젝트 분석 자동화 도구 (토큰 절약용)
│   ├── __init__.py
│   ├── __main__.py              # CLI 진입점 (python -m claude_tools <cmd>)
│   ├── project_scanner.py       # 프로젝트 구조/함수 스냅샷 생성
│   ├── change_tracker.py        # 이전 스냅샷 대비 변경 감지
│   └── report_updater.py        # PROJECT_ANALYSIS.md 섹션 11,12 자동 갱신
├── venv/                        # Python 가상환경
├── system_prompts/              # 시스템 프롬프트 파일 (자동 생성)
└── history/                     # 대화 이력 JSON 파일
```

---

## 3. 핵심 아키텍처 흐름

### 3.1 ReAct 루프 (핵심 실행 사이클)

```
사용자 CLI 입력
  → main.py (Typer CLI)
    → POST /agent/decide_and_act (api.py)
      → gemini_client.generate_execution_plan()
        → Gemini LLM이 "다음 1개 실행 그룹" 생성
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

### 3.2 상태 흐름

| 상태 | 의미 |
|------|------|
| `PLAN_CONFIRMATION` | 다음 실행 그룹에 대한 사용자 승인 요청 |
| `STEP_EXECUTED` | 그룹 실행 완료, 다음 계획 수립 트리거 |
| `FINAL_ANSWER` | 모든 작업 완료, 최종 답변 제공 |
| `ERROR` | 오류 발생 |

---

## 4. 핵심 모듈 상세 분석

### 4.1 orchestrator/config.py
- `LOCAL_MODULES`: 로컬로 구현된 4개 MCP 모듈 지정
  - user_interaction_atomic, user_interaction_composite
  - code_execution_atomic, code_execution_composite
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
- `generate_execution_plan()`: ReAct 플래너 - `history[-10:]`로 최근 10개만 사용, 다음 1개 ExecutionGroup 생성 또는 빈 리스트(완료)
- `generate_final_answer()`: 전체 작업 이력 기반 최종 답변 생성 (15개 초과 시 `history[:2] + history[-13:]`로 truncation)
- `generate_title_for_conversation()`: 대화 제목 자동 생성 (5단어 이내, history 처음 2개만 사용)
- JSON 응답 모드 사용 (`response_mime_type="application/json"`)

### 4.4 orchestrator/api.py (FastAPI 엔드포인트)
- **`POST /agent/decide_and_act`**: ReAct 핵심 엔드포인트
  - user_input 있으면: 첫 계획 수립
  - user_input 없으면(STEP_EXECUTED 후): history 기반 다음 계획 또는 최종 답변
- **`POST /agent/execute_group`**: 저장된 단일 그룹 실행
  - 각 task의 tool 함수를 tool_registry에서 가져와 실행
  - async/sync 함수 자동 처리

### 4.5 orchestrator/tool_registry.py
- **로컬 도구**: `_load_local_modules()` - config.LOCAL_MODULES의 모듈들을 동적 import
- **MCP 도구**: `_connect_mcp_server()` - StdioServerParameters로 MCP 서버 연결
- `get_tool()`: 도구명으로 함수 반환 (로컬 → 별칭 → MCP 순서로 검색)
- MCP 도구는 `session.call_tool()`을 감싸는 async wrapper로 제공

### 4.6 orchestrator/history_manager.py
- JSON 기반 대화 이력 관리 (`history/` 디렉토리)
- 진행 중: UUID 기반 파일명 (`{uuid}.json`)
- 완료 시: 타임스탬프-제목 파일명 (`{YYYYMMDDHHMMSS}-{safe_title}.json`)
- `_sanitize_title()`: 파일명 안전 문자만 허용 (한글/영문/숫자/-, 최대 20자)
- 기존 UUID 파일 자동 삭제 후 최종 파일명으로 변환

### 4.7 main.py (CLI)
- `server` 명령: FastAPI 서버 실행 (uvicorn, 포트 충돌 자동 처리)
- `run` 명령: 에이전트 상호작용 루프 (--query, --continue, --req, --model-pref, --gem)
- `list` 명령: 저장된 대화 목록 표시
- httpx 클라이언트로 오케스트레이터 서버와 통신 (timeout=120s)

---

## 5. MCP 도구 모듈 분류

### 5.1 구현 완료 (Python 소스 존재)

| 모듈 | 레벨 | 주요 함수 |
|------|------|-----------|
| `code_execution_atomic` | Atomic | execute_shell_command, execute_python_code, read_code_file, get/set_environment_variable, execute_sql_query, check_port_status, get_code_complexity, get_function_signature, list_installed_packages, docker_list_containers/images |
| `code_execution_composite` | Composite | run_python_script, install/uninstall_python_package, lint_code_file, format_code_file, get_git_status, clone_git_repository, setup_python_venv, build_docker_image, run_container_from_image, get_container_logs |
| `user_interaction_atomic` | Atomic | ask_user_for_input, ask_for_multiline_input, ask_user_for_confirmation, ask_for_password, show_message, display_table, show_progress_bar, clear_screen, show_alert, render_markdown, show_spinner, update_last_line |
| `user_interaction_composite` | Composite | present_options_and_get_choice, present_checkbox_and_get_choices, ask_for_file/directory_path, confirm_critical_action, get_form_input, ask_for_validated_input, select_file_from_directory, show_diff, prompt_with_autocomplete |

### 5.2 스펙만 존재 (YAML, 미구현 또는 MCP 서버 위임)

| 스펙 파일 | 설명 |
|-----------|------|
| `file_management.spec.yaml` | create_directory, list_directory, rename, delete_file, delete_empty_directory |
| `file_content_operations.spec.yaml` | read/write/append_file, read/write_binary_file |
| `file_attributes.spec.yaml` | path_exists, is_file, is_directory, get_file_size, get_modification/creation_time |
| `file_system_composite.spec.yaml` | move, copy_directory, find_files/text/large_files, read_specific_lines, replace_text, get_directory_size, batch_rename, delete_directory_recursively |
| `git_version_control.spec.yaml` | git_init/clone/status/add/commit/push/pull/fetch/branch/merge/log/diff/tag/revert 등 20개 함수 |
| `web_network_atomic.spec.yaml` | fetch_url_content, download_file, api_get/post/put/delete, get_http_status/headers, ping_host, resolve_dns, parse_rss, send_email_smtp, get_ssl_cert, fetch_dynamic_content, ftp_upload/download |

---

## 6. 테스트 현황

| 테스트 파일 | 대상 모듈 | 테스트 수 | 특징 |
|-------------|-----------|-----------|------|
| test_code_execution_atomic.py | code_execution_atomic | ~15 | 성공/실패/엣지 케이스, mock 활용 |
| test_code_execution_composite.py | code_execution_composite | ~15 | _run_command 전체 모킹, subprocess 격리 |
| test_user_interaction_atomic.py | user_interaction_atomic | ~14 | monkeypatch로 Rich 입력 모킹 |
| test_user_interaction_composite.py | user_interaction_composite | ~12 | questionary 전체 모킹 |

**테스트 실행**: `pytest` (pytest.ini: `pythonpath = .`)

---

## 7. 의존성 (requirements.txt)

| 패키지 | 용도 |
|--------|------|
| fastapi | 오케스트레이터 API 서버 |
| uvicorn[standard] | ASGI 서버 |
| typer[all] | CLI 인터페이스 |
| pydantic | 데이터 모델 검증 |
| google-genai | Gemini API 클라이언트 |
| python-dotenv | .env 파일 로드 |
| httpx | 비동기 HTTP 클라이언트 |
| feedparser | RSS 피드 파싱 |
| bs4 | HTML 파싱 |
| requests_mock | 테스트용 HTTP 모킹 |
| pytest-mock | 테스트용 모킹 |
| mcp>=1.0.0 | MCP Python SDK |
| mcp-server-git | Git MCP 서버 |
| mcp-server-fetch | Fetch MCP 서버 |
| questionary | 대화형 사용자 입력 UI |

---

## 8. 보안 설계

- **셸 명령어**: `FORBIDDEN_COMMANDS` 차단 (rm, mv, dd, mkfs), `shlex.split`으로 인젝션 방지
- **파일 접근**: `ALLOWED_BASE_PATH` 기반 경로 조작(Path Traversal) 방지 (주의: `os.getcwd()` 기반이므로 실행 위치에 따라 달라짐)
- **코드 실행**: `sandboxed=True` 플래그 필수 (execute_python_code)
- **SQL**: 파라미터화 쿼리 강제 (`text()` + 바인딩)
- **패키지명**: 정규식 검증 (`VALID_PACKAGE_NAME_REGEX`)
- **Docker/Git URL**: 정규식 검증 (`VALID_DOCKER_NAME_REGEX`, `VALID_GIT_URL_REGEX`)

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
```

---

## 10. 알려진 이슈 및 개선 포인트

1. **스펙만 존재하는 모듈**: file_management, file_content_operations, file_attributes, file_system_composite, git_version_control, web_network_atomic 등은 YAML 스펙만 있고 Python 구현체가 없음 (MCP 서버로 위임 예정)

---

## 11. 파일별 상세 카탈로그 (자동 생성)

> 자동 생성 시각: 2026-02-17T09:11:28
> Python 파일: 25개 | 함수: 106개 | 클래스: 29개 | 총 라인: 4579줄

### ./

#### `PROJECT_ANALYSIS.md` (772줄, 47,493B)

#### `main.py` (232줄, 10,192B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `list_conversations_cmd` | `` | `-` | 저장된 대화 목록을 표시합니다. |
| `run` | `query: Annotated[str, typer.Option("--query", "...` | `-` | AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다. |
| `is_port_in_use` | `port: int, host: str` | `bool` | - |
| `run_server` | `host: Annotated[str, typer.Option(help="서버가 바인딩...` | `-` | FastAPI 오케스트레이터 서버를 실행합니다. |

의존성: `httpx`, `orchestrator`, `os`, `re`, `rich`, `socket`, `subprocess`, `time`, `typer`, `typing`

#### `pytest.ini` (3줄, 37B)

#### `requirements.txt` (16줄, 363B)

#### `start.sh` (3줄, 81B)

### claude_tools/

#### `__init__.py` (2줄, 128B)

#### `__main__.py` (107줄, 3,927B)
> claude_tools CLI 진입점  사용법:     python -m claude_tools scan              # 프로젝트 스캔 (스냅샷 생성)     python -m claude_tools changes           # 변경 사항 감지     python -m claude_tools update            # 분석 보고서

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `main` | `` | `-` | - |

의존성: `change_tracker`, `json`, `os`, `project_scanner`, `report_updater`, `sys`

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

#### `report_updater.py` (183줄, 7,122B)
> report_updater.py - PROJECT_ANALYSIS.md 자동 갱신  스냅샷과 변경 사항 데이터를 기반으로 분석 보고서의 특정 섹션을 자동 갱신합니다. Claude가 이 보고서만 읽으면 전체 프로젝트를 파악할 수 있도록 합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `update_report` | `project_root: str` | `str` | PROJECT_ANALYSIS.md의 자동 생성 섹션(11, 12)을 갱신. |

의존성: `datetime`, `json`, `os`, `pathlib`, `project_scanner`, `re`, `sys`, `typing`

### mcp_modules/

#### `__init__.py` (9줄, 1,116B)

의존성: `code_execution_atomic`, `code_execution_composite`, `user_interaction_atomic`, `user_interaction_composite`

#### `code_execution_atomic.py` (489줄, 21,022B)
> code_execution_atomic.py: AI 에이전트를 위한 레벨 1 원자(Atomic) MCP 핵심 라이브러리  이 모듈은 AI 에이전트가 운영체제, 파일 시스템, 코드 분석 등 기본적인 작업을 수행할 수 있도록 돕는 저수준(low-level)의 원자적 기능들을 제공합니다. 각 함수는 프로덕션 환경에서 사용될 것을 가정하여 보안, 로깅, 예외 처리

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `execute_shell_command` | `command: str, timeout: int` | `str` | 안전하게 셸 명령어를 실행하고 결과를 문자열로 반환합니다. |
| `execute_python_code` | `code_str: str, sandboxed: bool, timeout: int` | `Any` | 파이썬 코드 문자열을 별도 프로세스에서 격리 실행하고 결과를 반환합니다. |
| `read_code_file` | `path: str` | `str` | 지정된 경로의 코드 파일 내용을 안전하게 읽어 문자열로 반환합니다. |
| `get_environment_variable` | `var_name: str` | `Optional[str]` | 특정 환경 변수의 값을 조회합니다. |
| `set_environment_variable` | `var_name: str, value: str` | `bool` | 특정 환경 변수의 값을 설정하거나 새로 생성합니다. |
| `execute_sql_query` | `db_uri: str, query: str, params: Optional[Dict]` | `List[Dict]` | 지정된 데이터베이스에 접속하여 SQL 쿼리를 안전하게 실행하고 결과를 반환합니다. |
| `check_port_status` | `host: str, port: int, timeout: int` | `Tuple[bool, str]` | 특정 호스트의 포트가 열려 있는지 확인합니다. |
| `get_code_complexity` | `file_path: str` | `Dict[str, Any]` | 코드 파일의 순환 복잡도(Cyclomatic Complexity)를 측정합니다. |
| `get_function_signature` | `file_path: str, function_name: str` | `Optional[str]` | 파이썬 파일 내에서 특정 함수의 시그니처를 추출합니다. |
| `list_installed_packages` | `` | `List[Tuple[str, str]]` | 현재 파이썬 환경에 설치된 패키지와 버전을 목록으로 반환합니다. |
| `docker_list_containers` | `` | `List[Dict]` | 실행 중이거나 정지된 모든 도커 컨테이너 목록을 반환합니다. |
| `docker_list_images` | `` | `List[Dict]` | 로컬에 저장된 모든 도커 이미지 목록을 반환합니다. |

의존성: `ast`, `importlib`, `json`, `logging`, `os`, `pathlib`, `shlex`, `socket`, `sqlalchemy`, `subprocess`

#### `code_execution_atomic.spec.yaml` (219줄, 8,179B)

정의된 MCP: `code_execution_atomic`, `execute_shell_command`, `command`, `timeout`, `execute_python_code`, `code_str`, `sandboxed`, `read_code_file`, `path`, `get_environment_variable`, `var_name`, `set_environment_variable`, `var_name`, `value`, `execute_sql_query`...

#### `code_execution_composite.py` (421줄, 16,378B)
> Composite Code & Execution Primitives ===================================== 이 모듈은 파일 실행, 패키지 관리, 버전 관리, 컨테이너 제어 등 복잡한 코드 및 시스템 실행 작업을 위한 복합 MCP(Mission Control Primitives)를 제공합니다. 모든 함수는 보안을 위해 외부 입력을

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `run_python_script` | `script_path: str` | `str` | 지정된 경로의 파이썬 스크립트 파일을 실행하고 결과를 반환합니다. |
| `install_python_package` | `package_name: str` | `str` | pip을 이용해 특정 파이썬 패키지를 설치합니다. |
| `uninstall_python_package` | `package_name: str` | `str` | pip을 이용해 설치된 파이썬 패키지를 삭제합니다. |
| `lint_code_file` | `file_path: str, linter: str` | `str` | 코드 파일의 문법 오류나 스타일 문제를 검사(linting)합니다. |
| `format_code_file` | `file_path: str` | `str` | 코드 포매터(black)를 실행하여 코드 스타일을 자동으로 정리합니다. |
| `get_git_status` | `repo_path: str` | `str` | 지정된 로컬 저장소의 git 상태를 확인합니다. |
| `clone_git_repository` | `repo_url: str, clone_path: str` | `str` | 원격 Git 저장소를 지정된 경로에 복제(clone)합니다. |
| `setup_python_venv` | `path: str` | `str` | 지정된 경로에 파이썬 가상 환경을 생성합니다. |
| `build_docker_image` | `dockerfile_path: str, image_name: str` | `str` | 지정된 Dockerfile을 사용하여 새로운 도커 이미지를 빌드합니다. |
| `run_container_from_image` | `image_name: str, ports: Dict[int, int]` | `str` | 지정된 도커 이미지로 컨테이너를 실행합니다. |
| `get_container_logs` | `container_id: str` | `str` | 실행 중인 도커 컨테이너의 로그를 가져옵니다. |

의존성: `logging`, `pathlib`, `re`, `shlex`, `subprocess`, `typing`

#### `code_execution_composite.spec.yaml` (198줄, 7,226B)

정의된 MCP: `run_python_script`, `script_path`, `install_python_package`, `package_name`, `uninstall_python_package`, `package_name`, `lint_code_file`, `file_path`, `linter`, `format_code_file`, `file_path`, `get_git_status`, `repo_path`, `clone_git_repository`, `repo_url`...

#### `file_attributes.spec.yaml` (87줄, 3,022B)

정의된 MCP: `file_attributes`, `path_exists`, `path`, `is_file`, `path`, `is_directory`, `path`, `get_file_size`, `path`, `get_modification_time`, `path`, `get_creation_time`, `path`, `get_current_working_directory`

#### `file_content_operations.spec.yaml` (98줄, 3,456B)

정의된 MCP: `file_content_operations`, `read_file`, `path`, `encoding`, `read_binary_file`, `path`, `write_file`, `path`, `content`, `encoding`, `write_binary_file`, `path`, `content`, `append_to_file`, `path`...

#### `file_management.spec.yaml` (97줄, 3,801B)

정의된 MCP: `file_management`, `create_directory`, `path`, `exist_ok`, `list_directory`, `path`, `rename`, `source_path`, `new_name`, `delete_file`, `path`, `delete_empty_directory`, `path`

#### `file_system_composite.spec.yaml` (94줄, 5,443B)

정의된 MCP: `file_system_composite`, `move`, `source, type: str, description: 이동할 원본 경로, required: true}`, `copy_directory`, `find_files`, `find_text_in_files`, `text, type: str, description: 검색할 텍스트, required: true}`, `find_large_files`, `read_specific_lines`, `path, type: str, description: 읽을 파일 경로, required: true}`, `replace_text_in_file`, `path, type: str, description: 수정할 파일 경로, required: true}`, `get_directory_size`, `batch_rename`, `delete_directory_recursively`...

#### `git_version_control.spec.yaml` (267줄, 8,991B)

정의된 MCP: `git_version_control`, `git_init`, `path`, `git_clone`, `repo_url`, `local_path`, `git_status`, `repo_path`, `git_add`, `repo_path`, `files`, `git_commit`, `repo_path`, `message`, `git_push`...

#### `test_code_execution_atomic.py` (194줄, 8,240B)
> test_code_execution_automic.py: code_execution_atomic 모듈에 대한 단위 테스트

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `temp_file` | `tmp_path` | `-` | 테스트용 임시 파일을 생성하는 Fixture |

**class `TestExecuteShellCommand`** (line 34)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_success` | `self` | 성공 케이스: 간단한 echo 명령어 실행 |
| `test_failure_command_not_found` | `self` | 실패 케이스: 존재하지 않는 명령어 |
| `test_edge_case_forbidden_command` | `self` | 엣지 케이스: 금지된 명령어 실행 시도 |
| `test_edge_case_timeout` | `self` | 엣지 케이스: 명령어 시간 초과 |

**class `TestExecutePythonCode`** (line 56)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_success` | `self` | 성공 케이스: 간단한 연산 코드 실행 |
| `test_failure_no_sandbox_flag` | `self` | 실패 케이스: sandboxed=True 플래그 없이 실행 |
| `test_edge_case_syntax_error` | `self` | 엣지 케이스: 문법 오류가 있는 코드 (subprocess에서 RuntimeError로 래핑) |
| `test_edge_case_timeout` | `self` | 엣지 케이스: 코드 실행 시간 초과 |

**class `TestReadCodeFile`** (line 77)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_success` | `self, mock_allowed_path, temp_file` | 성공 케이스: 생성된 임시 파일 읽기 |
| `test_failure_file_not_found` | `self` | 실패 케이스: 존재하지 않는 파일 읽기 |
| `test_edge_case_path_traversal` | `self` | 엣지 케이스: 허용된 경로 외부 접근 시도 |

**class `TestEnvironmentVariables`** (line 97)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_get_set_variable_success` | `self` | 성공 케이스: 환경 변수 설정 및 조회 |
| `test_get_non_existent_variable` | `self` | 엣지 케이스: 존재하지 않는 환경 변수 조회 |

**class `TestCheckPortStatus`** (line 119)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_success_port_open` | `self, mock_socket` | 성공 케이스: 포트가 열려있는 경우 |
| `test_failure_port_closed` | `self, mock_socket` | 실패 케이스: 포트가 닫혀있는 경우 |
| `test_edge_case_invalid_host` | `self` | 엣지 케이스: 유효하지 않은 호스트 |

**class `TestGetFunctionSignature`** (line 146)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_success` | `self, mock_allowed_path, temp_file` | 성공 케이스: 함수 시그니처 추출 |
| `test_failure_function_not_found` | `self, temp_file` | 실패 케이스: 존재하지 않는 함수 |
| `test_edge_case_file_not_found` | `self` | 엣지 케이스: 파일이 없음 |

**class `TestExternalDependencies`** (line 166)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_docker_list_containers_success` | `self, mock_shell` | Docker 컨테이너 목록 조회 성공 케이스 |
| `test_docker_list_images_empty` | `self, mock_shell` | Docker 이미지 목록이 비어있는 엣지 케이스 |
| `test_get_code_complexity_failure` | `self, mock_shell, tmp_path: Path` | Radon 실행 실패 케이스 |

의존성: `os`, `pathlib`, `pytest`, `subprocess`, `unittest`

#### `test_code_execution_composite.py` (200줄, 8,021B)
> code_execution_composite 모듈에 대한 단위 테스트 =============================================== pytest와 mocker를 사용하여 외부 프로세스 실행 없이 각 MCP의 로직, 입력 유효성 검사, 오류 처리를 테스트합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `mock_run_command` | `` | `-` | - |

**class `TestRunPythonScript`** (line 39)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_run_python_script_success` | `self, mock_run_command, tmp_path` | - |
| `test_run_python_script_file_not_found` | `self` | - |
| `test_run_python_script_command_error` | `self, mock_run_command, tmp_path` | - |

**class `TestPackageManagement`** (line 66)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_install_package_success` | `self, mock_run_command` | - |
| `test_uninstall_package_success` | `self, mock_run_command` | - |
| `test_install_invalid_package_name` | `self, invalid_name` | - |
| `test_uninstall_invalid_package_name` | `self, invalid_name` | - |

**class `TestCodeTools`** (line 94)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_lint_code_file_success` | `self, mock_run_command, tmp_path` | - |
| `test_format_code_file_success` | `self, mock_run_command, tmp_path` | - |
| `test_lint_file_not_found` | `self` | - |

**class `TestGitTools`** (line 119)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_get_git_status_success` | `self, mock_run_command, tmp_path` | - |
| `test_clone_git_repository_success` | `self, mock_run_command, tmp_path` | - |
| `test_clone_invalid_url` | `self` | - |
| `test_clone_path_exists` | `self, tmp_path` | - |

**class `TestVenv`** (line 149)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_setup_python_venv_success` | `self, mock_run_command, tmp_path` | - |
| `test_setup_venv_path_exists` | `self, tmp_path` | - |

**class `TestDockerTools`** (line 165)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_build_docker_image_success` | `self, mock_run_command, tmp_path` | - |
| `test_run_container_success` | `self, mock_run_command` | - |
| `test_get_container_logs_success` | `self, mock_run_command` | - |
| `test_build_invalid_image_name` | `self, tmp_path` | - |
| `test_run_invalid_port` | `self` | - |

의존성: `code_execution_composite`, `pytest`, `subprocess`, `unittest`

#### `test_user_interaction_atomic.py` (145줄, 6,002B)
> test_user_interaction_atomic.py  'interaction_utils.py' 모듈의 MCP 함수들에 대한 단위 테스트.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `test_ask_user_for_input_success` | `monkeypatch` | `-` | ask_user_for_input 성공 케이스 테스트 |
| `test_ask_for_multiline_input_success` | `monkeypatch` | `-` | ask_for_multiline_input 성공 케이스 테스트 |
| `test_ask_user_for_confirmation_yes` | `monkeypatch` | `-` | ask_user_for_confirmation 'yes' 케이스 테스트 |
| `test_ask_user_for_confirmation_no` | `monkeypatch` | `-` | ask_user_for_confirmation 'no' 케이스 테스트 |
| `test_ask_for_password_success` | `monkeypatch` | `-` | ask_for_password 성공 케이스 테스트 |
| `test_show_message_success` | `capsys` | `-` | show_message가 메시지를 정상 출력하는지 테스트 |
| `test_show_alert_success` | `capsys` | `-` | show_alert가 수준별 메시지를 정상 출력하는지 테스트 |
| `test_show_alert_success` | `monkeypatch` | `-` | show_alert가 성공 메시지를 올바른 스타일로 출력하는지 테스트 |
| `test_display_table_success` | `capsys` | `-` | display_table이 표를 정상 출력하는지 테스트 |
| `test_clear_screen` | `mock_system` | `-` | clear_screen이 올바른 OS 명령어를 호출하는지 테스트 |
| `test_ask_for_multiline_input_empty` | `monkeypatch` | `-` | ask_for_multiline_input 빈 입력 엣지 케이스 테스트 |
| `test_ask_for_password_fail` | `mock_getpass` | `-` | ask_for_password가 예외를 발생시키는지 테스트 |
| `test_display_table_empty_data_fail` | `` | `-` | display_table에 빈 데이터를 전달 시 예외 발생 테스트 |
| `test_display_table_empty_headers_fail` | `` | `-` | display_table에 빈 헤더를 전달 시 예외 발생 테스트 |
| `test_display_table_mismatched_keys_edge_case` | `capsys` | `-` | display_table에 키가 없는 데이터가 포함된 엣지 케이스 테스트 |

의존성: `io`, `os`, `pytest`, `rich`, `sys`, `unittest`, `user_interaction_atomic`

#### `test_user_interaction_composite.py` (181줄, 8,561B)
> user_interaction_composite 모듈에 대한 단위 테스트.  `pytest`와 `unittest.mock`을 사용하여 대화형 프롬프트를 시뮬레이션하고 각 MCP 함수의 동작을 검증합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `mock_questionary` | `` | `-` | questionary 라이브러리의 함수들을 모킹(Mocking)합니다. |

**class `TestUserInteractionComposite`** (line 41)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_present_options_and_get_choice_success` | `self, mock_questionary` | 성공 케이스: 사용자가 옵션 중 하나를 선택 |
| `test_present_options_and_get_choice_empty_options` | `self` | 실패 케이스: 옵션 리스트가 비어있을 때 ValueError 발생 |
| `test_present_options_and_get_choice_cancel` | `self, mock_questionary` | 엣지 케이스: 사용자가 선택을 취소(Ctrl+C)했을 때 None 반환 |
| `test_present_checkbox_and_get_choices_success` | `self, mock_questionary` | 성공 케이스: 사용자가 여러 옵션을 선택 |
| `test_present_checkbox_and_get_choices_empty_options` | `self, mock_questionary` | 엣지 케이스: 옵션이 비어있을 때 빈 리스트 반환 |
| `test_ask_for_file_path_success` | `self, mock_questionary, tmp_path` | 성공 케이스: 존재하는 파일 경로 입력 |
| `test_ask_for_file_path_must_exist_false` | `self, mock_questionary, tmp_path` | 엣지 케이스: 존재하지 않아도 되는 파일 경로 입력 |
| `test_ask_for_directory_path_success` | `self, mock_questionary, tmp_path` | 성공 케이스: 존재하는 디렉토리 경로 입력 |
| `test_confirm_critical_action_yes` | `self, mock_questionary` | 성공 케이스: 사용자가 'Yes'를 선택 |
| `test_confirm_critical_action_no` | `self, mock_questionary` | 실패 케이스: 사용자가 'No'를 선택 |
| `test_get_form_input_success` | `self, mock_questionary` | 성공 케이스: 모든 폼 필드를 정상적으로 입력 |
| `test_get_form_input_cancel` | `self, mock_questionary` | 엣지 케이스: 사용자가 중간에 입력을 취소 |
| `test_ask_for_validated_input_success` | `self, mock_questionary` | 성공 케이스: 유효한 이메일 입력 |
| `test_select_file_from_directory_success` | `self, mock_questionary, tmp_path` | 성공 케이스: 디렉토리 내 파일 선택 |
| `test_select_file_from_directory_no_files` | `self, mock_questionary, tmp_path` | 엣지 케이스: 디렉토리에 파일이 없을 때 None 반환 |
| `test_select_file_from_directory_not_found` | `self` | 실패 케이스: 존재하지 않는 디렉토리 경로 |
| `test_show_diff_captures_output` | `self, capsys` | 성공 케이스: diff 출력이 정상적으로 생성되는지 확인 |
| `test_prompt_with_autocomplete_success` | `self, mock_questionary` | 성공 케이스: 자동 완성 목록에서 선택 |

의존성: `os`, `pathlib`, `pytest`, `unittest`

#### `user_interaction_atomic.py` (291줄, 11,084B)
> user_interaction_atomic.py  사용자 상호작용을 위한 원자적(Atomic) MCP(Mission Control Primitives) 모음. 이 모듈은 터미널 환경에서 사용자로부터 입력을 받거나 정보를 표시하는 다양한 유틸리티 함수를 제공합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `ask_user_for_input` | `question: str` | `str` | 사용자에게 단일 텍스트 라인 질문을 던지고, 문자열 입력을 받아 반환합니다. |
| `ask_for_multiline_input` | `prompt: str` | `str` | 사용자에게 여러 줄의 텍스트 입력을 요청하고 반환합니다. |
| `ask_user_for_confirmation` | `question: str` | `bool` | 사용자에게 예(Yes)/아니오(No) 질문을 하고, True/False 불리언 값을 반환합니다. |
| `ask_for_password` | `prompt: str` | `str` | 사용자에게 민감한 정보(비밀번호 등)를 입력받습니다. 입력 내용은 화면에 표시되지 않습니다. |
| `show_message` | `message: str` | `-` | 사용자에게 단순 정보성 메시지를 보여줍니다. |
| `display_table` | `data: List[Dict[str, Any]], headers: List[str]` | `-` | 구조화된 데이터를 표(Table) 형식으로 깔끔하게 출력합니다. |
| `show_progress_bar` | `total: int, description: str` | `-` | 전체 작업량에 대한 진행률 표시줄(Progress Bar)을 보여줍니다. |
| `clear_screen` | `` | `-` | 터미널이나 콘솔 화면을 깨끗하게 지웁니다. |
| `show_alert` | `message: str, level: str` | `-` | 심각도 수준에 따라 다른 스타일의 경고 메시지를 보여줍니다. |
| `render_markdown` | `markdown_text: str` | `-` | 마크다운 형식의 텍스트를 서식이 적용된 형태로 터미널에 출력합니다. |
| `show_spinner` | `message: str, duration_sec: float` | `-` | 작업이 진행 중임을 알리는 애니메이션 스피너를 일정 시간 동안 보여줍니다. |
| `update_last_line` | `message: str` | `-` | 콘솔의 마지막 라인에 출력된 메시지를 새로운 메시지로 덮어씁니다. |

의존성: `getpass`, `logging`, `os`, `rich`, `sys`, `time`, `typing`

#### `user_interaction_composite.py` (424줄, 17,540B)
> 사용자 상호작용(User Interaction)을 위한 복합 MCP(Mission Control Primitives) 모음.  이 모듈은 AI 에이전트가 터미널 환경에서 사용자와 효과적으로 상호작용할 수 있도록 돕는 고수준 함수들을 제공합니다. 선택지 제공, 경로 입력, 중요 작업 확인 등 다양한 시나리오를 처리합니다.

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `present_options_and_get_choice` | `prompt: str, options: List[str]` | `Optional[str]` | 사용자에게 번호가 매겨진 선택지 목록을 보여주고, 하나를 선택하게 합니다. |
| `present_checkbox_and_get_choices` | `prompt: str, options: List[str]` | `List[str]` | 여러 선택지를 체크박스 형태로 보여주고, 사용자가 다중 선택한 항목들의 리스트를 반환합니다. |
| `ask_for_file_path` | `prompt: str, default_path: str, must_exist: bool` | `Optional[str]` | 사용자에게 파일 경로를 입력하도록 요청하고, 경로의 유효성을 검증합니다. |
| `ask_for_directory_path` | `prompt: str, default_path: str, must_exist: bool` | `Optional[str]` | 사용자에게 디렉토리 경로를 입력하도록 요청하고, 경로의 유효성을 검증합니다. |
| `confirm_critical_action` | `action_description: str, details_to_show: Optio...` | `bool` | 중요한 작업을 실행하기 전, 상세 내용을 보여주고 사용자에게 재확인받습니다. |
| `get_form_input` | `form_fields: Dict[str, str]` | `Dict[str, Any]` | 정의된 여러 필드에 대해 순차적으로 질문하여, 폼(Form)처럼 사용자 입력을 받습니다. |
| `ask_for_validated_input` | `question: str, validation_rule: Dict[str, str]` | `Optional[str]` | 정규식을 기반으로 입력값의 유효성을 검증하며 사용자 입력을 받습니다. |
| `select_file_from_directory` | `prompt: str, directory_path: str` | `Optional[str]` | 특정 디렉토리의 파일 목록을 보여주고, 사용자가 그중 하나를 선택하게 합니다. |
| `show_diff` | `text1: str, text2: str, fromfile: str, tofile: str` | `-` | 두 텍스트를 비교하여 차이점(diff)을 터미널에 시각적으로 강조하여 보여줍니다. |
| `prompt_with_autocomplete` | `prompt: str, choices: List[str]` | `Optional[str]` | 사용자 입력을 시작하면, 제공된 선택지 목록을 기반으로 자동 완성 제안을 보여줍니다. |

**class `PathValidator`** (line 30)
> 파일 또는 디렉토리 경로의 유효성을 검증하는 Validator 클래스.

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `__init__` | `self, is_file: bool, must_exist: bool` | - |
| `validate` | `self, document` | - |

의존성: `difflib`, `logging`, `os`, `pathlib`, `questionary`, `re`, `typing`

#### `user_interaction_composite.spec.yaml` (206줄, 8,216B)

정의된 MCP: `user_interaction_primitives`, `present_options_and_get_choice`, `prompt`, `options`, `present_checkbox_and_get_choices`, `prompt`, `options`, `ask_for_file_path`, `prompt`, `default_path`, `must_exist`, `ask_for_directory_path`, `prompt`, `default_path`, `must_exist`...

#### `user_interaction_utils.atomic.yaml` (179줄, 5,796B)

정의된 MCP: `ask_user_for_input`, `question`, `ask_for_multiline_input`, `prompt`, `ask_user_for_confirmation`, `question`, `ask_for_password`, `prompt`, `show_message`, `message`, `display_table`, `data`, `headers`, `show_progress_bar`, `total`...

#### `web_network_atomic.spec.yaml` (292줄, 10,297B)

정의된 MCP: `fetch_url_content`, `url`, `timeout`, `ValueError`, `requests.exceptions.RequestException`, `download_file_from_url`, `url`, `save_path`, `timeout`, `ValueError`, `requests.exceptions.RequestException`, `IOError`, `api_get_request`, `url`, `headers`...

### orchestrator/

#### `__init__.py` (8줄, 274B)

의존성: `logging`

#### `api.py` (227줄, 9,127B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async lifespan` | `app: FastAPI` | `-` | - |
| `async decide_and_act` | `request: AgentRequest` | `-` | (수정) ReAct 루프의 핵심. |
| `async execute_group` | `request: AgentRequest` | `-` | (수정) 저장된 '단일' 그룹을 실행합니다. |

의존성: `contextlib`, `datetime`, `fastapi`, `gemini_client`, `inspect`, `models`, `os`, `re`

#### `config.py` (69줄, 1,772B)

의존성: `os`

#### `gemini_client.py` (252줄, 8,662B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async generate_execution_plan` | `user_query: str, requirements_content: str, his...` | `List[ExecutionGroup]` | ReAct 아키텍처에 맞게 '다음 1개'의 실행 그룹을 생성합니다. |
| `async generate_final_answer` | `history: list, model_preference: ModelPreference` | `str` | - |
| `async generate_title_for_conversation` | `history: list, model_preference: ModelPreference` | `str` | - |

의존성: `dotenv`, `google`, `json`, `logging`, `models`, `os`, `tool_registry`, `typing`

#### `history_manager.py` (127줄, 4,602B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `new_conversation` | `` | `Tuple[str, List[str]]` | 새 대화 ID(UUID)와 초기 히스토리 리스트를 생성합니다. |
| `save_conversation` | `convo_id: str, history: List[str], title: str, ...` | `-` | 대화 내용, 실행 계획, 진행 상태를 JSON 파일로 저장합니다. |
| `load_conversation` | `convo_id: str` | `Optional[Dict[str, Any]]` | 파일에서 대화 상태(히스토리, 계획, 진행도 포함)를 불러옵니다. |
| `list_conversations` | `` | `List[Dict[str, Any]]` | 저장된 모든 대화의 메타데이터 목록을 반환합니다. |

의존성: `datetime`, `json`, `os`, `re`, `typing`, `uuid`

#### `models.py` (42줄, 1,633B)

**class `AgentRequest`** (line 8)
> CLI가 서버로 보내는 요청 모델

**class `GeminiToolCall`** (line 17)
> 단일 도구 호출(MCP)을 정의하는 모델

**class `ExecutionGroup`** (line 27)
> 여러 태스크를 묶는 실행 그룹 모델

**class `AgentResponse`** (line 33)
> 서버가 CLI로 보내는 응답 모델

의존성: `pydantic`, `typing`

#### `test_api.py` (162줄, 6,651B)
> orchestrator/api.py에 대한 단위 테스트

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `sample_group` | `` | `-` | - |

**class `TestDecideAndAct`** (line 22)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_new_request_returns_plan_confirmation` | `self, sample_group` | 신규 사용자 입력 시 PLAN_CONFIRMATION 반환 |
| `test_empty_plan_returns_final_answer` | `self` | 플래너가 빈 계획 반환 시 FINAL_ANSWER |

**class `TestExecuteGroup`** (line 70)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_conversation_returns_404` | `self` | 존재하지 않는 대화 ID는 404 |
| `test_successful_execution_returns_step_executed` | `self, sample_group` | 정상 실행 시 STEP_EXECUTED 반환 |
| `test_missing_tool_returns_error` | `self, sample_group` | 도구를 찾을 수 없을 때 ERROR 반환 |
| `test_empty_plan_returns_400` | `self` | 실행할 계획이 없으면 400 |

의존성: `api`, `httpx`, `models`, `pytest`, `unittest`

#### `test_gemini_client.py` (95줄, 3,685B)
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
| `test_auto_with_high_default` | `self` | auto + default_type='high'이면 HIGH_PERF_MODEL_NAME |
| `test_auto_with_standard_default` | `self` | auto + default_type='standard'이면 STANDARD_MODEL_NAME |

**class `TestGenerateExecutionPlan`** (line 64)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_raises_runtime_error` | `self` | client=None일 때 RuntimeError 발생 |

**class `TestGenerateFinalAnswer`** (line 73)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_raises_runtime_error` | `self` | client=None일 때 RuntimeError 발생 |

**class `TestGenerateTitleForConversation`** (line 82)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_no_client_returns_default` | `self` | client=None일 때 기본 제목 반환 |
| `test_short_history_returns_new_conversation` | `self` | history가 2개 미만이면 '새로운_대화' 반환 |

의존성: `json`, `models`, `pytest`, `unittest`

#### `test_tool_registry.py` (78줄, 2,468B)
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

**class `TestGetAllToolDescriptions`** (line 74)

| 메서드 | 인자 | 설명 |
|--------|------|------|
| `test_returns_dict` | `self` | 반환 타입이 dict |

의존성: `importlib`, `pytest`, `unittest`

#### `tool_registry.py` (165줄, 5,475B)

| 함수명 | 인자 | 반환 | 설명 |
|--------|------|------|------|
| `async initialize` | `` | `-` | 모든 로컬 모듈과 MCP 서버를 초기화합니다. |
| `async shutdown` | `` | `-` | MCP 서버 연결을 정리합니다. |
| `get_tool` | `name: str` | `Optional[Callable]` | 이름으로 도구 함수를 가져옵니다. |
| `get_all_tool_descriptions` | `` | `Dict[str, str]` | 모든 도구(로컬 + MCP)의 이름과 설명을 반환합니다. |

의존성: `contextlib`, `importlib`, `inspect`, `logging`, `mcp`, `os`, `typing`

### system_prompts/

#### `default.txt` (1줄, 48B)

---

## 12. 모듈 간 의존성 맵 (자동 생성)

```
  main.py → orchestrator.history_manager.list_conversations, orchestrator.history_manager.load_conversation, orchestrator.history_manager.new_conversation
  test_code_execution_atomic.py → .code_execution_atomic
  test_user_interaction_composite.py → .user_interaction_composite
  api.py → .history_manager, .tool_registry
  test_gemini_client.py → .gemini_client
  test_tool_registry.py → .config, .tool_registry
  tool_registry.py → .config
```
