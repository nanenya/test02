#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py
import sys
import os
import inspect
import asyncio

# (수정) 한글 깨짐 방지를 위해 표준 입출력 인코딩을 UTF-8로 강제 설정
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stdin.encoding.lower() != 'utf-8':
    sys.stdin.reconfigure(encoding='utf-8')

import typer
import httpx
import uvicorn
import subprocess
import time
import socket
import re
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm
from typing_extensions import Annotated
from typing import List, Dict, Any

# [신규] Shared 모듈 및 MCP 모듈 임포트
from shared.prompt_manager import prompt_manager
from orchestrator.history_manager import list_conversations, load_conversation, new_conversation
import mcp_modules # MCP 직접 실행을 위해 임포트

app = typer.Typer()
console = Console()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"

# (수정) 모바일/SSH 환경 등에서 입력 오류를 줄이기 위한 입력 헬퍼 함수
def safe_input(prompt_text: str, default: str = None) -> str:
    """
    typer.prompt 대신 rich.prompt를 사용하여 안전하게 입력을 받습니다.
    이는 터미널 인코딩 문제나 모바일에서의 중복 입력 문제를 완화합니다.
    """
    return Prompt.ask(prompt_text, default=default)

def display_full_plan(plan: List[Dict[str, Any]]):
    table = Table(title="[bold]전체 실행 계획[/bold]")
    table.add_column("No.", style="cyan")
    table.add_column("Group ID", style="magenta")
    table.add_column("Description")
    table.add_column("Tasks")

    for i, group in enumerate(plan, 1):
        group_id = group.get('group_id', 'N/A')
        description = group.get('description', 'N/A')
        tasks = group.get('tasks', [])
        
        task_details = []
        for j, task in enumerate(tasks, 1):
            tool_name = task.get('tool_name')
            model_pref = task.get('model_preference', 'auto')
            
            model_display = ""
            if tool_name in ["execute_shell_command", "execute_python_code"]:
                 model_display = f" ([bold red]위험: {tool_name}[/bold red])"
            elif model_pref == 'high':
                 model_display = " (Model: [bold red]High[/bold red])"
            elif model_pref == 'standard':
                 model_display = " (Model: [bold blue]Standard[/bold blue])"
            
            task_details.append(f"  {i}.{j}) {task.get('tool_name')}{model_display}")
        
        table.add_row(str(i), group_id, description, "\n".join(task_details))
    
    console.print(table)

# -------------------------------------------
# [신규] tool 커맨드: Orchestrator 없이 로컬에서 MCP 직접 실행
# -------------------------------------------
@app.command()
def tool(
    name: Annotated[str, typer.Argument(help="실행할 MCP 도구의 이름 (예: ask_gemini)")],
    args: Annotated[List[str], typer.Argument(help="도구에 전달할 인자 (key=value 형태)")] = None
):
    """
    로컬 환경에서 특정 MCP 도구를 직접 실행합니다. (서버 불필요)
    """
    # mcp_modules 패키지에서 함수 이름으로 검색
    tool_func = getattr(mcp_modules, name, None)
    if not tool_func:
        console.print(f"[bold red]오류: '{name}' 도구를 찾을 수 없습니다.[/bold red]")
        console.print(f"사용 가능한 도구: {', '.join([x for x in dir(mcp_modules) if not x.startswith('_')])}")
        return

    # 인자 파싱 (key=value 리스트 -> dict)
    kwargs = {}
    if args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                kwargs[k] = v
            else:
                console.print(f"[yellow]경고: 인자 '{arg}'는 key=value 형식이 아니어서 무시됩니다.[/yellow]")

    console.print(f"[cyan]도구 실행: {name}[/cyan]")
    try:
        # 동기/비동기 함수 구분하여 실행
        if hasattr(tool_func, '__code__'):
            if inspect.iscoroutinefunction(tool_func):
                result = asyncio.run(tool_func(**kwargs))
            else:
                result = tool_func(**kwargs)
            
            console.print(Panel(str(result), title="실행 결과", border_style="green"))
        else:
            console.print(f"[bold red]오류: '{name}'은(는) 실행 가능한 함수가 아닙니다.[/bold red]")

    except Exception as e:
        console.print(f"[bold red]실행 중 오류 발생: {e}[/bold red]")


