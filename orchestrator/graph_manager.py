#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/graph_manager.py
"""SQLite 기반 대화 지식 그래프 관리 모듈."""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from .constants import utcnow
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_BASE_DIR = Path(__file__).parent.parent
HISTORY_DIR = _BASE_DIR / "history"
HISTORY_DIR.mkdir(exist_ok=True)
DB_PATH = HISTORY_DIR / "conversations.db"


# ── DB 연결 / 초기화 ─────────────────────────────────────────────

@contextmanager
def get_db(path: Path = DB_PATH):
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_fts5(conn) -> None:
    """wisdom FTS5 가상 테이블 + INSERT/DELETE 트리거 생성."""
    # SQLite FTS5 지원 여부 확인
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS session_wisdom_fts USING fts5("
            "content, category, source_tool, content='session_wisdom', content_rowid='id')"
        )
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS wisdom_ai AFTER INSERT ON session_wisdom BEGIN "
            "INSERT INTO session_wisdom_fts(rowid, content, category, source_tool) "
            "VALUES (new.id, new.content, new.category, new.source_tool); END"
        )
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS wisdom_ad AFTER DELETE ON session_wisdom BEGIN "
            "INSERT INTO session_wisdom_fts(session_wisdom_fts, rowid, content, category, source_tool) "
            "VALUES ('delete', old.id, old.content, old.category, old.source_tool); END"
        )
    except Exception as e:
        logging.debug(f"FTS5 초기화 실패 (무시): {e}")


