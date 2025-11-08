#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py
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
from rich.panel import Panel
from rich.syntax import Syntax
from typing_extensions import Annotated
from typing import List, Dict, Any
from orchestrator.history_manager import list_conversations, load_conversation, new_conversation

app = typer.Typer()
console = Console()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"
PROMPTS_DIR = "system_prompts"

# --- (기존 디렉토리 생성 및 헬퍼 함수) ---
os.makedirs(PROMPTS_DIR, exist_ok=True)
default_prompt_path = os.path.join(PROMPTS_DIR, "default.txt")
if not os.path.exists(default_prompt_path):
    with open(default_prompt_path, "w", encoding="utf-8") as f:
        f.write("당신은 유능한 AI 어시스턴트입니다.")

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
        
        table.add_row(
            str(i),
            group_id,
            description,
            "\n".join(task_details)
        )
    
    console.print(table)
# -------------------------------------------


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
    system_prompts: Annotated[List[str], typer.Option("--gem", "-g", help="사용할 시스템 프롬프트 (Gem) 이름 (예: default)")] = None,
):
    """
    AI 에이전트와 상호작용을 시작합니다. (수정: 오류 복구 및 위험 작업 확인 로직 추가)
    """
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

    client = httpx.Client(timeout=300)
    
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
        
        # (신규) CLI 인자로 받은 query도 인코딩 오류가 있을 수 있으므로 수정
        safe_query = query.encode('utf-8', errors='replace').decode('utf-8')
        
        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": safe_query, # (수정)
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
        
        # (신규) UTF-8 인코딩 오류 수정 (1/4)
        if user_input:
            user_input = user_input.encode('utf-8', errors='replace').decode('utf-8')

        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": user_input or None,
            "model_preference": model_pref,
            "system_prompts": prompt_contents
        }
        endpoint = "/agent/decide_and_act"

    # --- 상호작용 루프 ---
    current_plan = [] 
    
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
                    current_plan = new_plan_data
                    console.print("\n[bold yellow]전체 실행 계획이 수립되었습니다.[/bold yellow]")
                    display_full_plan(current_plan)
                else:
                    console.print(f"\n[bold yellow]다음 실행 계획:[/bold yellow]\n{message}")
                
                is_dangerous = False
                if next_group:
                    for task in next_group.get('tasks', []):
                        if task.get('tool_name') in ["execute_shell_command", "execute_python_code"]:
                            is_dangerous = True
                            break
                elif new_plan_data:
                    if new_plan_data[0].get('tasks', []):
                        for task in new_plan_data[0].get('tasks', []):
                             if task.get('tool_name') in ["execute_shell_command", "execute_python_code"]:
                                is_dangerous = True
                                break

                if is_dangerous:
                    console.print("[bold red]경고: 다음 단계에 'execute_shell_command' 또는 'execute_python_code'가 포함되어 있습니다.[/bold red]")
                    action = typer.prompt("승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()
                else:
                     action = typer.prompt("계획을 승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()
                
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
                    edited_instruction = typer.prompt("어떻게 수정할까요? (새로운 계획 수립)")
                    
                    # (신규) UTF-8 인코딩 오류 수정 (2/4)
                    if edited_instruction:
                        edited_instruction = edited_instruction.encode('utf-8', errors='replace').decode('utf-8')

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
                
                code_to_run = ""
                if task_name == "execute_python_code":
                    code_to_run = arguments.get("code_str", "N/A")
                    lang = "python"
                else: # execute_shell_command
                    code_to_run = arguments.get("command", "N/A")
                    lang = "shell"

                console.print(Panel(Syntax(code_to_run, lang, theme="monokai", line_numbers=True), title="실행될 코드/명령어"))
                
                action = typer.prompt(
                    "어떻게 하시겠습니까? [P(즉시 실행) / m(신규 MCP 생성 요청) / n(작업 중단)]", 
                    default="n"
                ).lower()

                if action == 'p':
                    console.print("[cyan]...사용자 승인 (Proceed). 작업을 즉시 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history,
                        "model_preference": model_pref,
                        "user_decision": "proceed"
                    }
                elif action == 'm':
                    console.print("[cyan]...신규 MCP 생성 요청...[/cyan]")
                    mcp_instruction = typer.prompt("AI 개발자에게 MCP 생성을 어떻게 요청할까요?", default=f"'{task_name}'을(를) 대체할 안전한 MCP 모듈을 생성해줘. (목표: {code_to_run[:50]}...)")
                    
                    # (신규) UTF-8 인코딩 오류 수정 (3/4)
                    if mcp_instruction:
                        mcp_instruction = mcp_instruction.encode('utf-8', errors='replace').decode('utf-8')
                        
                    endpoint = "/agent/decide_and_act"
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history,
                        "model_preference": model_pref,
                        "user_decision": "create_mcp",
                        "user_input": mcp_instruction
                    }
                else:
                    console.print("[bold red]작업을 중단합니다.[/bold red]")
                    break

            elif status == "EXECUTION_ERROR":
                console.print(f"\n[bold red]❌ 작업 중 오류 발생:[/bold red]\n{message}")
                console.print(f"[cyan]오류가 발생한 대화 ID: {convo_id}[/cyan]")
                
                edited_instruction = typer.prompt("오류를 어떻게 수정할까요? (새로운 지시 입력. 중단하려면 'n' 또는 'exit')")
                
                # (신규) UTF-8 인코딩 오류 수정 (4/4)
                if edited_instruction:
                    edited_instruction = edited_instruction.encode('utf-8', errors='replace').decode('utf-8')

                if edited_instruction.lower() in ['n', 'exit']:
                    console.print("[bold red]작업을 중단합니다.[/bold red]")
                    break
                
                endpoint = "/agent/decide_and_act"
                request_data = {
                    "conversation_id": convo_id, 
                    "history": history, 
                    "user_input": edited_instruction,
                    "model_preference": model_pref,
                    "system_prompts": prompt_contents 
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

# --- (server 및 main 실행 코드는 기존과 동일) ---
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

if __name__ == "__main__":
    app()
