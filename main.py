#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py — CLI 진입점 (thin assembler)

import sys
from dotenv import load_dotenv

load_dotenv()

import click
import typer

from cli.core import (
    console,
    _print_help,
    list_conversations_cmd,
    run_server,
    graph_cmd,
    migrate_cmd,
    _check_sensitive_data,
    _check_security_context,
    _check_dangerous_tools,
    _DANGEROUS_TOOLS,
    _CATEGORY_TO_MODEL_PREF,
    _load_context_files,
    _scan_incomplete_markers,
    _fmt_usage,
)
from cli._run_cmd import run
from cli.mcp_cmds import mcp_app
from cli.model_cmds import model_app
from cli.conv_cmds import group_app, topic_app, keyword_app
from cli.agent_config_cmds import prompt_app, skill_app, macro_app, workflow_app, persona_app
from cli.ops_cmds import issue_app, test_app, template_app, gap_app, provider_app

app = typer.Typer(no_args_is_help=False)

# sub-app 등록
app.add_typer(mcp_app, name="mcp")
app.add_typer(model_app, name="model")
app.add_typer(group_app, name="group")
app.add_typer(topic_app, name="topic")
app.add_typer(keyword_app, name="keyword")
app.add_typer(prompt_app, name="prompt")
app.add_typer(skill_app, name="skill")
app.add_typer(macro_app, name="macro")
app.add_typer(workflow_app, name="workflow")
app.add_typer(persona_app, name="persona")
app.add_typer(issue_app, name="issue")
app.add_typer(test_app, name="test")
app.add_typer(template_app, name="template")
app.add_typer(gap_app, name="gap")
app.add_typer(provider_app, name="provider")

# 핵심 커맨드 등록
app.command(name="list")(list_conversations_cmd)
app.command(name="run")(run)
app.command(name="server")(run_server)
app.command(name="graph")(graph_cmd)
app.command(name="migrate")(migrate_cmd)


@app.callback(invoke_without_command=True)
def _main_callback(ctx: typer.Context) -> None:
    """Multi-Provider AI Agent Orchestrator CLI"""
    if ctx.invoked_subcommand is None:
        _print_help()
        raise typer.Exit()


if __name__ == "__main__":
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
