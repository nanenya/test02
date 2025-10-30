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
from typing_extensions import Annotated
from typing import List, Dict, Any
from orchestrator.history_manager import list_conversations, load_conversation, new_conversation

app = typer.Typer()
console = Console()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"
PROMPTS_DIR = "system_prompts"

# --- (요청사항 4) 시스템 프롬프트 디렉토리 생성 ---
os.makedirs(PROMPTS_DIR, exist_ok=True)
# 기본 프롬프트 파일 생성 (예시)
default_prompt_path = os.path.join(PROMPTS_DIR, "default.txt")
if not os.path.exists(default_prompt_path):
    with open(default_prompt_path, "w", encoding="utf-8") as f:
        f.write("당신은 유능한 AI 어시스턴트입니다.")
# -----------------------------------------------


# --- (요청사항 2) 전체 계획 표시 헬퍼 ---
def display_full_plan(plan: List[Dict[str, Any]]):
    """
    전체 실행 계획을 넘버링하여 상세하게 표시합니다.
    """
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
            
            # (요청사항 2) 모델 사용 여부 표시
            model_display = ""
            if model_pref == 'high':
                model_display = " (Model: [bold red]High[/bold red])"
            elif model_pref == 'standard':
                model_display = " (Model: [bold blue]Standard[/bold blue])"
            
            task_details.append(f"  {i}.{j}) {tool_name}{model_display}")
        
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
    """저장된 대화 목록을 표시합니다."""
    try:
        convos = list_conversations()
        
        table = Table("ID (Filename)", "Title", "Last Updated")
        for convo in convos:
            # (요청사항 3) ID가 이제 파일명임
            table.add_row(convo['id'], convo['title'], convo['last_updated'])
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]오류: 대화 목록을 불러올 수 없습니다. ({e})[/bold red]")

