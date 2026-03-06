#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/mcp_cmds.py — mcp / mcp function 서브커맨드

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.syntax import Syntax
from rich.table import Table
from typing_extensions import Annotated

from orchestrator import mcp_manager
from .core import console

mcp_app = typer.Typer(help="MCP 서버 관리 명령어")
func_app = typer.Typer(help="MCP 함수 DB 관리 명령어")
mcp_app.add_typer(func_app, name="function")


# ── mcp 서버 관리 ─────────────────────────────────────────────────

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
            s["name"], s.get("package", ""), s.get("package_manager", ""),
            enabled, s.get("description", ""),
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


@mcp_app.command(name="stats")
def mcp_stats(
    func: Annotated[Optional[str], typer.Option("--func", "-f", help="특정 함수 이름")] = None,
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 필터")] = None,
):
    """MCP 함수 실행 통계를 표시합니다."""
    from orchestrator import mcp_db_manager
    stats = mcp_db_manager.get_usage_stats(func_name=func, module_group=group)
    if stats["total_calls"] == 0:
        console.print("[yellow]실행 기록이 없습니다.[/yellow]")
        return
    console.print(f"[bold]전체 호출:[/bold] {stats['total_calls']}")
    console.print(f"[bold]성공률:[/bold] {stats['success_rate']:.1%}")
    console.print(f"[bold]평균 실행시간:[/bold] {stats['avg_duration_ms']:.1f}ms")
    if stats["by_function"]:
        table = Table("Function", "Calls", "Success Rate", "Avg ms")
        for fn, fstats in sorted(stats["by_function"].items()):
            table.add_row(
                fn, str(fstats["total_calls"]),
                f"{fstats['success_rate']:.1%}", f"{fstats['avg_duration_ms']:.1f}",
            )
        console.print(table)


# ── mcp function 관리 ─────────────────────────────────────────────

@func_app.command(name="add")
def func_add(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    group: Annotated[str, typer.Option("--group", "-g", help="모듈 그룹")] = "default",
    code: Annotated[Optional[str], typer.Option("--code", help="코드 파일 경로")] = None,
    test: Annotated[Optional[str], typer.Option("--test", help="테스트 코드 파일 경로")] = None,
    source_type: Annotated[str, typer.Option("--source-type", help="출처 유형 (internal|external)")] = "internal",
    source_url: Annotated[str, typer.Option("--source-url", help="출처 URL")] = "",
):
    """함수를 DB에 등록합니다."""
    from orchestrator import mcp_db_manager
    func_code = ""
    if code:
        try:
            func_code = Path(code).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold red]코드 파일 읽기 실패: {e}[/bold red]")
            raise typer.Exit(code=1)
    else:
        func_code = typer.prompt("함수 코드를 입력하세요 (EOF로 종료)")

    test_code = ""
    if test:
        try:
            test_code = Path(test).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold yellow]테스트 파일 읽기 실패 (무시): {e}[/bold yellow]")

    result = mcp_db_manager.register_function(
        func_name=name, module_group=group, code=func_code,
        test_code=test_code, source_type=source_type, source_url=source_url,
    )
    status = "[green]활성화됨[/green]" if result.get("activated") else "[yellow]테스트 실패 (비활성)[/yellow]"
    console.print(f"함수 '{name}' 등록됨 (v{result['version']}, 테스트: {result['test_status']}, {status})")


@func_app.command(name="list")
def func_list(
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 필터")] = None,
    all_versions: Annotated[bool, typer.Option("--all", "-a", help="비활성 버전도 포함")] = False,
):
    """등록된 함수 목록을 표시합니다."""
    from orchestrator import mcp_db_manager
    funcs = mcp_db_manager.list_functions(module_group=group, active_only=not all_versions)
    if not funcs:
        console.print("[yellow]등록된 함수가 없습니다.[/yellow]")
        return
    table = Table("Name", "Group", "Version", "Active", "Test", "Description")
    for f in funcs:
        active = "[green]Yes[/green]" if f["is_active"] else "[dim]No[/dim]"
        table.add_row(
            f["func_name"], f["module_group"], str(f["version"]),
            active, f["test_status"], f["description"][:50],
        )
    console.print(table)


@func_app.command(name="versions")
def func_versions(
    name: Annotated[str, typer.Argument(help="함수 이름")],
):
    """함수의 버전 이력을 표시합니다."""
    from orchestrator import mcp_db_manager
    versions = mcp_db_manager.get_function_versions(name)
    if not versions:
        console.print(f"[yellow]'{name}' 함수를 찾을 수 없습니다.[/yellow]")
        return
    table = Table("Version", "Active", "Test", "Created", "Activated")
    for v in versions:
        active = "[green]Yes[/green]" if v["is_active"] else "[dim]No[/dim]"
        table.add_row(
            str(v["version"]), active, v["test_status"],
            v["created_at"][:19], (v["activated_at"] or "")[:19],
        )
    console.print(table)


