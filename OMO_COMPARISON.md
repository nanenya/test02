# OMO vs 현재 프로젝트 비교 분석 및 도입 로드맵

> 작성일: 2026-03-01 (Phase 1-4 구현 완료 이후 갱신)
> 참조: https://github.com/code-yeongyu/oh-my-opencode
> 현재 프로젝트: Multi-Provider Agent Orchestrator (test02/)

---

## 1. 기본 포지셔닝

| 항목 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **목적** | OpenCode용 플러그인 (에이전트 하네스) | 독립형 AI 에이전트 오케스트레이터 |
| **언어/런타임** | TypeScript 5.7 + Bun 1.3.6 | Python 3.12 |
| **배포 형태** | npm 패키지 (OpenCode 플러그인) | FastAPI 서버 + Typer CLI |
| **GitHub 스타** | 35,700+ (출시 3개월) | 개인 프로젝트 |
| **최초 생성** | 2025-12-03 | 이전부터 개발 중 |
| **사용자 인터페이스** | TUI (OpenCode 내장) | CLI + REST API + Web UI |
| **의존성** | OpenCode 필수 설치 | 완전 독립형 |
| **에이전트 모델** | 11개 전문 에이전트 팀 | 단일 ReAct + 4층 파이프라인 |

---

## 2. 아키텍처 비교

### OMO 아키텍처

```
사용자 입력
  → Sisyphus (마스터 오케스트레이터, Claude Opus / Kimi K2.5 / GLM-5)
      ├─ Prometheus  — 전략 플래너 (인터뷰 모드, 사전 계획)
      ├─ Hephaestus  — 자율 실행 에이전트 (GPT-5.3-codex)
      ├─ Oracle      — 아키텍처 컨설턴트 (읽기 전용 고IQ)
      ├─ Librarian   — 문서/코드 검색 (Kimi K2.5)
      ├─ Explore     — 코드베이스 빠른 탐색
      ├─ Atlas       — 의존성/컨텍스트 매핑
      ├─ Metis       — 갭 분석 및 의사결정
      ├─ Momus       — 플랜 품질 리뷰
      └─ Multimodal-Looker — 비전/멀티모달 (Gemini 3 Pro)
→ 카테고리 기반 모델 라우팅 (quick→Haiku, visual→Gemini, ultrabrain→GPT-5.3)
→ 프로바이더별 폴백 체인 (anthropic→github-copilot→opencode)
→ 병렬 백그라운드 에이전트 5개+ 동시 실행
→ Ralph Loop: 완료까지 자율 반복
→ Hashline 편집: 라인별 해시 태그로 스테일 에러 방지
→ LSP: 11개 도구 (rename/goto-def/diagnostics 등)
→ AST-Grep: 25+ 언어 구조적 검색/교체
→ 스킬별 온디맨드 MCP (Playwright, Exa, Context7, grep.app)
```

### 현재 프로젝트 아키텍처 (Phase 1-4 이후)

```
사용자 입력
  ├─ [기존] POST /agent/decide_and_act
  │     → llm_client.generate_execution_plan() (활성 프로바이더 라우팅)
  │     → PLAN_CONFIRMATION (사용자 승인)
  │     → POST /agent/execute_group → 도구 순차 실행
  │     → 반복 → FINAL_ANSWER
  │
  └─ [신규] POST /agent/pipeline (4층 파이프라인)
        → [Layer 1] 설계 (llm_router: high tier)
              → generate_design() → DESIGN_CONFIRMATION (사용자 확인)
        → [Layer 2] 태스크 분해 (standard tier)
              → decompose_tasks() → pipeline_db.create_tasks()
        → [Layer 3] 계획 매핑 (캐시 우선)
              → task_plan_cache 히트 → LLM 호출 없음
              → 캐시 미스 → map_plans()
        → [Layer 4] 실행 그룹 빌드
              → template_engine.find_and_adapt() (기존 성공 패턴 재사용)
              → 미발견 → build_execution_group_for_step()
              → 누락 도구 → tool_discoverer.discover_and_resolve()
                  (로컬→npm MCP→Python 자동구현+보안검증)
        → PLAN_CONFIRMATION
  → POST /agent/pipeline/execute
        → 도구 실행
        → 성공: save_execution_template() (학습)
        → 실패: increment_template_fail() (자동 비활성화)
```

**핵심 차이**: OMO는 11개 전문 에이전트 병렬 팀. 현재 프로젝트는 단일 ReAct + DB 학습 기반 4층 파이프라인.

