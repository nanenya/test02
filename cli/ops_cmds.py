#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/ops_cmds.py — issue / test / template / gap / provider 서브커맨드

import asyncio
import json as _json
from typing import Optional

import typer
from rich.table import Table
from typing_extensions import Annotated

from .core import console, ORCHESTRATOR_URL

issue_app = typer.Typer(help="이슈 관리 명령어")
test_app = typer.Typer(help="테스트 파일 DB 관리 명령어")
template_app = typer.Typer(help="실행 템플릿 관리 명령어")
gap_app = typer.Typer(help="도구 부재 이력 조회")
provider_app = typer.Typer(help="LLM 프로바이더 상태 관리")


# ── issue ─────────────────────────────────────────────────────────

@issue_app.command("list")
def issue_list(
    status: Optional[str] = typer.Option(None, "--status", help="open|in_progress|resolved|ignored"),
    source: Optional[str] = typer.Option(None, "--source", help="api_server|agent|tool|cli"),
    limit: int = typer.Option(50, "--limit", help="최대 표시 개수"),
):
    """이슈 목록을 출력합니다."""
    from orchestrator import issue_tracker
    try:
        issues = issue_tracker.list_issues(status=status, source=source, limit=limit)
        if not issues:
            console.print("[yellow]조건에 맞는 이슈가 없습니다.[/yellow]")
            return
        table = Table(title="이슈 목록", show_lines=True)
        table.add_column("ID", style="bold", width=5)
        table.add_column("Severity", width=10)
        table.add_column("Status", width=12)
        table.add_column("Source", width=12)
        table.add_column("Title", width=60)
        table.add_column("Created At", width=19)
        severity_styles = {"critical": "bold red", "error": "red", "warning": "yellow"}
        for issue in issues:
            sev = issue["severity"]
            style = severity_styles.get(sev, "")
            table.add_row(
                str(issue["id"]),
                f"[{style}]{sev}[/{style}]" if style else sev,
                issue["status"],
                issue["source"],
                issue["title"][:60],
                (issue["created_at"] or "")[:19],
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]이슈 목록 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("show")
def issue_show(issue_id: int = typer.Argument(..., help="이슈 ID")):
    """이슈 상세 정보를 출력합니다."""
    from orchestrator import issue_tracker
    try:
        issue = issue_tracker.get_issue(issue_id)
        if issue is None:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]ID:[/bold] {issue['id']}")
        console.print(f"[bold]Title:[/bold] {issue['title']}")
        console.print(f"[bold]Error Type:[/bold] {issue['error_type']}")
        console.print(f"[bold]Error Message:[/bold] {issue['error_message']}")
        console.print(f"[bold]Source:[/bold] {issue['source']}")
        console.print(f"[bold]Severity:[/bold] {issue['severity']}")
        console.print(f"[bold]Status:[/bold] {issue['status']}")
        console.print(f"[bold]Context:[/bold] {issue['context']}")
        console.print(f"[bold]Created At:[/bold] {issue['created_at']}")
        console.print(f"[bold]Resolved At:[/bold] {issue['resolved_at'] or '-'}")
        console.print(f"[bold]Resolution Note:[/bold] {issue['resolution_note'] or '-'}")
        if issue["traceback"]:
            console.print("[bold]Traceback:[/bold]")
            console.print(f"[dim]{issue['traceback']}[/dim]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("resolve")
def issue_resolve(
    issue_id: int = typer.Argument(..., help="이슈 ID"),
    note: str = typer.Option("", "--note", help="해결 메모"),
):
    """이슈를 resolved 상태로 변경합니다."""
    from orchestrator import issue_tracker
    try:
        ok = issue_tracker.update_status(issue_id, "resolved", resolution_note=note)
        if ok:
            console.print(f"[green]이슈 #{issue_id}가 resolved 처리되었습니다.[/green]")
        else:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 resolve 실패: {e}[/red]")
        raise typer.Exit(1)


@issue_app.command("ignore")
def issue_ignore(issue_id: int = typer.Argument(..., help="이슈 ID")):
    """이슈를 ignored 상태로 변경합니다."""
    from orchestrator import issue_tracker
    try:
        ok = issue_tracker.update_status(issue_id, "ignored")
        if ok:
            console.print(f"[yellow]이슈 #{issue_id}가 ignored 처리되었습니다.[/yellow]")
        else:
            console.print(f"[red]이슈 #{issue_id}를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]이슈 ignore 실패: {e}[/red]")
        raise typer.Exit(1)


# ── test ──────────────────────────────────────────────────────────

@test_app.command("import")
def test_import(file_path: str = typer.Argument(..., help="임포트할 테스트 파일 경로")):
    """단일 테스트 파일을 DB에 저장합니다."""
    from orchestrator import test_registry
    try:
        result = test_registry.import_test_file(file_path)
        action = "신규 저장" if result["created"] else "갱신"
        console.print(f"[green]{action}:[/green] {result['name']} ({result['file_path']})")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]임포트 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("import-all")
