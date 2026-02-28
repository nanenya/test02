#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrator/api.py에 대한 단위 테스트"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

import logging
from .api import (
    app,
    _validate_requirement_path,
    _validate_tool_arguments,
    _prune_history,
    _extract_first_query,
)
from .models import AgentRequest, ExecutionGroup, ToolCall
from .constants import MAX_HISTORY_ENTRIES


@pytest.fixture
def sample_group():
    return ExecutionGroup(
        group_id="group_1",
        description="테스트 그룹",
        tasks=[ToolCall(tool_name="echo", arguments={"text": "hi"})]
    )


class TestDecideAndAct:
    @pytest.mark.asyncio
    async def test_new_request_returns_plan_confirmation(self, sample_group):
        """신규 사용자 입력 시 PLAN_CONFIRMATION 반환"""
        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm, \
             patch("orchestrator.api.generate_execution_plan", new_callable=AsyncMock) as mock_plan, \
             patch("orchestrator.api.classify_intent", new_callable=AsyncMock) as mock_intent:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = None
            mock_plan.return_value = [sample_group]
            mock_hm.save_conversation = MagicMock()
            mock_intent.return_value = "task"

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
             patch("orchestrator.api.generate_execution_plan", new_callable=AsyncMock) as mock_plan, \
             patch("orchestrator.api.classify_intent", new_callable=AsyncMock) as mock_intent:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = None
            mock_plan.return_value = []
            mock_intent.return_value = "task"

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
            mock_tr.ensure_tool_server_connected = AsyncMock()
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
            mock_tr.ensure_tool_server_connected = AsyncMock()
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


# ── TestValidateRequirementPath ───────────────────────────────────

class TestValidateRequirementPath:
    def test_valid_file_returns_realpath(self, tmp_path):
        f = tmp_path / "req.md"
        f.write_text("요구사항 내용", encoding="utf-8")
        result = _validate_requirement_path(str(f))
        assert os.path.isabs(result)
        assert os.path.isfile(result)

    def test_nonexistent_raises(self, tmp_path):
        with pytest.raises(ValueError, match="일반 파일이 아닙니다"):
            _validate_requirement_path(str(tmp_path / "nonexistent.md"))

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValueError, match="일반 파일이 아닙니다"):
            _validate_requirement_path(str(tmp_path))

    def test_symlink_resolved(self, tmp_path):
        real = tmp_path / "real.md"
        real.write_text("내용", encoding="utf-8")
        link = tmp_path / "link.md"
        link.symlink_to(real)
        result = _validate_requirement_path(str(link))
        assert result == str(real.resolve())

    def test_oversized_file_raises(self, tmp_path):
        f = tmp_path / "big.md"
        f.write_bytes(b"x" * (1 * 1024 * 1024 + 1))
        with pytest.raises(ValueError, match="너무 큽니다"):
            _validate_requirement_path(str(f))

    def test_exactly_1mb_passes(self, tmp_path):
        f = tmp_path / "exact.md"
        f.write_bytes(b"x" * (1 * 1024 * 1024))
        result = _validate_requirement_path(str(f))
        assert result is not None


# ── TestValidateToolArguments ─────────────────────────────────────

class TestValidateToolArguments:
    def test_valid_args_pass(self):
        def my_tool(path: str, recursive: bool = False):
            pass
        _validate_tool_arguments(my_tool, "my_tool", {"path": "/tmp"})

    def test_unknown_arg_raises(self):
        def my_tool(path: str):
            pass
        with pytest.raises(ValueError, match="허용되지 않은 인자"):
            _validate_tool_arguments(my_tool, "my_tool", {"path": "/tmp", "injected": "evil"})

    def test_empty_args_pass(self):
        def my_tool():
            pass
        _validate_tool_arguments(my_tool, "my_tool", {})

    def test_all_params_allowed(self):
        def my_tool(a: str, b: int, c: float = 1.0):
            pass
        _validate_tool_arguments(my_tool, "my_tool", {"a": "x", "b": 1, "c": 2.0})

    def test_invalid_args_blocked_in_execute_group(self, sample_group):
        """execute_group에서 허용되지 않은 인자 사용 시 ERROR 반환"""
        injected_group = ExecutionGroup(
            group_id="group_1",
            description="인젝션 테스트",
            tasks=[ToolCall(
                tool_name="echo",
                arguments={"text": "hi", "injected_arg": "evil"}
            )]
        )

        def echo(text: str):
            return text

        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm:

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_hm.load_conversation.return_value = {
                "id": "test-id",
                "history": [],
                "plan": [injected_group.model_dump()],
                "title": "test"
            }
            mock_tr.get_tool.return_value = echo
            mock_tr.get_tool_providers.return_value = []
            mock_hm.save_conversation = MagicMock()

            import asyncio
            from httpx import AsyncClient, ASGITransport

            async def run():
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as ac:
                    return await ac.post("/agent/execute_group", json={
                        "conversation_id": "test-id",
                        "history": []
                    })

            resp = asyncio.get_event_loop().run_until_complete(run())
            assert resp.status_code == 200
            assert resp.json()["status"] == "ERROR"


