#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/graph_renderer.py — 대화 관계 그래프 데이터 조회 + Rich 렌더링

from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .graph_manager import DB_PATH, get_db

console = Console()


def _build_conversation_nodes(conn, convs: list) -> list:
    return [
        {"type": "conversation", "id": c["id"], "label": c["title"][:30]}
        for c in convs
    ]


def _build_group_edges(conn, convo_ids: list) -> tuple:
    nodes: List[Dict] = []
    edges: List[Dict] = []
    for g in conn.execute("SELECT id, name FROM groups").fetchall():
        nodes.append({"type": "group", "id": f"g_{g['id']}", "label": g["name"]})
        for r in conn.execute(
            "SELECT conversation_id FROM conversation_groups WHERE group_id=?",
            (g["id"],),
        ).fetchall():
            if r["conversation_id"] in convo_ids:
                edges.append({"from": f"g_{g['id']}", "to": r["conversation_id"], "type": "group"})
    return nodes, edges


def _build_topic_edges(conn, convo_ids: list) -> tuple:
    nodes: List[Dict] = []
    edges: List[Dict] = []
    for t in conn.execute("SELECT id, name FROM topics").fetchall():
        nodes.append({"type": "topic", "id": f"t_{t['id']}", "label": t["name"]})
        for r in conn.execute(
            "SELECT conversation_id FROM conversation_topics WHERE topic_id=?",
            (t["id"],),
        ).fetchall():
            if r["conversation_id"] in convo_ids:
                edges.append({"from": f"t_{t['id']}", "to": r["conversation_id"], "type": "topic"})
        for lnk in conn.execute(
            "SELECT topic_id_b, relation FROM topic_links WHERE topic_id_a=?",
            (t["id"],),
        ).fetchall():
            edges.append({
                "from": f"t_{t['id']}",
                "to": f"t_{lnk['topic_id_b']}",
                "type": "topic_link",
                "relation": lnk["relation"],
            })
    return nodes, edges


def _build_keyword_edges(conn, convo_ids: list) -> tuple:
    nodes: List[Dict] = []
    edges: List[Dict] = []
    for kw in conn.execute("SELECT id, name FROM keywords").fetchall():
        used = conn.execute(
            "SELECT conversation_id FROM conversation_keywords WHERE keyword_id=?",
            (kw["id"],),
        ).fetchall()
        refs = [r["conversation_id"] for r in used if r["conversation_id"] in convo_ids]
        if refs:
            nodes.append({"type": "keyword", "id": f"k_{kw['id']}", "label": kw["name"]})
            for cid in refs:
                edges.append({"from": f"k_{kw['id']}", "to": cid, "type": "keyword"})
    return nodes, edges


def get_graph_data(
    center_id: Optional[str] = None,
    depth: int = 2,
    db_path: Path = DB_PATH,
) -> Dict:
    """nodes/edges 딕셔너리 반환."""
    nodes: List[Dict] = []
    edges: List[Dict] = []

    with get_db(db_path) as conn:
        if center_id:
            convos = conn.execute(
                "SELECT id, title, status FROM conversations WHERE id=?",
                (center_id,),
            ).fetchall()
        else:
            convos = conn.execute(
                "SELECT id, title, status FROM conversations "
                "ORDER BY last_updated DESC LIMIT 20"
            ).fetchall()

        convo_ids = [c["id"] for c in convos]
        nodes.extend(_build_conversation_nodes(conn, convos))

        g_nodes, g_edges = _build_group_edges(conn, convo_ids)
        nodes.extend(g_nodes)
        edges.extend(g_edges)

        t_nodes, t_edges = _build_topic_edges(conn, convo_ids)
        nodes.extend(t_nodes)
        edges.extend(t_edges)

        k_nodes, k_edges = _build_keyword_edges(conn, convo_ids)
        nodes.extend(k_nodes)
        edges.extend(k_edges)

        for cid in convo_ids:
            for lnk in conn.execute(
                "SELECT convo_id_b, link_type FROM conversation_links WHERE convo_id_a=?",
                (cid,),
            ).fetchall():
                edges.append({"from": cid, "to": lnk["convo_id_b"], "type": lnk["link_type"]})

    return {"nodes": nodes, "edges": edges}


def render_graph(graph_data: Dict, center_id: Optional[str] = None) -> None:
    """Rich Panel로 그래프 출력."""
    nodes = graph_data["nodes"]
    edges = graph_data["edges"]

    icon_map = {
        "conversation": "🗨",
        "group": "📁",
        "topic": "🔵",
        "keyword": "🏷",
    }

    groups = [n for n in nodes if n["type"] == "group"]
    topics = [n for n in nodes if n["type"] == "topic"]
    keywords = [n for n in nodes if n["type"] == "keyword"]
    convos = [n for n in nodes if n["type"] == "conversation"]

    text = Text()

    if groups:
        text.append("[GROUPS]\n", style="bold cyan")
        for g in groups:
            convo_count = sum(1 for e in edges if e["from"] == g["id"] and e["type"] == "group")
            text.append(f"  {icon_map['group']} {g['label']} ({convo_count})\n")

    if topics:
        text.append("\n[TOPICS]\n", style="bold blue")
        for t in topics:
            linked_topic_ids = [e["to"] for e in edges if e["from"] == t["id"] and e["type"] == "topic_link"]
            linked_labels = [n["label"] for n in nodes if n["id"] in linked_topic_ids]
            suffix = " ──── " + " / ".join(linked_labels) if linked_labels else ""
            text.append(f"  {icon_map['topic']} {t['label']}{suffix}\n")

    if keywords:
        text.append("\n[KEYWORDS]\n", style="bold yellow")
        for kw in keywords:
            convo_refs = [e["to"] for e in edges if e["from"] == kw["id"] and e["type"] == "keyword"]
            convo_labels = [n["label"] for n in nodes if n["id"] in convo_refs]
            suffix = " ──── " + ", ".join(convo_labels) if convo_labels else ""
            text.append(f"  {icon_map['keyword']} {kw['label']}{suffix}\n")

    if convos:
        text.append("\n[CONVERSATIONS]\n", style="bold green")
        for c in convos:
            star = " ★" if c["id"] == center_id else ""
            split_tos = [e["to"] for e in edges if e["from"] == c["id"] and e["type"] == "split_from"]
            split_labels = [n["label"] for n in nodes if n["id"] in split_tos]
            split_suffix = f" → [split_from] {', '.join(split_labels)}" if split_labels else ""
            text.append(f"  {icon_map['conversation']} {c['label']}{star}{split_suffix}\n")

    text.append("\n범례: 🗨 대화  🔵 토픽  🏷 키워드  📁 그룹", style="dim")
    console.print(Panel(text, title="대화 관계 그래프", border_style="bright_blue"))