def test_import_all():
    """orchestrator/ 디렉토리의 test_*.py 파일을 모두 DB에 저장합니다."""
    from orchestrator import test_registry
    try:
        results = test_registry.import_all()
        if not results:
            console.print("[yellow]임포트할 테스트 파일이 없습니다.[/yellow]")
            return
        for result in results:
            if "error" in result:
                console.print(f"[red]오류:[/red] {result['name']} — {result['error']}")
            else:
                action = "신규" if result["created"] else "갱신"
                console.print(f"[green]{action}:[/green] {result['name']}")
    except Exception as e:
        console.print(f"[red]일괄 임포트 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("list")
def test_list():
    """DB에 저장된 테스트 목록을 표시합니다."""
    from orchestrator import test_registry
    try:
        tests = test_registry.list_tests()
        if not tests:
            console.print("[yellow]저장된 테스트가 없습니다.[/yellow]")
            return
        table = Table(title="테스트 목록", show_lines=True)
        table.add_column("ID", style="bold", width=5)
        table.add_column("Name", width=40)
        table.add_column("Status", width=10)
        table.add_column("Lines", width=7)
        table.add_column("Updated At", width=19)
        status_styles = {"passed": "green", "failed": "red", "untested": "yellow"}
        for t in tests:
            st = t["status"]
            style = status_styles.get(st, "")
            lines = str(len(t["code"].splitlines()))
            table.add_row(
                str(t["id"]),
                t["name"],
                f"[{style}]{st}[/{style}]" if style else st,
                lines,
                (t["updated_at"] or "")[:19],
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]목록 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("show")
def test_show(name: str = typer.Argument(..., help="테스트 이름 (파일명 stem)")):
    """저장된 테스트 코드를 출력합니다."""
    from orchestrator import test_registry
    try:
        test = test_registry.get_test(name)
        if test is None:
            console.print(f"[red]테스트 '{name}'를 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]Name:[/bold] {test['name']}")
        console.print(f"[bold]File:[/bold] {test['file_path']}")
        console.print(f"[bold]Status:[/bold] {test['status']}")
        if test["last_output"]:
            console.print("[bold]Last Output:[/bold]")
            console.print(f"[dim]{test['last_output'][:500]}[/dim]")
        console.print("[bold]Code:[/bold]")
        console.print(f"[dim]{test['code']}[/dim]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]테스트 조회 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("run")
def test_run(name: str = typer.Argument(..., help="실행할 테스트 이름")):
    """특정 테스트를 실행합니다."""
    from orchestrator import test_registry
    try:
        console.print(f"[cyan]실행 중: {name}...[/cyan]")
        result = test_registry.run_test(name)
        if "error" in result:
            console.print(f"[red]오류: {result['error']}[/red]")
            raise typer.Exit(1)
        if result["status"] == "passed":
            console.print(f"[green]통과: {result['name']}[/green]")
        else:
            console.print(f"[red]실패: {result['name']}[/red]")
        console.print(result["output"])
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]테스트 실행 실패: {e}[/red]")
        raise typer.Exit(1)


@test_app.command("run-all")
def test_run_all():
    """저장된 모든 테스트를 실행하고 요약을 출력합니다."""
    from orchestrator import test_registry
    try:
        results = test_registry.run_all()
        if not results:
            console.print("[yellow]실행할 테스트가 없습니다.[/yellow]")
            return
        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") == "failed"]
        table = Table(title="전체 테스트 실행 결과", show_lines=True)
        table.add_column("Name", width=40)
        table.add_column("Status", width=10)
        for r in results:
            st = r.get("status", "error")
            style = "green" if st == "passed" else "red"
            table.add_row(r.get("name", "?"), f"[{style}]{st}[/{style}]")
        console.print(table)
        console.print(f"\n[green]통과: {len(passed)}[/green]  [red]실패: {len(failed)}[/red]")
    except Exception as e:
        console.print(f"[red]전체 실행 실패: {e}[/red]")
        raise typer.Exit(1)


# ── template ──────────────────────────────────────────────────────

@template_app.command("list")
def template_list(
    active_only: bool = typer.Option(False, "--active", "-a", help="활성 템플릿만 표시"),
    limit: int = typer.Option(30, "--limit", "-n", help="최대 출력 수"),
) -> None:
    """실행 템플릿 목록을 조회합니다."""
    from orchestrator.pipeline_db import list_templates, init_db
    init_db()
    templates = list_templates(active_only=active_only, limit=limit)
    if not templates:
        console.print("[yellow]템플릿이 없습니다.[/yellow]")
        return
    table = Table(title=f"실행 템플릿 목록 ({len(templates)}개)", show_lines=True)
    table.add_column("ID", width=5)
    table.add_column("이름", width=35)
    table.add_column("성공", width=6, justify="right")
    table.add_column("실패", width=6, justify="right")
    table.add_column("활성", width=5, justify="center")
    table.add_column("최근 사용", width=18)
    for t in templates:
        active_mark = "[green]✓[/green]" if t.get("is_active") else "[red]✗[/red]"
        table.add_row(
            str(t["id"]),
            t.get("name", "")[:34],
            str(t.get("success_count", 0)),
            str(t.get("fail_count", 0)),
            active_mark,
            (t.get("last_used_at") or "")[:16],
        )
    console.print(table)


@template_app.command("show")
def template_show(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿 상세 정보를 출력합니다."""
    from orchestrator.pipeline_db import get_template, init_db
    init_db()
    t = get_template(template_id)
    if not t:
        console.print(f"[red]템플릿 {template_id}를 찾을 수 없습니다.[/red]")
        raise typer.Exit(1)
    console.print(f"\n[bold cyan]템플릿 #{t['id']}[/bold cyan]: {t['name']}")
    console.print(f"  설명   : {t.get('description', '')}")
    console.print(f"  키워드 : {', '.join(t.get('keywords', []))}")
    console.print(f"  성공/실패: {t.get('success_count', 0)} / {t.get('fail_count', 0)}")
    console.print(f"  활성   : {'예' if t.get('is_active') else '아니오'}")
    console.print(f"  최근 사용: {t.get('last_used_at', '-')}")
    console.print("\n[bold]실행 그룹:[/bold]")
    console.print(_json.dumps(t.get("execution_group", {}), ensure_ascii=False, indent=2))


@template_app.command("stats")
def template_stats() -> None:
    """템플릿 통계를 출력합니다."""
    from orchestrator.pipeline_db import get_template_stats, init_db
    init_db()
    s = get_template_stats()
    console.print("\n[bold cyan]── 실행 템플릿 통계 ──[/bold cyan]")
    console.print(f"  전체 템플릿  : {s['total_templates']}개")
    console.print(f"  활성         : {s['active_templates']}개")
    console.print(f"  비활성       : {s['disabled_templates']}개")
    console.print(f"  총 성공 실행 : {s['total_success_executions']}회")
    console.print(f"  총 실패 실행 : {s['total_fail_executions']}회")
    console.print(f"  성공률       : {s['success_rate']*100:.1f}%")
    console.print(f"  계획 캐시 항목: {s['plan_cache_entries']}개")
    console.print(f"  계획 캐시 히트: {s['plan_cache_hits']}회")


@template_app.command("disable")
def template_disable(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿을 비활성화합니다."""
    from orchestrator.pipeline_db import disable_template, init_db
    init_db()
    disable_template(template_id)
    console.print(f"[yellow]템플릿 {template_id} 비활성화됨.[/yellow]")


@template_app.command("enable")
def template_enable(template_id: int = typer.Argument(..., help="템플릿 ID")) -> None:
    """템플릿을 활성화합니다."""
    from orchestrator.pipeline_db import enable_template, init_db
    init_db()
    enable_template(template_id)
    console.print(f"[green]템플릿 {template_id} 활성화됨.[/green]")


@template_app.command("delete")
def template_delete(
    template_id: int = typer.Argument(..., help="템플릿 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 없이 삭제"),
) -> None:
    """템플릿을 삭제합니다."""
    from orchestrator.pipeline_db import delete_template, init_db
    init_db()
    if not yes:
        if not typer.confirm(f"템플릿 {template_id}를 삭제하시겠습니까?"):
            console.print("[yellow]취소됨.[/yellow]")
            return
    delete_template(template_id)
    console.print(f"[red]템플릿 {template_id} 삭제됨.[/red]")


# ── gap ───────────────────────────────────────────────────────────

@gap_app.command("report")
def gap_report(limit: int = typer.Option(20, "--limit", "-n", help="최대 출력 수")) -> None:
    """도구 부재 이력을 조회합니다."""
    from orchestrator.tool_discoverer import get_gap_report
    from orchestrator.pipeline_db import init_db
    init_db()
    rows = get_gap_report(limit=limit)
    if not rows:
        console.print("[yellow]도구 부재 이력이 없습니다.[/yellow]")
        return
    table = Table(title=f"도구 부재 이력 (최근 {limit}건)", show_lines=True)
    table.add_column("도구", width=30)
    table.add_column("해결 방법", width=18)
    table.add_column("MCP 서버", width=25)
    table.add_column("구현 ID", width=8)
    table.add_column("시각", width=18)
    for r in rows:
        table.add_row(
            r.get("required_tool", ""),
            r.get("resolution_type", ""),
            r.get("mcp_server_name", "-"),
            str(r.get("func_id") or "-"),
            (r.get("created_at") or "")[:16],
        )
    console.print(table)


@gap_app.command("discover")
def gap_discover(
    tool: str = typer.Argument(..., help="발견할 도구 이름"),
    context: str = typer.Option("", "--context", "-c", help="도구 용도 설명"),
) -> None:
    """특정 도구를 MCP 탐색 → Python 자동 구현 순으로 해결합니다.

    사용자 확인 후 진행합니다.
    """
    from orchestrator.tool_discoverer import discover_and_resolve
    from orchestrator.pipeline_db import init_db
    init_db()
    console.print(f"\n[bold]도구 발견 시도:[/bold] {tool}")
    console.print(f"  컨텍스트: {context or '(없음)'}")
    if not typer.confirm("진행하시겠습니까?"):
        console.print("[yellow]취소됨.[/yellow]")
        return
    results = asyncio.run(discover_and_resolve([tool], context=context))
    r = results.get(tool, {})
    status = r.get("status", "failed")
    if status == "found":
        console.print(f"[green]이미 등록된 도구 발견: {r.get('resolved_name')}[/green]")
    elif status == "npm_found":
        console.print(f"[cyan]npm MCP 서버 발견: {r.get('npm_package')}[/cyan]")
        console.print(f"  설명: {r.get('description', '')}")
        console.print("  → [dim]python main.py mcp add[/dim] 명령으로 서버를 추가하세요.")
    elif status == "python_impl":
        console.print(f"[green]Python 구현 생성 완료: func_id={r.get('func_id')}[/green]")
        console.print("  → [dim]python main.py mcp function list[/dim] 에서 검토 후 활성화하세요.")
    else:
        console.print(f"[red]해결 실패: {tool}[/red]")


# ── provider ──────────────────────────────────────────────────────

@provider_app.command(name="status")
def provider_status():
    """LLM 프로바이더 Circuit Breaker 상태 출력 (차단 중인 프로바이더 및 재시도 시각)."""
    import httpx as _httpx
    try:
        resp = _httpx.get(f"{ORCHESTRATOR_URL}/api/v1/providers/status", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]서버 연결 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold cyan]LLM 프로바이더 상태[/bold cyan]")
    for p, info in sorted(data.items()):
        in_chain = info.get("in_fallback_chain", False)
        available = info.get("available", True)
        reason = info.get("reason", "")
        chain_tag = "[dim](폴백 체인 포함)[/dim]" if in_chain else "[dim](폴백 체인 미포함)[/dim]"
        if available:
            console.print(f"  [green]{p}[/green] {chain_tag}")
        else:
            console.print(f"  [red]{p}[/red] {chain_tag}")
            console.print(f"     [yellow]{reason}[/yellow]")
