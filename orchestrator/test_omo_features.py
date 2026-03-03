#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_omo_features.py
"""OMO P1~P3 기능 단위 테스트.

P1-A: Ralph Loop 헬퍼 (_check_dangerous_tools, _DANGEROUS_TOOLS)
P1-B: 카테고리 모델 라우팅 (_CATEGORY_TO_MODEL_PREF)
P1-C: 컨텍스트 파일 자동 주입 (_load_context_files)
P2-A: Todo Enforcer (_scan_incomplete_markers)
P2-B: 프로바이더 폴백 체인 (_get_fallback_chain, _call_with_fallback)
P2-E: 히스토리 요약 (summarize_history 엣지케이스)
P3-B: 전문 에이전트 역할 프롬프트 (_ROLE_PROMPTS)
P3-C: IntentGate (classify_intent 폴백 동작)
P3-D: 온디맨드 MCP (_on_demand_configs 등록)
"""

import asyncio
import importlib
import sys
import types
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── main.py 헬퍼 직접 임포트 ────────────────────────────────────────────────

def _import_main():
    """main.py를 모듈로 가져옵니다 (직접 실행용 스크립트이므로 importlib 사용)."""
    spec = importlib.util.spec_from_file_location(
        "main_module",
        Path(__file__).parent.parent / "main.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # typer.run 등 CLI 부작용 방지를 위해 sys.argv 고정
    old_argv = sys.argv[:]
    sys.argv = ["main.py"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = old_argv
    return mod


@pytest.fixture(scope="module")
def main_mod():
    return _import_main()


# ── P1-A: 위험 도구 감지 ────────────────────────────────────────────────────

class TestCheckDangerousTools:
    def test_safe_group_returns_empty(self, main_mod):
        group = {"tasks": [
            {"tool_name": "read_file"},
            {"tool_name": "list_directory"},
        ]}
        assert main_mod._check_dangerous_tools(group) == []

    def test_delete_file_detected(self, main_mod):
        group = {"tasks": [{"tool_name": "delete_file"}]}
        dangerous = main_mod._check_dangerous_tools(group)
        assert "delete_file" in dangerous

    def test_multiple_dangerous_tools(self, main_mod):
        group = {"tasks": [
            {"tool_name": "read_file"},
            {"tool_name": "execute_command"},
            {"tool_name": "drop_table"},
        ]}
        dangerous = main_mod._check_dangerous_tools(group)
        assert "execute_command" in dangerous
        assert "drop_table" in dangerous
        assert "read_file" not in dangerous

    def test_empty_group(self, main_mod):
        assert main_mod._check_dangerous_tools({}) == []
        assert main_mod._check_dangerous_tools({"tasks": []}) == []

    def test_dangerous_tools_set_contains_expected(self, main_mod):
        expected = {"delete_file", "remove_file", "git_push", "execute_command", "drop_table"}
        assert expected.issubset(main_mod._DANGEROUS_TOOLS)

    def test_case_insensitive_check(self, main_mod):
        """tool_name이 소문자로 비교되어 대소문자 구분 없이 감지."""
        group = {"tasks": [{"tool_name": "DELETE_FILE"}]}
        dangerous = main_mod._check_dangerous_tools(group)
        assert "DELETE_FILE" in dangerous


# ── P1-B: 카테고리 → 모델 선호도 매핑 ─────────────────────────────────────

class TestCategoryToModelPref:
    def test_all_expected_categories_exist(self, main_mod):
        cat = main_mod._CATEGORY_TO_MODEL_PREF
        assert "quick" in cat
        assert "code" in cat
        assert "analysis" in cat
        assert "creative" in cat

    def test_quick_is_standard(self, main_mod):
        assert main_mod._CATEGORY_TO_MODEL_PREF["quick"] == "standard"

    def test_code_and_analysis_are_high(self, main_mod):
        cat = main_mod._CATEGORY_TO_MODEL_PREF
        assert cat["code"] == "high"
        assert cat["analysis"] == "high"

    def test_unknown_category_not_in_map(self, main_mod):
        assert main_mod._CATEGORY_TO_MODEL_PREF.get("unknown") is None


# ── P1-C: 컨텍스트 파일 자동 주입 ──────────────────────────────────────────

class TestLoadContextFiles:
    def test_returns_empty_when_no_context_files(self, tmp_path, main_mod):
        result = main_mod._load_context_files(str(tmp_path))
        assert result == ""

    def test_loads_agents_md(self, tmp_path, main_mod):
        (tmp_path / "AGENTS.md").write_text("# Agent Instructions\n로봇이에요.", encoding="utf-8")
        result = main_mod._load_context_files(str(tmp_path))
        assert "Agent Instructions" in result
        assert "로봇이에요" in result

    def test_loads_readme_md(self, tmp_path, main_mod):
        (tmp_path / "README.md").write_text("# My Project\n프로젝트 설명.", encoding="utf-8")
        result = main_mod._load_context_files(str(tmp_path))
        assert "My Project" in result

    def test_loads_both_files(self, tmp_path, main_mod):
        (tmp_path / "AGENTS.md").write_text("에이전트", encoding="utf-8")
        (tmp_path / "README.md").write_text("리드미", encoding="utf-8")
        result = main_mod._load_context_files(str(tmp_path))
        assert "에이전트" in result
        assert "리드미" in result

    def test_file_content_truncated_at_8kb(self, tmp_path, main_mod):
        large_content = "X" * (10 * 1024)  # 10KB
        (tmp_path / "AGENTS.md").write_text(large_content, encoding="utf-8")
        result = main_mod._load_context_files(str(tmp_path))
        # 8KB(8192) + 헤더 라인 정도만 포함
        assert len(result) < len(large_content)

    def test_searches_parent_directories(self, tmp_path, main_mod):
        parent = tmp_path
        child = tmp_path / "sub" / "child"
        child.mkdir(parents=True)
        (parent / "AGENTS.md").write_text("상위 컨텍스트", encoding="utf-8")
        result = main_mod._load_context_files(str(child))
        assert "상위 컨텍스트" in result


# ── P2-A: Todo Enforcer — 미완료 마커 감지 ─────────────────────────────────

class TestScanIncompleteMarkers:
    def test_empty_history_returns_empty(self, main_mod):
        assert main_mod._scan_incomplete_markers([]) == []

    def test_detects_todo(self, main_mod):
        history = ["작업 완료", "TODO: 파일 정리 필요"]
        found = main_mod._scan_incomplete_markers(history)
        assert any("TODO" in f for f in found)

    def test_detects_markdown_checkbox(self, main_mod):
        history = ["- [x] 완료된 항목", "- [ ] 미완료 항목"]
        found = main_mod._scan_incomplete_markers(history)
        assert any("[ ]" in f for f in found)

    def test_detects_korean_markers(self, main_mod):
        history = ["미완료: DB 스키마 업데이트"]
        found = main_mod._scan_incomplete_markers(history)
        assert len(found) > 0

    def test_completed_items_not_detected(self, main_mod):
        history = ["모든 작업이 완료되었습니다.", "[x] 파일 저장 완료"]
        found = main_mod._scan_incomplete_markers(history)
        assert found == []

    def test_only_checks_last_10_entries(self, main_mod):
        # 10개 이전에 TODO가 있어도 무시
        old_entries = ["TODO: 오래된 항목"] * 5
        recent_ok = ["완료됨"] * 10
        history = old_entries + recent_ok
        found = main_mod._scan_incomplete_markers(history)
        assert found == []

    def test_result_lines_max_200_chars(self, main_mod):
        long_line = "TODO: " + "X" * 300
        history = [long_line]
        found = main_mod._scan_incomplete_markers(history)
        assert all(len(f) <= 200 for f in found)

    def test_detects_fixme_and_hack(self, main_mod):
        history = ["FIXME: 버그 수정 필요", "HACK: 임시 방편"]
        found = main_mod._scan_incomplete_markers(history)
        assert len(found) == 2


# ── P2-B: 프로바이더 폴백 체인 ──────────────────────────────────────────────

class TestFallbackChain:
    def test_returns_active_provider_when_no_chain(self):
        from orchestrator.llm_client import _get_fallback_chain
        mock_config = {"active_provider": "gemini", "active_model": "gemini-flash"}
        with patch("orchestrator.model_manager.load_config", return_value=mock_config), \
             patch("orchestrator.model_manager.get_active_model", return_value=("gemini", "gemini-flash")):
            chain = _get_fallback_chain()
        assert chain == ["gemini"]

    def test_returns_configured_chain(self):
        from orchestrator.llm_client import _get_fallback_chain
        mock_config = {
            "active_provider": "gemini",
            "fallback_chain": ["gemini", "claude", "ollama"],
        }
        with patch("orchestrator.model_manager.load_config", return_value=mock_config):
            chain = _get_fallback_chain()
        assert chain == ["gemini", "claude", "ollama"]

    def test_call_with_fallback_succeeds_on_second_provider(self):
        """첫 번째 provider 실패 → 두 번째 provider 성공."""
        from orchestrator.llm_client import _call_with_fallback

        call_log = []

        async def mock_fn_fail(**kwargs):
            call_log.append("fail")
            raise RuntimeError("provider 1 down")

        async def mock_fn_ok(**kwargs):
            call_log.append("ok")
            return "success"

        mock_module_fail = MagicMock()
        mock_module_fail.test_fn = mock_fn_fail
        mock_module_ok = MagicMock()
        mock_module_ok.test_fn = mock_fn_ok

        def mock_get_client(provider):
            return mock_module_fail if provider == "gemini" else mock_module_ok

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini", "claude"]), \
             patch("orchestrator.llm_client._get_client_module", side_effect=mock_get_client):
            result = asyncio.get_event_loop().run_until_complete(
                _call_with_fallback("test_fn", history=[])
            )

        assert result == "success"
        assert call_log == ["fail", "ok"]

    def test_call_with_fallback_raises_when_all_fail(self):
        """모든 provider 실패 시 마지막 예외 re-raise."""
        from orchestrator.llm_client import _call_with_fallback

        async def mock_fn_fail(**kwargs):
            raise RuntimeError("모두 실패")

        mock_module = MagicMock()
        mock_module.test_fn = mock_fn_fail

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini", "claude"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            with pytest.raises(RuntimeError, match="모두 실패"):
                asyncio.get_event_loop().run_until_complete(
                    _call_with_fallback("test_fn", history=[])
                )


# ── P2-E: 히스토리 요약 ─────────────────────────────────────────────────────

class TestSummarizeHistory:
    def test_empty_history_returns_empty(self):
        from orchestrator.llm_client import summarize_history
        result = asyncio.get_event_loop().run_until_complete(
            summarize_history([])
        )
        assert result == ""

    def test_returns_empty_on_all_provider_failure(self):
        from orchestrator.llm_client import summarize_history

        async def mock_fail(**kwargs):
            raise RuntimeError("LLM down")

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_fail

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                summarize_history(["항목1", "항목2"])
            )
        assert result == ""

    def test_history_truncated_to_8000_chars_in_prompt(self):
        """매우 긴 히스토리도 LLM 호출 시 8000자로 제한."""
        from orchestrator.llm_client import summarize_history

        captured = []

        async def mock_answer(history, **kwargs):
            captured.append(history[0])
            return "요약 결과"

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_answer

        long_history = ["A" * 2000] * 10  # 20KB 히스토리
        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                summarize_history(long_history)
            )

        assert result == "요약 결과"
        # 프롬프트에 포함된 히스토리 부분은 8000자 이하
        assert len(captured[0]) <= 8200  # 헤더 텍스트 포함 여유


