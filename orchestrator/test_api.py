#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/api.py에 대한 단위 테스트"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from .api import app
from .models import AgentRequest, ExecutionGroup, GeminiToolCall


@pytest.fixture
def sample_group():
    return ExecutionGroup(
        group_id="group_1",
        description="테스트 그룹",
        tasks=[GeminiToolCall(tool_name="echo", arguments={"text": "hi"})]
    )


class TestDecideAndAct:
    @pytest.mark.asyncio
    async def test_new_request_returns_plan_confirmation(self, sample_group):
        """신규 사용자 입력 시 PLAN_CONFIRMATION 반환"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm, \
             patch("orchestrator.api.generate_execution_plan", new_callable=AsyncMock) as mock_plan:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = None
            mock_plan.return_value = [sample_group]
            mock_hm.save_conversation = MagicMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/decide_and_act", json={
                    "conversation_id": "test-id",
                    "history": [],
                    "user_input": "파일 목록을 보여줘"
                })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "PLAN_CONFIRMATION"

    @pytest.mark.asyncio
    async def test_empty_plan_returns_final_answer(self):
        """플래너가 빈 계획 반환 시 FINAL_ANSWER"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm, \
             patch("orchestrator.api.generate_execution_plan", new_callable=AsyncMock) as mock_plan:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = None
            mock_plan.return_value = []

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/decide_and_act", json={
                    "conversation_id": "test-id",
                    "history": [],
                    "user_input": "완료"
                })
            assert resp.status_code == 200
            assert resp.json()["status"] == "FINAL_ANSWER"


class TestExecuteGroup:
    @pytest.mark.asyncio
    async def test_no_conversation_returns_404(self):
        """존재하지 않는 대화 ID는 404"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = None

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/execute_group", json={
                    "conversation_id": "nonexistent",
                    "history": []
                })
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_execution_returns_step_executed(self, sample_group):
        """정상 실행 시 STEP_EXECUTED 반환"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = {
                "id": "test-id",
                "history": ["사용자 요청: test"],
                "plan": [sample_group.model_dump()],
                "title": "test"
            }
            mock_tr.get_tool.return_value = lambda **kwargs: "ok"
            mock_hm.save_conversation = MagicMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/execute_group", json={
                    "conversation_id": "test-id",
                    "history": []
                })
            assert resp.status_code == 200
            assert resp.json()["status"] == "STEP_EXECUTED"

    @pytest.mark.asyncio
    async def test_missing_tool_returns_error(self, sample_group):
        """도구를 찾을 수 없을 때 ERROR 반환"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = {
                "id": "test-id",
                "history": [],
                "plan": [sample_group.model_dump()],
                "title": "test"
            }
            mock_tr.get_tool.return_value = None
            mock_hm.save_conversation = MagicMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/execute_group", json={
                    "conversation_id": "test-id",
                    "history": []
                })
            assert resp.status_code == 200
            assert resp.json()["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_empty_plan_returns_400(self):
        """실행할 계획이 없으면 400"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = {
                "id": "test-id",
                "history": [],
                "plan": [],
                "title": "test"
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/agent/execute_group", json={
                    "conversation_id": "test-id",
                    "history": []
                })
            assert resp.status_code == 400
