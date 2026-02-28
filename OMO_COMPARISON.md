# OMO vs 현재 프로젝트 비교 분석 및 도입 로드맵

> 작성일: 2026-02-28
> 참조: https://github.com/code-yeongyu/oh-my-opencode
> 현재 프로젝트: Multi-Provider Agent Orchestrator (test02/)

---

## 1. 기본 포지셔닝

| 항목 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **목적** | OpenCode용 플러그인 (에이전트 하네스) | 독립형 AI 에이전트 오케스트레이터 |
| **언어/런타임** | TypeScript + Bun | Python 3.12 |
| **배포 형태** | npm 패키지 (플러그인) | FastAPI 서버 + Typer CLI |
| **GitHub 스타** | 35,000+ (2개월 만) | 개인 프로젝트 |
| **생성일** | 2025-12-03 | 이전부터 개발 중 |
| **사용자 인터페이스** | TUI (OpenCode 내장) | CLI + REST API + Web UI |
| **의존성** | OpenCode 필수 | 완전 독립형 |

---

## 2. 아키텍처 비교

### OMO 아키텍처
```
사용자 입력
  → IntentGate (의도 분류)
  → Sisyphus (오케스트레이터, Claude/Kimi/GLM)
      ├─ Prometheus  — 전략 플래너 (인터뷰 모드, 사전 계획)
      ├─ Atlas       — 실행 지휘관 (Prometheus 계획 실행)
      ├─ Hephaestus  — 자율 실행 에이전트 (GPT-5.3-codex)
      ├─ Oracle      — 아키텍처 컨설턴트 (읽기 전용 고IQ)
      ├─ Librarian   — 문서/코드 검색 (GLM)
      ├─ Explore     — 코드베이스 빠른 탐색 (Grok)
      ├─ Metis       — 갭 분석 (플랜 검증 전)
      ├─ Momus       — 플랜 루틴 리뷰
      └─ Category 기반 동적 위임
          visual-engineering → Gemini
          ultrabrain         → GPT-5.3-codex
          quick              → Haiku
          deep               → 자율 실행
→ 병렬 백그라운드 에이전트 5개+ 동시 실행
→ Ralph Loop: 완료까지 자율 반복
```

### 현재 프로젝트 아키텍처
```
사용자 입력
  → decide_and_act (단일 LLM 플래너)
      └─ LLM이 1개 ExecutionGroup 즉석 생성
  → PLAN_CONFIRMATION (사용자 승인)
  → execute_group (도구 순차 실행)
  → STEP_EXECUTED → 반복
  → FINAL_ANSWER (빈 계획 반환 시)
```

**핵심 차이**: OMO는 전문 에이전트들의 병렬 팀, 현재 프로젝트는 단일 LLM + 도구 순차 실행.

---

## 3. 기능별 상세 비교

### 3.1 멀티 LLM 지원

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **지원 프로바이더** | Claude, GPT, Gemini, Kimi, GLM, Grok, Ollama | Gemini, Claude, Ollama, OpenAI, Grok |
| **동시 멀티모델** | 에이전트별 다른 모델 동시 실행 | 한 번에 1개 active_provider만 |
| **모델 라우팅** | 카테고리 → 자동 최적 모델 선택 | model_preference: auto/standard/high |
| **폴백 체인** | 자동 (프로바이더 다운 시) | 없음 |
| **모델 목록 조회** | 없음 (설정 파일 기반) | fetch_models() 실시간 API 조회 |

### 3.2 에이전트 구조

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **에이전트 수** | 10+ 전문 역할 분리 에이전트 | 1개 (단일 ReAct 에이전트) |
| **병렬 실행** | 5+ 백그라운드 에이전트 동시 | 없음 (순차 실행) |
| **계획 수립** | Prometheus (인터뷰 → 사전 계획) | LLM 즉석 1그룹씩 계획 |
| **의도 분류** | IntentGate (실행 전 의도 파악) | 없음 |
| **전략 검증** | Metis(갭 분석) + Momus(플랜 리뷰) | 없음 |
| **페르소나** | 에이전트별 고정 역할 | DB 기반 동적 페르소나 |
| **자율 완료** | Ralph Loop (완료까지 중단 없음) | 그룹마다 사용자 승인 필요 |

### 3.3 도구 & 통합

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **파일 편집** | Hashline (해시 기반 정밀 편집) | MCP filesystem |
| **코드 검색** | LSP + AST-Grep (25개 언어) | MCP grep |
| **터미널** | Tmux 통합 (REPL, 디버거, TUI) | code_execution_atomic |
| **웹 검색** | Exa + Grep.app + Context7 내장 | MCP fetch |
| **MCP 관리** | 스킬별 온디맨드 (컨텍스트 절약) | 상시 연결 서버 |
| **LSP** | rename, goto-def, diagnostics, find-ref | 없음 |
| **비전/멀티모달** | Multimodal Looker 에이전트 | 없음 |
| **Comment 품질** | Comment Checker (AI 슬롭 방지) | 없음 |
| **Todo 강제** | Todo Enforcer (에이전트 아이들 방지) | 없음 |

