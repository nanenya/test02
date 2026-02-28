#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_graph_manager.py

import json
import uuid

import pytest

from orchestrator.graph_manager import (
    assign_conversation_to_group,
    assign_conversation_to_topic,
    assign_keywords_to_conversation,
    create_conversation,
    create_group,
    create_topic,
    delete_conversation,
    delete_group,
    delete_topic,
    get_linked_conversations,
    get_or_create_keyword,
    init_db,
    link_conversations,
    link_topics,
    list_conversations,
    list_groups,
    list_keywords,
    list_topics,
    load_conversation,
    migrate_json_to_sqlite,
    remove_conversation_from_group,
    save_conversation,
    split_conversation,
    update_conversation_keywords,
)


@pytest.fixture
def db(tmp_path):
    """각 테스트마다 격리된 임시 DB."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


# ─────────────────────────────────────────────────────────────────
class TestInitDb:
    def test_all_tables_exist(self, db):
        import sqlite3

        conn = sqlite3.connect(str(db))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "conversations",
            "groups",
            "topics",
            "keywords",
            "conversation_groups",
            "conversation_topics",
            "conversation_keywords",
            "topic_keywords",
            "topic_links",
            "conversation_links",
        }
        assert expected.issubset(tables)


# ─────────────────────────────────────────────────────────────────
class TestConversationCRUD:
    def test_create_and_load(self, db):
        create_conversation("abc-123", db)
        data = load_conversation("abc-123", db)
        assert data is not None
        assert data["id"] == "abc-123"
        assert data["status"] == "active"

    def test_save_new_conversation(self, db):
        cid = save_conversation("xyz", ["msg1"], "Title", [], 0, False, db)
        assert cid == "xyz"
        data = load_conversation("xyz", db)
        assert data["title"] == "Title"
        assert data["history"] == ["msg1"]

    def test_save_updates_existing(self, db):
        save_conversation("xyz", ["msg1"], "Old", [], 0, False, db)
        save_conversation("xyz", ["msg1", "msg2"], "New", [], 0, False, db)
        data = load_conversation("xyz", db)
        assert data["title"] == "New"
        assert len(data["history"]) == 2

    def test_is_final_sets_status(self, db):
        save_conversation("xyz", [], "Done", [], 0, True, db)
        data = load_conversation("xyz", db)
        assert data["status"] == "final"

    def test_load_nonexistent_returns_none(self, db):
        assert load_conversation("no-such-id", db) is None

    def test_list_conversations(self, db):
        save_conversation("a", [], "A", [], 0, False, db)
        save_conversation("b", [], "B", [], 0, False, db)
        convos = list_conversations(db_path=db)
        ids = [c["id"] for c in convos]
        assert "a" in ids and "b" in ids

    def test_list_filter_by_status(self, db):
        save_conversation("a", [], "A", [], 0, True, db)
        save_conversation("b", [], "B", [], 0, False, db)
        finals = list_conversations(status="final", db_path=db)
        assert len(finals) == 1
        assert finals[0]["id"] == "a"

    def test_list_filter_by_group(self, db):
        save_conversation("c1", [], "C1", [], 0, False, db)
        save_conversation("c2", [], "C2", [], 0, False, db)
        gid = create_group("G", db_path=db)
        assign_conversation_to_group("c1", gid, db)
        result = list_conversations(group_id=gid, db_path=db)
        ids = [c["id"] for c in result]
        assert "c1" in ids
        assert "c2" not in ids

    def test_list_filter_by_keyword(self, db):
        save_conversation("c1", [], "C1", [], 0, False, db)
        save_conversation("c2", [], "C2", [], 0, False, db)
        assign_keywords_to_conversation("c1", ["FastAPI"], db)
        result = list_conversations(keyword="FastAPI", db_path=db)
        ids = [c["id"] for c in result]
        assert "c1" in ids
        assert "c2" not in ids

    def test_delete_conversation(self, db):
        save_conversation("del", [], "Del", [], 0, False, db)
        assert delete_conversation("del", db)
        assert load_conversation("del", db) is None

    def test_delete_nonexistent_returns_false(self, db):
        assert not delete_conversation("ghost", db)


# ─────────────────────────────────────────────────────────────────
class TestGroupCRUD:
    def test_create_and_list(self, db):
        gid = create_group("GroupA", "desc", db)
        assert gid > 0
        groups = list_groups(db)
        names = [g["name"] for g in groups]
        assert "GroupA" in names

    def test_assign_and_list_with_count(self, db):
        gid = create_group("G1", db_path=db)
        save_conversation("c1", [], "C1", [], 0, False, db)
        assign_conversation_to_group("c1", gid, db)
        groups = list_groups(db)
        g = next(g for g in groups if g["id"] == gid)
        assert g["convo_count"] == 1

    def test_remove_conversation_from_group(self, db):
        gid = create_group("G2", db_path=db)
        save_conversation("c1", [], "C", [], 0, False, db)
        assign_conversation_to_group("c1", gid, db)
        remove_conversation_from_group("c1", gid, db)
        groups = list_groups(db)
        g = next(g for g in groups if g["id"] == gid)
        assert g["convo_count"] == 0

    def test_duplicate_group_name_raises(self, db):
        create_group("Dup", db_path=db)
        with pytest.raises(Exception):
            create_group("Dup", db_path=db)

    def test_delete_group(self, db):
        gid = create_group("Del", db_path=db)
        assert delete_group(gid, db)
        groups = list_groups(db)
        assert not any(g["id"] == gid for g in groups)


# ─────────────────────────────────────────────────────────────────
class TestKeywordCRUD:
    def test_get_or_create_idempotent(self, db):
        kid1 = get_or_create_keyword("Python", db)
        kid2 = get_or_create_keyword("Python", db)
        assert kid1 == kid2

    def test_assign_and_list(self, db):
        save_conversation("c1", [], "C", [], 0, False, db)
        assign_keywords_to_conversation("c1", ["FastAPI", "SQLite"], db)
        kws = list_keywords("c1", db)
        names = [k["name"] for k in kws]
        assert "FastAPI" in names and "SQLite" in names

    def test_update_replaces_keywords(self, db):
        save_conversation("c1", [], "C", [], 0, False, db)
        assign_keywords_to_conversation("c1", ["Old"], db)
        update_conversation_keywords("c1", ["New1", "New2"], db)
        kws = list_keywords("c1", db)
        names = [k["name"] for k in kws]
        assert "Old" not in names
        assert "New1" in names and "New2" in names

    def test_list_all_keywords_usage_count(self, db):
        save_conversation("c1", [], "C", [], 0, False, db)
        save_conversation("c2", [], "D", [], 0, False, db)
        assign_keywords_to_conversation("c1", ["shared"], db)
        assign_keywords_to_conversation("c2", ["shared"], db)
        kws = list_keywords(db_path=db)
        shared = next(k for k in kws if k["name"] == "shared")
        assert shared["usage_count"] == 2


# ─────────────────────────────────────────────────────────────────
class TestTopicCRUD:
    def test_create_and_list(self, db):
        tid = create_topic("Python개발", db_path=db)
        assert tid > 0
        topics = list_topics(db)
        names = [t["name"] for t in topics]
        assert "Python개발" in names

    def test_assign_convo_to_topic(self, db):
        tid = create_topic("T1", db_path=db)
        save_conversation("c1", [], "C", [], 0, False, db)
        assign_conversation_to_topic("c1", tid, db)
        topics = list_topics(db)
        t = next(t for t in topics if t["id"] == tid)
        assert t["convo_count"] == 1

    def test_link_topics_bidirectional(self, db):
        tid_a = create_topic("A", db_path=db)
        tid_b = create_topic("B", db_path=db)
        link_topics(tid_a, tid_b, "related", db)
        import sqlite3

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT * FROM topic_links").fetchall()
        conn.close()
        assert len(rows) == 2

    def test_delete_topic(self, db):
        tid = create_topic("ToDel", db_path=db)
        assert delete_topic(tid, db)
        topics = list_topics(db)
        assert not any(t["id"] == tid for t in topics)


# ─────────────────────────────────────────────────────────────────
class TestSplitConversation:
    def test_split_creates_new_uuid(self, db):
        save_conversation("orig", ["a", "b", "c", "d"], "Orig", [], 0, False, db)
        orig_id, new_id = split_conversation("orig", 2, db)
        assert orig_id == "orig"
        assert new_id != "orig"
        uuid.UUID(new_id)  # 유효한 UUID여야 함

    def test_split_histories(self, db):
        save_conversation("orig", ["a", "b", "c", "d"], "Orig", [], 0, False, db)
        orig_id, new_id = split_conversation("orig", 2, db)
        orig_data = load_conversation(orig_id, db)
        new_data = load_conversation(new_id, db)
        assert orig_data["history"] == ["a", "b"]
        assert new_data["history"] == ["c", "d"]

    def test_split_registers_link(self, db):
        save_conversation("orig", ["a", "b", "c"], "Orig", [], 0, False, db)
        orig_id, new_id = split_conversation("orig", 1, db)
        linked = get_linked_conversations(new_id, "split_from", db)
        assert any(l["linked_id"] == orig_id for l in linked)

    def test_split_original_status(self, db):
        save_conversation("orig", ["a", "b"], "Orig", [], 0, False, db)
        split_conversation("orig", 1, db)
        data = load_conversation("orig", db)
        assert data["status"] == "split"

    def test_split_copies_keywords(self, db):
        save_conversation("orig", ["a", "b"], "Orig", [], 0, False, db)
        assign_keywords_to_conversation("orig", ["KW1"], db)
        orig_id, new_id = split_conversation("orig", 1, db)
        kws = list_keywords(new_id, db)
        assert any(k["name"] == "KW1" for k in kws)

    def test_split_copies_group(self, db):
        save_conversation("orig", ["a", "b"], "Orig", [], 0, False, db)
        gid = create_group("G", db_path=db)
        assign_conversation_to_group("orig", gid, db)
        orig_id, new_id = split_conversation("orig", 1, db)
        groups = list_groups(db)
        g = next(g for g in groups if g["id"] == gid)
        assert g["convo_count"] == 2

    def test_split_nonexistent_raises(self, db):
        with pytest.raises(ValueError):
            split_conversation("no-such", 1, db)


# ─────────────────────────────────────────────────────────────────
class TestConversationLinks:
    def test_link_and_get(self, db):
        save_conversation("a", [], "A", [], 0, False, db)
        save_conversation("b", [], "B", [], 0, False, db)
        link_conversations("a", "b", "related", db)
        linked = get_linked_conversations("a", db_path=db)
        assert any(l["linked_id"] == "b" for l in linked)

    def test_get_linked_with_type_filter(self, db):
        save_conversation("a", [], "A", [], 0, False, db)
        save_conversation("b", [], "B", [], 0, False, db)
        link_conversations("a", "b", "referenced_by", db)
        result = get_linked_conversations("a", "referenced_by", db)
        assert len(result) == 1
        assert result[0]["link_type"] == "referenced_by"


# ─────────────────────────────────────────────────────────────────
class TestMigrateJson:
    def test_migrates_json_to_db(self, db, tmp_path):
        history_dir = tmp_path / "hist"
        history_dir.mkdir()
        data = {
            "id": "test-convo-1",
            "title": "Test",
            "last_updated": "2025-01-01T00:00:00",
            "history": ["msg1", "msg2"],
            "plan": [],
            "current_group_index": 0,
        }
        (history_dir / "test.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        count = migrate_json_to_sqlite(history_dir, db)
        assert count == 1
        loaded = load_conversation("test-convo-1", db)
        assert loaded is not None
        assert loaded["title"] == "Test"
        assert loaded["history"] == ["msg1", "msg2"]

    def test_migrates_duplicate_skipped(self, db, tmp_path):
        history_dir = tmp_path / "hist"
        history_dir.mkdir()
        data = {
            "id": "dup-1",
            "title": "D",
            "last_updated": "2025-01-01T00:00:00",
            "history": [],
            "plan": [],
            "current_group_index": 0,
        }
        (history_dir / "dup.json").write_text(json.dumps(data), encoding="utf-8")
        migrate_json_to_sqlite(history_dir, db)
        count2 = migrate_json_to_sqlite(history_dir, db)
        assert count2 == 0

    def test_skips_invalid_json(self, db, tmp_path):
        history_dir = tmp_path / "hist"
        history_dir.mkdir()
        (history_dir / "bad.json").write_text("not valid json", encoding="utf-8")
        count = migrate_json_to_sqlite(history_dir, db)
        assert count == 0


# ─────────────────────────────────────────────────────────────────
class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_client_none_returns_empty(self, monkeypatch):
        import orchestrator.gemini_client as gc

        monkeypatch.setattr(gc, "client", None)
        from orchestrator.gemini_client import extract_keywords

        result = await extract_keywords(["msg1"])
        assert result == []


class TestDetectTopicSplit:
    @pytest.mark.asyncio
    async def test_client_none_returns_none(self, monkeypatch):
        import orchestrator.gemini_client as gc

        monkeypatch.setattr(gc, "client", None)
        from orchestrator.gemini_client import detect_topic_split

        result = await detect_topic_split(["msg1"])
        assert result is None