@func_app.command(name="show")
def func_show(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (생략 시 활성 버전)")] = None,
):
    """함수 상세 정보 및 코드를 출력합니다."""
    from orchestrator import mcp_db_manager
    if version:
        versions = mcp_db_manager.get_function_versions(name)
        func = next((v for v in versions if v["version"] == version), None)
    else:
        func = mcp_db_manager.get_active_function(name)

    if not func:
        console.print(f"[bold red]오류: 함수 '{name}' (v{version})을 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]이름:[/bold] {func['func_name']}")
    console.print(f"[bold]그룹:[/bold] {func['module_group']}")
    console.print(f"[bold]버전:[/bold] {func['version']}")
    console.print(f"[bold]활성:[/bold] {'예' if func['is_active'] else '아니오'}")
    console.print(f"[bold]테스트:[/bold] {func['test_status']}")
    console.print(f"[bold]설명:[/bold] {func['description']}")
    if func.get("source_url"):
        console.print(f"[bold]출처:[/bold] {func['source_type']} — {func['source_url']}")
    console.print(f"[bold]코드:[/bold]\n{func['code']}")


@func_app.command(name="test")
def func_test(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (생략 시 활성 버전)")] = None,
):
    """함수 테스트를 실행합니다."""
    from orchestrator import mcp_db_manager
    if version is None:
        func = mcp_db_manager.get_active_function(name)
        if not func:
            console.print(f"[bold red]오류: 활성 버전이 없습니다.[/bold red]")
            raise typer.Exit(code=1)
        version = func["version"]
    console.print(f"[cyan]테스트 실행 중: {name} v{version}...[/cyan]")
    result = mcp_db_manager.run_function_tests(name, version)
    if result["test_status"] == "passed":
        console.print(f"[green]테스트 통과[/green]")
    else:
        console.print(f"[bold red]테스트 실패[/bold red]")
    if result.get("test_output"):
        console.print(result["test_output"])


@func_app.command(name="import")
def func_import(
    file: Annotated[str, typer.Argument(help="임포트할 Python 파일 경로")],
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="모듈 그룹 (기본: 파일명)")] = None,
    test_file: Annotated[Optional[str], typer.Option("--test-file", "-t", help="테스트 파일 경로")] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="테스트 실행 건너뜀")] = False,
):
    """Python 파일의 함수들을 DB로 일괄 임포트합니다."""
    from orchestrator import mcp_db_manager
    console.print(f"[cyan]임포트 중: {file}...[/cyan]")
    result = mcp_db_manager.import_from_file(
        file_path=file, module_group=group,
        test_file_path=test_file, run_tests=not no_tests,
    )
    console.print(f"[green]임포트 완료: {result['imported_functions']}개 함수[/green]")
    if result["failed"]:
        console.print(f"[bold red]실패: {len(result['failed'])}개[/bold red]")
        for f in result["failed"]:
            console.print(f"  - {f}")


@func_app.command(name="update")
def func_update(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    code: Annotated[str, typer.Option("--code", help="새 코드 파일 경로")],
    test: Annotated[Optional[str], typer.Option("--test", help="새 테스트 코드 파일 경로 (미지정 시 기존 테스트 유지)")] = None,
    no_tests: Annotated[bool, typer.Option("--no-tests", help="테스트 실행 건너뜀")] = False,
):
    """함수 코드를 업데이트합니다 (새 버전으로 등록).

    기존 활성 버전의 테스트 코드를 새 버전에도 그대로 이어받습니다.
    --test 로 새 테스트 파일을 지정하면 교체됩니다.
    """
    from orchestrator import mcp_db_manager
    current = mcp_db_manager.get_active_function(name)
    if not current:
        console.print(f"[bold red]오류: '{name}' 함수를 찾을 수 없습니다. 'add'로 먼저 등록하세요.[/bold red]")
        raise typer.Exit(code=1)

    try:
        func_code = Path(code).read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[bold red]코드 파일 읽기 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    test_code = current.get("test_code", "")
    if test:
        try:
            test_code = Path(test).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold yellow]테스트 파일 읽기 실패 (기존 테스트 유지): {e}[/bold yellow]")

    result = mcp_db_manager.register_function(
        func_name=name, module_group=current["module_group"],
        code=func_code, test_code=test_code,
        run_tests=not no_tests and bool(test_code.strip()),
    )
    if result.get("activated"):
        console.print(f"[green]'{name}' 업데이트됨 v{result['version']} — 테스트: {result['test_status']}, 활성화됨[/green]")
    else:
        console.print(f"[yellow]'{name}' v{result['version']} 등록됨 — 테스트: {result['test_status']} (비활성, 이전 버전 유지)[/yellow]")
        if result.get("test_output"):
            console.print(result["test_output"])


