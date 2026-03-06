#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/core.py — 핵심 CLI 커맨드 (run, server, list, graph, migrate) + 공통 유틸리티

import asyncio
import json
import re as _re
import socket
import subprocess
import time
import os
from pathlib import Path
from typing import List, Optional

import httpx
import typer
import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from typing_extensions import Annotated

load_dotenv()

from orchestrator.history_manager import (
    list_conversations,
    load_conversation,
    new_conversation,
    split_conversation,
)

console = Console()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"
PROMPTS_DIR = "system_prompts"

# --auto 모드에서 사용자 확인이 필요한 위험 도구 목록
_DANGEROUS_TOOLS: frozenset = frozenset({
    "delete_file", "remove_file", "delete_directory", "remove_directory",
    "delete", "remove", "unlink", "rmdir",
    "git_push", "git_force_push", "git_reset", "git_clean",
    "execute_command", "run_command", "shell_exec", "bash",
    "drop_table", "delete_database", "truncate_table",
})

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

# P1-B: 태스크 카테고리 → model_preference 매핑
_CATEGORY_TO_MODEL_PREF: dict = {
    "quick":      "standard",
    "code":       "high",
    "analysis":   "high",
    "creative":   "high",
    "deep":       "high",
    "ultrabrain": "high",
    "visual":     "auto",
}

# P2-A: 미완료 항목 키워드 목록
_INCOMPLETE_MARKERS = [
    "TODO", "FIXME", "HACK", "XXX",
    "미완료", "추후", "나중에", "해야 할", "남은 작업", "아직", "보류",
    "[ ]",
]
_TODO_MAX_RETRIES = 3

_CONTEXT_FILES = ["AGENTS.md", "README.md"]
_CONTEXT_MAX_BYTES = 8 * 1024

_OLLAMA_BIN_CANDIDATES = [
    "/home/nanenya/.local/bin/ollama",
    os.path.expanduser("~/.local/bin/ollama"),
]

os.makedirs(PROMPTS_DIR, exist_ok=True)
default_prompt_path = os.path.join(PROMPTS_DIR, "default.txt")
if not os.path.exists(default_prompt_path):
    with open(default_prompt_path, "w", encoding="utf-8") as f:
        f.write("당신은 유능한 AI 어시스턴트입니다.")


# ── 유틸리티 함수 ────────────────────────────────────────────────

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


def _check_dangerous_tools(execution_group: dict) -> List[str]:
    """실행 그룹 내 위험 도구 이름을 반환합니다."""
    return [
        task.get("tool_name", "")
        for task in execution_group.get("tasks", [])
        if task.get("tool_name", "").lower() in _DANGEROUS_TOOLS
    ]


def _check_sensitive_data(execution_group: dict) -> List[str]:
    """실행 그룹 인자에서 민감 데이터 패턴을 탐지합니다."""
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


def _scan_incomplete_markers(history: List[str]) -> List[str]:
    """히스토리에서 미완료 마커가 포함된 항목을 반환합니다."""
    found = []
    for entry in history[-10:]:
        if not isinstance(entry, str):
            continue
        for marker in _INCOMPLETE_MARKERS:
            if marker in entry:
                for line in entry.splitlines():
                    if marker in line:
                        found.append(line.strip()[:200])
                break
    return found


def _load_context_files(start_dir: Optional[str] = None) -> str:
    """작업 디렉토리부터 상위로 올라가며 AGENTS.md / README.md를 찾아 반환합니다."""
    search_dir = Path(start_dir or os.getcwd()).resolve()
    visited: set = set()
    collected: List[str] = []
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


def _find_ollama_bin() -> Optional[str]:
    """ollama 실행 파일 경로를 반환합니다. 없으면 None."""
    for path in _OLLAMA_BIN_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
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
    """활성 프로바이더가 ollama일 때 서버가 실행 중인지 보장합니다."""
    from orchestrator.model_manager import load_config, get_active_model
    provider, _ = get_active_model(load_config())
    if provider != "ollama":
        return True

    if _is_ollama_running():
        return True

    console.print("[yellow]Ollama 서버가 실행 중이 아닙니다. 자동 시작을 시도합니다...[/yellow]")

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


def _print_help() -> None:
    """상세 도움말 출력."""
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


# ── list ─────────────────────────────────────────────────────────

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


# ── server ───────────────────────────────────────────────────────

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


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
