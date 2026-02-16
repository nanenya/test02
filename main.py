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

if __name__ == "__main__":
    app()
