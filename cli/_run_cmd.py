#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/_run_cmd.py — `run` CLI 커맨드 (AI 에이전트 상호작용)

import asyncio
import json
import os
import time
from typing import List, Optional

import httpx
import typer
from rich.console import Console
from typing_extensions import Annotated

from orchestrator.history_manager import (
    list_conversations,
    load_conversation,
    new_conversation,
    split_conversation,
)

# core에서 공유 상수·유틸리티 임포트 (역방향 의존 없음)
from .core import (
    console,
    ORCHESTRATOR_URL,
    PROMPTS_DIR,
    _CATEGORY_TO_MODEL_PREF,
    _ensure_ollama_running,
    _load_context_files,
    _scan_incomplete_markers,
    _check_dangerous_tools,
    _check_sensitive_data,
    _check_security_context,
    _fmt_usage,
    _TODO_MAX_RETRIES,
)

# ── run ──────────────────────────────────────────────────────────

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
    """AI 에이전트와 상호작용을 시작합니다. 새로운 쿼리 또는 기존 대화 ID가 필요합니다."""
    if not query and not continue_id:
        console.print("[bold red]오류: --query 또는 --continue 옵션 중 하나는 반드시 필요합니다.[/bold red]")
        raise typer.Exit()

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

    if not no_context:
        ctx_content = _load_context_files()
        if ctx_content:
            prompt_contents.insert(0, f"# 프로젝트 컨텍스트 (자동 주입)\n\n{ctx_content}")
            console.print("[dim]📄 AGENTS.md / README.md 컨텍스트 자동 주입됨[/dim]")

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

    _sess_in = _sess_out = 0
    _sess_cost = 0.0
    _step_count = 0
    _todo_retries = 0

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

            _usage = data.get("token_usage") or {}
            if _usage:
                _sess_in += _usage.get("input_tokens", 0)
                _sess_out += _usage.get("output_tokens", 0)
                _sess_cost += _usage.get("cost_usd", 0.0)

            if status == "FINAL_ANSWER":
                console.print(f"\n[bold green]최종 답변:[/bold green]\n{message}")

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
                        continue

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
                    _step_count = 0

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
                        action = typer.prompt("계속하시겠습니까? [Y/n/edit]", default="Y").lower()
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
                else:
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


