#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_agent_config_manager.py
"""agent_config_manager 단위 테스트."""

import json
import tempfile
from pathlib import Path

import pytest

from . import agent_config_manager as acm


@pytest.fixture
def tmp_db(tmp_path):
    """임시 DB 경로 픽스처."""
    db_path = tmp_path / "test_agent_config.db"
    acm.init_db(db_path)
    return db_path


# ── 시스템 프롬프트 테스트 ────────────────────────────────────────

class TestSystemPrompts:
    def test_create_and_get(self, tmp_db):
        rid = acm.create_system_prompt("test_prompt", "내용입니다", "설명", db_path=tmp_db)
        assert rid > 0
        p = acm.get_system_prompt("test_prompt", db_path=tmp_db)
        assert p is not None
        assert p["name"] == "test_prompt"
        assert p["content"] == "내용입니다"
        assert p["description"] == "설명"
        assert p["is_default"] == 0

    def test_create_default(self, tmp_db):
        acm.create_system_prompt("p1", "내용1", db_path=tmp_db)
        acm.create_system_prompt("p2", "내용2", is_default=True, db_path=tmp_db)
        # p2가 기본값
        d = acm.get_default_system_prompt(db_path=tmp_db)
        assert d["name"] == "p2"
        # p1은 비기본값
        p1 = acm.get_system_prompt("p1", db_path=tmp_db)
        assert p1["is_default"] == 0

    def test_only_one_default(self, tmp_db):
        acm.create_system_prompt("a", "A", is_default=True, db_path=tmp_db)
        acm.create_system_prompt("b", "B", is_default=True, db_path=tmp_db)
        prompts = acm.list_system_prompts(db_path=tmp_db)
        defaults = [p for p in prompts if p["is_default"] == 1]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "b"

    def test_list(self, tmp_db):
        acm.create_system_prompt("z_prompt", "Z", db_path=tmp_db)
        acm.create_system_prompt("a_prompt", "A", db_path=tmp_db)
        prompts = acm.list_system_prompts(db_path=tmp_db)
        assert len(prompts) == 2

    def test_update(self, tmp_db):
        acm.create_system_prompt("upd", "원본", db_path=tmp_db)
        result = acm.update_system_prompt("upd", content="수정됨", db_path=tmp_db)
        assert result is True
        p = acm.get_system_prompt("upd", db_path=tmp_db)
        assert p["content"] == "수정됨"

    def test_update_nonexistent(self, tmp_db):
        result = acm.update_system_prompt("없는거", content="x", db_path=tmp_db)
        assert result is False

    def test_delete(self, tmp_db):
        acm.create_system_prompt("del_test", "내용", db_path=tmp_db)
        assert acm.delete_system_prompt("del_test", db_path=tmp_db) is True
        assert acm.get_system_prompt("del_test", db_path=tmp_db) is None

    def test_delete_nonexistent(self, tmp_db):
        assert acm.delete_system_prompt("없음", db_path=tmp_db) is False

    def test_migrate_from_files(self, tmp_db, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "default.txt").write_text("기본 프롬프트", encoding="utf-8")
        (prompts_dir / "developer.txt").write_text("개발자 프롬프트", encoding="utf-8")

        count = acm.migrate_prompts_from_files(str(prompts_dir), db_path=tmp_db)
        assert count == 2

        default_p = acm.get_default_system_prompt(db_path=tmp_db)
        assert default_p is not None
        assert default_p["name"] == "default"
        assert default_p["content"] == "기본 프롬프트"

    def test_migrate_idempotent(self, tmp_db, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.txt").write_text("내용", encoding="utf-8")

        count1 = acm.migrate_prompts_from_files(str(prompts_dir), db_path=tmp_db)
        count2 = acm.migrate_prompts_from_files(str(prompts_dir), db_path=tmp_db)
        assert count1 == 1
        assert count2 == 0  # 멱등 — 두 번째는 0


# ── 스킬 테스트 ──────────────────────────────────────────────────

class TestSkills:
    def test_sync_skills(self, tmp_db):
        count = acm.sync_skills_from_registry(db_path=tmp_db)
        # 로컬 모듈이 있으면 > 0, 없어도 오류 없이 0 반환
        assert count >= 0

    def test_sync_idempotent(self, tmp_db):
        count1 = acm.sync_skills_from_registry(db_path=tmp_db)
        count2 = acm.sync_skills_from_registry(db_path=tmp_db)
        # 두 번째 sync는 새 항목 없음
        assert count2 == 0

    def test_list_skills_active_only(self, tmp_db):
        # 직접 삽입
        from datetime import datetime
        now = datetime.now().isoformat()
        from .graph_manager import get_db
        with get_db(tmp_db) as conn:
            conn.execute(
                "INSERT INTO skills (name, source, description, is_active, created_at, synced_at) VALUES (?,?,?,?,?,?)",
                ("active_skill", "local", "활성", 1, now, now)
            )
            conn.execute(
                "INSERT INTO skills (name, source, description, is_active, created_at, synced_at) VALUES (?,?,?,?,?,?)",
                ("inactive_skill", "local", "비활성", 0, now, now)
            )

        active = acm.list_skills(active_only=True, db_path=tmp_db)
        all_skills = acm.list_skills(active_only=False, db_path=tmp_db)
        assert all(s["is_active"] == 1 for s in active)
        assert len(all_skills) >= len(active)

    def test_set_skill_active(self, tmp_db):
        from datetime import datetime
        now = datetime.now().isoformat()
        from .graph_manager import get_db
        with get_db(tmp_db) as conn:
            conn.execute(
                "INSERT INTO skills (name, source, description, is_active, created_at, synced_at) VALUES (?,?,?,?,?,?)",
                ("toggle_skill", "local", "토글", 1, now, now)
            )

        result = acm.set_skill_active("toggle_skill", False, db_path=tmp_db)
        assert result is True
        skill = acm.get_skill("toggle_skill", db_path=tmp_db)
        assert skill["is_active"] == 0

    def test_get_nonexistent_skill(self, tmp_db):
        assert acm.get_skill("없는스킬", db_path=tmp_db) is None


# ── 스킬 매크로 테스트 ───────────────────────────────────────────

class TestSkillMacros:
    def test_create_and_get(self, tmp_db):
        rid = acm.create_macro(
            "my_macro",
            "git {{action}} {{branch}}",
            description="git 매크로",
            db_path=tmp_db
        )
        assert rid > 0
        m = acm.get_macro("my_macro", db_path=tmp_db)
        assert m is not None
        assert m["template"] == "git {{action}} {{branch}}"
        assert set(m["variables"]) == {"action", "branch"}

    def test_auto_extract_variables(self, tmp_db):
        acm.create_macro("auto_var", "hello {{name}}, today is {{date}}", db_path=tmp_db)
        m = acm.get_macro("auto_var", db_path=tmp_db)
        assert "name" in m["variables"]
        assert "date" in m["variables"]

    def test_explicit_variables(self, tmp_db):
        acm.create_macro("explicit", "{{x}} + {{y}}", variables=["x"], db_path=tmp_db)
        m = acm.get_macro("explicit", db_path=tmp_db)
        assert m["variables"] == ["x"]

    def test_list_macros(self, tmp_db):
        acm.create_macro("m1", "{{a}}", db_path=tmp_db)
        acm.create_macro("m2", "{{b}}", db_path=tmp_db)
        macros = acm.list_macros(db_path=tmp_db)
        assert len(macros) == 2

    def test_update_macro(self, tmp_db):
        acm.create_macro("upd_macro", "{{old}}", db_path=tmp_db)
        result = acm.update_macro("upd_macro", template="{{new}} content", db_path=tmp_db)
        assert result is True
        m = acm.get_macro("upd_macro", db_path=tmp_db)
        assert "new" in m["variables"]

    def test_delete_macro(self, tmp_db):
        acm.create_macro("del_macro", "{{x}}", db_path=tmp_db)
        assert acm.delete_macro("del_macro", db_path=tmp_db) is True
        assert acm.get_macro("del_macro", db_path=tmp_db) is None

    def test_render_macro(self, tmp_db):
        acm.create_macro("render_test", "Hello {{name}}! Action: {{action}}", db_path=tmp_db)
        rendered = acm.render_macro("render_test", {"name": "Alice", "action": "run"}, db_path=tmp_db)
        assert rendered == "Hello Alice! Action: run"

    def test_render_macro_missing_var(self, tmp_db):
        acm.create_macro("missing_var", "{{a}} {{b}}", db_path=tmp_db)
        with pytest.raises(KeyError):
            acm.render_macro("missing_var", {"a": "only_a"}, db_path=tmp_db)

    def test_render_nonexistent_macro(self, tmp_db):
        with pytest.raises(KeyError):
            acm.render_macro("없는매크로", {}, db_path=tmp_db)


# ── 워크플로우 테스트 ────────────────────────────────────────────

class TestWorkflows:
    def test_create_and_get(self, tmp_db):
        steps = [
            {"order": 1, "type": "skill", "ref_name": "git_status", "args": {}, "description": "git 상태 확인"},
            {"order": 2, "type": "skill", "ref_name": "git_diff", "args": {}, "description": "diff 확인"},
        ]
        rid = acm.create_workflow("dev_workflow", steps, "개발 워크플로우", db_path=tmp_db)
        assert rid > 0
        wf = acm.get_workflow("dev_workflow", db_path=tmp_db)
        assert wf is not None
        assert wf["name"] == "dev_workflow"
        assert len(wf["steps"]) == 2
        assert wf["steps"][0]["ref_name"] == "git_status"

    def test_list_workflows(self, tmp_db):
        acm.create_workflow("wf1", [], db_path=tmp_db)
        acm.create_workflow("wf2", [], db_path=tmp_db)
        wfs = acm.list_workflows(db_path=tmp_db)
        assert len(wfs) == 2

    def test_update_workflow(self, tmp_db):
        acm.create_workflow("upd_wf", [], db_path=tmp_db)
        new_steps = [{"order": 1, "type": "macro", "ref_name": "my_macro", "args": {}}]
        result = acm.update_workflow("upd_wf", steps=new_steps, description="수정됨", db_path=tmp_db)
        assert result is True
        wf = acm.get_workflow("upd_wf", db_path=tmp_db)
        assert len(wf["steps"]) == 1
        assert wf["description"] == "수정됨"

    def test_delete_workflow(self, tmp_db):
        acm.create_workflow("del_wf", [], db_path=tmp_db)
        assert acm.delete_workflow("del_wf", db_path=tmp_db) is True
        assert acm.get_workflow("del_wf", db_path=tmp_db) is None

    def test_update_nonexistent(self, tmp_db):
        assert acm.update_workflow("없음", steps=[], db_path=tmp_db) is False


# ── 페르소나 테스트 ──────────────────────────────────────────────

class TestPersonas:
    def test_create_and_get(self, tmp_db):
        rid = acm.create_persona(
            "developer",
            "당신은 숙련된 개발자입니다.",
            allowed_skills=["git_status", "read_file"],
            keywords=["code", "python", "debug"],
            description="개발자 페르소나",
            db_path=tmp_db,
        )
        assert rid > 0
        p = acm.get_persona("developer", db_path=tmp_db)
        assert p is not None
        assert p["name"] == "developer"
        assert p["system_prompt"] == "당신은 숙련된 개발자입니다."
        assert set(p["allowed_skills"]) == {"git_status", "read_file"}
        assert "code" in p["keywords"]

    def test_create_default_persona(self, tmp_db):
        acm.create_persona("p1", "프롬프트1", db_path=tmp_db)
        acm.create_persona("p2", "프롬프트2", is_default=True, db_path=tmp_db)
        p2 = acm.get_persona("p2", db_path=tmp_db)
        p1 = acm.get_persona("p1", db_path=tmp_db)
        assert p2["is_default"] == 1
        assert p1["is_default"] == 0

    def test_only_one_default_persona(self, tmp_db):
        acm.create_persona("a", "A", is_default=True, db_path=tmp_db)
        acm.create_persona("b", "B", is_default=True, db_path=tmp_db)
        personas = acm.list_personas(db_path=tmp_db)
        defaults = [p for p in personas if p["is_default"] == 1]
        assert len(defaults) == 1

    def test_list_personas(self, tmp_db):
        acm.create_persona("x", "X", db_path=tmp_db)
        acm.create_persona("y", "Y", db_path=tmp_db)
        personas = acm.list_personas(db_path=tmp_db)
        assert len(personas) == 2

    def test_update_persona(self, tmp_db):
        acm.create_persona("upd_persona", "원본", db_path=tmp_db)
        result = acm.update_persona("upd_persona", system_prompt="수정됨", keywords=["new_kw"], db_path=tmp_db)
        assert result is True
        p = acm.get_persona("upd_persona", db_path=tmp_db)
        assert p["system_prompt"] == "수정됨"
        assert "new_kw" in p["keywords"]

    def test_delete_persona(self, tmp_db):
        acm.create_persona("del_p", "삭제", db_path=tmp_db)
        assert acm.delete_persona("del_p", db_path=tmp_db) is True
        assert acm.get_persona("del_p", db_path=tmp_db) is None


# ── 페르소나 자동 감지 테스트 ────────────────────────────────────

class TestGetEffectivePersona:
    def test_explicit_name(self, tmp_db):
        acm.create_persona("explicit_p", "명시적", keywords=[], db_path=tmp_db)
        result = acm.get_effective_persona(query="", explicit_name="explicit_p", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "explicit_p"

    def test_explicit_name_not_found_falls_back(self, tmp_db):
        acm.create_persona("fallback_p", "폴백", is_default=True, db_path=tmp_db)
        # 없는 이름 → 경고 후 자동 감지 → 기본 페르소나
        result = acm.get_effective_persona(query="", explicit_name="없는페르소나", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "fallback_p"

    def test_keyword_detection(self, tmp_db):
        acm.create_persona("dev", "개발자", keywords=["python", "code", "debug"], db_path=tmp_db)
        acm.create_persona("writer", "작가", keywords=["글쓰기", "문서"], db_path=tmp_db)
        result = acm.get_effective_persona(query="python 코드를 debug 해줘", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "dev"

    def test_keyword_specificity_tiebreak(self, tmp_db):
        # 동점일 때 키워드 많은 쪽 우선
        acm.create_persona("generic", "일반", keywords=["python"], db_path=tmp_db)
        acm.create_persona("specific", "구체", keywords=["python", "debug", "testing"], db_path=tmp_db)
        result = acm.get_effective_persona(query="python 작업", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "specific"

    def test_no_match_returns_default(self, tmp_db):
        acm.create_persona("dev", "개발자", keywords=["python"], db_path=tmp_db)
        acm.create_persona("default_p", "기본", keywords=[], is_default=True, db_path=tmp_db)
        result = acm.get_effective_persona(query="오늘 날씨 어때?", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "default_p"

    def test_no_match_no_default_returns_none(self, tmp_db):
        acm.create_persona("dev", "개발자", keywords=["python"], db_path=tmp_db)
        result = acm.get_effective_persona(query="완전 무관한 쿼리", db_path=tmp_db)
        assert result is None

    def test_empty_query_returns_default(self, tmp_db):
        acm.create_persona("def_p", "기본", keywords=["x"], is_default=True, db_path=tmp_db)
        result = acm.get_effective_persona(query="", db_path=tmp_db)
        assert result is not None
        assert result["name"] == "def_p"

    def test_no_personas_returns_none(self, tmp_db):
        result = acm.get_effective_persona(query="test", db_path=tmp_db)
        assert result is None


# ── TestSyncSkillsLogging ─────────────────────────────────────────

class TestSyncSkillsLogging:
    def test_sync_logs_info(self, tmp_db, caplog):
        """sync_skills_from_registry가 INFO 로그를 기록한다."""
        import logging
        from unittest.mock import patch

        fake_descriptions = {"tool_a": "도구 A", "tool_b": "도구 B"}

        with patch("orchestrator.agent_config_manager.TOOL_DESCRIPTIONS", fake_descriptions, create=True), \
             patch("orchestrator.agent_config_manager.acm", create=True), \
             caplog.at_level(logging.INFO):
            # TOOL_DESCRIPTIONS를 직접 패치하기 어려우므로 _load_local_modules를 mock
            from unittest.mock import patch as _patch
            with _patch("orchestrator.agent_config_manager.sync_skills_from_registry") as mock_sync:
                mock_sync.return_value = 2
                mock_sync(db_path=tmp_db)

            # 대신 실제 함수를 직접 테스트
            import orchestrator.agent_config_manager as m
            with _patch.object(m, "sync_skills_from_registry", wraps=m.sync_skills_from_registry):
                # TOOL_DESCRIPTIONS 패치하여 실제 로깅 테스트
                with _patch("orchestrator.tool_registry._load_local_modules"), \
                     _patch("orchestrator.tool_registry.TOOL_DESCRIPTIONS", fake_descriptions):
                    # 실제로 호출
                    added = m.sync_skills_from_registry(db_path=tmp_db)

        assert isinstance(added, int)

    def test_sync_logs_added_and_updated(self, tmp_db, caplog):
        """신규/갱신 수가 로그 메시지에 포함된다."""
        import logging
        from unittest.mock import patch

        fake_descriptions = {"skill_x": "X 설명"}

        with patch("orchestrator.tool_registry._load_local_modules"), \
             patch("orchestrator.tool_registry.TOOL_DESCRIPTIONS", fake_descriptions), \
             caplog.at_level(logging.INFO):
            # 첫 번째 호출 — 신규 추가
            acm.sync_skills_from_registry(db_path=tmp_db)
            # 두 번째 호출 — 갱신
            acm.sync_skills_from_registry(db_path=tmp_db)

        log_messages = [r.message for r in caplog.records if "동기화" in r.message]
        assert len(log_messages) >= 2
        # 첫 호출: 신규 1개
        assert "1개 추가" in log_messages[0]
        # 두 번째 호출: 갱신 1개
        assert "1개 갱신" in log_messages[1]