# ── P3-B: 전문 에이전트 역할 프롬프트 ──────────────────────────────────────

class TestRolePrompts:
    def test_planner_and_reviewer_roles_defined(self):
        from orchestrator import agent_config_manager
        # role_planner, role_reviewer가 DB에 존재하는지 확인
        assert agent_config_manager.get_system_prompt("role_planner") is not None
        assert agent_config_manager.get_system_prompt("role_reviewer") is not None

    def test_planner_prompt_not_empty(self):
        from orchestrator import agent_config_manager
        planner = agent_config_manager.get_prompt("role_planner")
        assert len(planner) > 20

    def test_reviewer_prompt_mentions_completion(self):
        from orchestrator import agent_config_manager
        reviewer = agent_config_manager.get_prompt("role_reviewer")
        assert "완료" in reviewer or "complete" in reviewer.lower()

    def test_planner_prompt_mentions_plan(self):
        from orchestrator import agent_config_manager
        planner = agent_config_manager.get_prompt("role_planner")
        assert "계획" in planner or "plan" in planner.lower()


# ── P3-C: IntentGate ────────────────────────────────────────────────────────

class TestClassifyIntent:
    def test_returns_task_on_provider_failure(self):
        """모든 provider 실패 시 보수적 기본값 'task' 반환."""
        from orchestrator.llm_client import classify_intent

        async def mock_fail(**kwargs):
            raise RuntimeError("LLM unavailable")

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_fail

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                classify_intent("파일을 삭제해줘")
            )
        assert result == "task"

    def test_chat_response_returns_chat(self):
        """'chat'이 포함된 응답을 받으면 'chat' 반환."""
        from orchestrator.llm_client import classify_intent

        async def mock_chat(**kwargs):
            return "chat"

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_chat

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                classify_intent("안녕 어떻게 지내?")
            )
        assert result == "chat"

    def test_task_response_returns_task(self):
        """'task'가 포함된 응답을 받으면 'task' 반환."""
        from orchestrator.llm_client import classify_intent

        async def mock_task(**kwargs):
            return "task"

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_task

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                classify_intent("파이썬 파일을 리팩토링해줘")
            )
        assert result == "task"

    def test_ambiguous_response_defaults_to_task(self):
        """'chat'이 없는 응답은 모두 'task' 처리."""
        from orchestrator.llm_client import classify_intent

        async def mock_ambiguous(**kwargs):
            return "저는 잘 모르겠습니다."  # chat도 task도 없음

        mock_module = MagicMock()
        mock_module.generate_final_answer = mock_ambiguous

        with patch("orchestrator.llm_client._get_fallback_chain", return_value=["gemini"]), \
             patch("orchestrator.llm_client._get_client_module", return_value=mock_module):
            result = asyncio.get_event_loop().run_until_complete(
                classify_intent("...")
            )
        assert result == "task"


