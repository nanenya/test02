#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/web_router.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from .api import app


# ── TestConversations ─────────────────────────────────────────────

class TestConversations:
    @pytest.mark.asyncio
    async def test_list_conversations_empty(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.list_conversations.return_value = []

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/conversations")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_conversations_with_keyword_filter(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.list_conversations.return_value = [
                {"id": "abc", "title": "test", "status": "active", "keywords": ["python"]}
            ]

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/conversations?keyword=python")
            assert resp.status_code == 200
            mock_gm.list_conversations.assert_called_once_with(
                keyword="python", status=None, group_id=None
            )

    @pytest.mark.asyncio
    async def test_get_conversation_found(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.load_conversation.return_value = {
                "id": "abc", "title": "test", "history": [], "status": "active", "keywords": []
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/conversations/abc")
            assert resp.status_code == 200
            assert resp.json()["id"] == "abc"

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.load_conversation.return_value = None

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/conversations/nonexistent")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_conversation_found(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.delete_conversation.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/conversations/abc")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self):
        with patch("orchestrator.web_router.graph_manager") as mock_gm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_gm.delete_conversation.return_value = False

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/conversations/nonexistent")
            assert resp.status_code == 404


# ── TestFunctions ─────────────────────────────────────────────────

class TestFunctions:
    @pytest.mark.asyncio
    async def test_list_functions(self):
        with patch("orchestrator.web_router.mcp_db_manager") as mock_mdb, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_mdb.list_functions.return_value = [
                {"func_name": "my_func", "module_group": "utils", "version": 1, "is_active": 1}
            ]

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/functions")
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_get_function_found(self):
        with patch("orchestrator.web_router.mcp_db_manager") as mock_mdb, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_mdb.get_active_function.return_value = {
                "func_name": "my_func", "version": 1, "code": "def my_func(): pass"
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/functions/my_func")
            assert resp.status_code == 200
            assert resp.json()["func_name"] == "my_func"

    @pytest.mark.asyncio
    async def test_get_function_not_found(self):
        with patch("orchestrator.web_router.mcp_db_manager") as mock_mdb, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_mdb.get_active_function.return_value = None

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/functions/nonexistent")
            assert resp.status_code == 404


# ── TestSettingsPrompts ───────────────────────────────────────────

class TestSettingsPrompts:
    @pytest.mark.asyncio
    async def test_list_prompts(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.list_system_prompts.return_value = [
                {"name": "default", "content": "You are helpful.", "description": ""}
            ]

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/settings/prompts")
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_create_prompt(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.create_system_prompt.return_value = 1

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/v1/settings/prompts", json={
                    "name": "test_prompt", "content": "Be helpful."
                })
            assert resp.status_code == 201
            assert resp.json()["name"] == "test_prompt"

    @pytest.mark.asyncio
    async def test_update_prompt_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.update_system_prompt.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put("/api/v1/settings/prompts/test_prompt", json={
                    "content": "Updated content."
                })
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_update_prompt_not_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.update_system_prompt.return_value = False

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put("/api/v1/settings/prompts/nonexistent", json={
                    "content": "x"
                })
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_prompt_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.delete_system_prompt.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/settings/prompts/test_prompt")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True


# ── TestSettingsSkills ────────────────────────────────────────────

class TestSettingsSkills:
    @pytest.mark.asyncio
    async def test_list_skills(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.list_skills.return_value = [
                {"name": "read_file", "is_active": 1, "description": "파일 읽기"}
            ]

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/settings/skills")
            assert resp.status_code == 200
            mock_acm.list_skills.assert_called_once_with(active_only=False)

    @pytest.mark.asyncio
    async def test_toggle_skill_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.set_skill_active.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/v1/settings/skills/read_file/toggle", json={"active": False})
            assert resp.status_code == 200
            assert resp.json()["active"] is False

    @pytest.mark.asyncio
    async def test_toggle_skill_not_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.set_skill_active.return_value = False

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/v1/settings/skills/nonexistent/toggle", json={"active": True})
            assert resp.status_code == 404


# ── TestSettingsPersonas ──────────────────────────────────────────

class TestSettingsPersonas:
    @pytest.mark.asyncio
    async def test_list_personas(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.list_personas.return_value = [
                {"name": "dev", "system_prompt": "You are a developer.", "keywords": [], "allowed_skills": []}
            ]

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/settings/personas")
            assert resp.status_code == 200
            assert resp.json()[0]["name"] == "dev"

    @pytest.mark.asyncio
    async def test_create_persona(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.create_persona.return_value = 1

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/v1/settings/personas", json={
                    "name": "dev", "system_prompt": "You are a developer."
                })
            assert resp.status_code == 201
            assert resp.json()["name"] == "dev"

    @pytest.mark.asyncio
    async def test_delete_persona_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.delete_persona.return_value = True

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/settings/personas/dev")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_persona_not_found(self):
        with patch("orchestrator.web_router.agent_config_manager") as mock_acm, \
             patch("orchestrator.api.tool_registry") as mock_tr:
            mock_tr.initialize = MagicMock()
            mock_tr.shutdown = MagicMock()
            mock_acm.delete_persona.return_value = False

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/settings/personas/nonexistent")
            assert resp.status_code == 404
