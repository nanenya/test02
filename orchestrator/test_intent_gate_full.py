#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_intent_gate_full.py
"""classify_intent_full() 5-카테고리 분류 단위 테스트."""

import pytest
from unittest.mock import AsyncMock, patch

from .llm_client import classify_intent_full, classify_intent_and_category, _INTENT_CATEGORIES, _COMPLEXITY_CATEGORIES


class TestIntentCategories:
    def test_categories_set(self):
        assert "dialogue" in _INTENT_CATEGORIES
        assert "code_write" in _INTENT_CATEGORIES
        assert "file_ops" in _INTENT_CATEGORIES
        assert "web_search" in _INTENT_CATEGORIES
        assert "analysis" in _INTENT_CATEGORIES
        assert len(_INTENT_CATEGORIES) == 5


@pytest.mark.asyncio
class TestClassifyIntentFull:
    async def _call_with_mock(self, raw_response: str, query: str = "test") -> str:
        with patch(
            "orchestrator.llm_client._call_with_parse_fallback",
            new_callable=AsyncMock,
        ) as mock_fn:
            # _call_with_parse_fallback는 parser_fn 결과를 반환
            # 실제 parser 로직을 시뮬레이션
            cat = raw_response.strip().lower().split()[0] if raw_response.strip() else ""
            mock_fn.return_value = cat if cat in _INTENT_CATEGORIES else None
            result = await classify_intent_full(query)
        return result

    async def test_dialogue_category(self):
        result = await self._call_with_mock("dialogue", "오늘 날씨 어때?")
        assert result == "dialogue"

    async def test_code_write_category(self):
        result = await self._call_with_mock("code_write", "파이썬 함수 작성해줘")
        assert result == "code_write"

    async def test_file_ops_category(self):
        result = await self._call_with_mock("file_ops", "파일 삭제해줘")
        assert result == "file_ops"

    async def test_web_search_category(self):
        result = await self._call_with_mock("web_search", "최신 뉴스 검색해줘")
        assert result == "web_search"

    async def test_analysis_category(self):
        result = await self._call_with_mock("analysis", "이 코드를 분석해줘")
        assert result == "analysis"

    async def test_fallback_on_invalid(self):
        """잘못된 카테고리 응답 시 'analysis' 폴백."""
        with patch(
            "orchestrator.llm_client._call_with_parse_fallback",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = None  # 파싱 실패 시뮬레이션
            result = await classify_intent_full("테스트")
        assert result == "analysis"

    async def test_fallback_on_exception(self):
        """LLM 호출 실패 시 'analysis' 폴백."""
        with patch(
            "orchestrator.llm_client._call_with_parse_fallback",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.side_effect = RuntimeError("네트워크 오류")
            result = await classify_intent_full("테스트")
        assert result == "analysis"

    async def test_parse_strips_whitespace(self):
        """앞뒤 공백이 있어도 정상 파싱."""
        result = await self._call_with_mock("  code_write  ", "코드 작성")
        assert result == "code_write"

    async def test_parse_uppercase(self):
        """대소문자 무관 파싱."""
        result = await self._call_with_mock("DIALOGUE", "대화 테스트")
        assert result == "dialogue"


class TestPromptTemplates:
    """프롬프트 템플릿 등록 확인."""

    def test_intent_full_template_registered(self):
        from . import agent_config_manager as acm
        prompt = acm.get_prompt("classify_intent_full_user")
        assert "{user_query}" in prompt
        assert "dialogue" in prompt
        assert "code_write" in prompt
        assert "file_ops" in prompt
        assert "web_search" in prompt
        assert "analysis" in prompt

    def test_intent_system_prompts_registered(self):
        from . import agent_config_manager as acm
        for name in [
            "intent_code_write_system",
            "intent_file_ops_system",
            "intent_search_system",
            "intent_analysis_system",
            "intent_dialogue_system",
        ]:
            content = acm.get_prompt(name)
            assert len(content) > 0, f"프롬프트 '{name}'이 비어 있음"


class TestComplexityCategories:
    def test_complexity_set(self):
        assert _COMPLEXITY_CATEGORIES == {"quick", "deep", "ultrabrain", "visual"}


@pytest.mark.asyncio
class TestClassifyIntentAndCategory:
    async def _call_with_mock(self, raw_response: str, query: str = "test"):
        with patch(
            "orchestrator.llm_client._call_with_parse_fallback",
            new_callable=AsyncMock,
        ) as mock_fn:
            # _parse 함수가 None을 반환하면 기본값을 반환하도록 mock 설정
            def side_effect(log_prefix, prompt, model_pref, label, parser_fn, **kw):
                return parser_fn(raw_response)
            mock_fn.side_effect = side_effect
            return await classify_intent_and_category(query)

    async def test_valid_pair_code_deep(self):
        result = await self._call_with_mock("intent: code_write\ncomplexity: deep")
        assert result == ("code_write", "deep")

    async def test_valid_pair_dialogue_quick(self):
        result = await self._call_with_mock("intent: dialogue\ncomplexity: quick")
        assert result == ("dialogue", "quick")

    async def test_valid_pair_analysis_ultrabrain(self):
        result = await self._call_with_mock("intent: analysis\ncomplexity: ultrabrain")
        assert result == ("analysis", "ultrabrain")

    async def test_fallback_on_invalid_intent(self):
        result = await self._call_with_mock("intent: unknown\ncomplexity: deep")
        # _parse returns None → caller returns ("analysis", "deep")
        assert result == ("analysis", "deep")

    async def test_fallback_on_invalid_complexity(self):
        result = await self._call_with_mock("intent: code_write\ncomplexity: unknown")
        assert result == ("analysis", "deep")

    async def test_fallback_on_exception(self):
        with patch(
            "orchestrator.llm_client._call_with_parse_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM 오류"),
        ):
            result = await classify_intent_and_category("test query")
            assert result == ("analysis", "deep")

    async def test_case_insensitive(self):
        result = await self._call_with_mock("Intent: CODE_WRITE\nComplexity: DEEP")
        assert result == ("code_write", "deep")


class TestClassifyIntentAndCategoryTemplate:
    def test_template_registered(self):
        from . import agent_config_manager as acm
        prompt = acm.get_prompt("classify_intent_and_category_user")
        assert "{user_query}" in prompt
        assert "intent" in prompt
        assert "complexity" in prompt
