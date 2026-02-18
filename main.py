#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py
import asyncio
import typer
import httpx
import uvicorn
import subprocess
import time
import socket
import os
import re
from rich.console import Console
from rich.table import Table
from typing_extensions import Annotated
from typing import List, Dict, Any
from orchestrator.history_manager import list_conversations, load_conversation, new_conversation
from orchestrator import mcp_manager

app = typer.Typer()
mcp_app = typer.Typer(help="MCP 서버 관리 명령어")
app.add_typer(mcp_app, name="mcp")
model_app = typer.Typer(help="AI 모델 관리 명령어")
app.add_typer(model_app, name="model")
console = Console()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"
PROMPTS_DIR = "system_prompts"

os.makedirs(PROMPTS_DIR, exist_ok=True)
default_prompt_path = os.path.join(PROMPTS_DIR, "default.txt")
if not os.path.exists(default_prompt_path):
    with open(default_prompt_path, "w", encoding="utf-8") as f:
        f.write("당신은 유능한 AI 어시스턴트입니다.")


# --- (수정) display_full_plan 함수 제거 ---
# (ReAct 아키텍처에서는 '전체 계획'을 미리 알 수 없으므로 이 기능은 제거됩니다.)
# def display_full_plan(plan: List[Dict[str, Any]]):
#     ...
# -------------------------------------------


@app.command(name="list")
def list_conversations_cmd():
    """저장된 대화 목록을 표시합니다."""
    try:
        convos = list_conversations()
        
        table = Table("ID (Filename)", "Title", "Last Updated")
        for convo in convos:
            table.add_row(convo['id'], convo['title'], convo['last_updated'])
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]오류: 대화 목록을 불러올 수 없습니다. ({e})[/bold red]")

@app.command()
def run(
    query: Annotated[str, typer.Option("--query", "-q", help="AI 에이전트에게 내릴 새로운 명령어")] = None,
    continue_id: Annotated[str, typer.Option("--continue", "-c", help="이어갈 대화의 ID (파일명)")] = None,
    requirement_paths: Annotated[List[str], typer.Option("--req", "-r", help="참조할 요구사항 파일 경로")] = None,
    model_pref: Annotated[str, typer.Option("--model-pref", "-m", help="모델 선호도 (auto, standard, high)")] = "auto",
    system_prompts: Annotated[List[str], typer.Option("--gem", "-g", help="사용할 시스템 프롬프트 (Gem) 이름 (예: default)")] = None,
):
    """
    AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다.
    """
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

    client = httpx.Client(timeout=120)
    
    prompt_contents = []
    if system_prompts:
        for prompt_name in system_prompts:
            prompt_file = os.path.join(PROMPTS_DIR, f"{prompt_name}.txt")
            if os.path.exists(prompt_file):
                try:
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        prompt_contents.append(f.read())
                except Exception as e:
                    console.print(f"[bold yellow]경고: 프롬프트 파일 '{prompt_file}'을 읽을 수 없습니다: {e}[/bold yellow]")
            else:
                console.print(f"[bold yellow]경고: 프롬프트 파일 '{prompt_file}'을 찾을 수 없습니다.[/bold yellow]")

    if query:
        convo_id, history = new_conversation()
        console.print(f"새로운 대화를 시작합니다. (ID: {convo_id})")
        
        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": query, 
            "requirement_paths": requirement_paths,
            "model_preference": model_pref,
            "system_prompts": prompt_contents
        }
        endpoint = "/agent/decide_and_act"
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
            "system_prompts": prompt_contents
        }
        endpoint = "/agent/decide_and_act"

    # --- 상호작용 루프 ---
    
    while True:
        try:
            response = client.post(f"{ORCHESTRATOR_URL}{endpoint}", json=request_data)
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status")
            message = data.get("message")
            convo_id = data.get("conversation_id")
            history = data.get("history")
            # (수정) plan 필드는 더 이상 사용하지 않음
            # new_plan_data = data.get("plan") 

            if status == "FINAL_ANSWER":
                console.print(f"\n[bold green]최종 답변:[/bold green]\n{message}")
                break
            
            # --- (수정) STEP_EXECUTED 상태 처리 ---
            elif status == "STEP_EXECUTED":
                console.print(f"[cyan]...{message}[/cyan]")
                console.print("[cyan]...다음 단계를 계획합니다...[/cyan]")
                endpoint = "/agent/decide_and_act"
                request_data = {
                    "conversation_id": convo_id, 
                    "history": history, 
                    "user_input": None, # (중요) Re-plan 트리거
                    "model_preference": model_pref,
                    "system_prompts": prompt_contents
                }
            # ------------------------------------

            elif status == "PLAN_CONFIRMATION":
                
                # (수정) ReAct 모델에서는 '전체 계획' 표시 로직 제거
                # if new_plan_data: ...
                
                console.print(f"\n[bold yellow]다음 실행 계획:[/bold yellow]\n{message}")
                action = typer.prompt("승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()

                if action in ["y", "yes"]:
                    console.print("[cyan]...승인됨. 계획 그룹을 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history,
                        "model_preference": model_pref
                    }
                elif action == 'edit':
                    edited_instruction = typer.prompt("어떻게 수정할까요? (새로운 계획 수립)")
                        
                    endpoint = "/agent/decide_and_act"
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history, 
                        "user_input": edited_instruction,
                        "model_preference": model_pref,
                        "system_prompts": prompt_contents
                    }
                else:
                    console.print("[bold red]작업을 중단합니다.[/bold red]")
                    break
            
            elif status == "ERROR":
                console.print(f"[bold red]서버 오류: {message}[/bold red]")
                break

        except httpx.RequestError:
            console.print("[bold red]오류: 오케스트레이터 서버에 연결할 수 없습니다. 서버를 실행하세요.[/bold red]")
            break
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]오류: 서버에서 에러 응답을 받았습니다. {e.response.text}[/bold red]")
            break

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