### 3.4 지속성 & 관리

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **대화 저장** | OpenCode 세션 기반 | SQLite (conversations.db) |
| **함수 버전관리** | 없음 | mcp_db_manager (버전/롤백/테스트) |
| **이슈 추적** | 없음 | issue_tracker (자동 에러 캡처) |
| **토큰 비용 추적** | 없음 | token_tracker (프로바이더별 USD 계산) |
| **요구사항 추적** | 없음 | claude_tools DB 기반 자동화 |
| **대화 그래프** | 없음 | 그룹/토픽/키워드 관계 그래프 |
| **스킬/매크로/워크플로우** | SKILL.md 파일 기반 | DB CRUD (동적 관리) |
| **웹 UI** | 없음 (TUI 전용) | /api/v1/* 16개 REST 엔드포인트 |

### 3.5 보안

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **입력 검증** | TypeScript 타입 시스템 | Pydantic 강제 검증 |
| **크기 제한** | 없음 (명시적) | tool_name 100자, arguments 10KB, tasks 50개 |
| **코드 실행 검증** | 없음 | ast.parse() 사전 검증 후 exec() |
| **MCP 화이트리스트** | 없음 | ALLOWED_MCP_COMMANDS |
| **SQL 인젝션 방지** | 없음 | 파라미터화 쿼리 강제 |

---

## 4. 강약점 요약

### OMO가 앞선 점
| 항목 | 근거 |
|------|------|
| 병렬 멀티에이전트 | 5+ 에이전트 동시 → 복잡한 작업을 팀처럼 처리 |
| Hashline 편집 | 해시 검증 → 스테일 라인 에러 0% (성공률 6.7% → 68.3%) |
| LSP 통합 | IDE 수준 리팩토링 (rename, goto-def, diagnostics) |
| IntentGate | 사용자 의도 사전 분류로 오해 방지 |
| Prometheus 플래너 | 코드 작성 전 인터뷰 → 범위/모호성 사전 제거 |
| 스킬 온디맨드 MCP | 필요할 때만 MCP 기동 → 컨텍스트 절약 |
| Ralph Loop | 완료까지 자율 반복 (사람 개입 최소화) |
| 커뮤니티 검증 | 35K 스타, 구글/MS 엔지니어 실사용 |

### 현재 프로젝트가 앞선 점
| 항목 | 근거 |
|------|------|
| 완전한 지속성 | 모든 상태 SQLite 저장 (대화/함수/설정/이슈) |
| 함수 버전관리 | MCP 함수 코드 버전/롤백/테스트/통계 |
| 비용 추적 | 프로바이더·모델별 USD 토큰 비용 실시간 집계 |
| 이슈 자동화 | 런타임 에러 → 요구사항 자동 승격 파이프라인 |
| 입력 보안 | Pydantic + ast.parse() 이중 검증 |
| 독립성 | OpenCode 없이도 단독 실행 가능 |
| 대화 그래프 | 그룹/토픽/키워드 관계망으로 지식 구조화 |
| 프로바이더 관리 | 5종 프로바이더 DB화, 실시간 모델 조회 |
| 자체 분석 도구 | claude_tools로 프로젝트 분석/추적 자동화 |

---

## 5. OMO 도입 기능 우선순위

### 우선순위 기준
- **P1 (즉시)**: 구현 난이도 낮음 + 현재 사용자 경험에 직접적 영향
- **P2 (단기)**: 아키텍처 변경 없이 추가 가능, 효과 크다
- **P3 (중기)**: 설계 변경 필요, 하지만 핵심 경쟁력
- **P4 (장기)**: 근본적 구조 변경 또는 외부 의존성 필요

---

### P1 — 즉시 도입 (1~2주)

#### P1-A: 자율 반복 루프 (Ralph Loop)
- **현황**: 매 ExecutionGroup마다 사용자 승인 필요
- **도입**: `--auto` 플래그 추가 → 사용자 승인 없이 완료까지 자동 반복
- **구현 위치**: `main.py`의 `run()` 함수
- **난이도**: 낮음 (while 루프 + 플래그 추가)
- **효과**: 단순 작업 자동화, 사용자 개입 최소화
- **보안 고려**: 위험 도구(삭제, 덮어쓰기) 실행 시 강제 중단 or 확인

#### P1-B: 카테고리 기반 모델 라우팅
- **현황**: model_preference가 auto/standard/high 단순 3단계
- **도입**: 태스크 유형 카테고리 → 최적 모델 자동 선택
  ```
  code_heavy  → ollama (비용 절약) or gemini-flash
  analysis    → claude-sonnet or gemini-pro
  quick_edit  → gemini-flash-lite or haiku
  creative    → gemini-pro
  ```
- **구현 위치**: `orchestrator/models.py` + `llm_client.py`
- **난이도**: 낮음 (Enum 추가 + 매핑 테이블)
- **효과**: 작업별 최적 모델 자동 사용 → 비용 절감 + 품질 향상

#### P1-C: 컨텍스트 파일 자동 주입 (`/init-deep` 유사)
- **현황**: system_prompts를 수동으로 지정해야 함
- **도입**: 작업 디렉토리의 `AGENTS.md`, `README.md` 자동 감지 → 시스템 프롬프트에 주입
- **구현 위치**: `orchestrator/api.py`의 `decide_and_act()`
- **난이도**: 낮음 (파일 탐색 + 내용 prepend)
- **효과**: 프로젝트 컨텍스트를 LLM이 자동으로 인지

---

### P2 — 단기 도입 (2~4주)

#### P2-A: Todo Enforcer (태스크 완료 강제)
- **현황**: LLM이 중간에 완료 선언해도 검증 없음
- **도입**: FINAL_ANSWER 반환 시 미완료 항목 체크 → 재실행 트리거
  - 히스토리에서 `TODO`, `미완료`, `추후` 등 키워드 스캔
  - 발견 시 `decide_and_act` 재진입
- **구현 위치**: `orchestrator/api.py`
- **난이도**: 중간
- **효과**: 에이전트가 작업을 중도에 포기하는 현상 방지

#### P2-B: 프로바이더 폴백 체인
- **현황**: active_provider 하나만 사용, 실패 시 에러
- **도입**: `model_config.json`에 fallback 순서 추가
  ```json
  "fallback_chain": ["gemini", "claude", "ollama"]
  ```
  → API 실패 시 다음 프로바이더로 자동 전환
- **구현 위치**: `orchestrator/llm_client.py`
- **난이도**: 중간
- **효과**: 안정성 대폭 향상, 특정 프로바이더 장애 시 무중단

#### P2-C: Prometheus 모드 (사전 계획 인터뷰)
- **현황**: 쿼리 입력 즉시 실행 계획 수립
- **도입**: `--plan` 플래그 → 실행 전 LLM이 요구사항 질문 → 범위 확정 후 실행
  - `generate_clarifying_questions()` 함수 추가
  - 답변 수집 후 `generate_execution_plan()` 호출
- **구현 위치**: `main.py` + `llm_client.py`
- **난이도**: 중간
- **효과**: 복잡한 작업에서 방향 오류 사전 차단

#### P2-D: 실행 중 히스토리 요약 (컨텍스트 압축)
- **현황**: HISTORY_MAX_CHARS=6000 단순 트런케이션
- **도입**: 오래된 히스토리를 LLM으로 요약 → 요약본 + 최신 N개 유지
  - `summarize_history()` 함수 추가
  - threshold 초과 시 자동 요약 트리거
- **구현 위치**: `orchestrator/gemini_client.py` + `claude_client.py`
- **난이도**: 중간
- **효과**: 긴 대화에서 핵심 컨텍스트 보존, 토큰 효율화

---

### P3 — 중기 도입 (1~2개월)

#### P3-A: 병렬 서브에이전트 실행
- **현황**: ExecutionGroup 내 태스크 순차 실행
- **도입**: 독립적 태스크를 asyncio.gather()로 병렬 실행
  - 의존 관계 분석 (태스크 A의 결과가 B에 필요한지)
  - 독립 태스크 → 병렬, 의존 태스크 → 순차
- **구현 위치**: `orchestrator/api.py`의 `execute_group()`
- **난이도**: 높음 (의존성 분석 + 동시성 제어)
- **효과**: 실행 속도 N배 향상 (독립 태스크 수에 비례)

#### P3-B: 전문 서브에이전트 (역할 분리)
- **현황**: 단일 LLM이 모든 역할 수행
- **도입**: 역할별 에이전트 추가
  - `PlannerAgent` — 계획 수립 전담 (현재 generate_execution_plan)
  - `ReviewerAgent` — 결과 검증 전담
  - `SummaryAgent` — 최종 답변 전담 (현재 generate_final_answer)
  - 각 에이전트에 최적 모델 별도 지정
- **구현 위치**: `orchestrator/` 신규 모듈
- **난이도**: 높음 (새 모듈 + DB 스키마 추가)
- **효과**: 역할별 최적 모델 사용 → 품질 향상 + 비용 최적화

#### P3-C: IntentGate (의도 사전 분류)
- **현황**: 사용자 입력을 그대로 LLM에 전달
- **도입**: 실행 전 의도 분류 레이어 추가
  ```
  코드 작성 / 파일 조작 / 정보 검색 / 분석 / 대화
  ```
  → 분류 결과에 따라 시스템 프롬프트 자동 선택
- **구현 위치**: `orchestrator/api.py`
- **난이도**: 중간~높음
- **효과**: 오해로 인한 잘못된 실행 방지

#### P3-D: 온디맨드 MCP (스킬별 MCP 기동/종료)
- **현황**: 서버 시작 시 모든 MCP 서버 상시 연결
- **도입**: 태스크에 필요한 MCP만 실행 시 기동 → 완료 후 종료
  - `tool_registry`에 lazy-connect 추가
  - 스킬/페르소나에 `required_mcps` 필드 추가
- **구현 위치**: `orchestrator/tool_registry.py`
- **난이도**: 높음 (연결 라이프사이클 관리)
- **효과**: 컨텍스트 절약, 불필요한 MCP 연결 제거

---

### P4 — 장기 도입 (2개월+)

#### P4-A: Hashline 편집 도구
- **현황**: MCP filesystem의 write_file (전체 덮어쓰기)
- **도입**: 해시 기반 라인 편집 도구 구현
  ```
  11#VK| function hello() {
  22#XJ|   return "world";
  ```
  → 라인별 해시 태그 → 변경 전 hash 검증 → 실패 시 거부
- **구현 위치**: `mcp_db_manager`에 신규 도구 등록
- **난이도**: 매우 높음 (해시 계산 + 검증 + 편집 엔진)
- **효과**: 파일 편집 정확도 획기적 향상

#### P4-B: LSP 통합
- **현황**: 텍스트 기반 grep만 지원
- **도입**: Python LSP (pylsp) 연동
  - `lsp_goto_definition`, `lsp_find_references`, `lsp_rename`, `lsp_diagnostics`
  - MCP 서버로 래핑하여 tool_registry에 등록
- **구현 위치**: 신규 MCP 모듈
- **난이도**: 매우 높음 (LSP 프로토콜 구현)
- **효과**: IDE 수준 코드 네비게이션/리팩토링

#### P4-C: 멀티모달 지원
- **현황**: 텍스트만 처리
- **도입**: 이미지/스크린샷 입력 처리
  - Gemini/Claude의 vision API 활용
  - `AgentRequest`에 `attachments` 필드 추가
- **구현 위치**: `orchestrator/models.py` + 각 클라이언트
- **난이도**: 중간 (API는 지원됨, UI 연동 필요)
- **효과**: UI 버그 캡처, 디자인 구현 등 비주얼 작업 가능

---

## 6. 도입 로드맵 요약

```
Week 1-2 (P1)
  ├─ P1-A: 자율 반복 루프 (--auto 플래그)
  ├─ P1-B: 카테고리 기반 모델 라우팅
  └─ P1-C: 컨텍스트 파일 자동 주입 (AGENTS.md)

Week 3-4 (P2)
  ├─ P2-A: Todo Enforcer
  ├─ P2-B: 프로바이더 폴백 체인
  ├─ P2-C: Prometheus 모드 (--plan 플래그)
  └─ P2-D: 히스토리 요약 압축

Month 2 (P3)
  ├─ P3-A: 병렬 서브에이전트 실행
  ├─ P3-B: 전문 역할 에이전트 분리
  ├─ P3-C: IntentGate
  └─ P3-D: 온디맨드 MCP

Month 3+ (P4)
  ├─ P4-A: Hashline 편집 도구
  ├─ P4-B: LSP 통합
  └─ P4-C: 멀티모달 지원
```

---

## 7. 도입 시 주의사항

1. **P1-A 자율 루프**: 위험 도구(파일 삭제, DB 수정 등) 실행 시 강제 확인 필요. `ALLOWED_AUTO_TOOLS` 화이트리스트 관리
2. **P3-A 병렬 실행**: SQLite write lock 충돌 주의 → WAL 모드 활성화 필요
3. **P3-D 온디맨드 MCP**: 연결/종료 비용이 크므로 TTL 캐싱 고려
4. **P4-A Hashline**: 기존 MCP filesystem과 충돌 없이 공존 설계 필요
5. **전반**: 모든 기능은 기존 보안 검증 (Pydantic, ast.parse) 통과 후 등록

---

*참조: https://github.com/code-yeongyu/oh-my-opencode*