---

## 3. 기능별 상세 비교 (Phase 1-4 반영)

### 3.1 멀티 LLM 지원

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **지원 프로바이더** | Claude, GPT, Gemini, Kimi, GLM, Grok, Ollama | Gemini, Claude, Ollama, OpenAI, Grok |
| **동시 멀티모델** | 에이전트별 다른 모델 동시 실행 | 한 번에 1개 active_provider만 |
| **모델 라우팅** | 카테고리 기반 자동 최적 모델 선택 | **llm_router: 파이프라인 단계별 high/standard 자동 결정** ✅ |
| **폴백 체인** | 자동 (프로바이더 다운 시) | 미구현 |
| **예산 기반 강등** | 없음 | **llm_router: 누적 비용 ≥$0.10 → high 금지** ✅ |
| **모델 목록 조회** | 없음 (설정 파일 기반) | fetch_models() 실시간 API 조회 ✅ |
| **비용 추적** | 없음 | **token_tracker: 모델별 USD 실시간 집계** ✅ |

### 3.2 에이전트 / 파이프라인 구조

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **에이전트 수** | 11개 전문 역할 분리 에이전트 | 1개 ReAct + 4층 파이프라인 |
| **병렬 실행** | 5+ 백그라운드 에이전트 동시 | 없음 (순차 실행) |
| **설계/계획 수립** | Prometheus (인터뷰 → 사전 계획) | **pipeline_manager.start_design_phase() + DESIGN_CONFIRMATION** ✅ |
| **태스크 분해** | Sisyphus 위임 | **decompose_tasks() → pipeline_db.create_tasks()** ✅ |
| **계획 캐싱** | 플랜 캐싱 (언급) | **task_plan_cache SHA-256 시그니처 기반** ✅ |
| **실행 템플릿 재사용** | 없음 | **template_engine: 스코어링+인자적응** ✅ |
| **자동 실패 비활성화** | 없음 | **increment_template_fail() → 60% 실패율 시 자동 비활성화** ✅ |
| **의도 분류** | IntentGate (실행 전 의도 파악) | 파이프라인 API에 IntentGate 체크 (단순 채팅 단락) 부분 구현 |
| **전략 검증** | Metis(갭 분석) + Momus(플랜 리뷰) | 없음 |
| **페르소나** | 에이전트별 고정 역할 | DB 기반 동적 페르소나 (agent_config_manager) ✅ |
| **자율 완료** | Ralph Loop (완료까지 중단 없음) | 그룹마다 사용자 승인 필요 |

### 3.3 도구 & 통합

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **파일 편집** | **Hashline (해시 기반 정밀 편집)** | MCP filesystem + **hashline_editor.py (구현 중)** 🔶 |
| **코드 검색** | **LSP + AST-Grep (25개 언어)** | MCP grep |
| **누락 도구 발견** | 없음 | **tool_discoverer: 로컬→npm MCP→Python 자동구현** ✅ |
| **도구 코드 보안 검증** | 없음 | **_DANGEROUS_PATTERNS + ast.parse() 이중 검증** ✅ |
| **터미널** | Tmux 통합 (REPL, 디버거) | code_execution_atomic |
| **웹 검색** | Exa + Grep.app + Context7 내장 | MCP fetch |
| **MCP 관리** | 스킬별 온디맨드 (컨텍스트 절약) | 상시 연결 서버 |
| **LSP** | 11개 도구 (rename/goto-def/diagnostics/find-ref) | 없음 |
| **AST-Grep** | 25+ 언어 구조적 검색/교체 | 없음 |
| **비전/멀티모달** | Multimodal Looker 에이전트 | 없음 |
| **Comment 품질** | Comment Checker (AI 슬롭 방지) | 없음 |

