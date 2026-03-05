#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py
import asyncio
import json
import re as _re
import typer
import httpx
import uvicorn
import subprocess
import time
import socket
import os
from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from rich.console import Console
from rich.table import Table
from typing_extensions import Annotated
from typing import List, Optional
from orchestrator.history_manager import (
    list_conversations,
    load_conversation,
    new_conversation,
    split_conversation,
)
from orchestrator import mcp_manager

app = typer.Typer(no_args_is_help=False)
mcp_app = typer.Typer(help="MCP 서버 관리 명령어")
func_app = typer.Typer(help="MCP 함수 DB 관리 명령어")
mcp_app.add_typer(func_app, name="function")
app.add_typer(mcp_app, name="mcp")
model_app = typer.Typer(help="AI 모델 관리 명령어")
app.add_typer(model_app, name="model")
group_app = typer.Typer(help="그룹 관리 명령어")
app.add_typer(group_app, name="group")
topic_app = typer.Typer(help="토픽 관리 명령어")
app.add_typer(topic_app, name="topic")
keyword_app = typer.Typer(help="키워드 관리 명령어")
app.add_typer(keyword_app, name="keyword")
prompt_app = typer.Typer(help="시스템 프롬프트 관리 명령어")
app.add_typer(prompt_app, name="prompt")
skill_app = typer.Typer(help="스킬 관리 명령어")
app.add_typer(skill_app, name="skill")
macro_app = typer.Typer(help="스킬 매크로 관리 명령어")
app.add_typer(macro_app, name="macro")
workflow_app = typer.Typer(help="워크플로우 관리 명령어")
app.add_typer(workflow_app, name="workflow")
persona_app = typer.Typer(help="페르소나 관리 명령어")
app.add_typer(persona_app, name="persona")
issue_app = typer.Typer(help="이슈 관리 명령어")
app.add_typer(issue_app, name="issue")
test_app = typer.Typer(help="테스트 파일 DB 관리 명령어")
app.add_typer(test_app, name="test")
template_app = typer.Typer(help="실행 템플릿 관리 명령어")
app.add_typer(template_app, name="template")
gap_app = typer.Typer(help="도구 부재 이력 조회")
app.add_typer(gap_app, name="gap")
provider_app = typer.Typer(help="LLM 프로바이더 상태 관리")
app.add_typer(provider_app, name="provider")

console = Console()


def _print_help() -> None:
    """상세 도움말 출력 — 실행 방법이 틀렸을 때 또는 인수 없이 실행했을 때 호출됩니다."""
    from rich.rule import Rule

    def rule(title: str) -> None:
        console.print(Rule(f"[bold yellow]{title}[/bold yellow]", style="dim", align="left"))

    console.print()
    console.print(Rule("[bold cyan]Multi-Provider AI Agent Orchestrator CLI[/bold cyan]", style="cyan"))
    console.print(
        "[dim]ReAct 기반 AI 에이전트 | FastAPI + Typer + MCP SDK[/dim]",
        justify="center",
    )
    console.print()
    console.print(
        "  [bold]사용법:[/bold]  [green]python main.py[/green] [bold cyan]<명령>[/bold cyan] [옵션...]"
        "    │    "
        "[green]python main.py[/green] [bold cyan]<명령>[/bold cyan] [bold]--help[/bold]  "
        "[dim](명령별 상세 도움말)[/dim]"
    )
    console.print()

    rule("핵심 명령")
    console.print("  [bold cyan]server[/bold cyan]   FastAPI 오케스트레이터 서버 실행  [dim]--host  --port  --reload[/dim]")
    console.print("  [bold cyan]run[/bold cyan]      AI 에이전트 실행  [dim]-q <쿼리>  또는  -c <대화ID> 계속  -a(자동) --max-steps N[/dim]")
    console.print("  [bold cyan]list[/bold cyan]     저장된 대화 목록 조회  [dim]-g 그룹  -k 키워드  -t 토픽  -s 상태[/dim]")
    console.print("  [bold cyan]graph[/bold cyan]    대화 관계 그래프 출력  [dim]-c 중심ID  -d 깊이[/dim]")
    console.print("  [bold cyan]migrate[/bold cyan]  JSON 히스토리 → SQLite 마이그레이션  [dim]--dry-run[/dim]")
    console.print()

    rule("AI 모델 관리  (model)")
    console.print("  [bold cyan]model status[/bold cyan]                    현재 활성 프로바이더 / 모델 확인")
    console.print("  [bold cyan]model list[/bold cyan] [dim]<provider>[/dim]          프로바이더별 사용 가능 모델 목록")
    console.print("  [bold cyan]model set[/bold cyan]  [dim]<provider> <model>[/dim]  활성 모델 변경")
    console.print()

    rule("MCP 서버 관리  (mcp)")
    console.print("  [bold cyan]mcp[/bold cyan]  [dim]list · add · remove · search · enable · disable · stats[/dim]")
    console.print("  [bold cyan]mcp function[/bold cyan]  [dim]add · list · show · versions · test · import · update · activate · template · edit-test[/dim]")
    console.print()

    rule("대화 관리  (group / topic / keyword)")
    console.print("  [bold cyan]group[/bold cyan]    [dim]list · create · delete · add-convo · remove-convo[/dim]")
    console.print("  [bold cyan]topic[/bold cyan]    [dim]list · create · delete · link · add-convo[/dim]")
    console.print("  [bold cyan]keyword[/bold cyan]  [dim]list · edit · search[/dim]")
    console.print()

    rule("시스템 프롬프트  (prompt)")
    console.print("  [bold cyan]prompt[/bold cyan]  [dim]list · show · create · edit · delete · import[/dim]")
    console.print()

    rule("에이전트 설정  (skill / macro / workflow / persona)")
    console.print("  [bold cyan]skill[/bold cyan]     [dim]list · sync · enable · disable · show[/dim]")
    console.print("  [bold cyan]macro[/bold cyan]     [dim]list · show · create · edit · delete · render[/dim]")
    console.print("  [bold cyan]workflow[/bold cyan]  [dim]list · show · create · add-step · delete[/dim]")
    console.print("  [bold cyan]persona[/bold cyan]   [dim]list · show · create · edit · delete · set-default · detect[/dim]")
    console.print()

    rule("이슈 & 테스트  (issue / test)")
    console.print("  [bold cyan]issue[/bold cyan]  [dim]list · show · resolve · ignore[/dim]")
    console.print("  [bold cyan]test[/bold cyan]   [dim]import · import-all · list · show · run · run-all[/dim]")
    console.print()

    rule("4층 파이프라인 관리  (template / gap)")
    console.print("  [bold cyan]template[/bold cyan]  [dim]list · show · stats · disable · enable · delete[/dim]")
    console.print("  [bold cyan]gap[/bold cyan]       [dim]report · discover[/dim]  [dim]← 누락 도구 발견/자동구현[/dim]")
    console.print()

    rule("사용 예시")
    console.print("  [green]python main.py server[/green]                    [dim]# 서버 시작[/dim]")
    console.print('  [green]python main.py run -q "파일 목록 알려줘"[/green]      [dim]# 새 쿼리 실행[/dim]')
    console.print('  [green]python main.py run -q "빌드 수정해줘" --auto[/green]  [dim]# 자동 실행 (승인 생략)[/dim]')
    console.print('  [green]python main.py run -q "..." -a --max-steps 20[/green] [dim]# 최대 20단계 자동[/dim]')
    console.print("  [green]python main.py run -c <대화ID>[/green]               [dim]# 기존 대화 계속[/dim]")
    console.print("  [green]python main.py model status[/green]              [dim]# 현재 모델 확인[/dim]")
    console.print("  [green]python main.py issue list[/green]                [dim]# 이슈 목록 조회[/dim]")
    console.print("  [green]python main.py run --help[/green]                [dim]# run 명령 상세 도움말[/dim]")
    console.print()


@app.callback(invoke_without_command=True)
def _main_callback(ctx: typer.Context) -> None:
    """Multi-Provider AI Agent Orchestrator CLI"""
    if ctx.invoked_subcommand is None:
        _print_help()
        raise typer.Exit()


def _fmt_usage(usage: dict) -> str:
    """토큰 사용량 dict를 한 줄 문자열로 포맷합니다."""
    if not usage:
        return ""
    in_t = usage.get("input_tokens", 0)
    out_t = usage.get("output_tokens", 0)
    cost = usage.get("cost_usd", 0.0)
    provider = usage.get("provider", "")
    parts = [f"입력 {in_t:,} · 출력 {out_t:,} tok"]
    if cost > 0:
        cost_str = f"${cost:.6f}" if cost < 0.0001 else (f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}")
        parts.append(f"비용 {cost_str}")
    elif provider == "ollama":
        parts.append("무료 (로컬)")
    rl_limit = usage.get("rate_limit_limit")
    rl_rem = usage.get("rate_limit_remaining")
    if rl_limit and rl_rem is not None:
        pct = rl_rem / rl_limit * 100
        parts.append(f"잔여 {rl_rem:,}/{rl_limit:,} tok ({pct:.0f}%)")
    return "  │  ".join(parts)


ORCHESTRATOR_URL = "http://127.0.0.1:8000"
PROMPTS_DIR = "system_prompts"

# --auto 모드에서 사용자 확인이 필요한 위험 도구 목록
_DANGEROUS_TOOLS: frozenset = frozenset({
    # 파일/디렉토리 삭제
    "delete_file", "remove_file", "delete_directory", "remove_directory",
    "delete", "remove", "unlink", "rmdir",
    # git 원격/파괴적 작업
    "git_push", "git_force_push", "git_reset", "git_clean",
    # 셸/코드 실행 (잠재적 부작용)
    "execute_command", "run_command", "shell_exec", "bash",
    # DB 파괴
    "drop_table", "delete_database", "truncate_table",
})


def _check_dangerous_tools(execution_group: dict) -> List[str]:
    """실행 그룹 내 위험 도구 이름을 반환합니다."""
    return [
        task.get("tool_name", "")
        for task in execution_group.get("tasks", [])
        if task.get("tool_name", "").lower() in _DANGEROUS_TOOLS
    ]


_SENSITIVE_PATTERN = _re.compile(
    r'(?i)('
    r'password\s*[=:]\s*\S+|'
    r'passwd\s*[=:]\s*\S+|'
    r'api[_-]?key\s*[=:]\s*\S+|'
    r'secret[_-]?key\s*[=:]\s*\S+|'
    r'access[_-]?token\s*[=:]\s*\S+|'
    r'auth[_-]?token\s*[=:]\s*\S+|'
    r'AKIA[0-9A-Z]{16}|'
    r'sk-[A-Za-z0-9]{40,}|'
    r'ghp_[A-Za-z0-9]{36}|'
    r'-----BEGIN .* PRIVATE KEY-----'
    r')'
)

_SECURITY_CONTEXT_TOOLS: frozenset = frozenset({
    "git_push", "git_force_push", "git_commit",
    "network_request", "http_post", "http_put",
    "send_email", "send_message",
    "upload_file", "ftp_upload",
    "execute_script", "run_python",
})


def _check_sensitive_data(execution_group: dict) -> List[str]:
    """실행 그룹 인자에서 민감 데이터 패턴을 탐지합니다. 매칭된 패턴 목록 반환."""
    try:
        serialized = json.dumps(execution_group.get("tasks", []))
    except Exception:
        return []
    matches = _SENSITIVE_PATTERN.findall(serialized)
    return list({m[:20] + "..." for m in matches}) if matches else []


def _check_security_context(execution_group: dict) -> List[str]:
    """보안 컨텍스트 도구를 감지합니다."""
    return [
        task.get("tool_name", "")
        for task in execution_group.get("tasks", [])
        if task.get("tool_name", "") in _SECURITY_CONTEXT_TOOLS
    ]


# P1-C: 컨텍스트 파일 자동 주입 (AGENTS.md / README.md)
_CONTEXT_FILES = ["AGENTS.md", "README.md"]
_CONTEXT_MAX_BYTES = 8 * 1024  # 파일당 최대 8KB


# P2-A: 미완료 항목 키워드 목록
_INCOMPLETE_MARKERS = [
    "TODO", "FIXME", "HACK", "XXX",
    "미완료", "추후", "나중에", "해야 할", "남은 작업", "아직", "보류",
    "[ ]",  # Markdown 체크박스 미완료
]
_TODO_MAX_RETRIES = 3  # Todo Enforcer 최대 재시도 횟수


def _scan_incomplete_markers(history: List[str]) -> List[str]:
    """히스토리에서 미완료 마커가 포함된 항목을 반환합니다."""
    found = []
    for entry in history[-10:]:  # 최근 10개 항목만 검사
        if not isinstance(entry, str):
            continue
        for marker in _INCOMPLETE_MARKERS:
            if marker in entry:
                # 해당 줄만 추출 (최대 200자)
                for line in entry.splitlines():
                    if marker in line:
                        found.append(line.strip()[:200])
                break
    return found


def _load_context_files(start_dir: Optional[str] = None) -> str:
    """작업 디렉토리부터 상위로 올라가며 AGENTS.md / README.md 를 찾아 내용을 반환합니다.

    여러 파일이 있으면 개행으로 구분해 합칩니다.
    파일당 _CONTEXT_MAX_BYTES를 초과하면 잘라냅니다.
    """
    search_dir = Path(start_dir or os.getcwd()).resolve()
    visited: set = set()
    collected: List[str] = []

    # 현재 디렉토리 → 상위 3단계까지 탐색
    for directory in [search_dir] + list(search_dir.parents)[:3]:
        if directory in visited:
            continue
        visited.add(directory)
        for fname in _CONTEXT_FILES:
            fpath = directory / fname
            if fpath.is_file():
                try:
                    raw = fpath.read_bytes()[:_CONTEXT_MAX_BYTES].decode("utf-8", errors="replace")
                    collected.append(f"## [{fname}] ({fpath})\n{raw}")
                except Exception:
                    pass

    return "\n\n".join(collected)