# ── TestPruneHistory ──────────────────────────────────────────────

class TestPruneHistory:
    def test_no_pruning_when_under_limit(self):
        history = [f"항목 {i}" for i in range(MAX_HISTORY_ENTRIES)]
        result = _prune_history(history)
        assert len(result) == MAX_HISTORY_ENTRIES

    def test_prunes_oldest_when_over_limit(self):
        history = [f"항목 {i}" for i in range(MAX_HISTORY_ENTRIES + 10)]
        result = _prune_history(history)
        assert len(result) == MAX_HISTORY_ENTRIES
        # 최신 항목이 보존되어야 함
        assert result[-1] == f"항목 {MAX_HISTORY_ENTRIES + 9}"
        assert result[0] == f"항목 10"

    def test_empty_history_unchanged(self):
        assert _prune_history([]) == []

    def test_one_over_limit_removes_oldest(self):
        history = [f"항목 {i}" for i in range(MAX_HISTORY_ENTRIES + 1)]
        result = _prune_history(history)
        assert len(result) == MAX_HISTORY_ENTRIES
        assert "항목 0" not in result


# ── TestExtractFirstQuery ─────────────────────────────────────────

class TestExtractFirstQuery:
    def test_extracts_first_user_request(self):
        history = ["사용자 요청: 파일 목록을 보여줘", "에이전트: 처리 중"]
        assert _extract_first_query(history) == "파일 목록을 보여줘"

    def test_returns_default_when_not_found(self):
        history = ["에이전트: 이전 작업 완료", "결과: 성공"]
        assert _extract_first_query(history) == "이전 작업을 계속하세요."

    def test_empty_history_returns_default(self):
        assert _extract_first_query([]) == "이전 작업을 계속하세요."

    def test_colon_in_content_preserved(self):
        history = ["사용자 요청: http://example.com 을 분석해줘"]
        assert _extract_first_query(history) == "http://example.com 을 분석해줘"

    def test_finds_first_not_second(self):
        history = ["사용자 요청: 첫 번째 요청", "사용자 요청: 두 번째 요청"]
        assert _extract_first_query(history) == "첫 번째 요청"

    def test_non_string_entries_skipped(self):
        history = [None, 42, "사용자 요청: 유효한 요청"]
        assert _extract_first_query(history) == "유효한 요청"


# ── TestResultTruncationWarning ───────────────────────────────────

class TestResultTruncationWarning:
    @pytest.mark.asyncio
    async def test_truncation_logs_warning(self, sample_group, caplog):
        """도구 결과가 1000자 초과 시 WARNING 로그 발생"""
        long_result_group = ExecutionGroup(
            group_id="group_1",
            description="긴 결과 테스트",
            tasks=[ToolCall(tool_name="big_tool", arguments={})]
        )

        def big_tool():
            return "x" * 1500

        with patch("orchestrator.api.tool_registry") as mock_tr, \
             patch("orchestrator.api.history_manager") as mock_hm, \
             patch("orchestrator.api.mcp_db_manager"):

            mock_tr.initialize = AsyncMock()
            mock_tr.shutdown = AsyncMock()
            mock_tr.ensure_tool_server_connected = AsyncMock()
            mock_hm.load_conversation.return_value = {
                "id": "test-id",
                "history": [],
                "plan": [long_result_group.model_dump()],
                "title": "test"
            }
            mock_tr.get_tool.return_value = big_tool
            mock_tr.get_tool_providers.return_value = []
            mock_hm.save_conversation = MagicMock()

            with caplog.at_level(logging.WARNING, logger="orchestrator.api"):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as ac:
                    resp = await ac.post("/agent/execute_group", json={
                        "conversation_id": "test-id",
                        "history": []
                    })

        assert resp.status_code == 200
        assert resp.json()["status"] == "STEP_EXECUTED"
        assert any("1500자" in r.message for r in caplog.records)
