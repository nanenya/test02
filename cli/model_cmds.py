#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/model_cmds.py — model 서브커맨드

import asyncio
from typing import Optional

import typer
from rich.table import Table
from typing_extensions import Annotated

from .core import console

model_app = typer.Typer(help="AI 모델 관리 명령어")


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