@app.command()
def list():
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
    system_prompts: Annotated[List[str], typer.Option("--gem", "-g", help="사용할 시스템 프롬프트 이름 (예: default, developer)")] = None,
):
    """
    AI 에이전트와 상호작용을 시작합니다.
    """
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

    client = httpx.Client(timeout=300)
    
    # [수정] 프롬프트 매니저를 사용하여 파일 로드
    prompt_contents = []
    if system_prompts:
        for prompt_name in system_prompts:
            content = prompt_manager.load(prompt_name)
            if "System Error" in content or "System Warning" in content:
                console.print(f"[bold yellow]{content}[/bold yellow]")
            else:
                prompt_contents.append(content)

    if query:
        convo_id, history = new_conversation()
        console.print(f"새로운 대화를 시작합니다. (ID: {convo_id})")
        
        safe_query = query
        
        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": safe_query, 
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
        
        user_input = safe_input("추가/수정 지시가 있나요? (없으면 Enter 키로 기존 계획 계속)")
        
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
            new_plan_data = data.get("plan")
            next_group = data.get("execution_group") 

            if status == "FINAL_ANSWER":
                console.print(f"\n[bold green]✅ 최종 답변:[/bold green]\n{message}")
                break

            elif status == "PLAN_CONFIRMATION":
                if new_plan_data:
                    console.print("\n[bold yellow]전체 실행 계획이 수립되었습니다.[/bold yellow]")
                    display_full_plan(new_plan_data)
                else:
                    console.print(f"\n[bold yellow]다음 실행 계획:[/bold yellow]\n{message}")
                
                is_dangerous = False
                # 위험 작업 체크 로직 (기존과 동일)
                tasks_to_check = []
                if next_group:
                    tasks_to_check = next_group.get('tasks', [])
                elif new_plan_data and new_plan_data[0].get('tasks'):
                    tasks_to_check = new_plan_data[0].get('tasks', [])
                
                for task in tasks_to_check:
                    if task.get('tool_name') in ["execute_shell_command", "execute_python_code"]:
                        is_dangerous = True
                        break

                if is_dangerous:
                    console.print("[bold red]경고: 다음 단계에 위험 작업이 포함되어 있습니다.[/bold red]")
                    action = safe_input("승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()
                else:
                      action = safe_input("계획을 승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()
                
                if action in ["y", "yes"]:
                    console.print("[cyan]...승인됨. 계획 그룹을 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history,
                        "model_preference": model_pref,
                        "user_decision": None
                    }
                elif action == 'edit':
                    edited_instruction = safe_input("어떻게 수정할까요? (새로운 계획 수립)")
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
            
            elif status == "DANGEROUS_TASK_CONFIRMATION":
                details = data.get("dangerous_task_details", {})
                task_name = details.get("tool_name")
                arguments = details.get("arguments", {})
                
                console.print(f"\n[bold red]🚨 위험 작업 확인 🚨[/bold red]")
                console.print(f"서버가 '{task_name}' 작업을 실행하려고 합니다.")
                
                code_to_run = arguments.get("code_str") or arguments.get("command") or "N/A"
                lang = "python" if task_name == "execute_python_code" else "shell"

                console.print(Panel(Syntax(code_to_run, lang, theme="monokai", line_numbers=True), title="실행될 코드/명령어"))
                
                action = safe_input(
                    "어떻게 하시겠습니까? [P(즉시 실행) / m(신규 MCP 생성 요청) / n(작업 중단)]", 
                    default="n"
                ).lower()

                if action == 'p':
                    console.print("[cyan]...사용자 승인. 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    request_data = {
                        "conversation_id": convo_id, "history": history, "model_preference": model_pref,
                        "user_decision": "proceed"
                    }
                elif action == 'm':
                    console.print("[cyan]...신규 MCP 생성 요청...[/cyan]")
                    mcp_instruction = safe_input("요청 사항 입력:", default=f"'{task_name}'을(를) 대체할 안전한 MCP 모듈을 생성해줘.")
                    endpoint = "/agent/decide_and_act"
                    request_data = {
                        "conversation_id": convo_id, "history": history, "model_preference": model_pref,
                        "user_decision": "create_mcp", "user_input": mcp_instruction
                    }
                else:
                    console.print("[bold red]작업을 중단합니다.[/bold red]")
                    break

            elif status == "EXECUTION_ERROR":
                console.print(f"\n[bold red]❌ 작업 중 오류 발생:[/bold red]\n{message}")
                
                edited_instruction = safe_input("오류 수정 지시 (중단: 'n'/'exit'):")
                
                if edited_instruction.lower() in ['n', 'exit']:
                    console.print("[bold red]작업을 중단합니다.[/bold red]")
                    break
                
                endpoint = "/agent/decide_and_act"
                request_data = {
                    "conversation_id": convo_id, "history": history, "user_input": edited_instruction,
                    "model_preference": model_pref, "system_prompts": prompt_contents 
                }

            elif status == "ERROR":
                console.print(f"[bold red]서버 오류: {message}[/bold red]")
                break

        except httpx.RequestError:
            console.print("[bold red]오류: 서버에 연결할 수 없습니다.[/bold red]")
            break
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]오류: 서버 응답 에러 {e.response.text}[/bold red]")
            break

# --- Server ---
def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

@app.command(name="server")
def run_server(
    host: Annotated[str, typer.Option(help="호스트 주소")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="포트 번호")] = 8000,
    reload: Annotated[bool, typer.Option(help="자동 재시작 여부")] = True,
):
    """FastAPI 오케스트레이터 서버를 실행합니다."""
    
    typer.echo(f"{port}번 포트 확인 중...")
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        typer.secho("기존 프로세스 종료 완료.", fg=typer.colors.GREEN)
        time.sleep(1)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    typer.echo(f"FastAPI 서버 시작: http://{host}:{port}")
    # (수정) loop="asyncio" 추가: nest_asyncio 호환성 문제 해결
    uvicorn.run("orchestrator.api:app", host=host, port=port, reload=reload, loop="asyncio")

if __name__ == "__main__":
    app()