# P1-B: 태스크 카테고리 → model_preference 매핑
_CATEGORY_TO_MODEL_PREF: dict = {
    "quick":      "standard",   # 단순 수정, 타이핑 수정
    "code":       "high",       # 코드 작성/분석
    "analysis":   "high",       # 심층 분석, 아키텍처 결정
    "creative":   "high",       # 창의적 작업, 문서 작성
    "deep":       "high",       # 심층 분석
    "ultrabrain": "high",       # 최고 복잡도 → 파이프라인 자동 라우팅
    "visual":     "auto",       # 시각/UI → gemini preferred
}

os.makedirs(PROMPTS_DIR, exist_ok=True)
default_prompt_path = os.path.join(PROMPTS_DIR, "default.txt")
if not os.path.exists(default_prompt_path):
    with open(default_prompt_path, "w", encoding="utf-8") as f:
        f.write("당신은 유능한 AI 어시스턴트입니다.")


# ── ollama auto-start ─────────────────────────────────────────────

_OLLAMA_BIN_CANDIDATES = [
    "/home/nanenya/.local/bin/ollama",
    os.path.expanduser("~/.local/bin/ollama"),
]

def _find_ollama_bin() -> Optional[str]:
    """ollama 실행 파일 경로를 반환합니다. 없으면 None."""
    for path in _OLLAMA_BIN_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    # PATH에서도 탐색
    import shutil
    return shutil.which("ollama")