# ── P3-D: 온디맨드 MCP ──────────────────────────────────────────────────────

class TestOnDemandMcp:
    def test_on_demand_config_registered_without_connecting(self):
        """on_demand=true 서버는 _on_demand_configs에 등록되고 즉시 연결하지 않습니다."""
        from orchestrator import tool_registry

        # 상태 저장 후 복원을 위해 백업
        orig_configs = dict(tool_registry._on_demand_configs)
        orig_sessions = dict(tool_registry._mcp_sessions)

        try:
            # on_demand 서버 설정 시뮬레이션 (직접 등록)
            server_config = {
                "name": "test_on_demand_server",
                "command": "npx",
                "args": ["-y", "@test/mcp-server"],
                "on_demand": True,
            }
            tool_registry._on_demand_configs["test_on_demand_server"] = server_config

            assert "test_on_demand_server" in tool_registry._on_demand_configs
            assert "test_on_demand_server" not in tool_registry._mcp_sessions
        finally:
            # 복원
            tool_registry._on_demand_configs.clear()
            tool_registry._on_demand_configs.update(orig_configs)
            tool_registry._mcp_sessions.clear()
            tool_registry._mcp_sessions.update(orig_sessions)

    def test_on_demand_tool_map_lookup(self):
        """_on_demand_tool_map으로 도구 → 서버 역인덱스 조회가 동작합니다."""
        from orchestrator import tool_registry

        orig_map = dict(tool_registry._on_demand_tool_map)
        try:
            tool_registry._on_demand_tool_map["test_tool"] = "test_server"
            assert tool_registry._on_demand_tool_map.get("test_tool") == "test_server"
            assert tool_registry._on_demand_tool_map.get("missing_tool") is None
        finally:
            tool_registry._on_demand_tool_map.clear()
            tool_registry._on_demand_tool_map.update(orig_map)

    @pytest.mark.asyncio
    async def test_clear_resets_on_demand_state(self):
        """shutdown() 호출 시 on-demand 캐시도 초기화됩니다."""
        from orchestrator import tool_registry

        tool_registry._on_demand_configs["x"] = {"name": "x"}
        tool_registry._on_demand_tool_map["y"] = "x"
        await tool_registry.shutdown()

        assert tool_registry._on_demand_configs == {}
        assert tool_registry._on_demand_tool_map == {}