@app.command()
def run(
    query: Annotated[str, typer.Option("--query", "-q", help="AI 에이전트에게 내릴 새로운 명령어")] = None,
    continue_id: Annotated[str, typer.Option("--continue", "-c", help="이어갈 대화의 ID (파일명)")] = None,
    requirement_paths: Annotated[List[str], typer.Option("--req", "-r", help="참조할 요구사항 파일 경로")] = None,
    # (요청사항 1) 모델 선호도 옵션
    model_pref: Annotated[str, typer.Option("--model-pref", "-m", help="모델 선호도 (auto, standard, high)")] = "auto",
    # (요청사항 4) 시스템 프롬프트(Gem) 옵션
    system_prompts: Annotated[List[str], typer.Option("--gem", "-g", help="사용할 시스템 프롬프트 (Gem) 이름 (예: default)")] = None,
):
    """
    AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다.
    """
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

    client = httpx.Client(timeout=120)
    
    # (요청사항 4) 시스템 프롬프트 파일 읽기
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

    # 대화 시작 또는 이어가기
    if query:
        convo_id, history = new_conversation()
        console.print(f"새로운 대화를 시작합니다. (ID: {convo_id})")
        
        # (요청사항 5) 한글 처리: 불필요한 encode/decode 제거 (Typer가 처리)
        
        # 새 쿼리는 user_input으로 전달하여 서버가 '계획 수립'을 하도록 함
        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": query, 
            "requirement_paths": requirement_paths,
            "model_preference": model_pref, # (요청사항 1)
            "system_prompts": prompt_contents # (요청사항 4)
        }
        endpoint = "/agent/decide_and_act"
    else: # 대화 이어가기
        convo_id = continue_id
        data = load_conversation(convo_id)
        if not data:
            console.print(f"[bold red]오류: ID '{convo_id}'에 해당하는 대화를 찾을 수 없습니다.[/bold red]")
            raise typer.Exit()
        
        history = data.get("history", [])
        # (요청사항 3) 파일명이 ID이므로, ID를 업데이트
        convo_id = data.get("id", convo_id) 
        console.print(f"대화를 이어합니다. (ID: {convo_id})")
        
        # 추가 지시사항 받기 (수정 또는 계속)
        user_input = typer.prompt("추가/수정 지시가 있나요? (없으면 Enter 키로 기존 계획 계속)")
        
        # (요청사항 5) 한글 처리: 불필요한 encode/decode 제거
        
        request_data = {
            "conversation_id": convo_id, 
            "history": history, 
            "user_input": user_input or None,
            "model_preference": model_pref, # (요청사항 1)
            "system_prompts": prompt_contents # (요청사항 4)
            # 요구사항 파일과 시스템 프롬프트는 이어하기 시 새로 입력받지 않음 (필요시 추가 가능)
        }
        endpoint = "/agent/decide_and_act"

    # --- 상호작용 루프 ---
    current_plan = [] # (요청사항 2)
    
    while True:
        try:
            response = client.post(f"{ORCHESTRATOR_URL}{endpoint}", json=request_data)
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status")
            message = data.get("message")
            convo_id = data.get("conversation_id")
            history = data.get("history") # 항상 최신 히스토리로 업데이트
            new_plan_data = data.get("plan") # (요청사항 2)

            if status == "FINAL_ANSWER":
                console.print(f"\n[bold green]최종 답변:[/bold green]\n{message}")
                break

            elif status == "PLAN_CONFIRMATION":
                
                # (요청사항 2)
                # Case 1: 서버가 전체 계획을 처음으로 보낸 경우
                if new_plan_data:
                    current_plan = new_plan_data
                    console.print("\n[bold yellow]전체 실행 계획이 수립되었습니다.[/bold yellow]")
                    display_full_plan(current_plan)
                    
                    # (요청사항 2) 계획 수정/승인
                    action = typer.prompt("계획을 승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()
                
                # Case 2: 서버가 다음 그룹 실행을 확인하는 경우
                else:
                    console.print(f"\n[bold yellow]다음 실행 계획:[/bold yellow]\n{message}")
                    # (요청사항 2) 계획 수정/승인
                    action = typer.prompt("승인하시겠습니까? [Y(예)/n(아니오)/edit(계획 수정)]", default="Y").lower()

                
                if action in ["y", "yes"]:
                    console.print("[cyan]...승인됨. 계획 그룹을 실행합니다...[/cyan]")
                    endpoint = "/agent/execute_group"
                    # 서버가 ID를 기반으로 계획을 알고 있으므로 ID와 히스토리만 전달
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history,
                        "model_preference": model_pref # (요청사항 1)
                    }
                elif action == 'edit':
                    # (요청사항 2) 'edit'는 전체 계획을 수정(재수립)하도록 유도
                    edited_instruction = typer.prompt("어떻게 수정할까요? (새로운 계획 수립)")
                    
                    # (요청사항 5) 한글 처리: 불필요한 encode/decode 제거
                        
                    endpoint = "/agent/decide_and_act"
                    # user_input을 전달하여 re-planning 트리거
                    request_data = {
                        "conversation_id": convo_id, 
                        "history": history, 
                        "user_input": edited_instruction,
                        "model_preference": model_pref, # (요청사항 1)
                        "system_prompts": prompt_contents # (요청사항 4)
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
    """지정된 호스트와 포트가 현재 사용 중인지 확인합니다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # connect_ex는 연결 실패 시 에러 코드를 반환하므로 try-except가 필요 없습니다.
        # 연결에 성공하면 0을 반환하며, 이는 포트가 사용 중임을 의미합니다.
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
        # fuser -k {port}/tcp: 지정된 TCP 포트를 사용하는 프로세스를 강제 종료(-k)
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        typer.secho(f"기존 프로세스를 성공적으로 종료했습니다.", fg=typer.colors.GREEN)

        # --- 핵심 수정 부분 ---
        # 포트가 해제될 때까지 최대 5초간 대기합니다.
        typer.echo(f"포트가 해제되기를 기다리고 있습니다...")
        max_wait_seconds = 5
        wait_start_time = time.time()
        while is_port_in_use(port, host):
            if time.time() - wait_start_time > max_wait_seconds:
                typer.secho(f"{max_wait_seconds}초가 지나도 {port}번 포트가 여전히 사용 중입니다. 스크립트를 종료합니다.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            time.sleep(0.5) # 0.5초 간격으로 확인
        typer.secho(f"포트가 성공적으로 해제되었습니다.", fg=typer.colors.GREEN)
        # --------------------

    except FileNotFoundError:
        typer.secho("경고: 'fuser' 명령어를 찾을 수 없습니다. (Linux 시스템 필요). 포트 충돌이 발생할 수 있습니다.", fg=typer.colors.YELLOW)
    except subprocess.CalledProcessError:
        typer.echo(f"{port}번 포트를 사용하는 기존 프로세스가 없습니다. 바로 시작합니다.")

    typer.echo(f"FastAPI 서버 시작: http://{host}:{port}")
    # uvicorn.run의 첫 번째 인자는 "모듈_이름:FastAPI_앱_인스턴스" 형식이어야 합니다.
    uvicorn.run("orchestrator.api:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    app()