def _is_ollama_running(base_url: str = "http://localhost:11434") -> bool:
    """Ollama 서버가 응답하는지 확인합니다."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(base_url)
            return resp.status_code == 200
    except Exception:
        return False


def _ensure_ollama_running() -> bool:
    """활성 프로바이더가 ollama일 때 서버가 실행 중인지 보장합니다.

    이미 실행 중이면 즉시 True를 반환합니다.
    실행 중이 아니면:
      1. systemctl --user start ollama 시도
      2. 실패 시 ollama 바이너리 직접 실행
    반환값: 서버 준비 완료 여부
    """
    from orchestrator.model_manager import load_config, get_active_model
    provider, _ = get_active_model(load_config())
    if provider != "ollama":
        return True  # ollama가 아니면 무관

    if _is_ollama_running():
        return True

    console.print("[yellow]Ollama 서버가 실행 중이 아닙니다. 자동 시작을 시도합니다...[/yellow]")

    # 1차: systemctl --user start ollama
    try:
        result = subprocess.run(
            ["systemctl", "--user", "start", "ollama"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            for _ in range(10):
                time.sleep(1)
                if _is_ollama_running():
                    console.print("[green]Ollama 서버가 systemd 서비스로 시작되었습니다.[/green]")
                    return True
    except Exception:
        pass

    # 2차: 바이너리 직접 실행
    ollama_bin = _find_ollama_bin()
    if not ollama_bin:
        console.print("[bold red]오류: ollama 바이너리를 찾을 수 없습니다.[/bold red]")
        console.print("  설치 경로 확인: ~/.local/bin/ollama")
        return False

    env = os.environ.copy()
    env.setdefault("OLLAMA_HOME", os.path.expanduser("~/.ollama"))
    subprocess.Popen(
        [ollama_bin, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    for _ in range(15):
        time.sleep(1)
        if _is_ollama_running():
            console.print("[green]Ollama 서버가 시작되었습니다.[/green]")
            return True

    console.print("[bold red]Ollama 서버 시작 실패. 수동으로 실행하세요: ollama serve[/bold red]")
    return False


# ── list ──────────────────────────────────────────────────────────

@app.command(name="list")
def list_conversations_cmd(
    group: Annotated[Optional[int], typer.Option("--group", "-g", help="그룹 ID로 필터")] = None,
    keyword: Annotated[Optional[str], typer.Option("--keyword", "-k", help="키워드로 필터")] = None,
    topic: Annotated[Optional[int], typer.Option("--topic", "-t", help="토픽 ID로 필터")] = None,
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="상태로 필터 (active|final|split)")] = None,
):
    """저장된 대화 목록을 표시합니다."""
    try:
        convos = list_conversations(
            group_id=group, keyword=keyword, topic_id=topic, status=status
        )
        table = Table("ID", "Title", "Last Updated", "Status", "Keywords")
        for convo in convos:
            kw_str = ", ".join(convo.get("keywords", [])[:5])
            table.add_row(
                convo["id"][:8] + "...",
                convo["title"],
                convo["last_updated"],
                convo.get("status", ""),
                kw_str,
            )
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]오류: 대화 목록을 불러올 수 없습니다. ({e})[/bold red]")


# ── run ───────────────────────────────────────────────────────────

@app.command()
def run(
    query: Annotated[str, typer.Option("--query", "-q", help="AI 에이전트에게 내릴 새로운 명령어")] = None,
    continue_id: Annotated[str, typer.Option("--continue", "-c", help="이어갈 대화의 ID")] = None,
    requirement_paths: Annotated[List[str], typer.Option("--req", "-r", help="참조할 요구사항 파일 경로")] = None,
    model_pref: Annotated[str, typer.Option("--model-pref", "-m", help="모델 선호도 (auto, standard, high)")] = "auto",
    system_prompts: Annotated[List[str], typer.Option("--gem", "-g", help="사용할 시스템 프롬프트 (Gem) 이름 (예: default)")] = None,
    persona: Annotated[Optional[str], typer.Option("--persona", "-p", help="사용할 페르소나 이름 (DB에서 조회)")] = None,
    auto: Annotated[bool, typer.Option("--auto", "-a", help="자동 실행 모드: 계획 승인 없이 완료까지 자동 반복")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="--auto 모드에서 위험 도구도 자동 승인 (주의 필요)")] = False,
    max_steps: Annotated[int, typer.Option("--max-steps", help="자동 모드 최대 실행 단계 수 (0=무제한, 기본 50)")] = 50,
    category: Annotated[Optional[str], typer.Option("--category", "-C", help="태스크 유형 (quick/code/analysis/creative/deep/ultrabrain/visual) → 모델 자동 선택")] = None,
    no_context: Annotated[bool, typer.Option("--no-context", help="AGENTS.md / README.md 자동 주입 비활성화")] = False,
    plan: Annotated[bool, typer.Option("--plan", help="Prometheus 모드: 실행 전 요구사항 명확화 질문")] = False,
    summarize: Annotated[bool, typer.Option("--summarize", help="히스토리 임계치 초과 시 LLM 요약 압축 활성화")] = False,
    force_react: Annotated[bool, typer.Option("--force-react", help="3-tier 자동 라우팅 우회, 항상 ReAct 모드 사용")] = False,
    parallel: Annotated[bool, typer.Option("--parallel", help="병렬 플래닝 모드: 독립 태스크를 한 번에 계획해 동시 실행")] = False,
    pipeline: Annotated[bool, typer.Option("--pipeline", help="4층 파이프라인 모드 강제 사용 (설계→태스크분해→플랜→실행)")] = False,
):
    """
    AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다.
    """
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

    # P1-B: 카테고리 → model_preference 자동 매핑
    if category:
        mapped = _CATEGORY_TO_MODEL_PREF.get(category.lower())
        if mapped:
            model_pref = mapped
            console.print(f"[dim]카테고리 '{category}' → 모델 선호도 '{model_pref}' 자동 설정[/dim]")
        else:
            console.print(
                f"[bold yellow]경고: 알 수 없는 카테고리 '{category}'. "
                f"사용 가능: {', '.join(_CATEGORY_TO_MODEL_PREF)}[/bold yellow]"
            )

    _ensure_ollama_running()

    client = httpx.Client(timeout=120)

    prompt_contents = []
    if system_prompts:
        for prompt_name in system_prompts:
            prompt_file = os.path.join(PROMPTS_DIR, f"{prompt_name}.txt")
            if os.path.exists(prompt_file):
                try:
                    with open(prompt_file, "r", encoding="utf-8") as f:
                        prompt_contents.append(f.read())
                except Exception as e:
                    console.print(f"[bold yellow]경고: 프롬프트 파일 '{prompt_file}'을 읽을 수 없습니다: {e}[/bold yellow]")
            else:
                console.print(f"[bold yellow]경고: 프롬프트 파일 '{prompt_file}'을 찾을 수 없습니다.[/bold yellow]")

    # P1-C: AGENTS.md / README.md 자동 주입
    if not no_context:
        ctx_content = _load_context_files()
        if ctx_content:
            prompt_contents.insert(0, f"# 프로젝트 컨텍스트 (자동 주입)\n\n{ctx_content}")
            console.print("[dim]📄 AGENTS.md / README.md 컨텍스트 자동 주입됨[/dim]")

    # P2-C: Prometheus 모드 — 실행 전 요구사항 명확화 인터뷰
    if plan and query:
        console.print("[bold cyan]🧠 Prometheus 모드: 요구사항을 명확히 합니다...[/bold cyan]")
        from orchestrator.llm_client import generate_clarifying_questions
        questions = asyncio.run(generate_clarifying_questions(query, model_preference=model_pref))
        if questions:
            console.print("[bold yellow]실행 전 확인 사항:[/bold yellow]")
            answers = []
            for i, q in enumerate(questions, 1):
                ans = typer.prompt(f"  [{i}] {q}")
                answers.append(f"Q: {q}\nA: {ans}")
            # 질문/답변을 쿼리에 컨텍스트로 추가
            qa_context = "\n".join(answers)
            query = f"{query}\n\n[사전 확인 사항]\n{qa_context}"
            console.print("[dim]사전 확인 사항이 쿼리에 추가되었습니다.[/dim]")
        else:
            console.print("[dim]추가 확인 사항 없음. 바로 실행합니다.[/dim]")

    if query:
        convo_id, history = new_conversation()
        console.print(f"새로운 대화를 시작합니다. (ID: {convo_id})")

        request_data = {
            "conversation_id": convo_id,
            "history": history,
            "user_input": query,
            "requirement_paths": requirement_paths,
            "model_preference": model_pref,
            "system_prompts": prompt_contents,
            "persona": persona,
            "force_react": force_react,
            "parallel_mode": parallel,
        }
        endpoint = "/agent/pipeline" if pipeline else "/agent/decide_and_act"
        if pipeline:
            console.print("[bold magenta]🏗️  4층 파이프라인 모드[/bold magenta]")
    else:
        convo_id = continue_id
        data = load_conversation(convo_id)
        if not data:
            console.print(f"[bold red]오류: ID '{convo_id}'에 해당하는 대화를 찾을 수 없습니다.[/bold red]")
            raise typer.Exit()

        history = data.get("history", [])
        convo_id = data.get("id", convo_id)
        console.print(f"대화를 이어합니다. (ID: {convo_id})")

        user_input = typer.prompt("추가/수정 지시가 있나요? (없으면 Enter 키로 기존 계획 계속)")

        request_data = {
            "conversation_id": convo_id,
            "history": history,
            "user_input": user_input or None,
            "model_preference": model_pref,
            "system_prompts": prompt_contents,
            "persona": persona,
            "force_react": force_react,
            "parallel_mode": parallel,
        }
        endpoint = "/agent/pipeline" if pipeline else "/agent/decide_and_act"

    # --- 상호작용 루프 ---
    _sess_in = _sess_out = 0
    _sess_cost = 0.0
    _step_count = 0       # 자동 모드 실행 단계 카운터
    _todo_retries = 0     # P2-A Todo Enforcer 재시도 카운터

    if auto:
        _limit_str = f"최대 {max_steps}단계" if max_steps > 0 else "무제한"
        _force_str = " [bold red](--force: 위험 도구 자동 승인)[/bold red]" if force else ""
        console.print(f"[bold cyan]🤖 자동 실행 모드[/bold cyan] ({_limit_str}){_force_str}")

    while True:
        try:
            response = client.post(f"{ORCHESTRATOR_URL}{endpoint}", json=request_data)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            message = data.get("message")
            convo_id = data.get("conversation_id")
            history = data.get("history")

            # 토큰 사용량 누적
            _usage = data.get("token_usage") or {}
            if _usage:
                _sess_in += _usage.get("input_tokens", 0)
                _sess_out += _usage.get("output_tokens", 0)
                _sess_cost += _usage.get("cost_usd", 0.0)

            if status == "FINAL_ANSWER":
                console.print(f"\n[bold green]최종 답변:[/bold green]\n{message}")

                # P2-A: Todo Enforcer — 미완료 항목 감지 후 재실행
                if _todo_retries < _TODO_MAX_RETRIES:
                    incomplete = _scan_incomplete_markers(history or [])
                    if incomplete:
                        _todo_retries += 1
                        items_str = "\n".join(f"  - {i}" for i in incomplete[:5])
                        console.print(
                            f"\n[bold yellow]📋 Todo Enforcer: 미완료 항목 감지 "
                            f"({_todo_retries}/{_TODO_MAX_RETRIES})[/bold yellow]\n{items_str}"
                        )
                        followup = (
                            f"아직 완료되지 않은 항목이 있습니다:\n{items_str}\n\n"
                            "위 항목들을 완료해 주세요."
                        )
                        endpoint = "/agent/decide_and_act"
                        request_data = {
                            "conversation_id": convo_id,
                            "history": history,
                            "user_input": followup,
                            "model_preference": model_pref,
                            "system_prompts": prompt_contents,
                        }
                        continue  # 루프 재진입

                # topic_split_info 처리
                topic_split_info = data.get("topic_split_info")
                if topic_split_info and topic_split_info.get("detected"):
                    console.print("\n[bold yellow]주제 전환 감지됨:[/bold yellow]")
                    console.print(f"  전환 지점: 인덱스 {topic_split_info.get('split_index')}")
                    console.print(f"  이유: {topic_split_info.get('reason')}")
                    console.print(f"  주제 A: {topic_split_info.get('topic_a')}")
                    console.print(f"  주제 B: {topic_split_info.get('topic_b')}")
                    if typer.confirm("이 대화를 두 개로 분리하시겠습니까?", default=False):
                        idx = topic_split_info.get("split_index", 0)
                        orig_id, new_id = split_conversation(convo_id, idx)
                        console.print(f"[green]대화가 분리되었습니다.[/green]")
                        console.print(f"  원본: {orig_id}")
                        console.print(f"  새 대화: {new_id}")

                # 세션 토큰 사용량 합계
                if _sess_in:
                    sess_cost_str = (
                        f"  │  총 비용 ${_sess_cost:.4f}" if _sess_cost > 0 else ""
                    )
                    console.print(
                        f"[dim]📊 세션 합계  입력 {_sess_in:,} · 출력 {_sess_out:,} tok{sess_cost_str}[/dim]"
                    )
                break

            elif status == "STEP_EXECUTED":
                _step_count += 1
                console.print(f"[cyan]...{message}[/cyan]")

                # 자동 모드 최대 단계 체크
                if auto and max_steps > 0 and _step_count >= max_steps:
                    console.print(
                        f"\n[bold yellow]⚠️  최대 단계 수({max_steps})에 도달했습니다.[/bold yellow]"
                    )
                    action = typer.prompt(
                        "계속 진행할까요? [Y(계속)/n(중단)]", default="Y"
                    ).lower()
                    if action not in ["y", "yes", ""]:
                        console.print("[bold red]자동 실행을 중단합니다.[/bold red]")
                        break
                    _step_count = 0  # 카운터 리셋 후 계속

                # P2-D: 히스토리 임계치 초과 시 LLM 요약 압축
                _SUMMARIZE_THRESHOLD = 30
                if summarize and history and len(history) >= _SUMMARIZE_THRESHOLD:
                    console.print(
                        f"[dim]📝 히스토리 {len(history)}개 항목 → LLM 요약 중...[/dim]"
                    )
                    from orchestrator.llm_client import summarize_history as _summarize
                    summary = asyncio.run(_summarize(history[:-5], model_preference=model_pref))
                    if summary:
                        history = [f"[이전 대화 요약]\n{summary}"] + history[-5:]
                        console.print(
                            f"[dim]히스토리 압축 완료: {_SUMMARIZE_THRESHOLD}개 → {len(history)}개[/dim]"
                        )

                console.print("[cyan]...다음 단계를 계획합니다...[/cyan]")
                endpoint = "/agent/pipeline" if pipeline else "/agent/decide_and_act"
                request_data = {
                    "conversation_id": convo_id,
                    "history": history,
                    "user_input": None,
                    "model_preference": model_pref,
                    "system_prompts": prompt_contents,
                }

            elif status == "PLAN_CONFIRMATION":
                console.print(f"\n[bold yellow]다음 실행 계획:[/bold yellow]\n{message}")
                if _usage:
                    console.print(f"[dim]📊 {_fmt_usage(_usage)}[/dim]")

                if auto:
                    exec_group = data.get("execution_group") or {}
                    dangerous = _check_dangerous_tools(exec_group)
                    sensitive = _check_sensitive_data(exec_group)
                    security = _check_security_context(exec_group)
                    needs_confirm = bool(dangerous or sensitive or security)

                    if needs_confirm and not force:
                        if dangerous:
                            console.print(f"\n[bold red]⚠️  위험 도구 감지: {', '.join(dangerous)}[/bold red]")
                        if sensitive:
                            console.print(f"[bold red]🔐 민감 데이터 패턴 감지: {sensitive}[/bold red]")
                        if security:
                            console.print(f"[bold yellow]🔒 보안 컨텍스트 도구: {security}[/bold yellow]")
                        console.print("[dim]--force 플래그를 사용하면 자동 승인됩니다.[/dim]")
                        action = typer.prompt(
                            "계속하시겠습니까? [Y/n/edit]",
                            default="Y",
                        ).lower()
                        if action == "edit":
                            edited_instruction = typer.prompt("어떻게 수정할까요? (새로운 계획 수립)")
                            endpoint = "/agent/decide_and_act"
                            request_data = {
                                "conversation_id": convo_id,
                                "history": history,
                                "user_input": edited_instruction,
                                "model_preference": model_pref,
                                "system_prompts": prompt_contents,
                            }
                            continue
                        elif action not in ["y", "yes", ""]:
                            console.print("[bold red]자동 실행을 중단합니다.[/bold red]")
                            break
                    elif needs_confirm and force:
                        if dangerous:
                            console.print(f"[bold yellow]⚡ --force 자동 승인 (위험 도구: {dangerous})[/bold yellow]")
                        if sensitive:
                            console.print(f"[bold yellow]⚡ --force 자동 승인 (민감 데이터 감지)[/bold yellow]")
                        if security:
                            console.print(f"[bold yellow]⚡ --force 자동 승인 (보안 컨텍스트: {security})[/bold yellow]")
                    else:
                        step_info = f" (단계 {_step_count + 1}" + (f"/{max_steps}" if max_steps > 0 else "") + ")"
                        console.print(f"[dim cyan]🤖 자동 승인{step_info}[/dim cyan]")

                    console.print("[cyan]...계획 그룹을 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    request_data = {
                        "conversation_id": convo_id,
                        "history": history,
                        "model_preference": model_pref,
                    }

                else:
                    # 수동 승인 모드 (기존 동작)
                    action = typer.prompt(
                        "승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y"
                    ).lower()

                    if action in ["y", "yes"]:
                        console.print("[cyan]...승인됨. 계획 그룹을 실행합니다...[/cyan]")
                        endpoint = "/agent/execute_group"
                        request_data = {
                            "conversation_id": convo_id,
                            "history": history,
                            "model_preference": model_pref,
                        }
                    elif action == "edit":
                        edited_instruction = typer.prompt("어떻게 수정할까요? (새로운 계획 수립)")
                        endpoint = "/agent/decide_and_act"
                        request_data = {
                            "conversation_id": convo_id,
                            "history": history,
                            "user_input": edited_instruction,
                            "model_preference": model_pref,
                            "system_prompts": prompt_contents,
                        }
                    else:
                        console.print("[bold red]작업을 중단합니다.[/bold red]")
                        break

            elif status == "DESIGN_CONFIRMATION":
                console.print(f"\n[bold blue]🎨 설계안:[/bold blue]\n{message}")
                if _usage:
                    console.print(f"[dim]📊 {_fmt_usage(_usage)}[/dim]")

                # 자율성 정책: --auto 모드에서도 설계는 항상 사용자 확인
                action = typer.prompt(
                    "설계를 확인하시겠습니까? [confirm/reject/edit]",
                    default="confirm",
                ).lower()

                if action == "reject":
                    endpoint = "/agent/pipeline"
                    request_data = {
                        "conversation_id": convo_id,
                        "history": history,
                        "user_input": None,
                        "model_preference": model_pref,
                        "system_prompts": prompt_contents,
                        "pipeline_action": "reject_design",
                    }
                elif action == "edit":
                    new_instruction = typer.prompt("수정 지시사항을 입력하세요")
                    endpoint = "/agent/pipeline"
                    request_data = {
                        "conversation_id": convo_id,
                        "history": history,
                        "user_input": new_instruction,
                        "model_preference": model_pref,
                        "system_prompts": prompt_contents,
                        "pipeline_action": "reject_design",
                    }
                else:  # confirm
                    console.print("[cyan]...설계 확인됨. 태스크 분해를 시작합니다...[/cyan]")
                    endpoint = "/agent/pipeline"
                    request_data = {
                        "conversation_id": convo_id,
                        "history": history,
                        "user_input": None,
                        "model_preference": model_pref,
                        "system_prompts": prompt_contents,
                        "pipeline_action": "confirm_design",
                    }

            elif status == "ERROR":
                console.print(f"[bold red]서버 오류: {message}[/bold red]")
                break

        except httpx.RequestError:
            console.print("[bold red]오류: 오케스트레이터 서버에 연결할 수 없습니다. 서버를 실행하세요.[/bold red]")
            break
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]오류: 서버에서 에러 응답을 받았습니다. {e.response.text}[/bold red]")
            break


# ── server ───────────────────────────────────────────────────────

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


@app.command(name="server")
def run_server(
    host: Annotated[str, typer.Option(help="서버가 바인딩할 호스트 주소")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="서버가 리스닝할 포트 번호")] = 8000,
    reload: Annotated[bool, typer.Option(help="코드 변경 시 서버 자동 재시작 여부")] = False,
):
    """FastAPI 오케스트레이터 서버를 실행합니다."""
    _ensure_ollama_running()
    typer.echo(f"{port}번 포트를 사용하는 기존 프로세스를 확인하고 종료합니다...")
    try:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        typer.secho("기존 프로세스를 성공적으로 종료했습니다.", fg=typer.colors.GREEN)
        typer.echo("포트가 해제되기를 기다리고 있습니다...")
        max_wait_seconds = 5
        wait_start_time = time.time()
        while is_port_in_use(port, host):
            if time.time() - wait_start_time > max_wait_seconds:
                typer.secho(
                    f"{max_wait_seconds}초가 지나도 {port}번 포트가 여전히 사용 중입니다.",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(code=1)
            time.sleep(0.5)
        typer.secho("포트가 성공적으로 해제되었습니다.", fg=typer.colors.GREEN)
    except FileNotFoundError:
        typer.secho(
            "경고: 'fuser' 명령어를 찾을 수 없습니다. 포트 충돌이 발생할 수 있습니다.",
            fg=typer.colors.YELLOW,
        )
    except subprocess.CalledProcessError:
        typer.echo(f"{port}번 포트를 사용하는 기존 프로세스가 없습니다. 바로 시작합니다.")

    typer.echo(f"FastAPI 서버 시작: http://{host}:{port}")
    uvicorn.run("orchestrator.api:app", host=host, port=port, reload=reload)


# ── graph ─────────────────────────────────────────────────────────

@app.command(name="graph")
def graph_cmd(
    center: Annotated[Optional[str], typer.Option("--center", "-c", help="중심 대화 UUID")] = None,
    depth: Annotated[int, typer.Option("--depth", "-d", help="탐색 깊이")] = 2,
):
    """대화 관계 그래프를 Rich 뷰로 출력합니다."""
    from orchestrator import graph_manager

    graph_data = graph_manager.get_graph_data(center_id=center, depth=depth)
    if not graph_data["nodes"]:
        console.print("[yellow]표시할 노드가 없습니다. 대화를 먼저 생성하세요.[/yellow]")
        return
    graph_manager.render_graph(graph_data, center_id=center)


# ── migrate ───────────────────────────────────────────────────────

@app.command(name="migrate")
def migrate_cmd(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="실제 마이그레이션 없이 변환 대상 확인")] = False,
):
    """기존 JSON 히스토리를 SQLite로 마이그레이션합니다."""
    from orchestrator import graph_manager

    history_dir = Path("history")
    if not history_dir.exists():
        console.print("[yellow]history/ 디렉토리가 없습니다.[/yellow]")
        return

    json_files = sorted(history_dir.glob("*.json"))
    if dry_run:
        console.print(f"[cyan]마이그레이션 대상: {len(json_files)}개 파일[/cyan]")
        for f in json_files:
            console.print(f"  - {f.name}")
        return

    count = graph_manager.migrate_json_to_sqlite(history_dir)
    console.print(f"[green]마이그레이션 완료: {count}개 대화 이전됨[/green]")


# ── group 서브커맨드 ──────────────────────────────────────────────

@group_app.command(name="list")
def group_list():
    """그룹 목록 표시."""
    from orchestrator import graph_manager

    groups = graph_manager.list_groups()
    if not groups:
        console.print("[yellow]등록된 그룹이 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Description", "Conversations")
    for g in groups:
        table.add_row(
            str(g["id"]), g["name"], g.get("description", ""), str(g["convo_count"])
        )
    console.print(table)


@group_app.command(name="create")
def group_create(
    name: Annotated[str, typer.Argument(help="그룹 이름")],
    desc: Annotated[str, typer.Option("--desc", "-d", help="그룹 설명")] = "",
):
    """새 그룹 생성."""
    from orchestrator import graph_manager

    try:
        gid = graph_manager.create_group(name, desc)
        console.print(f"[green]그룹 '{name}' 생성됨 (ID: {gid})[/green]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@group_app.command(name="delete")
def group_delete(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
):
    """그룹 삭제."""
    from orchestrator import graph_manager

    if graph_manager.delete_group(group_id):
        console.print(f"[green]그룹 {group_id} 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 그룹 {group_id}를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@group_app.command(name="add-convo")
def group_add_convo(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 그룹에 추가."""
    from orchestrator import graph_manager

    graph_manager.assign_conversation_to_group(convo_id, group_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 그룹 {group_id}에 추가되었습니다.[/green]")


@group_app.command(name="remove-convo")
def group_remove_convo(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 그룹에서 제거."""
    from orchestrator import graph_manager

    graph_manager.remove_conversation_from_group(convo_id, group_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 그룹 {group_id}에서 제거되었습니다.[/green]")


# ── topic 서브커맨드 ──────────────────────────────────────────────

@topic_app.command(name="list")
def topic_list():
    """토픽 목록 표시."""
    from orchestrator import graph_manager

    topics = graph_manager.list_topics()
    if not topics:
        console.print("[yellow]등록된 토픽이 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Description", "Conversations", "Keywords")
    for t in topics:
        table.add_row(
            str(t["id"]),
            t["name"],
            t.get("description", ""),
            str(t["convo_count"]),
            str(t["keyword_count"]),
        )
    console.print(table)


@topic_app.command(name="create")
def topic_create(
    name: Annotated[str, typer.Argument(help="토픽 이름")],
    desc: Annotated[str, typer.Option("--desc", "-d", help="토픽 설명")] = "",
):
    """새 토픽 생성."""
    from orchestrator import graph_manager

    tid = graph_manager.create_topic(name, desc)
    console.print(f"[green]토픽 '{name}' 생성됨 (ID: {tid})[/green]")


@topic_app.command(name="delete")
def topic_delete(
    topic_id: Annotated[int, typer.Argument(help="토픽 ID")],
):
    """토픽 삭제."""
    from orchestrator import graph_manager

    if graph_manager.delete_topic(topic_id):
        console.print(f"[green]토픽 {topic_id} 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 토픽 {topic_id}를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@topic_app.command(name="link")
def topic_link(
    id_a: Annotated[int, typer.Argument(help="토픽 ID A")],
    id_b: Annotated[int, typer.Argument(help="토픽 ID B")],
    relation: Annotated[str, typer.Option("--relation", "-r", help="관계 설명")] = "",
):
    """두 토픽을 양방향 연결."""
    from orchestrator import graph_manager

    graph_manager.link_topics(id_a, id_b, relation)
    console.print(f"[green]토픽 {id_a} ↔ {id_b} 연결됨[/green]")


@topic_app.command(name="add-convo")
def topic_add_convo(
    topic_id: Annotated[int, typer.Argument(help="토픽 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 토픽에 추가."""
    from orchestrator import graph_manager

    graph_manager.assign_conversation_to_topic(convo_id, topic_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 토픽 {topic_id}에 추가되었습니다.[/green]")


# ── keyword 서브커맨드 ────────────────────────────────────────────

@keyword_app.command(name="list")
def keyword_list(
    convo_id: Annotated[Optional[str], typer.Argument(help="대화 UUID (생략 시 전체)")] = None,
):
    """키워드 목록 표시. 대화 UUID를 지정하면 해당 대화의 키워드만 표시."""
    from orchestrator import graph_manager

    kws = graph_manager.list_keywords(convo_id)
    if not kws:
        console.print("[yellow]키워드가 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Usage Count")
    for k in kws:
        table.add_row(str(k["id"]), k["name"], str(k["usage_count"]))
    console.print(table)


@keyword_app.command(name="edit")
def keyword_edit(
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화의 키워드를 수동으로 편집합니다."""
    from orchestrator import graph_manager

    data = load_conversation(convo_id)
    if not data:
        console.print(f"[bold red]오류: 대화 '{convo_id}'를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)

    current_kws = graph_manager.list_keywords(convo_id)
    current_names = [k["name"] for k in current_kws]
    console.print(f"현재 키워드: {', '.join(current_names) if current_names else '(없음)'}")

    new_input = typer.prompt("새 키워드를 입력하세요 (쉼표로 구분)")
    new_names = [k.strip() for k in new_input.split(",") if k.strip()]

    if not new_names:
        console.print("[yellow]키워드가 입력되지 않았습니다. 변경하지 않습니다.[/yellow]")
        return

    graph_manager.update_conversation_keywords(convo_id, new_names)
    console.print(f"[green]키워드 업데이트 완료: {', '.join(new_names)}[/green]")


@keyword_app.command(name="search")
def keyword_search(
    keyword: Annotated[str, typer.Argument(help="검색할 키워드")],
):
    """키워드로 대화를 검색합니다."""
    convos = list_conversations(keyword=keyword)
    if not convos:
        console.print(f"[yellow]'{keyword}' 키워드를 가진 대화가 없습니다.[/yellow]")
        return
    table = Table("ID", "Title", "Last Updated", "Keywords")
    for c in convos:
        kw_str = ", ".join(c.get("keywords", [])[:5])
        table.add_row(c["id"][:8] + "...", c["title"], c["last_updated"], kw_str)
    console.print(table)


# ── mcp 서브커맨드 ────────────────────────────────────────────────

@mcp_app.command(name="list")
def mcp_list(
    all_servers: Annotated[bool, typer.Option("--all", "-a", help="비활성 서버도 포함하여 표시")] = False,
):
    """등록된 MCP 서버 목록을 표시합니다."""
    registry = mcp_manager.load_registry()
    servers = mcp_manager.get_servers(registry, enabled_only=not all_servers)

    if not servers:
        console.print("[yellow]등록된 MCP 서버가 없습니다.[/yellow]")
        return

    table = Table("Name", "Package", "Manager", "Enabled", "Description")
    for s in servers:
        enabled = "[green]Yes[/green]" if s.get("enabled", True) else "[red]No[/red]"
        table.add_row(
            s["name"],
            s.get("package", ""),
            s.get("package_manager", ""),
            enabled,
            s.get("description", ""),
        )
    console.print(table)


@mcp_app.command(name="add")
def mcp_add(
    name: Annotated[str, typer.Argument(help="서버 이름")],
    package: Annotated[str, typer.Option("--package", "-p", help="패키지 이름")] = "",
    manager: Annotated[str, typer.Option("--manager", "-m", help="패키지 매니저 (npm|pip)")] = "npm",
    desc: Annotated[str, typer.Option("--desc", "-d", help="서버 설명")] = "",
    compare: Annotated[bool, typer.Option("--compare/--no-compare", help="등록 전 도구 중복 비교")] = True,
):
    """MCP 서버를 레지스트리에 추가합니다."""
    registry = mcp_manager.load_registry()

    try:
        server_entry = mcp_manager.add_server(
            registry,
            name=name,
            package=package,
            package_manager=manager,
            description=desc,
        )
    except ValueError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)

    if compare:
        console.print("[cyan]도구 목록을 조회하고 중복을 비교합니다...[/cyan]")
        try:
            new_tools = asyncio.run(mcp_manager.probe_server_tools(server_entry))
            if new_tools:
                from orchestrator.tool_registry import TOOL_DESCRIPTIONS

                overlaps = mcp_manager.get_tool_overlap_report(
                    new_tools, TOOL_DESCRIPTIONS
                )
                if overlaps:
                    overlap_table = Table("Tool", "New Description", "Existing Description")
                    for o in overlaps:
                        overlap_table.add_row(
                            o["name"], o["new_desc"], o["existing_desc"]
                        )
                    console.print("[bold yellow]중복 도구 발견:[/bold yellow]")
                    console.print(overlap_table)
                else:
                    console.print("[green]중복 도구가 없습니다.[/green]")

                tool_table = Table("Tool Name", "Description")
                for t in new_tools:
                    tool_table.add_row(t["name"], t["description"])
                console.print("[bold]새 서버가 제공하는 도구:[/bold]")
                console.print(tool_table)
            else:
                console.print("[yellow]도구를 조회할 수 없습니다. (서버 연결 실패)[/yellow]")
        except Exception as e:
            console.print(f"[yellow]도구 비교 중 오류 (서버는 등록됩니다): {e}[/yellow]")

        if not typer.confirm("이 서버를 등록하시겠습니까?", default=True):
            mcp_manager.remove_server(registry, name)
            console.print("[yellow]등록이 취소되었습니다.[/yellow]")
            return

    mcp_manager.save_registry(registry)
    console.print(f"[green]서버 '{name}'이(가) 등록되었습니다.[/green]")


@mcp_app.command(name="remove")
def mcp_remove(
    name: Annotated[str, typer.Argument(help="제거할 서버 이름")],
):
    """MCP 서버를 레지스트리에서 제거합니다."""
    registry = mcp_manager.load_registry()
    if mcp_manager.remove_server(registry, name):
        mcp_manager.save_registry(registry)
        console.print(f"[green]서버 '{name}'이(가) 제거되었습니다.[/green]")
    else:
        console.print(f"[bold red]오류: 서버 '{name}'을(를) 찾을 수 없습니다.[/bold red]")


@mcp_app.command(name="search")
def mcp_search(
    query: Annotated[str, typer.Argument(help="검색 키워드")],
    manager: Annotated[str, typer.Option("--manager", "-m", help="패키지 매니저 (npm|pip|all)")] = "all",
):
    """npm/PyPI에서 MCP 서버 패키지를 검색합니다."""
    console.print(f"[cyan]'{query}' 검색 중...[/cyan]")
    results = mcp_manager.search_packages(query, manager)

    for mgr, packages in results.items():
        if not packages:
            console.print(f"[yellow]{mgr}: 결과 없음[/yellow]")
            continue
        table = Table(f"{mgr} - Name", "Version", "Description")
        for p in packages:
            table.add_row(p["name"], p.get("version", ""), p["description"])
        console.print(table)


@mcp_app.command(name="enable")
def mcp_enable(
    name: Annotated[str, typer.Argument(help="활성화할 서버 이름")],
):
    """MCP 서버를 활성화합니다."""
    registry = mcp_manager.load_registry()
    if mcp_manager.enable_server(registry, name, enabled=True):
        mcp_manager.save_registry(registry)
        console.print(f"[green]서버 '{name}'이(가) 활성화되었습니다.[/green]")
    else:
        console.print(f"[bold red]오류: 서버 '{name}'을(를) 찾을 수 없습니다.[/bold red]")


@mcp_app.command(name="disable")
def mcp_disable(
    name: Annotated[str, typer.Argument(help="비활성화할 서버 이름")],
):
    """MCP 서버를 비활성화합니다."""
    registry = mcp_manager.load_registry()
    if mcp_manager.enable_server(registry, name, enabled=False):
        mcp_manager.save_registry(registry)
        console.print(f"[yellow]서버 '{name}'이(가) 비활성화되었습니다.[/yellow]")
    else:
        console.print(f"[bold red]오류: 서버 '{name}'을(를) 찾을 수 없습니다.[/bold red]")


# ── mcp function 서브커맨드 ───────────────────────────────────────

@func_app.command(name="add")
def func_add(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    group: Annotated[str, typer.Option("--group", "-g", help="모듈 그룹")] = "default",
    code: Annotated[Optional[str], typer.Option("--code", help="코드 파일 경로")] = None,
    test: Annotated[Optional[str], typer.Option("--test", help="테스트 코드 파일 경로")] = None,
    source_type: Annotated[str, typer.Option("--source-type", help="출처 유형 (internal|external)")] = "internal",
    source_url: Annotated[str, typer.Option("--source-url", help="출처 URL")] = "",
):
    """함수를 DB에 등록합니다."""
    from orchestrator import mcp_db_manager

    func_code = ""
    if code:
        try:
            func_code = Path(code).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold red]코드 파일 읽기 실패: {e}[/bold red]")
            raise typer.Exit(code=1)
    else:
        func_code = typer.prompt("함수 코드를 입력하세요 (EOF로 종료)")

    test_code = ""
    if test:
        try:
            test_code = Path(test).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold yellow]테스트 파일 읽기 실패 (무시): {e}[/bold yellow]")

    result = mcp_db_manager.register_function(
        func_name=name,
        module_group=group,
        code=func_code,
        test_code=test_code,
        source_type=source_type,
        source_url=source_url,
    )
    status = "[green]활성화됨[/green]" if result.get("activated") else "[yellow]테스트 실패 (비활성)[/yellow]"
    console.print(f"함수 '{name}' 등록됨 (v{result['version']}, 테스트: {result['test_status']}, {status})")


@func_app.command(name="list")
def func_list(
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 필터")] = None,
    all_versions: Annotated[bool, typer.Option("--all", "-a", help="비활성 버전도 포함")] = False,
):
    """등록된 함수 목록을 표시합니다."""
    from orchestrator import mcp_db_manager

    funcs = mcp_db_manager.list_functions(module_group=group, active_only=not all_versions)
    if not funcs:
        console.print("[yellow]등록된 함수가 없습니다.[/yellow]")
        return
    table = Table("Name", "Group", "Version", "Active", "Test", "Description")
    for f in funcs:
        active = "[green]Yes[/green]" if f["is_active"] else "[dim]No[/dim]"
        table.add_row(
            f["func_name"], f["module_group"], str(f["version"]),
            active, f["test_status"], f["description"][:50],
        )
    console.print(table)


@func_app.command(name="versions")
def func_versions(
    name: Annotated[str, typer.Argument(help="함수 이름")],
):
    """함수의 버전 이력을 표시합니다."""
    from orchestrator import mcp_db_manager

    versions = mcp_db_manager.get_function_versions(name)
    if not versions:
        console.print(f"[yellow]'{name}' 함수를 찾을 수 없습니다.[/yellow]")
        return
    table = Table("Version", "Active", "Test", "Created", "Activated")
    for v in versions:
        active = "[green]Yes[/green]" if v["is_active"] else "[dim]No[/dim]"
        table.add_row(
            str(v["version"]), active, v["test_status"],
            v["created_at"][:19], (v["activated_at"] or "")[:19],
        )
    console.print(table)


@func_app.command(name="show")
def func_show(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (생략 시 활성 버전)")] = None,
):
    """함수 상세 정보 및 코드를 출력합니다."""
    from orchestrator import mcp_db_manager

    if version:
        versions = mcp_db_manager.get_function_versions(name)
        func = next((v for v in versions if v["version"] == version), None)
    else:
        func = mcp_db_manager.get_active_function(name)

    if not func:
        console.print(f"[bold red]오류: 함수 '{name}' (v{version})을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]이름:[/bold] {func['func_name']}")
    console.print(f"[bold]그룹:[/bold] {func['module_group']}")
    console.print(f"[bold]버전:[/bold] {func['version']}")
    console.print(f"[bold]활성:[/bold] {'예' if func['is_active'] else '아니오'}")
    console.print(f"[bold]테스트:[/bold] {func['test_status']}")
    console.print(f"[bold]설명:[/bold] {func['description']}")
    if func.get("source_url"):
        console.print(f"[bold]출처:[/bold] {func['source_type']} — {func['source_url']}")
    console.print(f"[bold]코드:[/bold]\n{func['code']}")


@func_app.command(name="test")
def func_test(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (생략 시 활성 버전)")] = None,
):
    """함수 테스트를 실행합니다."""
    from orchestrator import mcp_db_manager

    if version is None:
        func = mcp_db_manager.get_active_function(name)
        if not func:
            console.print(f"[bold red]오류: 활성 버전이 없습니다.[/bold red]")
            raise typer.Exit(code=1)
        version = func["version"]

    console.print(f"[cyan]테스트 실행 중: {name} v{version}...[/cyan]")
    result = mcp_db_manager.run_function_tests(name, version)
    if result["test_status"] == "passed":
        console.print(f"[green]테스트 통과[/green]")
    else:
        console.print(f"[bold red]테스트 실패[/bold red]")
    if result.get("test_output"):
        console.print(result["test_output"])


@func_app.command(name="import")
def func_import(
    file: Annotated[str, typer.Argument(help="임포트할 Python 파일 경로")],
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 (기본: 파일명)")] = None,
    test_file: Annotated[Optional[str], typer.Option("--test-file", "-t", help="테스트 파일 경로")] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="테스트 실행 건너뜀")] = False,
):
    """Python 파일의 함수들을 DB로 일괄 임포트합니다."""
    from orchestrator import mcp_db_manager

    console.print(f"[cyan]임포트 중: {file}...[/cyan]")
    result = mcp_db_manager.import_from_file(
        file_path=file,
        module_group=group,
        test_file_path=test_file,
        run_tests=not no_tests,
    )
    console.print(f"[green]임포트 완료: {result['imported_functions']}개 함수[/green]")
    if result["failed"]:
        console.print(f"[bold red]실패: {len(result['failed'])}개[/bold red]")
        for f in result["failed"]:
            console.print(f"  - {f}")


# ── mcp function update / edit-test / activate / template ─────────

@func_app.command(name="update")
def func_update(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    code: Annotated[str, typer.Option("--code", help="새 코드 파일 경로")],
    test: Annotated[Optional[str], typer.Option("--test", help="새 테스트 코드 파일 경로 (미지정 시 기존 테스트 유지)")] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="테스트 실행 건너뜀")] = False,
):
    """함수 코드를 업데이트합니다 (새 버전으로 등록).

    기존 활성 버전의 테스트 코드를 새 버전에도 그대로 이어받습니다.
    --test 로 새 테스트 파일을 지정하면 교체됩니다.
    """
    from orchestrator import mcp_db_manager

    current = mcp_db_manager.get_active_function(name)
    if not current:
        console.print(f"[bold red]오류: '{name}' 함수를 찾을 수 없습니다. 'add'로 먼저 등록하세요.[/bold red]")
        raise typer.Exit(code=1)

    try:
        func_code = Path(code).read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[bold red]코드 파일 읽기 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    test_code = current.get("test_code", "")
    if test:
        try:
            test_code = Path(test).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold yellow]테스트 파일 읽기 실패 (기존 테스트 유지): {e}[/bold yellow]")

    result = mcp_db_manager.register_function(
        func_name=name,
        module_group=current["module_group"],
        code=func_code,
        test_code=test_code,
        run_tests=not no_tests and bool(test_code.strip()),
    )
    if result.get("activated"):
        console.print(f"[green]'{name}' 업데이트됨 v{result['version']} — 테스트: {result['test_status']}, 활성화됨[/green]")
    else:
        console.print(f"[yellow]'{name}' v{result['version']} 등록됨 — 테스트: {result['test_status']} (비활성, 이전 버전 유지)[/yellow]")
        if result.get("test_output"):
            console.print(result["test_output"])


@func_app.command(name="edit-test")
def func_edit_test(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    file: Annotated[str, typer.Option("--file", "-f", help="테스트 코드 파일 경로")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (기본: 활성 버전)")] = None,
    no_run: Annotated[bool, typer.Option("--no-run", help="저장만 하고 테스트 실행 안 함")] = False,
):
    """함수의 테스트 코드를 업데이트하고 테스트를 실행합니다.

    새 버전을 생성하지 않고 기존 버전의 test_code만 교체합니다.
    테스트 통과 시 해당 버전을 활성화합니다.

    테스트 코드 형식은 'mcp function template' 참조.
    """
    from orchestrator import mcp_db_manager

    try:
        test_code = Path(file).read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[bold red]테스트 파일 읽기 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    result = mcp_db_manager.update_function_test_code(
        func_name=name,
        test_code=test_code,
        version=version,
        run_tests=not no_run,
    )
    if "error" in result:
        console.print(f"[bold red]오류: {result['error']}[/bold red]")
        raise typer.Exit(code=1)

    if no_run:
        console.print(f"[green]테스트 코드 저장됨 (v{result['version']}, 실행 안 함)[/green]")
        return

    if result.get("test_status") == "passed":
        console.print(f"[green]테스트 통과 — v{result['version']} 활성화됨[/green]")
    else:
        console.print(f"[bold red]테스트 실패 (v{result['version']})[/bold red]")
        if result.get("test_output"):
            console.print(result["test_output"])


@func_app.command(name="activate")
def func_activate(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[int, typer.Option("--version", "-v", help="활성화할 버전 번호")],
):
    """특정 버전을 수동으로 활성화합니다 (롤백/롤포워드)."""
    from orchestrator import mcp_db_manager

    try:
        mcp_db_manager.activate_function(name, version)
        console.print(f"[green]'{name}' v{version} 활성화됨[/green]")
    except ValueError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@func_app.command(name="template")
def func_template(
    name: Annotated[Optional[str], typer.Argument(help="함수 이름 (지정 시 해당 함수 코드도 함께 출력)")] = None,
):
    """독립 실행형 테스트 코드 작성 가이드를 출력합니다.

    DB에 저장된 테스트 코드는 함수 코드와 합쳐 단일 .py 파일로 실행됩니다.
    따라서 기존 상대 임포트(from . import ...) 방식은 사용 불가합니다.
    """
    from orchestrator import mcp_db_manager
    from rich.syntax import Syntax

    guide = """# ─────────────────────────────────────────────────────────────
# MCP 함수 테스트 코드 형식 (독립 실행형)
# ─────────────────────────────────────────────────────────────
#
# 테스트 실행 시 생성되는 임시 파일 구조:
#
#   ┌── [preamble] ── mcp_module_contexts.preamble_code ──────┐
#   │  import os, logging, ...                                │
#   │  CONST = ...   # 모듈 레벨 상수                         │
#   └─────────────────────────────────────────────────────────┘
#   ┌── [함수 코드] ── mcp_functions.code ────────────────────┐
#   │  def your_func(...):                                    │
#   │      ...                                                │
#   └─────────────────────────────────────────────────────────┘
#   ┌── [테스트 코드] ── mcp_functions.test_code ─────────────┐
#   │  ← 여기에 작성 (아래 규칙 준수)                          │
#   └─────────────────────────────────────────────────────────┘
#
# 규칙:
#   1. 함수는 이미 정의되어 있으므로 직접 호출 (import 불필요)
#   2. preamble의 imports/상수도 바로 사용 가능
#   3. 전역 변수 패치:
#        monkeypatch.setattr(sys.modules[__name__], 'CONST', new_val)
#   4. pytest 내장 픽스처 사용 가능: tmp_path, monkeypatch, capsys ...
#   5. @pytest.fixture 정의도 test_code 안에 포함 가능
#   6. from . import ... 같은 상대 임포트는 사용 불가
#
# ─── 예시 1: 순수 함수 테스트 ────────────────────────────────
import pytest

class TestAdd:
    def test_basic(self):
        assert add(1, 2) == 3

    def test_negative(self):
        assert add(-1, -2) == -3

# ─── 예시 2: 전역 상수를 가진 함수 테스트 ────────────────────
import pytest
import sys

@pytest.fixture(autouse=True)
def patch_base(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], 'ALLOWED_BASE_PATH', tmp_path)

class TestCreateDirectory:
    def test_success(self, tmp_path):
        new_dir = tmp_path / "new_dir"
        assert create_directory(str(new_dir)) is True
        assert new_dir.is_dir()

    def test_path_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="보안"):
            create_directory("/etc/evil_dir")

# ─── 예시 3: 파일 I/O 함수 테스트 ───────────────────────────
import pytest

class TestReadFile:
    def test_reads_content(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        assert read_file(str(f)) == "hello world"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_file(str(tmp_path / "nope.txt"))
# ─────────────────────────────────────────────────────────────"""

    console.print(Syntax(guide, "python", theme="monokai", line_numbers=False))

    if name:
        func = mcp_db_manager.get_active_function(name)
        if func:
            console.print(f"\n[bold cyan]── '{name}' 현재 코드 (v{func['version']}) ──[/bold cyan]")
            console.print(Syntax(func["code"], "python", theme="monokai"))
            if func["test_code"]:
                console.print(f"\n[bold cyan]── '{name}' 현재 테스트 코드 ──[/bold cyan]")
                console.print(Syntax(func["test_code"], "python", theme="monokai"))
            else:
                console.print("\n[yellow]테스트 코드 없음 — 'mcp function edit-test'로 추가하세요.[/yellow]")
        else:
            console.print(f"[yellow]'{name}' 함수를 찾을 수 없습니다.[/yellow]")


# ── mcp stats ──────────────────────────────────────────────────────

@mcp_app.command(name="stats")
def mcp_stats(
    func: Annotated[Optional[str], typer.Option("--func", "-f", help="특정 함수 이름")] = None,
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 필터")] = None,
):
    """MCP 함수 실행 통계를 표시합니다."""
    from orchestrator import mcp_db_manager

    stats = mcp_db_manager.get_usage_stats(func_name=func, module_group=group)
    if stats["total_calls"] == 0:
        console.print("[yellow]실행 기록이 없습니다.[/yellow]")
        return

    console.print(f"[bold]전체 호출:[/bold] {stats['total_calls']}")
    console.print(f"[bold]성공률:[/bold] {stats['success_rate']:.1%}")
    console.print(f"[bold]평균 실행시간:[/bold] {stats['avg_duration_ms']:.1f}ms")

    if stats["by_function"]:
        table = Table("Function", "Calls", "Success Rate", "Avg ms")
        for fn, fstats in sorted(stats["by_function"].items()):
            table.add_row(
                fn,
                str(fstats["total_calls"]),
                f"{fstats['success_rate']:.1%}",
                f"{fstats['avg_duration_ms']:.1f}",
            )
        console.print(table)


# ── model 서브커맨드 ──────────────────────────────────────────────

@model_app.command(name="status")
def model_status():
    """현재 활성 프로바이더와 모델을 표시합니다."""
    from orchestrator.model_manager import load_config, get_active_model, list_providers

    config = load_config()
    provider, model = get_active_model(config)

    console.print(f"[bold]활성 프로바이더:[/bold] {provider}")
    console.print(f"[bold]활성 모델:[/bold] {model}")
    console.print()

    providers = list_providers(config)
    table = Table("Provider", "Enabled", "API Key", "Default Model")
    for p in providers:
        enabled = "[green]Yes[/green]" if p["enabled"] else "[red]No[/red]"
        has_key = (
            "[green]설정됨[/green]"
            if p["has_api_key"]
            else f"[red]미설정 ({p['api_key_env']})[/red]"
        )
        table.add_row(p["name"], enabled, has_key, p["default_model"] or "-")
    console.print(table)


@model_app.command(name="list")
def model_list(
    provider: Annotated[Optional[str], typer.Option("--provider", "-p", help="특정 프로바이더만 조회")] = None,
):
    """프로바이더별 사용 가능한 모델 목록을 조회합니다."""
    from orchestrator.model_manager import load_config, list_providers, fetch_models

    config = load_config()
    providers = list_providers(config)

    if provider:
        providers = [p for p in providers if p["name"] == provider]
        if not providers:
            console.print(f"[bold red]오류: 알 수 없는 프로바이더 '{provider}'[/bold red]")
            raise typer.Exit(code=1)

    for p in providers:
        console.print(f"\n[bold cyan]── {p['name'].upper()} ──[/bold cyan]")

        if not p["has_api_key"]:
            console.print(f"  [yellow]API 키 미설정 (환경변수: {p['api_key_env']})[/yellow]")
            continue

        try:
            models = asyncio.run(fetch_models(p["name"], config))
            if not models:
                console.print("  [yellow]사용 가능한 모델이 없습니다.[/yellow]")
                continue

            table = Table("ID", "Name", "Description")
            for m in models:
                desc = m.get("description", "")
                if len(desc) > 80:
                    desc = desc[:77] + "..."
                table.add_row(m["id"], m["name"], desc)
            console.print(table)

        except Exception as e:
            console.print(f"  [bold red]조회 실패: {e}[/bold red]")


@model_app.command(name="set")
def model_set(
    provider: Annotated[str, typer.Argument(help="프로바이더 이름 (gemini, claude, openai, grok, ollama)")],
    model: Annotated[Optional[str], typer.Argument(help="모델 ID (생략 시 목록에서 선택)")] = None,
):
    """활성 프로바이더와 모델을 변경합니다.

    모델 ID를 생략하면 API에서 목록을 조회하여 선택할 수 있습니다.
    """
    from orchestrator.model_manager import load_config, set_active_model, list_providers, fetch_models

    config = load_config()

    # 모델 ID가 없으면 API에서 목록 조회 후 선택
    if not model:
        providers = list_providers(config)
        pinfo = next((p for p in providers if p["name"] == provider), None)
        if pinfo is None:
            console.print(f"[bold red]오류: 알 수 없는 프로바이더 '{provider}'[/bold red]")
            raise typer.Exit(code=1)

        if not pinfo["has_api_key"]:
            console.print(f"[bold red]오류: API 키 미설정 (환경변수: {pinfo['api_key_env']})[/bold red]")
            raise typer.Exit(code=1)

        console.print(f"[cyan]{provider} 모델 목록을 조회합니다...[/cyan]")
        try:
            models = asyncio.run(fetch_models(provider, config))
        except Exception as e:
            console.print(f"[bold red]모델 목록 조회 실패: {e}[/bold red]")
            raise typer.Exit(code=1)

        if not models:
            console.print("[yellow]사용 가능한 모델이 없습니다.[/yellow]")
            raise typer.Exit(code=1)

        table = Table("#", "ID", "Name", "Description")
        for i, m in enumerate(models, 1):
            desc = m.get("description") or ""
            if len(desc) > 60:
                desc = desc[:57] + "..."
            table.add_row(str(i), m["id"], m["name"], desc)
        console.print(table)

        choice = typer.prompt(f"번호를 입력하세요 (1-{len(models)})")
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(models)):
                raise ValueError
        except ValueError:
            console.print("[bold red]오류: 유효하지 않은 번호입니다.[/bold red]")
            raise typer.Exit(code=1)

        model = models[idx]["id"]

    try:
        set_active_model(provider, model, config)
        console.print(f"[green]활성 모델이 변경되었습니다: {provider} / {model}[/green]")
    except ValueError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


# ── prompt 서브커맨드 ─────────────────────────────────────────────

@prompt_app.command(name="list")
def prompt_list():
    """등록된 시스템 프롬프트 목록 표시."""
    from orchestrator import agent_config_manager as acm

    prompts = acm.list_system_prompts()
    if not prompts:
        console.print("[yellow]등록된 시스템 프롬프트가 없습니다.[/yellow]")
        return
    table = Table("Name", "Description", "Default", "Updated")
    for p in prompts:
        default = "[green]★[/green]" if p["is_default"] else ""
        table.add_row(p["name"], p.get("description", ""), default, p["updated_at"][:19])
    console.print(table)


@prompt_app.command(name="show")
def prompt_show(
    name: Annotated[str, typer.Argument(help="프롬프트 이름")],
):
    """시스템 프롬프트 내용 출력."""
    from orchestrator import agent_config_manager as acm

    p = acm.get_system_prompt(name)
    if not p:
        console.print(f"[bold red]오류: 프롬프트 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]이름:[/bold] {p['name']}")
    console.print(f"[bold]설명:[/bold] {p.get('description', '')}")
    console.print(f"[bold]기본값:[/bold] {'예' if p['is_default'] else '아니오'}")
    console.print(f"[bold]내용:[/bold]\n{p['content']}")


@prompt_app.command(name="create")
def prompt_create(
    name: Annotated[str, typer.Argument(help="프롬프트 이름")],
    content: Annotated[str, typer.Option("--content", "-c", help="프롬프트 내용")] = "",
    desc: Annotated[str, typer.Option("--desc", "-d", help="설명")] = "",
    is_default: Annotated[bool, typer.Option("--default", help="기본값으로 설정")] = False,
):
    """새 시스템 프롬프트 생성."""
    from orchestrator import agent_config_manager as acm

    if not content:
        content = typer.prompt("프롬프트 내용을 입력하세요")
    try:
        rid = acm.create_system_prompt(name, content, desc, is_default)
        console.print(f"[green]프롬프트 '{name}' 생성됨 (ID: {rid})[/green]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@prompt_app.command(name="edit")
def prompt_edit(
    name: Annotated[str, typer.Argument(help="프롬프트 이름")],
    content: Annotated[Optional[str], typer.Option("--content", "-c", help="새 내용")] = None,
    desc: Annotated[Optional[str], typer.Option("--desc", "-d", help="새 설명")] = None,
):
    """시스템 프롬프트 수정."""
    from orchestrator import agent_config_manager as acm

    result = acm.update_system_prompt(name, content=content, description=desc)
    if not result:
        console.print(f"[bold red]오류: 프롬프트 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[green]프롬프트 '{name}' 수정됨[/green]")


@prompt_app.command(name="delete")
def prompt_delete(
    name: Annotated[str, typer.Argument(help="프롬프트 이름")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="확인 없이 삭제")] = False,
):
    """시스템 프롬프트 삭제."""
    from orchestrator import agent_config_manager as acm

    if not yes:
        typer.confirm(f"'{name}' 프롬프트를 삭제하시겠습니까?", abort=True)
    if acm.delete_system_prompt(name):
        console.print(f"[green]프롬프트 '{name}' 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 프롬프트 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@prompt_app.command(name="import")
def prompt_import(
    directory: Annotated[str, typer.Option("--dir", "-d", help="프롬프트 파일 디렉토리")] = "system_prompts",
):
    """system_prompts/*.txt 파일을 DB로 임포트합니다."""
    from orchestrator import agent_config_manager as acm

    count = acm.migrate_prompts_from_files(directory)
    console.print(f"[green]{count}개 프롬프트 임포트됨[/green]")


# ── skill 서브커맨드 ──────────────────────────────────────────────

@skill_app.command(name="list")
def skill_list(
    all_skills: Annotated[bool, typer.Option("--all", "-a", help="비활성 스킬도 포함")] = False,
):
    """등록된 스킬 목록 표시."""
    from orchestrator import agent_config_manager as acm

    skills = acm.list_skills(active_only=not all_skills)
    if not skills:
        console.print("[yellow]등록된 스킬이 없습니다. 'skill sync'를 실행하세요.[/yellow]")
        return
    table = Table("Name", "Source", "Active", "Description")
    for s in skills:
        active = "[green]Yes[/green]" if s["is_active"] else "[red]No[/red]"
        table.add_row(s["name"], s["source"], active, s.get("description", "")[:60])
    console.print(table)


@skill_app.command(name="sync")
def skill_sync():
    """로컬 모듈에서 스킬을 동기화합니다."""
    from orchestrator import agent_config_manager as acm

    count = acm.sync_skills_from_registry()
    console.print(f"[green]스킬 동기화 완료: {count}개 신규 추가됨[/green]")


@skill_app.command(name="enable")
def skill_enable(
    name: Annotated[str, typer.Argument(help="스킬 이름")],
):
    """스킬 활성화."""
    from orchestrator import agent_config_manager as acm

    if acm.set_skill_active(name, True):
        console.print(f"[green]스킬 '{name}' 활성화됨[/green]")
    else:
        console.print(f"[bold red]오류: 스킬 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@skill_app.command(name="disable")
def skill_disable(
    name: Annotated[str, typer.Argument(help="스킬 이름")],
):
    """스킬 비활성화."""
    from orchestrator import agent_config_manager as acm

    if acm.set_skill_active(name, False):
        console.print(f"[yellow]스킬 '{name}' 비활성화됨[/yellow]")
    else:
        console.print(f"[bold red]오류: 스킬 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@skill_app.command(name="show")
def skill_show(
    name: Annotated[str, typer.Argument(help="스킬 이름")],
):
    """스킬 상세 정보 출력."""
    from orchestrator import agent_config_manager as acm

    s = acm.get_skill(name)
    if not s:
        console.print(f"[bold red]오류: 스킬 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]이름:[/bold] {s['name']}")
    console.print(f"[bold]소스:[/bold] {s['source']}")
    console.print(f"[bold]활성:[/bold] {'예' if s['is_active'] else '아니오'}")
    console.print(f"[bold]설명:[/bold] {s.get('description', '')}")


@skill_app.command(name="status")
def skill_status():
    """현재 로드된 도구(로컬 + MCP + 온디맨드) 실제 상태 출력."""
    import httpx as _httpx
    try:
        resp = _httpx.get(f"{ORCHESTRATOR_URL}/api/v1/tools/status", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]서버 연결 실패: {e}[/bold red]")
        console.print("[dim]서버가 실행 중인지 확인하세요: python main.py server[/dim]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan]도구 로드 상태[/bold cyan]  ({data.get('summary', '')})")

    local = data.get("local", {})
    loaded = local.get("loaded", [])
    missing = local.get("modules_missing_file", [])
    console.print(f"\n[bold]로컬 도구 ({len(loaded)}개 로드됨)[/bold]")
    for t in sorted(loaded):
        console.print(f"  ✅ {t}")
    if missing:
        console.print(f"\n[bold yellow]파일 없는 모듈 ({len(missing)}개)[/bold yellow]")
        for m in missing:
            console.print(f"  ⚠️  {m}")

    mcp = data.get("mcp", {})
    connected = mcp.get("connected", {})
    on_demand = mcp.get("on_demand", [])
    if connected:
        console.print(f"\n[bold]MCP 연결된 도구[/bold]")
        for server, tools in connected.items():
            console.print(f"  [cyan]{server}[/cyan] ({len(tools)}개)")
            for t in sorted(tools):
                console.print(f"    ✅ {t}")
    if on_demand:
        console.print(f"\n[bold]온디맨드 서버 (미연결)[/bold]")
        for s in on_demand:
            console.print(f"  ⏳ {s}")

    console.print(f"\n[bold green]총 {data.get('total', 0)}개 도구 사용 가능[/bold green]")


# ── macro 서브커맨드 ──────────────────────────────────────────────

@macro_app.command(name="list")
def macro_list():
    """등록된 스킬 매크로 목록 표시."""
    from orchestrator import agent_config_manager as acm

    macros = acm.list_macros()
    if not macros:
        console.print("[yellow]등록된 매크로가 없습니다.[/yellow]")
        return
    table = Table("Name", "Variables", "Description")
    for m in macros:
        table.add_row(m["name"], ", ".join(m["variables"]), m.get("description", ""))
    console.print(table)


@macro_app.command(name="show")
def macro_show(
    name: Annotated[str, typer.Argument(help="매크로 이름")],
):
    """매크로 상세 정보 출력."""
    from orchestrator import agent_config_manager as acm

    m = acm.get_macro(name)
    if not m:
        console.print(f"[bold red]오류: 매크로 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]이름:[/bold] {m['name']}")
    console.print(f"[bold]변수:[/bold] {', '.join(m['variables'])}")
    console.print(f"[bold]설명:[/bold] {m.get('description', '')}")
    console.print(f"[bold]템플릿:[/bold]\n{m['template']}")


@macro_app.command(name="create")
def macro_create(
    name: Annotated[str, typer.Argument(help="매크로 이름")],
    template: Annotated[str, typer.Option("--template", "-t", help="매크로 템플릿 ({{변수}} 사용)")] = "",
    desc: Annotated[str, typer.Option("--desc", "-d", help="설명")] = "",
):
    """새 스킬 매크로 생성."""
    from orchestrator import agent_config_manager as acm

    if not template:
        template = typer.prompt("매크로 템플릿을 입력하세요 ({{변수}} 사용)")
    try:
        rid = acm.create_macro(name, template, desc)
        console.print(f"[green]매크로 '{name}' 생성됨 (ID: {rid})[/green]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@macro_app.command(name="edit")
def macro_edit(
    name: Annotated[str, typer.Argument(help="매크로 이름")],
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="새 템플릿")] = None,
    desc: Annotated[Optional[str], typer.Option("--desc", "-d", help="새 설명")] = None,
):
    """매크로 수정."""
    from orchestrator import agent_config_manager as acm

    result = acm.update_macro(name, template=template, description=desc)
    if not result:
        console.print(f"[bold red]오류: 매크로 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[green]매크로 '{name}' 수정됨[/green]")


@macro_app.command(name="delete")
def macro_delete(
    name: Annotated[str, typer.Argument(help="매크로 이름")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="확인 없이 삭제")] = False,
):
    """매크로 삭제."""
    from orchestrator import agent_config_manager as acm

    if not yes:
        typer.confirm(f"'{name}' 매크로를 삭제하시겠습니까?", abort=True)
    if acm.delete_macro(name):
        console.print(f"[green]매크로 '{name}' 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 매크로 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@macro_app.command(name="render")
def macro_render(
    name: Annotated[str, typer.Argument(help="매크로 이름")],
    var: Annotated[Optional[List[str]], typer.Option("--var", help="변수 바인딩 (KEY=VALUE 형식)")] = None,
):
    """매크로 렌더링 (변수 치환)."""
    from orchestrator import agent_config_manager as acm

    bindings = {}
    if var:
        for v in var:
            if "=" not in v:
                console.print(f"[bold red]오류: 변수 형식이 잘못됨 (KEY=VALUE 필요): {v}[/bold red]")
                raise typer.Exit(code=1)
            k, _, val = v.partition("=")
            bindings[k.strip()] = val.strip()
    try:
        result = acm.render_macro(name, bindings)
        console.print(f"[bold]렌더링 결과:[/bold]\n{result}")
    except KeyError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


# ── workflow 서브커맨드 ───────────────────────────────────────────

@workflow_app.command(name="list")
def workflow_list():
    """등록된 워크플로우 목록 표시."""
    from orchestrator import agent_config_manager as acm

    wfs = acm.list_workflows()
    if not wfs:
        console.print("[yellow]등록된 워크플로우가 없습니다.[/yellow]")
        return
    table = Table("Name", "Steps", "Description")
    for w in wfs:
        table.add_row(w["name"], str(len(w["steps"])), w.get("description", ""))
    console.print(table)


@workflow_app.command(name="show")
def workflow_show(
    name: Annotated[str, typer.Argument(help="워크플로우 이름")],
):
    """워크플로우 상세 정보 출력."""
    from orchestrator import agent_config_manager as acm

    wf = acm.get_workflow(name)
    if not wf:
        console.print(f"[bold red]오류: 워크플로우 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]이름:[/bold] {wf['name']}")
    console.print(f"[bold]설명:[/bold] {wf.get('description', '')}")
    console.print(f"[bold]스텝 ({len(wf['steps'])}개):[/bold]")
    for step in wf["steps"]:
        console.print(f"  {step.get('order', '?')}. [{step.get('type', '?')}] {step.get('ref_name', '')} — {step.get('description', '')}")


@workflow_app.command(name="create")
def workflow_create(
    name: Annotated[str, typer.Argument(help="워크플로우 이름")],
    desc: Annotated[str, typer.Option("--desc", "-d", help="설명")] = "",
):
    """새 빈 워크플로우 생성."""
    from orchestrator import agent_config_manager as acm

    try:
        rid = acm.create_workflow(name, [], desc)
        console.print(f"[green]워크플로우 '{name}' 생성됨 (ID: {rid})[/green]")
        console.print("[dim]'workflow add-step'으로 스텝을 추가하세요.[/dim]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@workflow_app.command(name="add-step")
def workflow_add_step(
    name: Annotated[str, typer.Argument(help="워크플로우 이름")],
    step_type: Annotated[str, typer.Option("--type", help="스텝 타입 (skill|macro)")] = "skill",
    ref: Annotated[str, typer.Option("--ref", help="스킬 또는 매크로 이름")] = "",
    desc: Annotated[str, typer.Option("--desc", "-d", help="스텝 설명")] = "",
    args: Annotated[str, typer.Option("--args", help="JSON 형식 인자")] = "{}",
):
    """워크플로우에 스텝 추가."""
    from orchestrator import agent_config_manager as acm

    wf = acm.get_workflow(name)
    if not wf:
        console.print(f"[bold red]오류: 워크플로우 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    try:
        parsed_args = json.loads(args)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]오류: --args JSON 파싱 실패: {e}[/bold red]")
        raise typer.Exit(code=1)
    steps = wf["steps"]
    new_step = {
        "order": len(steps) + 1,
        "type": step_type,
        "ref_name": ref,
        "args": parsed_args,
        "description": desc,
    }
    steps.append(new_step)
    acm.update_workflow(name, steps=steps)
    console.print(f"[green]스텝 추가됨 (총 {len(steps)}개)[/green]")


@workflow_app.command(name="delete")
def workflow_delete(
    name: Annotated[str, typer.Argument(help="워크플로우 이름")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="확인 없이 삭제")] = False,
):
    """워크플로우 삭제."""
    from orchestrator import agent_config_manager as acm

    if not yes:
        typer.confirm(f"'{name}' 워크플로우를 삭제하시겠습니까?", abort=True)
    if acm.delete_workflow(name):
        console.print(f"[green]워크플로우 '{name}' 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 워크플로우 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


# ── persona 서브커맨드 ────────────────────────────────────────────

@persona_app.command(name="list")
def persona_list():
    """등록된 페르소나 목록 표시."""
    from orchestrator import agent_config_manager as acm

    personas = acm.list_personas()
    if not personas:
        console.print("[yellow]등록된 페르소나가 없습니다.[/yellow]")
        return
    table = Table("Name", "Display Name", "Keywords", "Skills", "Default")
    for p in personas:
        default = "[green]★[/green]" if p["is_default"] else ""
        kws = ", ".join(p.get("keywords", [])[:5])
        skills = str(len(p.get("allowed_skills", []))) + "개" if p.get("allowed_skills") else "전체"
        table.add_row(p["name"], p.get("display_name", ""), kws, skills, default)
    console.print(table)


@persona_app.command(name="show")
def persona_show(
    name: Annotated[str, typer.Argument(help="페르소나 이름")],
):
    """페르소나 상세 정보 출력."""
    from orchestrator import agent_config_manager as acm

    p = acm.get_persona(name)
    if not p:
        console.print(f"[bold red]오류: 페르소나 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]이름:[/bold] {p['name']}")
    console.print(f"[bold]표시명:[/bold] {p.get('display_name', '')}")
    console.print(f"[bold]설명:[/bold] {p.get('description', '')}")
    console.print(f"[bold]기본값:[/bold] {'예' if p['is_default'] else '아니오'}")
    console.print(f"[bold]키워드:[/bold] {', '.join(p.get('keywords', []))}")
    skills = p.get("allowed_skills", [])
    console.print(f"[bold]허용 스킬:[/bold] {', '.join(skills) if skills else '(전체 허용)'}")
    console.print(f"[bold]시스템 프롬프트:[/bold]\n{p['system_prompt']}")


@persona_app.command(name="create")
def persona_create(
    name: Annotated[str, typer.Argument(help="페르소나 이름")],
    prompt_name: Annotated[Optional[str], typer.Option("--prompt-name", "-p", help="시스템 프롬프트 이름 (DB에서 조회)")] = None,
    prompt_content: Annotated[Optional[str], typer.Option("--prompt-content", help="직접 입력할 시스템 프롬프트 내용")] = None,
    keywords: Annotated[Optional[List[str]], typer.Option("--keywords", "-k", help="자동 감지 키워드 (반복 가능)")] = None,
    skills: Annotated[Optional[List[str]], typer.Option("--skills", "-s", help="허용할 스킬 이름 (반복 가능)")] = None,
    desc: Annotated[str, typer.Option("--desc", "-d", help="설명")] = "",
    is_default: Annotated[bool, typer.Option("--default", help="기본 페르소나로 설정")] = False,
):
    """새 페르소나 생성."""
    from orchestrator import agent_config_manager as acm

    system_prompt = ""
    system_prompt_ref = None

    if prompt_name:
        sp = acm.get_system_prompt(prompt_name)
        if not sp:
            console.print(f"[bold red]오류: 시스템 프롬프트 '{prompt_name}'을 찾을 수 없습니다.[/bold red]")
            raise typer.Exit(code=1)
        system_prompt = sp["content"]
        system_prompt_ref = prompt_name
    elif prompt_content:
        system_prompt = prompt_content
    else:
        system_prompt = typer.prompt("시스템 프롬프트 내용을 입력하세요")

    try:
        rid = acm.create_persona(
            name=name,
            system_prompt=system_prompt,
            allowed_skills=skills or [],
            keywords=keywords or [],
            description=desc,
            system_prompt_ref=system_prompt_ref,
            is_default=is_default,
        )
        console.print(f"[green]페르소나 '{name}' 생성됨 (ID: {rid})[/green]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@persona_app.command(name="edit")
def persona_edit(
    name: Annotated[str, typer.Argument(help="페르소나 이름")],
    prompt_name: Annotated[Optional[str], typer.Option("--prompt-name", "-p", help="새 시스템 프롬프트 이름")] = None,
    prompt_content: Annotated[Optional[str], typer.Option("--prompt-content", help="새 시스템 프롬프트 내용")] = None,
    keywords: Annotated[Optional[List[str]], typer.Option("--keywords", "-k", help="새 키워드")] = None,
    skills: Annotated[Optional[List[str]], typer.Option("--skills", "-s", help="새 허용 스킬")] = None,
    desc: Annotated[Optional[str], typer.Option("--desc", "-d", help="새 설명")] = None,
):
    """페르소나 수정."""
    from orchestrator import agent_config_manager as acm

    system_prompt = None
    system_prompt_ref = None

    if prompt_name:
        sp = acm.get_system_prompt(prompt_name)
        if not sp:
            console.print(f"[bold red]오류: 시스템 프롬프트 '{prompt_name}'을 찾을 수 없습니다.[/bold red]")
            raise typer.Exit(code=1)
        system_prompt = sp["content"]
        system_prompt_ref = prompt_name
    elif prompt_content:
        system_prompt = prompt_content

    result = acm.update_persona(
        name,
        system_prompt=system_prompt,
        allowed_skills=skills,
        keywords=keywords,
        description=desc,
        system_prompt_ref=system_prompt_ref,
    )
    if not result:
        console.print(f"[bold red]오류: 페르소나 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[green]페르소나 '{name}' 수정됨[/green]")


@persona_app.command(name="delete")
def persona_delete(
    name: Annotated[str, typer.Argument(help="페르소나 이름")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="확인 없이 삭제")] = False,
):
    """페르소나 삭제."""
    from orchestrator import agent_config_manager as acm

    if not yes:
        typer.confirm(f"'{name}' 페르소나를 삭제하시겠습니까?", abort=True)
    if acm.delete_persona(name):
        console.print(f"[green]페르소나 '{name}' 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 페르소나 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@persona_app.command(name="set-default")
def persona_set_default(
    name: Annotated[str, typer.Argument(help="페르소나 이름")],
):
    """페르소나를 기본값으로 설정."""
    from orchestrator import agent_config_manager as acm

    result = acm.update_persona(name, is_default=True)
    if not result:
        console.print(f"[bold red]오류: 페르소나 '{name}'을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[green]페르소나 '{name}'이 기본값으로 설정됨[/green]")


@persona_app.command(name="detect")
def persona_detect(
    query: Annotated[str, typer.Argument(help="자동 감지 시뮬레이션에 사용할 쿼리")],
):
    """쿼리에 대해 자동 감지되는 페르소나를 출력합니다."""
    from orchestrator import agent_config_manager as acm

    persona = acm.get_effective_persona(query=query)
    if persona:
        console.print(f"[bold green]감지된 페르소나: {persona['name']}[/bold green]")
        console.print(f"  표시명: {persona.get('display_name', '')}")
        console.print(f"  키워드: {', '.join(persona.get('keywords', []))}")
    else:
        console.print("[yellow]매치되는 페르소나가 없습니다. 기본 시스템 동작을 사용합니다.[/yellow]")


# ── issue 명령어 ──────────────────────────────────────────────────

@issue_app.command("list")
def issue_list(
    status: Optional[str] = typer.Option(None, "--status", help="open|in_progress|resolved|ignored"),
    source: Optional[str] = typer.Option(None, "--source", help="api_server|agent|tool|cli"),
    limit: int = typer.Option(50, "--limit", help="최대 표시 개수"),
):
    """이슈 목록을 출력합니다."""
    from orchestrator import issue_tracker
    try:
        issues = issue_tracker.list_issues(status=status, source=source, limit=limit)
        if not issues:
            console.print("[yellow]조건에 맞는 이슈가 없습니다.[/yellow]")
            return
        table = Table(title="이슈 목록", show_lines=True)
        table.add_column("ID", style="bold", width=5)
        table.add_column("Severity", width=10)
        table.add_column("Status", width=12)
        table.add_column("Source", width=12)
        table.add_column("Title", width=60)
        table.add_column("Created At", width=19)
        severity_styles = {"critical": "bold red", "error": "red", "warning": "yellow"}
        for issue in issues:
            sev = issue["severity"]
            style = severity_styles.get(sev, "")
            table.add_row(
                str(issue["id"]),
                f"[{style}]{sev}[/{style}]" if style else sev,
                issue["status"],
                issue["source"],
                issue["title"][:60],
                (issue["created_at"] or "")[:19],
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]이슈 목록 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("show")
def issue_show(issue_id: int = typer.Argument(..., help="이슈 ID")):
    """이슈 상세 정보를 출력합니다."""
    from orchestrator import issue_tracker
    try:
        issue = issue_tracker.get_issue(issue_id)
        if issue is None:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]ID:[/bold] {issue['id']}")
        console.print(f"[bold]Title:[/bold] {issue['title']}")
        console.print(f"[bold]Error Type:[/bold] {issue['error_type']}")
        console.print(f"[bold]Error Message:[/bold] {issue['error_message']}")
        console.print(f"[bold]Source:[/bold] {issue['source']}")
        console.print(f"[bold]Severity:[/bold] {issue['severity']}")
        console.print(f"[bold]Status:[/bold] {issue['status']}")
        console.print(f"[bold]Context:[/bold] {issue['context']}")
        console.print(f"[bold]Created At:[/bold] {issue['created_at']}")
        console.print(f"[bold]Resolved At:[/bold] {issue['resolved_at'] or '-'}")
        console.print(f"[bold]Resolution Note:[/bold] {issue['resolution_note'] or '-'}")
        if issue["traceback"]:
            console.print(f"[bold]Traceback:[/bold]")
            console.print(f"[dim]{issue['traceback']}[/dim]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("resolve")
def issue_resolve(
    issue_id: int = typer.Argument(..., help="이슈 ID"),
    note: str = typer.Option("", "--note", help="해결 메모"),
):
    """이슈를 resolved 상태로 변경합니다."""
    from orchestrator import issue_tracker
    try:
        ok = issue_tracker.update_status(issue_id, "resolved", resolution_note=note)
        if ok:
            console.print(f"[green]이슈 #{issue_id}가 resolved 처리되었습니다.[/green]")
        else:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 resolve 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("ignore")
def issue_ignore(issue_id: int = typer.Argument(..., help="이슈 ID")):
    """이슈를 ignored 상태로 변경합니다."""
    from orchestrator import issue_tracker
    try:
        ok = issue_tracker.update_status(issue_id, "ignored")
        if ok:
            console.print(f"[yellow]이슈 #{issue_id}가 ignored 처리되었습니다.[/yellow]")
        else:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 ignore 실패: {e}[/red]")
        raise typer.Exit(1)


# ── test 명령어 ───────────────────────────────────────────────────

@test_app.command("import")
def test_import(file_path: str = typer.Argument(..., help="임포트할 테스트 파일 경로")):
    """단일 테스트 파일을 DB에 저장합니다."""
    from orchestrator import test_registry
    try:
        result = test_registry.import_test_file(file_path)
        action = "신규 저장" if result["created"] else "갱신"
        console.print(f"[green]{action}:[/green] {result['name']} ({result['file_path']})")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]임포트 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("import-all")
def test_import_all():
    """orchestrator/ 디렉토리의 test_*.py 파일을 모두 DB에 저장합니다."""
    from orchestrator import test_registry
    try:
        results = test_registry.import_all()
        if not results:
            console.print("[yellow]임포트할 테스트 파일이 없습니다.[/yellow]")
            return
        for result in results:
            if "error" in result:
                console.print(f"[red]오류:[/red] {result['name']} — {result['error']}")
            else:
                action = "신규" if result["created"] else "갱신"
                console.print(f"[green]{action}:[/green] {result['name']}")
    except Exception as e:
        console.print(f"[red]일괄 임포트 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("list")
def test_list():
    """DB에 저장된 테스트 목록을 표시합니다."""
    from orchestrator import test_registry
    try:
        tests = test_registry.list_tests()
        if not tests:
            console.print("[yellow]저장된 테스트가 없습니다.[/yellow]")
            return
        table = Table(title="테스트 목록", show_lines=True)
        table.add_column("ID", style="bold", width=5)
        table.add_column("Name", width=40)
        table.add_column("Status", width=10)
        table.add_column("Lines", width=7)
        table.add_column("Updated At", width=19)
        status_styles = {"passed": "green", "failed": "red", "untested": "yellow"}
        for t in tests:
            st = t["status"]
            style = status_styles.get(st, "")
            lines = str(len(t["code"].splitlines()))
            table.add_row(
                str(t["id"]),
                t["name"],
                f"[{style}]{st}[/{style}]" if style else st,
                lines,
                (t["updated_at"] or "")[:19],
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]목록 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("show")
def test_show(name: str = typer.Argument(..., help="테스트 이름 (파일명 stem)")):
    """저장된 테스트 코드를 출력합니다."""
    from orchestrator import test_registry
    try:
        test = test_registry.get_test(name)
        if test is None:
            console.print(f"[red]테스트 '{name}'를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]Name:[/bold] {test['name']}")
        console.print(f"[bold]File:[/bold] {test['file_path']}")
        console.print(f"[bold]Status:[/bold] {test['status']}")
        if test["last_output"]:
            console.print(f"[bold]Last Output:[/bold]")
            console.print(f"[dim]{test['last_output'][:500]}[/dim]")
        console.print(f"[bold]Code:[/bold]")
        console.print(f"[dim]{test['code']}[/dim]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]테스트 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("run")
def test_run(name: str = typer.Argument(..., help="실행할 테스트 이름")):
    """특정 테스트를 실행합니다."""
    from orchestrator import test_registry
    try:
        console.print(f"[cyan]실행 중: {name}...[/cyan]")
        result = test_registry.run_test(name)
        if "error" in result:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1)
        if result["status"] == "passed":
            console.print(f"[green]통과: {result['name']}[/green]")
        else:
            console.print(f"[red]실패: {result['name']}[/red]")
        console.print(result["output"])
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]테스트 실행 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("run-all")
def test_run_all():
    """저장된 모든 테스트를 실행하고 요약을 출력합니다."""
    from orchestrator import test_registry
    try:
        results = test_registry.run_all()
        if not results:
            console.print("[yellow]실행할 테스트가 없습니다.[/yellow]")
            return
        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") == "failed"]
        table = Table(title="전체 테스트 실행 결과", show_lines=True)
        table.add_column("Name", width=40)
        table.add_column("Status", width=10)
        for r in results:
            st = r.get("status", "error")
            style = "green" if st == "passed" else "red"
            table.add_row(r.get("name", "?"), f"[{style}]{st}[/{style}]")
        console.print(table)
        console.print(f"\n[green]통과: {len(passed)}[/green]  [red]실패: {len(failed)}[/red]")
    except Exception as e:
        console.print(f"[red]전체 실행 실패: {e}[/red]")
        raise typer.Exit(1)


# ── template 서브커맨드 ───────────────────────────────────────────────────────

@template_app.command("list")
def template_list(
    active_only: bool = typer.Option(False, "--active", "-a", help="활성 템플릿만 표시"),
    limit: int = typer.Option(30, "--limit", "-n", help="최대 출력 수"),
) -> None:
    """실행 템플릿 목록을 조회합니다."""
    from orchestrator.pipeline_db import list_templates, init_db
    init_db()
    templates = list_templates(active_only=active_only, limit=limit)
    if not templates:
        console.print("[yellow]템플릿이 없습니다.[/yellow]")
        return
    table = Table(title=f"실행 템플릿 목록 ({len(templates)}개)", show_lines=True)
    table.add_column("ID", width=5)
    table.add_column("이름", width=35)
    table.add_column("성공", width=6, justify="right")
    table.add_column("실패", width=6, justify="right")
    table.add_column("활성", width=5, justify="center")
    table.add_column("최근 사용", width=18)
    for t in templates:
        active_mark = "[green]✓[/green]" if t.get("is_active") else "[red]✗[/red]"
        table.add_row(
            str(t["id"]),
            t.get("name", "")[:34],
            str(t.get("success_count", 0)),
            str(t.get("fail_count", 0)),
            active_mark,
            (t.get("last_used_at") or "")[:16],
        )
    console.print(table)


@template_app.command("show")
def template_show(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿 상세 정보를 출력합니다."""
    import json as _json
    from orchestrator.pipeline_db import get_template, init_db
    init_db()
    t = get_template(template_id)
    if not t:
        console.print(f"[red]템플릿 {template_id}를 찾을 수 없습니다.[/red]")
        raise typer.Exit(1)
    console.print(f"\n[bold cyan]템플릿 #{t['id']}[/bold cyan]: {t['name']}")
    console.print(f"  설명   : {t.get('description', '')}")
    console.print(f"  키워드 : {', '.join(t.get('keywords', []))}")
    console.print(f"  성공/실패: {t.get('success_count', 0)} / {t.get('fail_count', 0)}")
    console.print(f"  활성   : {'예' if t.get('is_active') else '아니오'}")
    console.print(f"  최근 사용: {t.get('last_used_at', '-')}")
    console.print("\n[bold]실행 그룹:[/bold]")
    console.print(_json.dumps(t.get("execution_group", {}), ensure_ascii=False, indent=2))


@template_app.command("stats")
def template_stats() -> None:
    """템플릿 통계를 출력합니다."""
    from orchestrator.pipeline_db import get_template_stats, init_db
    init_db()
    s = get_template_stats()
    console.print("\n[bold cyan]── 실행 템플릿 통계 ──[/bold cyan]")
    console.print(f"  전체 템플릿  : {s['total_templates']}개")
    console.print(f"  활성         : {s['active_templates']}개")
    console.print(f"  비활성       : {s['disabled_templates']}개")
    console.print(f"  총 성공 실행 : {s['total_success_executions']}회")
    console.print(f"  총 실패 실행 : {s['total_fail_executions']}회")
    console.print(f"  성공률       : {s['success_rate']*100:.1f}%")
    console.print(f"  계획 캐시 항목: {s['plan_cache_entries']}개")
    console.print(f"  계획 캐시 히트: {s['plan_cache_hits']}회")


@template_app.command("disable")
def template_disable(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿을 비활성화합니다."""
    from orchestrator.pipeline_db import disable_template, init_db
    init_db()
    disable_template(template_id)
    console.print(f"[yellow]템플릿 {template_id} 비활성화됨.[/yellow]")


@template_app.command("enable")
def template_enable(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿을 활성화합니다."""
    from orchestrator.pipeline_db import enable_template, init_db
    init_db()
    enable_template(template_id)
    console.print(f"[green]템플릿 {template_id} 활성화됨.[/green]")


@template_app.command("delete")
def template_delete(
    template_id: int = typer.Argument(..., help="템플릿 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 없이 삭제"),
) -> None:
    """템플릿을 삭제합니다."""
    from orchestrator.pipeline_db import delete_template, init_db
    init_db()
    if not yes:
        confirm = typer.confirm(f"템플릿 {template_id}를 삭제하시겠습니까?")
        if not confirm:
            console.print("[yellow]취소됨.[/yellow]")
            return
    delete_template(template_id)
    console.print(f"[red]템플릿 {template_id} 삭제됨.[/red]")


# ── gap 서브커맨드 ────────────────────────────────────────────────────────────

@gap_app.command("report")
def gap_report(limit: int = typer.Option(20, "--limit", "-n", help="최대 출력 수")) -> None:
    """도구 부재 이력을 조회합니다."""
    from orchestrator.tool_discoverer import get_gap_report
    from orchestrator.pipeline_db import init_db
    init_db()
    rows = get_gap_report(limit=limit)
    if not rows:
        console.print("[yellow]도구 부재 이력이 없습니다.[/yellow]")
        return
    table = Table(title=f"도구 부재 이력 (최근 {limit}건)", show_lines=True)
    table.add_column("도구", width=30)
    table.add_column("해결 방법", width=18)
    table.add_column("MCP 서버", width=25)
    table.add_column("구현 ID", width=8)
    table.add_column("시각", width=18)
    for r in rows:
        table.add_row(
            r.get("required_tool", ""),
            r.get("resolution_type", ""),
            r.get("mcp_server_name", "-"),
            str(r.get("func_id") or "-"),
            (r.get("created_at") or "")[:16],
        )
    console.print(table)


@gap_app.command("discover")
def gap_discover(
    tool: str = typer.Argument(..., help="발견할 도구 이름"),
    context: str = typer.Option("", "--context", "-c", help="도구 용도 설명"),
) -> None:
    """특정 도구를 MCP 탐색 → Python 자동 구현 순으로 해결합니다.

    사용자 확인 후 진행합니다.
    """
    import asyncio
    from orchestrator.tool_discoverer import discover_and_resolve
    from orchestrator.pipeline_db import init_db
    init_db()
    console.print(f"\n[bold]도구 발견 시도:[/bold] {tool}")
    console.print(f"  컨텍스트: {context or '(없음)'}")
    confirm = typer.confirm("진행하시겠습니까?")
    if not confirm:
        console.print("[yellow]취소됨.[/yellow]")
        return
    results = asyncio.run(discover_and_resolve([tool], context=context))
    r = results.get(tool, {})
    status = r.get("status", "failed")
    if status == "found":
        console.print(f"[green]이미 등록된 도구 발견: {r.get('resolved_name')}[/green]")
    elif status == "npm_found":
        console.print(f"[cyan]npm MCP 서버 발견: {r.get('npm_package')}[/cyan]")
        console.print(f"  설명: {r.get('description', '')}")
        console.print("  → [dim]python main.py mcp add[/dim] 명령으로 서버를 추가하세요.")
    elif status == "python_impl":
        console.print(f"[green]Python 구현 생성 완료: func_id={r.get('func_id')}[/green]")
        console.print("  → [dim]python main.py mcp function list[/dim] 에서 검토 후 활성화하세요.")
    else:
        console.print(f"[red]해결 실패: {tool}[/red]")


@provider_app.command(name="status")
def provider_status():
    """LLM 프로바이더 Circuit Breaker 상태 출력 (차단 중인 프로바이더 및 재시도 시각)."""
    import httpx as _httpx
    try:
        resp = _httpx.get(f"{ORCHESTRATOR_URL}/api/v1/providers/status", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]서버 연결 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold cyan]LLM 프로바이더 상태[/bold cyan]")
    for p, info in sorted(data.items()):
        in_chain = info.get("in_fallback_chain", False)
        available = info.get("available", True)
        reason = info.get("reason", "")
        chain_tag = "[dim](폴백 체인 포함)[/dim]" if in_chain else "[dim](폴백 체인 미포함)[/dim]"
        if available:
            console.print(f"  ✅ [green]{p}[/green] {chain_tag}")
        else:
            console.print(f"  ⛔ [red]{p}[/red] {chain_tag}")
            console.print(f"     [yellow]{reason}[/yellow]")


if __name__ == "__main__":
    import sys
    import click

    try:
        rv = app(standalone_mode=False)
    except click.exceptions.UsageError as e:
        console.print(f"\n[bold red]오류: {e.format_message()}[/bold red]\n")
        _print_help()
        sys.exit(2)
    except click.exceptions.Abort:
        console.print("\n[yellow]중단됨.[/yellow]")
        sys.exit(1)
    else:
        sys.exit(rv if isinstance(rv, int) and rv != 0 else 0)