def init_db(path: Path = DB_PATH) -> None:
    """모든 테이블을 IF NOT EXISTS로 생성."""
    with get_db(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id                  TEXT PRIMARY KEY,
            title               TEXT NOT NULL DEFAULT 'Untitled',
            created_at          TEXT NOT NULL,
            last_updated        TEXT NOT NULL,
            history             TEXT NOT NULL DEFAULT '[]',
            plan                TEXT NOT NULL DEFAULT '[]',
            current_group_index INTEGER NOT NULL DEFAULT 0,
            status              TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS keywords (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS conversation_groups (
            conversation_id TEXT NOT NULL,
            group_id        INTEGER NOT NULL,
            PRIMARY KEY (conversation_id, group_id),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id)        REFERENCES groups(id)        ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversation_topics (
            conversation_id TEXT NOT NULL,
            topic_id        INTEGER NOT NULL,
            PRIMARY KEY (conversation_id, topic_id),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (topic_id)        REFERENCES topics(id)        ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversation_keywords (
            conversation_id TEXT NOT NULL,
            keyword_id      INTEGER NOT NULL,
            PRIMARY KEY (conversation_id, keyword_id),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (keyword_id)      REFERENCES keywords(id)      ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS topic_keywords (
            topic_id   INTEGER NOT NULL,
            keyword_id INTEGER NOT NULL,
            PRIMARY KEY (topic_id, keyword_id),
            FOREIGN KEY (topic_id)   REFERENCES topics(id)   ON DELETE CASCADE,
            FOREIGN KEY (keyword_id) REFERENCES keywords(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS topic_links (
            topic_id_a INTEGER NOT NULL,
            topic_id_b INTEGER NOT NULL,
            relation   TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (topic_id_a, topic_id_b),
            FOREIGN KEY (topic_id_a) REFERENCES topics(id) ON DELETE CASCADE,
            FOREIGN KEY (topic_id_b) REFERENCES topics(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversation_links (
            convo_id_a TEXT NOT NULL,
            convo_id_b TEXT NOT NULL,
            link_type  TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (convo_id_a, convo_id_b, link_type),
            FOREIGN KEY (convo_id_a) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (convo_id_b) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS session_wisdom (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT    NOT NULL,
            category        TEXT    NOT NULL,
            content         TEXT    NOT NULL,
            source_tool     TEXT    DEFAULT '',
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_wisdom_convo ON session_wisdom(conversation_id);

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            query       TEXT    NOT NULL,
            cron_expr   TEXT    NOT NULL,
            convo_id    TEXT    DEFAULT '',
            enabled     INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT    DEFAULT '',
            next_run_at TEXT    DEFAULT '',
            run_count   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL
        );
        """)
        _init_fts5(conn)


# ── 자동 초기화 ──────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    logging.warning(f"DB 자동 초기화 실패: {_e}")


# ── 마이그레이션 ─────────────────────────────────────────────────

def migrate_json_to_sqlite(
    history_dir: Path = HISTORY_DIR,
    db_path: Path = DB_PATH,
) -> int:
    """history/*.json → conversations 테이블. 파일은 보존. 마이그레이션된 수 반환."""
    migrated = 0
    for json_file in sorted(history_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"마이그레이션 건너뜀 {json_file.name}: {e}")
            continue

        convo_id = data.get("id", json_file.stem)
        title = data.get("title", "Untitled")
        last_updated = data.get("last_updated", utcnow())
        history_json = json.dumps(data.get("history", []), ensure_ascii=False)
        plan_json = json.dumps(data.get("plan", []), ensure_ascii=False)
        current_group_index = data.get("current_group_index", 0)

        with get_db(db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM conversations WHERE id=?", (convo_id,)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO conversations
                    (id, title, created_at, last_updated, history, plan,
                     current_group_index, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (convo_id, title, last_updated, last_updated,
                 history_json, plan_json, current_group_index, "final"),
            )
        migrated += 1

    return migrated


def _fetch_keywords(conn, convo_id: str) -> List[str]:
    """주어진 대화 ID에 연결된 키워드 이름 목록을 반환합니다."""
    rows = conn.execute(
        """
        SELECT k.name FROM keywords k
        JOIN conversation_keywords ck ON ck.keyword_id = k.id
        WHERE ck.conversation_id=?
        """,
        (convo_id,),
    ).fetchall()
    return [r["name"] for r in rows]


# ── 대화 CRUD ────────────────────────────────────────────────────

def create_conversation(convo_id: str, db_path: Path = DB_PATH) -> None:
    now = utcnow()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO conversations
                (id, title, created_at, last_updated, history, plan,
                 current_group_index, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (convo_id, "Untitled", now, now, "[]", "[]", 0, "active"),
        )


def save_conversation(
    convo_id: str,
    history: List[str],
    title: str = "Untitled",
    plan: Optional[List[Dict]] = None,
    current_group_index: int = 0,
    is_final: bool = False,
    db_path: Path = DB_PATH,
) -> str:
    """Upsert 대화. UUID 그대로 유지. convo_id 반환."""
    status = "final" if is_final else "active"
    now = utcnow()
    history_json = json.dumps(history, ensure_ascii=False)
    plan_json = json.dumps(plan or [], ensure_ascii=False)

    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM conversations WHERE id=?", (convo_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE conversations
                SET title=?, last_updated=?, history=?, plan=?,
                    current_group_index=?, status=?
                WHERE id=?
                """,
                (title, now, history_json, plan_json,
                 current_group_index, status, convo_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO conversations
                    (id, title, created_at, last_updated, history, plan,
                     current_group_index, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (convo_id, title, now, now, history_json, plan_json,
                 current_group_index, status),
            )
    return convo_id


def load_conversation(
    convo_id: str, db_path: Path = DB_PATH
) -> Optional[Dict[str, Any]]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id=?", (convo_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["history"] = json.loads(data["history"])
        data["plan"] = json.loads(data["plan"])
        data["keywords"] = _fetch_keywords(conn, convo_id)
        return data


def list_conversations(
    group_id: Optional[int] = None,
    keyword: Optional[str] = None,
    topic_id: Optional[int] = None,
    status: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> List[Dict[str, Any]]:
    with get_db(db_path) as conn:
        query = (
            "SELECT DISTINCT c.id, c.title, c.last_updated, c.status "
            "FROM conversations c"
        )
        joins: List[str] = []
        wheres: List[str] = []
        params: List[Any] = []

        if group_id is not None:
            joins.append(
                "JOIN conversation_groups cg ON cg.conversation_id = c.id"
            )
            wheres.append("cg.group_id = ?")
            params.append(group_id)

        if topic_id is not None:
            joins.append(
                "JOIN conversation_topics ct ON ct.conversation_id = c.id"
            )
            wheres.append("ct.topic_id = ?")
            params.append(topic_id)

        if keyword is not None:
            joins.append(
                "JOIN conversation_keywords ck2 ON ck2.conversation_id = c.id "
                "JOIN keywords kw ON kw.id = ck2.keyword_id"
            )
            wheres.append("kw.name LIKE ?")
            params.append(f"%{keyword}%")

        if status is not None:
            wheres.append("c.status = ?")
            params.append(status)

        if joins:
            query += " " + " ".join(joins)
        if wheres:
            query += " WHERE " + " AND ".join(wheres)
        query += " ORDER BY c.last_updated DESC"

        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["keywords"] = _fetch_keywords(conn, d["id"])
            result.append(d)
        return result


def delete_conversation(convo_id: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id=?", (convo_id,)
        )
        return cur.rowcount > 0


# ── 그룹 CRUD ────────────────────────────────────────────────────

def create_group(
    name: str, description: str = "", db_path: Path = DB_PATH
) -> int:
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO groups (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, now),
        )
        return cur.lastrowid


def list_groups(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT g.id, g.name, g.description, g.created_at,
                   COUNT(cg.conversation_id) AS convo_count
            FROM groups g
            LEFT JOIN conversation_groups cg ON cg.group_id = g.id
            GROUP BY g.id
            ORDER BY g.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def assign_conversation_to_group(
    convo_id: str, group_id: int, db_path: Path = DB_PATH
) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_groups "
            "(conversation_id, group_id) VALUES (?, ?)",
            (convo_id, group_id),
        )


def remove_conversation_from_group(
    convo_id: str, group_id: int, db_path: Path = DB_PATH
) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "DELETE FROM conversation_groups "
            "WHERE conversation_id=? AND group_id=?",
            (convo_id, group_id),
        )


def delete_group(group_id: int, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM groups WHERE id=?", (group_id,))
        return cur.rowcount > 0


# ── 토픽 CRUD ────────────────────────────────────────────────────

def create_topic(
    name: str, description: str = "", db_path: Path = DB_PATH
) -> int:
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO topics (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, now),
        )
        return cur.lastrowid


def list_topics(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.description, t.created_at,
                   COUNT(DISTINCT ct.conversation_id) AS convo_count,
                   COUNT(DISTINCT tk.keyword_id)      AS keyword_count
            FROM topics t
            LEFT JOIN conversation_topics ct ON ct.topic_id = t.id
            LEFT JOIN topic_keywords tk      ON tk.topic_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def assign_conversation_to_topic(
    convo_id: str, topic_id: int, db_path: Path = DB_PATH
) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_topics "
            "(conversation_id, topic_id) VALUES (?, ?)",
            (convo_id, topic_id),
        )


def link_topics(
    topic_id_a: int,
    topic_id_b: int,
    relation: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """양방향 INSERT OR IGNORE."""
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO topic_links "
            "(topic_id_a, topic_id_b, relation) VALUES (?, ?, ?)",
            (topic_id_a, topic_id_b, relation),
        )
        conn.execute(
            "INSERT OR IGNORE INTO topic_links "
            "(topic_id_a, topic_id_b, relation) VALUES (?, ?, ?)",
            (topic_id_b, topic_id_a, relation),
        )


def delete_topic(topic_id: int, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM topics WHERE id=?", (topic_id,))
        return cur.rowcount > 0


# ── 키워드 CRUD ──────────────────────────────────────────────────

def get_or_create_keyword(name: str, db_path: Path = DB_PATH) -> int:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM keywords WHERE name=?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO keywords (name) VALUES (?)", (name,))
        return cur.lastrowid


def assign_keywords_to_conversation(
    convo_id: str, keyword_names: List[str], db_path: Path = DB_PATH
) -> None:
    with get_db(db_path) as conn:
        for name in keyword_names:
            row = conn.execute("SELECT id FROM keywords WHERE name=?", (name,)).fetchone()
            kid = row["id"] if row else conn.execute(
                "INSERT INTO keywords (name) VALUES (?)", (name,)
            ).lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO conversation_keywords "
                "(conversation_id, keyword_id) VALUES (?, ?)",
                (convo_id, kid),
            )


def list_keywords(
    convo_id: Optional[str] = None, db_path: Path = DB_PATH
) -> List[Dict]:
    with get_db(db_path) as conn:
        if convo_id:
            rows = conn.execute(
                """
                SELECT k.id, k.name, COUNT(ck.conversation_id) AS usage_count
                FROM keywords k
                JOIN conversation_keywords ck ON ck.keyword_id = k.id
                WHERE ck.conversation_id = ?
                GROUP BY k.id
                ORDER BY k.name
                """,
                (convo_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT k.id, k.name, COUNT(ck.conversation_id) AS usage_count
                FROM keywords k
                LEFT JOIN conversation_keywords ck ON ck.keyword_id = k.id
                GROUP BY k.id
                ORDER BY usage_count DESC, k.name
                """
            ).fetchall()
        return [dict(r) for r in rows]


def update_conversation_keywords(
    convo_id: str, keyword_names: List[str], db_path: Path = DB_PATH
) -> None:
    """기존 키워드 연결 삭제 후 재연결."""
    with get_db(db_path) as conn:
        conn.execute(
            "DELETE FROM conversation_keywords WHERE conversation_id=?",
            (convo_id,),
        )
    assign_keywords_to_conversation(convo_id, keyword_names, db_path)


# ── 대화 간 링크 ─────────────────────────────────────────────────

def link_conversations(
    convo_id_a: str,
    convo_id_b: str,
    link_type: str,
    db_path: Path = DB_PATH,
) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_links "
            "(convo_id_a, convo_id_b, link_type) VALUES (?, ?, ?)",
            (convo_id_a, convo_id_b, link_type),
        )


def get_linked_conversations(
    convo_id: str,
    link_type: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> List[Dict]:
    with get_db(db_path) as conn:
        if link_type:
            rows = conn.execute(
                """
                SELECT cl.convo_id_b AS linked_id, cl.link_type, c.title
                FROM conversation_links cl
                JOIN conversations c ON c.id = cl.convo_id_b
                WHERE cl.convo_id_a=? AND cl.link_type=?
                UNION
                SELECT cl.convo_id_a AS linked_id, cl.link_type, c.title
                FROM conversation_links cl
                JOIN conversations c ON c.id = cl.convo_id_a
                WHERE cl.convo_id_b=? AND cl.link_type=?
                """,
                (convo_id, link_type, convo_id, link_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT cl.convo_id_b AS linked_id, cl.link_type, c.title
                FROM conversation_links cl
                JOIN conversations c ON c.id = cl.convo_id_b
                WHERE cl.convo_id_a=?
                UNION
                SELECT cl.convo_id_a AS linked_id, cl.link_type, c.title
                FROM conversation_links cl
                JOIN conversations c ON c.id = cl.convo_id_a
                WHERE cl.convo_id_b=?
                """,
                (convo_id, convo_id),
            ).fetchall()
        return [dict(r) for r in rows]


# ── 대화 분리 ────────────────────────────────────────────────────

def _copy_metadata(conn, src_id: str, dst_id: str, table: str, col: str) -> None:
    """src 대화의 메타데이터(그룹/토픽/키워드)를 dst로 복사합니다."""
    for row in conn.execute(
        f"SELECT {col} FROM {table} WHERE conversation_id=?", (src_id,)
    ).fetchall():
        conn.execute(
            f"INSERT OR IGNORE INTO {table} (conversation_id, {col}) VALUES (?, ?)",
            (dst_id, row[col]),
        )


def split_conversation(
    original_id: str,
    split_point_index: int,
    db_path: Path = DB_PATH,
) -> Tuple[str, str]:
    """
    history[:idx] → 원본 유지 (status='split')
    history[idx:] → 새 UUID 대화 생성
    그룹/토픽/키워드 복사 + split_from 링크 등록.
    Returns (original_id, new_id).
    """
    data = load_conversation(original_id, db_path)
    if not data:
        raise ValueError(f"대화 '{original_id}'를 찾을 수 없습니다.")

    history = data["history"]
    history_a = history[:split_point_index]
    history_b = history[split_point_index:]
    new_id = str(uuid.uuid4())
    now = utcnow()

    with get_db(db_path) as conn:
        # 원본 축소
        conn.execute(
            "UPDATE conversations SET history=?, last_updated=?, status='split' "
            "WHERE id=?",
            (json.dumps(history_a, ensure_ascii=False), now, original_id),
        )
        # 신규 생성
        conn.execute(
            """
            INSERT INTO conversations
                (id, title, created_at, last_updated, history, plan,
                 current_group_index, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id,
                data.get("title", "Untitled") + " (분리)",
                now,
                now,
                json.dumps(history_b, ensure_ascii=False),
                "[]",
                0,
                "active",
            ),
        )
        # 그룹/토픽/키워드 복사
        _copy_metadata(conn, original_id, new_id, "conversation_groups", "group_id")
        _copy_metadata(conn, original_id, new_id, "conversation_topics", "topic_id")
        _copy_metadata(conn, original_id, new_id, "conversation_keywords", "keyword_id")
        # split_from 링크
        conn.execute(
            "INSERT OR IGNORE INTO conversation_links "
            "(convo_id_a, convo_id_b, link_type) VALUES (?, ?, ?)",
            (new_id, original_id, "split_from"),
        )

    return original_id, new_id



# ── 그래프 뷰 / 누적 지식 — 하위 모듈 위임 (하위 호환 re-export) ─────────
from .graph_renderer import (  # noqa: E402
    get_graph_data,
    render_graph,
)
from .wisdom_store import (  # noqa: E402
    save_wisdom,
    load_wisdom,
    search_wisdom_fts,
    add_scheduled_task,
    list_scheduled_tasks,
    get_scheduled_task,
    remove_scheduled_task,
    toggle_scheduled_task,
    update_scheduled_task_run,
)

__all__ = [
    "DB_PATH", "get_db", "init_db",
    "get_graph_data", "render_graph",
    "save_wisdom", "load_wisdom", "search_wisdom_fts",
    "add_scheduled_task", "list_scheduled_tasks", "get_scheduled_task",
    "remove_scheduled_task", "toggle_scheduled_task", "update_scheduled_task_run",
]