@app.command(name="server")
def run_server(
    host: Annotated[str, typer.Option(help="서버가 바인딩할 호스트 주소")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="서버가 리스닝할 포트 번호")] = 8000,
    reload: Annotated[bool, typer.Option(help="코드 변경 시 서버 자동 재시작 여부")] = True,
):
    """FastAPI 오케스트레이터 서버를 실행합니다."""

    typer.echo(f"{port}번 포트를 사용하는 기존 프로세스를 확인하고 종료합니다...")
    try:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        typer.secho(f"기존 프로세스를 성공적으로 종료했습니다.", fg=typer.colors.GREEN)

        typer.echo(f"포트가 해제되기를 기다리고 있습니다...")
        max_wait_seconds = 5
        wait_start_time = time.time()
        while is_port_in_use(port, host):
            if time.time() - wait_start_time > max_wait_seconds:
                typer.secho(f"{max_wait_seconds}초가 지나도 {port}번 포트가 여전히 사용 중입니다. 스크립트를 종료합니다.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            time.sleep(0.5) 
        typer.secho(f"포트가 성공적으로 해제되었습니다.", fg=typer.colors.GREEN)

    except FileNotFoundError:
        typer.secho("경고: 'fuser' 명령어를 찾을 수 없습니다. (Linux 시스템 필요). 포트 충돌이 발생할 수 있습니다.", fg=typer.colors.YELLOW)
    except subprocess.CalledProcessError:
        typer.echo(f"{port}번 포트를 사용하는 기존 프로세스가 없습니다. 바로 시작합니다.")

    typer.echo(f"FastAPI 서버 시작: http://{host}:{port}")
    uvicorn.run("orchestrator.api:app", host=host, port=port, reload=reload)

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
            registry, name=name, package=package,
            package_manager=manager, description=desc,
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
                overlaps = mcp_manager.get_tool_overlap_report(new_tools, TOOL_DESCRIPTIONS)
                if overlaps:
                    overlap_table = Table("Tool", "New Description", "Existing Description")
                    for o in overlaps:
                        overlap_table.add_row(o["name"], o["new_desc"], o["existing_desc"])
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


# --- model 서브커맨드 ---

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
        has_key = "[green]설정됨[/green]" if p["has_api_key"] else f"[red]미설정 ({p['api_key_env']})[/red]"
        table.add_row(p["name"], enabled, has_key, p["default_model"] or "-")
    console.print(table)


@model_app.command(name="list")
def model_list(
    provider: Annotated[str, typer.Option("--provider", "-p", help="특정 프로바이더만 조회")] = None,
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
    provider: Annotated[str, typer.Argument(help="프로바이더 이름 (gemini, claude, openai, grok)")],
    model: Annotated[str, typer.Argument(help="모델 ID")],
):
    """활성 프로바이더와 모델을 변경합니다."""
    from orchestrator.model_manager import load_config, set_active_model

    try:
        config = load_config()
        set_active_model(provider, model, config)
        console.print(f"[green]활성 모델이 변경되었습니다: {provider} / {model}[/green]")
    except ValueError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