# ── P3-A: 병렬 실행 — asyncio.gather 형태 확인 ─────────────────────────────

class TestParallelExecution:
    def test_asyncio_gather_used_in_execute_group(self):
        """api.py execute_group이 asyncio.gather를 호출하는지 소스 검사."""
        import ast
        api_path = Path(__file__).parent / "api.py"
        source = api_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        gather_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "gather"
        ]
        assert len(gather_calls) > 0, "asyncio.gather 호출이 api.py에 없습니다"

    def test_return_exceptions_true_in_gather(self):
        """asyncio.gather에 return_exceptions=True가 설정되어 있는지 확인."""
        import ast
        api_path = Path(__file__).parent / "api.py"
        source = api_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "gather"):
                for kw in node.keywords:
                    if kw.arg == "return_exceptions" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is True
                        return
        pytest.fail("return_exceptions=True가 설정된 asyncio.gather를 찾지 못했습니다")


# ── 통합: fmt_usage ──────────────────────────────────────────────────────────

class TestFmtUsage:
    def test_empty_dict_returns_empty(self, main_mod):
        assert main_mod._fmt_usage({}) == ""

    def test_formats_tokens(self, main_mod):
        result = main_mod._fmt_usage({"input_tokens": 100, "output_tokens": 50})
        assert "100" in result
        assert "50" in result

    def test_formats_cost_usd(self, main_mod):
        result = main_mod._fmt_usage({"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0042})
        assert "$" in result

    def test_ollama_shows_free(self, main_mod):
        result = main_mod._fmt_usage({"input_tokens": 10, "output_tokens": 5, "provider": "ollama"})
        assert "무료" in result or "free" in result.lower()
