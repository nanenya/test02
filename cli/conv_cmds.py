#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cli/conv_cmds.py — group / topic / keyword 서브커맨드

from typing import Optional
import typer
from rich.table import Table
from typing_extensions import Annotated

from orchestrator.history_manager import list_conversations, load_conversation
from .core import console

group_app = typer.Typer(help="그룹 관리 명령어")
topic_app = typer.Typer(help="토픽 관리 명령어")
keyword_app = typer.Typer(help="키워드 관리 명령어")


# ── group ─────────────────────────────────────────────────────────

@group_app.command(name="list")
def group_list():
    """그룹 목록 표시."""
    from orchestrator import graph_manager
    groups = graph_manager.list_groups()
    if not groups:
        console.print("[yellow]등록된 그룹이 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Description", "Conversations")
    for g in groups:
        table.add_row(
            str(g["id"]), g["name"], g.get("description", ""), str(g["convo_count"])
        )
    console.print(table)


@group_app.command(name="create")
def group_create(
    name: Annotated[str, typer.Argument(help="그룹 이름")],
    desc: Annotated[str, typer.Option("--desc", "-d", help="그룹 설명")] = "",
):
    """새 그룹 생성."""
    from orchestrator import graph_manager
    try:
        gid = graph_manager.create_group(name, desc)
        console.print(f"[green]그룹 '{name}' 생성됨 (ID: {gid})[/green]")
    except Exception as e:
        console.print(f"[bold red]오류: {e}[/bold red]")
        raise typer.Exit(code=1)


@group_app.command(name="delete")
def group_delete(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
):
    """그룹 삭제."""
    from orchestrator import graph_manager
    if graph_manager.delete_group(group_id):
        console.print(f"[green]그룹 {group_id} 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 그룹 {group_id}를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@group_app.command(name="add-convo")
def group_add_convo(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 그룹에 추가."""
    from orchestrator import graph_manager
    graph_manager.assign_conversation_to_group(convo_id, group_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 그룹 {group_id}에 추가되었습니다.[/green]")


@group_app.command(name="remove-convo")
def group_remove_convo(
    group_id: Annotated[int, typer.Argument(help="그룹 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 그룹에서 제거."""
    from orchestrator import graph_manager
    graph_manager.remove_conversation_from_group(convo_id, group_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 그룹 {group_id}에서 제거되었습니다.[/green]")


# ── topic ─────────────────────────────────────────────────────────

@topic_app.command(name="list")
def topic_list():
    """토픽 목록 표시."""
    from orchestrator import graph_manager
    topics = graph_manager.list_topics()
    if not topics:
        console.print("[yellow]등록된 토픽이 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Description", "Conversations", "Keywords")
    for t in topics:
        table.add_row(
            str(t["id"]), t["name"], t.get("description", ""),
            str(t["convo_count"]), str(t["keyword_count"]),
        )
    console.print(table)


@topic_app.command(name="create")
def topic_create(
    name: Annotated[str, typer.Argument(help="토픽 이름")],
    desc: Annotated[str, typer.Option("--desc", "-d", help="토픽 설명")] = "",
):
    """새 토픽 생성."""
    from orchestrator import graph_manager
    tid = graph_manager.create_topic(name, desc)
    console.print(f"[green]토픽 '{name}' 생성됨 (ID: {tid})[/green]")


@topic_app.command(name="delete")
def topic_delete(
    topic_id: Annotated[int, typer.Argument(help="토픽 ID")],
):
    """토픽 삭제."""
    from orchestrator import graph_manager
    if graph_manager.delete_topic(topic_id):
        console.print(f"[green]토픽 {topic_id} 삭제됨[/green]")
    else:
        console.print(f"[bold red]오류: 토픽 {topic_id}를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)


@topic_app.command(name="link")
def topic_link(
    id_a: Annotated[int, typer.Argument(help="토픽 ID A")],
    id_b: Annotated[int, typer.Argument(help="토픽 ID B")],
    relation: Annotated[str, typer.Option("--relation", "-r", help="관계 설명")] = "",
):
    """두 토픽을 양방향 연결."""
    from orchestrator import graph_manager
    graph_manager.link_topics(id_a, id_b, relation)
    console.print(f"[green]토픽 {id_a} ↔ {id_b} 연결됨[/green]")


@topic_app.command(name="add-convo")
def topic_add_convo(
    topic_id: Annotated[int, typer.Argument(help="토픽 ID")],
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화를 토픽에 추가."""
    from orchestrator import graph_manager
    graph_manager.assign_conversation_to_topic(convo_id, topic_id)
    console.print(f"[green]대화 {convo_id[:8]}...가 토픽 {topic_id}에 추가되었습니다.[/green]")


# ── keyword ───────────────────────────────────────────────────────

@keyword_app.command(name="list")
def keyword_list(
    convo_id: Annotated[Optional[str], typer.Argument(help="대화 UUID (생략 시 전체)")] = None,
):
    """키워드 목록 표시. 대화 UUID를 지정하면 해당 대화의 키워드만 표시."""
    from orchestrator import graph_manager
    kws = graph_manager.list_keywords(convo_id)
    if not kws:
        console.print("[yellow]키워드가 없습니다.[/yellow]")
        return
    table = Table("ID", "Name", "Usage Count")
    for k in kws:
        table.add_row(str(k["id"]), k["name"], str(k["usage_count"]))
    console.print(table)


@keyword_app.command(name="edit")
def keyword_edit(
    convo_id: Annotated[str, typer.Argument(help="대화 UUID")],
):
    """대화의 키워드를 수동으로 편집합니다."""
    from orchestrator import graph_manager
    data = load_conversation(convo_id)
    if not data:
        console.print(f"[bold red]오류: 대화 '{convo_id}'를 찾을 수 없습니다.[/bold red]")
        raise typer.Exit(code=1)
    current_kws = graph_manager.list_keywords(convo_id)
    current_names = [k["name"] for k in current_kws]
    console.print(f"현재 키워드: {', '.join(current_names) if current_names else '(없음)'}")
    new_input = typer.prompt("새 키워드를 입력하세요 (쉼표로 구분)")
    new_names = [k.strip() for k in new_input.split(",") if k.strip()]
    if not new_names:
        console.print("[yellow]키워드가 입력되지 않았습니다. 변경하지 않습니다.[/yellow]")
        return
    graph_manager.update_conversation_keywords(convo_id, new_names)
    console.print(f"[green]키워드 업데이트 완료: {', '.join(new_names)}[/green]")


@keyword_app.command(name="search")
def keyword_search(
    keyword: Annotated[str, typer.Argument(help="검색할 키워드")],
):
    """키워드로 대화를 검색합니다."""
    convos = list_conversations(keyword=keyword)
    if not convos:
        console.print(f"[yellow]'{keyword}' 키워드를 가진 대화가 없습니다.[/yellow]")
        return
    table = Table("ID", "Title", "Last Updated", "Keywords")
    for c in convos:
        kw_str = ", ".join(c.get("keywords", [])[:5])
        table.add_row(c["id"][:8] + "...", c["title"], c["last_updated"], kw_str)
    console.print(table)
