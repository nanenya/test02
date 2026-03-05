#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_ollama_client.py

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from . import ollama_client


def _patch_chat(content: str):
    """_ollama_chat을 주어진 content로 응답하도록 패치합니다."""
    return patch.object(
        ollama_client,
        "_ollama_chat",
        new=AsyncMock(return_value=content),
    )


# ── generate_execution_plan ───────────────────────────────────────

class TestGenerateExecutionPlan:
    @pytest.mark.asyncio
    async def test_returns_execution_group(self):
        plan_json = json.dumps([{
            "group_id": "group_1",
            "description": "파일 목록 조회",
            "tasks": [{"tool_name": "list_directory", "arguments": {"path": "."}, "model_preference": "standard"}],
        }])
        with _patch_chat(plan_json):
            result = await ollama_client.generate_execution_plan(
                user_query="파일 목록을 조회해줘",
                requirements_content="",
                history=[],
            )
        assert len(result) == 1
        assert result[0].group_id == "group_1"
        assert result[0].tasks[0].tool_name == "list_directory"

    @pytest.mark.asyncio
    async def test_returns_empty_when_done(self):
        with _patch_chat("[]"):
            result = await ollama_client.generate_execution_plan(
                user_query="파일 목록 조회", requirements_content="", history=[]
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_dict_with_tasks_field_converted(self):
        """{"tasks": [...]} 형태 응답을 ExecutionGroup으로 자동 변환합니다."""
        plan_json = json.dumps({
            "tasks": [{"tool_name": "list_directory", "arguments": {}, "model_preference": "auto"}]
        })
        with _patch_chat(plan_json):
            result = await ollama_client.generate_execution_plan(
                user_query="테스트", requirements_content="", history=[]
            )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_connect_error_raises_runtime(self):
        import httpx
        with patch.object(ollama_client, "_ollama_chat", side_effect=httpx.ConnectError("연결 실패")):
            with pytest.raises(RuntimeError, match="Ollama 서버에 연결할 수 없습니다"):
                await ollama_client.generate_execution_plan("쿼리", "", [])

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self):
        with _patch_chat("이것은 JSON이 아닙니다"):
            with pytest.raises(ValueError, match="유효한 JSON"):
                await ollama_client.generate_execution_plan("쿼리", "", [])


# ── generate_final_answer ─────────────────────────────────────────

class TestGenerateFinalAnswer:
    @pytest.mark.asyncio
    async def test_returns_stripped_answer(self):
        with _patch_chat("  최종 답변입니다.  "):
            result = await ollama_client.generate_final_answer(history=["작업 완료"])
        assert result == "최종 답변입니다."

    @pytest.mark.asyncio
    async def test_connect_error_raises_runtime(self):
        import httpx
        with patch.object(ollama_client, "_ollama_chat", side_effect=httpx.ConnectError("실패")):
            with pytest.raises(RuntimeError, match="Ollama 서버에 연결할 수 없습니다"):
                await ollama_client.generate_final_answer(history=["히스토리"])

    @pytest.mark.asyncio
    async def test_error_propagates(self):
        """예외는 상위(_call_with_fallback)로 전파되어 폴백 체인이 동작해야 함."""
        history = ["  - 실행 결과: 파일 목록: ['a.txt']"]
        with patch.object(ollama_client, "_ollama_chat", side_effect=Exception("오류")):
            with pytest.raises(Exception, match="오류"):
                await ollama_client.generate_final_answer(history=history)

    @pytest.mark.asyncio
    async def test_error_propagates_empty_history(self):
        """히스토리가 없어도 예외는 전파됨."""
        with patch.object(ollama_client, "_ollama_chat", side_effect=Exception("오류")):
            with pytest.raises(Exception, match="오류"):
                await ollama_client.generate_final_answer(history=["일반 메시지"])


# ── extract_keywords ──────────────────────────────────────────────

class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_list_response(self):
        with _patch_chat('["FastAPI", "SQLite", "Python"]'):
            result = await ollama_client.extract_keywords(history=["대화 내용"])
        assert "FastAPI" in result
        assert "SQLite" in result

    @pytest.mark.asyncio
    async def test_dict_response(self):
        with _patch_chat('{"keywords": ["ReAct", "Gemini"]}'):
            result = await ollama_client.extract_keywords(history=["대화"])
        assert "ReAct" in result

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        with patch.object(ollama_client, "_ollama_chat", side_effect=Exception("오류")):
            result = await ollama_client.extract_keywords(history=["대화"])
        assert result == []


# ── detect_topic_split ────────────────────────────────────────────

class TestDetectTopicSplit:
    @pytest.mark.asyncio
    async def test_detected_split(self):
        response = json.dumps({
            "detected": True,
            "split_index": 5,
            "reason": "주제 전환됨",
            "topic_a": "파이썬",
            "topic_b": "데이터베이스",
        })
        with _patch_chat(response):
            result = await ollama_client.detect_topic_split(history=["대화1", "대화2"])
        assert result["detected"] is True
        assert result["split_index"] == 5

    @pytest.mark.asyncio
    async def test_no_split(self):
        response = json.dumps({"detected": False})
        with _patch_chat(response):
            result = await ollama_client.detect_topic_split(history=["대화"])
        assert result["detected"] is False

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        with patch.object(ollama_client, "_ollama_chat", side_effect=Exception("오류")):
            result = await ollama_client.detect_topic_split(history=["대화"])
        assert result is None


# ── generate_title_for_conversation ──────────────────────────────

class TestGenerateTitleForConversation:
    @pytest.mark.asyncio
    async def test_returns_cleaned_title(self):
        with _patch_chat('  "파일_목록_조회"  '):
            result = await ollama_client.generate_title_for_conversation(
                history=["사용자: 파일 목록", "에이전트: 완료"]
            )
        assert result == "파일_목록_조회"

    @pytest.mark.asyncio
    async def test_short_history_returns_default(self):
        result = await ollama_client.generate_title_for_conversation(history=[])
        assert result == "새로운_대화"

    @pytest.mark.asyncio
    async def test_exception_returns_fallback(self):
        with patch.object(ollama_client, "_ollama_chat", side_effect=Exception("오류")):
            result = await ollama_client.generate_title_for_conversation(
                history=["사용자: 질문", "에이전트: 답변"]
            )
        assert result == "Untitled_Conversation"
