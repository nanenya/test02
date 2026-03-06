#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/agent_config_cmds.py — prompt / skill / macro / workflow / persona 서브커맨드

import json
from typing import List, Optional

import typer
from rich.table import Table
from typing_extensions import Annotated

from .core import console, ORCHESTRATOR_URL

prompt_app = typer.Typer(help="시스템 프롬프트 관리 명령어")
skill_app = typer.Typer(help="스킬 관리 명령어")
macro_app = typer.Typer(help="스킬 매크로 관리 명령어")
workflow_app = typer.Typer(help="워크플로우 관리 명령어")
persona_app = typer.Typer(help="페르소나 관리 명령어")


# ── prompt ────────────────────────────────────────────────────────

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


# ── skill ─────────────────────────────────────────────────────────

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


# ── macro ─────────────────────────────────────────────────────────

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


# ── workflow ──────────────────────────────────────────────────────

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


# ── persona ───────────────────────────────────────────────────────

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
            name=name, system_prompt=system_prompt,
            allowed_skills=skills or [], keywords=keywords or [],
            description=desc, system_prompt_ref=system_prompt_ref, is_default=is_default,
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
        name, system_prompt=system_prompt, allowed_skills=skills,
        keywords=keywords, description=desc, system_prompt_ref=system_prompt_ref,
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