@func_app.command(name="edit-test")
def func_edit_test(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    file: Annotated[str, typer.Option("--file", "-f", help="테스트 코드 파일 경로")],
    version: Annotated[Optional[int], typer.Option("--version", "-v", help="버전 번호 (기본: 활성 버전)")] = None,
    no_run: Annotated[bool, typer.Option("--no-run", help="저장만 하고 테스트 실행 안 함")] = False,
):
    """함수의 테스트 코드를 업데이트하고 테스트를 실행합니다.

    새 버전을 생성하지 않고 기존 버전의 test_code만 교체합니다.
    테스트 통과 시 해당 버전을 활성화합니다.
    """
    from orchestrator import mcp_db_manager
    try:
        test_code = Path(file).read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[bold red]테스트 파일 읽기 실패: {e}[/bold red]")
        raise typer.Exit(code=1)

    result = mcp_db_manager.update_function_test_code(
        func_name=name, test_code=test_code, version=version, run_tests=not no_run,
    )
    if "error" in result:
        console.print(f"[bold red]오류: {result['error']}[/bold red]")
        raise typer.Exit(code=1)

    if no_run:
        console.print(f"[green]테스트 코드 저장됨 (v{result['version']}, 실행 안 함)[/green]")
        return

    if result.get("test_status") == "passed":
        console.print(f"[green]테스트 통과 — v{result['version']} 활성화됨[/green]")
    else:
        console.print(f"[bold red]테스트 실패 (v{result['version']})[/bold red]")
        if result.get("test_output"):
            console.print(result["test_output"])


@func_app.command(name="activate")
def func_activate(
    name: Annotated[str, typer.Argument(help="함수 이름")],
    version: Annotated[int, typer.Option("--version", "-v", help="활성화할 버전 번호")],
):
    """특정 버전을 수동으로 활성화합니다 (롤백/롤포워드)."""
    from orchestrator import mcp_db_manager
    try:
        mcp_db_manager.activate_function(name, version)
        console.print(f"[green]'{name}' v{version} 활성화됨[/green]")
    except ValueError as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@func_app.command(name="template")
def func_template(
    name: Annotated[Optional[str], typer.Argument(help="함수 이름 (지정 시 해당 함수 코드도 함께 출력)")] = None,
):
    """독립 실행형 테스트 코드 작성 가이드를 출력합니다."""
    from orchestrator import mcp_db_manager
    guide = """# ─────────────────────────────────────────────────────────────
# MCP 함수 테스트 코드 형식 (독립 실행형)
# ─────────────────────────────────────────────────────────────
#
# 테스트 실행 시 생성되는 임시 파일 구조:
#
#   ┌── [preamble] ── mcp_module_contexts.preamble_code ──────┐
#   │  import os, logging, ...                                │
#   │  CONST = ...   # 모듈 레벨 상수                         │
#   └─────────────────────────────────────────────────────────┘
#   ┌── [함수 코드] ── mcp_functions.code ────────────────────┐
#   │  def your_func(...):                                    │
#   │      ...                                                │
#   └─────────────────────────────────────────────────────────┘
#   ┌── [테스트 코드] ── mcp_functions.test_code ─────────────┐
#   │  ← 여기에 작성 (아래 규칙 준수)                          │
#   └─────────────────────────────────────────────────────────┘
#
# 규칙:
#   1. 함수는 이미 정의되어 있으므로 직접 호출 (import 불필요)
#   2. preamble의 imports/상수도 바로 사용 가능
#   3. 전역 변수 패치:
#        monkeypatch.setattr(sys.modules[__name__], 'CONST', new_val)
#   4. pytest 내장 픽스처 사용 가능: tmp_path, monkeypatch, capsys ...
#   5. @pytest.fixture 정의도 test_code 안에 포함 가능
#   6. from . import ... 같은 상대 임포트는 사용 불가
#
# ─── 예시 ─────────────────────────────────────────────────────
import pytest

class TestAdd:
    def test_basic(self):
        assert add(1, 2) == 3
# ─────────────────────────────────────────────────────────────"""

    console.print(Syntax(guide, "python", theme="monokai", line_numbers=False))

    if name:
        func = mcp_db_manager.get_active_function(name)
        if func:
            console.print(f"\n[bold cyan]── '{name}' 현재 코드 (v{func['version']}) ──[/bold cyan]")
            console.print(Syntax(func["code"], "python", theme="monokai"))
            if func["test_code"]:
                console.print(f"\n[bold cyan]── '{name}' 현재 테스트 코드 ──[/bold cyan]")
                console.print(Syntax(func["test_code"], "python", theme="monokai"))
            else:
                console.print("\n[yellow]테스트 코드 없음 — 'mcp function edit-test'로 추가하세요.[/yellow]")
        else:
            console.print(f"[yellow]'{name}' 함수를 찾을 수 없습니다.[/yellow]")