### 3.4 지속성 & 학습

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **대화 저장** | OpenCode 세션 기반 | SQLite (conversations.db) ✅ |
| **실행 템플릿 DB** | 없음 | **execution_templates: 성공 패턴 저장·재사용** ✅ |
| **계획 캐시 DB** | 없음 | **task_plan_cache: 동일 태스크 LLM 호출 0회** ✅ |
| **도구 갭 로그** | 없음 | **tool_gap_log: 누락 도구 발견 이력** ✅ |
| **파이프라인 커서** | 없음 | **pipeline_cursors: 대화별 진행 상태 추적** ✅ |
| **함수 버전관리** | 없음 | mcp_db_manager (버전/롤백/테스트) ✅ |
| **이슈 추적** | 없음 | issue_tracker (자동 에러 캡처) ✅ |
| **요구사항 추적** | 없음 | claude_tools DB 기반 자동화 ✅ |
| **대화 그래프** | 없음 | 그룹/토픽/키워드 관계 그래프 ✅ |
| **스킬/매크로/워크플로우** | SKILL.md 파일 기반 | DB CRUD (동적 관리) ✅ |
| **웹 UI** | 없음 (TUI 전용) | /api/v1/* 16개 REST 엔드포인트 ✅ |

### 3.5 보안

| 기능 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **입력 검증** | TypeScript 타입 시스템 | Pydantic 강제 검증 ✅ |
| **크기 제한** | 없음 (명시적) | tool_name 100자, arguments 10KB, tasks 50개 ✅ |
| **DB 코드 실행 검증** | 없음 | ast.parse() 사전 검증 후 exec() ✅ |
| **명령 화이트리스트** | 없음 | **_ALLOWED_COMMANDS {npm,npx,pip,pip3,uvx}** ✅ |
| **셸 인젝션 차단** | 없음 | **_SHELL_INJECT_CHARS + shell=False 강제** ✅ |
| **자동생성 코드 격리** | 없음 | **비활성 상태 저장 → 사용자 수동 활성화** ✅ |
| **SQL 인젝션 방지** | 없음 | 파라미터화 쿼리 강제 ✅ |

---

## 4. 강약점 요약 (Phase 1-4 이후)

### OMO가 앞선 점

| 항목 | 근거 |
|------|------|
| **병렬 멀티에이전트** | 11개 전문 에이전트 동시 실행 → 복잡한 작업을 팀처럼 처리 |
| **Hashline 편집** | 해시 검증 → 스테일 라인 에러 방지 (성공률 6.7% → 68.3%) |
| **LSP + AST-Grep** | IDE 수준 리팩토링 25개 언어 (rename/goto-def/diagnostics) |
| **Ralph Loop** | 완료까지 자율 반복 (사람 개입 최소화) |
| **스킬 온디맨드 MCP** | 필요할 때만 MCP 기동 → 컨텍스트 절약 |
| **프로바이더 폴백 체인** | 자동 프로바이더 전환 → 무중단 |
| **커뮤니티 검증** | 35K 스타, 구글/MS 엔지니어 실사용, $24K+ 토큰 실험 |
| **비전/멀티모달** | 스크린샷 → 코드 구현 (Gemini 3 Pro 활용) |

### 현재 프로젝트가 앞선 점

| 항목 | 근거 |
|------|------|
| **DB 학습 파이프라인** | 성공한 실행 그룹을 템플릿으로 저장 → 재사용 → 점점 빨라지는 구조 |
| **계획 캐싱** | 동일 태스크 서명 → LLM 호출 0회 (무한 토큰 절약) |
| **누락 도구 자동 해결** | tool_discoverer: 로컬→npm MCP→Python 자동구현 3단계 파이프라인 |
| **단계별 LLM 예산 제어** | llm_router + token_tracker → 비용 초과 시 자동 모델 강등 |
| **완전한 지속성** | 모든 상태 SQLite 저장 (설계/태스크/계획/템플릿/캐시/커서/이슈) |
| **함수 버전관리** | MCP 함수 코드 버전/롤백/테스트/통계 |
| **자동 도구 보안 검증** | _DANGEROUS_PATTERNS + ast.parse() + shell=False 이중 검증 |
| **독립성** | OpenCode 없이도 단독 실행 가능 |
| **이슈→요구사항 자동화** | 런타임 에러 → 이슈 → 요구사항 자동 승격 파이프라인 |
| **프로바이더 동적 관리** | 5종 프로바이더 DB화, 실시간 모델 조회, 런타임 전환 |

---

## 5. OMO 도입 기능 우선순위 (갱신)

### 완료된 항목 (Phase 1-4에서 구현)

| 구 우선순위 | 기능 | 구현 모듈 | 비고 |
|------------|------|----------|------|
| P1-B | 카테고리 기반 모델 라우팅 | `llm_router.py` | 단계별 high/standard + 예산 강등 ✅ |
| P2-C | Prometheus 모드 (사전 계획) | `pipeline_manager.start_design_phase()` | DESIGN_CONFIRMATION 흐름 ✅ |
| P2-D | 히스토리 요약 압축 | `history_summarization` 스테이지 정의 | llm_router에 스테이지 등록 ✅ (클라이언트 구현 별도) |
| P4-A | Hashline 편집 도구 | `mcp_modules/hashline_editor.py` | 기초 구현 완료, 고도화 필요 🔶 |

---

### 잔여 우선순위

#### P1 — 즉시 도입 (1~2주)

##### P1-A: 자율 반복 루프 (Ralph Loop)
- **현황**: 매 ExecutionGroup마다 사용자 승인 필요
- **도입**: `--auto` 플래그 → 사용자 승인 없이 완료까지 자동 반복
- **구현 위치**: `main.py`의 `run()` 함수
- **보안 고려**: `ALLOWED_AUTO_TOOLS` 화이트리스트 — 삭제/덮어쓰기 도구는 강제 확인
- **난이도**: 낮음

##### P1-C: 컨텍스트 파일 자동 주입 (`AGENTS.md` / `README.md`)
- **현황**: system_prompts를 수동으로 지정해야 함
- **도입**: 작업 디렉토리의 `AGENTS.md`, `README.md` 자동 감지 → 시스템 프롬프트 prepend
- **구현 위치**: `orchestrator/api.py`의 `decide_and_act()`
- **난이도**: 낮음

---

#### P2 — 단기 도입 (2~4주)

##### P2-A: Todo Enforcer (태스크 완료 강제)
- **현황**: LLM이 중간에 완료 선언해도 검증 없음
- **도입**: FINAL_ANSWER 반환 시 히스토리에서 `TODO`, `미완료`, `추후` 키워드 스캔 → 발견 시 `decide_and_act` 재진입
- **구현 위치**: `orchestrator/api.py`
- **난이도**: 중간

##### P2-B: 프로바이더 폴백 체인
- **현황**: active_provider 하나만 사용, 실패 시 에러
- **도입**: `model_config.json`에 `fallback_chain: ["gemini", "claude", "ollama"]` → 실패 시 자동 전환
- **구현 위치**: `orchestrator/llm_client.py`
- **난이도**: 중간

##### P2-E: 히스토리 LLM 요약 (클라이언트 구현)
- **현황**: `history_summarization` 스테이지만 정의됨, 실제 요약 호출 없음
- **도입**: `threshold` 초과 시 오래된 항목을 LLM으로 요약 → 요약본 + 최신 N개 유지
- **구현 위치**: 각 LLM 클라이언트 (gemini/claude/ollama)
- **난이도**: 중간

---

#### P3 — 중기 도입 (1~2개월)

##### P3-A: 병렬 서브에이전트 실행
- **현황**: ExecutionGroup 내 태스크 순차 실행
- **도입**: 의존 관계 없는 태스크 → `asyncio.gather()` 병렬 실행
- **주의**: SQLite WAL 모드 활성화 필요 (write lock 충돌)
- **구현 위치**: `orchestrator/api.py`의 `execute_group()`
- **난이도**: 높음

##### P3-B: 전문 서브에이전트 역할 분리
- **현황**: 단일 LLM이 모든 역할 수행
- **도입**: `PlannerAgent`, `ReviewerAgent`, `SummaryAgent` 분리 → 각각 최적 모델 지정
- **구현 위치**: `orchestrator/` 신규 모듈 + pipeline_db 스키마 추가
- **난이도**: 높음

##### P3-C: 완전한 IntentGate
- **현황**: 파이프라인 API에서 단순 채팅만 단락, 세분화 없음
- **도입**: `코드 작성 / 파일 조작 / 정보 검색 / 분석 / 대화` 5분류 → 분류별 시스템 프롬프트 자동 선택
- **구현 위치**: `orchestrator/api.py`
- **난이도**: 중간~높음

##### P3-D: 온디맨드 MCP (스킬별 MCP 기동/종료)
- **현황**: 서버 시작 시 모든 MCP 서버 상시 연결
- **도입**: 태스크에 필요한 MCP만 기동 → 완료 후 종료 (TTL 캐싱으로 기동 비용 절감)
- **구현 위치**: `orchestrator/tool_registry.py` — lazy-connect 추가
- **난이도**: 높음

---

#### P4 — 장기 도입 (2개월+)

##### P4-A: Hashline 편집 도구 고도화
- **현황**: `mcp_modules/hashline_editor.py` 기초 구현 완료 🔶
- **도입**: 라인별 해시 태그 검증 완전 구현 → write 시 hash 불일치 거부
  ```
  11#VK| function hello() {
  22#XJ|   return "world";
  ```
- **구현 위치**: `mcp_modules/hashline_editor.py` 고도화 + tool_registry 등록
- **난이도**: 높음 (이미 기초 있어 P4→P3 격상 고려)

##### P4-B: LSP 통합
- **현황**: 텍스트 기반 grep만 지원
- **도입**: Python LSP (pylsp) 연동 → `lsp_rename`, `lsp_find_references`, `lsp_diagnostics`를 MCP 서버로 래핑
- **구현 위치**: 신규 MCP 모듈
- **난이도**: 매우 높음

##### P4-C: 멀티모달 지원
- **현황**: 텍스트만 처리
- **도입**: Gemini/Claude vision API 활용 → `AgentRequest`에 `attachments` 필드 추가
- **구현 위치**: `orchestrator/models.py` + 각 LLM 클라이언트
- **난이도**: 중간 (API는 지원됨, UI 연동 필요)

---

## 6. 도입 로드맵 (갱신)

```
✅ 완료 (Phase 1-4)
  ├─ 카테고리 기반 LLM 라우팅 (llm_router.py)
  ├─ 사전 계획 수립 (pipeline_manager + DESIGN_CONFIRMATION)
  ├─ 계획 캐싱 (task_plan_cache)
  ├─ 실행 템플릿 재사용 (template_engine)
  ├─ 누락 도구 자동 해결 (tool_discoverer)
  └─ Hashline 기초 구현 (mcp_modules/hashline_editor.py)

🔜 P1 (1~2주)
  ├─ P1-A: 자율 반복 루프 (--auto 플래그)
  └─ P1-C: 컨텍스트 파일 자동 주입 (AGENTS.md)

🔜 P2 (2~4주)
  ├─ P2-A: Todo Enforcer
  ├─ P2-B: 프로바이더 폴백 체인
  └─ P2-E: 히스토리 LLM 요약 (클라이언트 구현)

🔜 P3 (1~2개월)
  ├─ P3-A: 병렬 서브에이전트 실행
  ├─ P3-B: 전문 역할 에이전트 분리
  ├─ P3-C: 완전한 IntentGate
  └─ P3-D: 온디맨드 MCP

🔜 P4 (2개월+)
  ├─ P4-A: Hashline 완전 구현 (P3 격상 고려)
  ├─ P4-B: LSP 통합 (pylsp)
  └─ P4-C: 멀티모달 지원
```

---

## 7. 아키텍처 방향성 비교

| 관점 | OMO | 현재 프로젝트 |
|------|-----|---------------|
| **확장 전략** | 에이전트 수 늘려 병렬성 확보 | DB 학습으로 점진적 자동화 |
| **토큰 절감** | 스킬별 온디맨드 MCP + 카테고리 라우팅 | 계획 캐시 + 예산 기반 모델 강등 + 템플릿 재사용 |
| **신뢰성** | 여러 에이전트 교차 검증 | 템플릿 성공률 통계 + 자동 비활성화 |
| **보안** | TypeScript 타입 + 권한 설정 | Pydantic + 다층 정적 검증 + 화이트리스트 |
| **학습 구조** | 없음 (매번 새로 계획) | execution_templates + task_plan_cache 누적 학습 |
| **독립성** | OpenCode 종속 | 완전 독립 (어떤 환경에서도 구동) |

**결론**: OMO는 "지금 당장 최고 성능의 팀을 투입"하는 접근. 현재 프로젝트는 "경험이 쌓일수록 점점 빨라지고 저렴해지는" 학습형 파이프라인 접근. 두 전략은 상호보완적이며 장기적으로 병합 가능.

---

## 8. 도입 시 주의사항

1. **P1-A 자율 루프**: 삭제/덮어쓰기 도구는 `ALLOWED_AUTO_TOOLS` 화이트리스트 외 강제 확인
2. **P3-A 병렬 실행**: SQLite write lock 충돌 → WAL 모드 (`PRAGMA journal_mode=WAL`) 활성화 필수
3. **P3-D 온디맨드 MCP**: 기동/종료 비용이 크므로 TTL 캐싱(최소 5분) 설계 필요
4. **P4-A Hashline**: 기존 MCP filesystem과 공존 설계 (동일 파일 동시 편집 lock 처리)
5. **전반**: 모든 자동 생성 코드는 비활성 상태로 저장 → 사용자 수동 활성화 원칙 유지

---

*참조: https://github.com/code-yeongyu/oh-my-opencode*
*갱신: 2026-03-01 (Phase 1-4 구현 완료 이후)*
