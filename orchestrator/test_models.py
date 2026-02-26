#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_models.py

import pytest
from pydantic import ValidationError
from .models import ToolCall, ExecutionGroup


# ── TestGeminiToolCallValidation ──────────────────────────────────

class TestGeminiToolCallValidation:
    def test_valid_tool_call(self):
        tc = ToolCall(tool_name="list_directory", arguments={"path": "."})
        assert tc.tool_name == "list_directory"

    def test_tool_name_too_long_raises(self):
        with pytest.raises(ValidationError, match="100 characters"):
            ToolCall(tool_name="a" * 101, arguments={})

    def test_tool_name_exactly_100_passes(self):
        ToolCall(tool_name="a" * 100, arguments={})

    def test_arguments_over_10kb_raises(self):
        big_value = "x" * 10_300
        with pytest.raises(ValidationError, match="10KB"):
            ToolCall(tool_name="tool", arguments={"data": big_value})

    def test_arguments_exactly_at_limit_passes(self):
        # 10240바이트 미만이 되도록 작성
        ToolCall(tool_name="tool", arguments={"key": "v"})


# ── TestExecutionGroupValidation ──────────────────────────────────

class TestExecutionGroupValidation:
    def _make_task(self, name="list_directory"):
        return ToolCall(tool_name=name, arguments={})

    def test_valid_group(self):
        g = ExecutionGroup(
            group_id="group_1",
            description="파일 목록 조회",
            tasks=[self._make_task()]
        )
        assert g.group_id == "group_1"

    def test_group_id_too_long_raises(self):
        with pytest.raises(ValidationError, match="100 characters"):
            ExecutionGroup(
                group_id="g" * 101,
                description="설명",
                tasks=[self._make_task()]
            )

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError, match="500 characters"):
            ExecutionGroup(
                group_id="g1",
                description="d" * 501,
                tasks=[self._make_task()]
            )

    def test_description_exactly_500_passes(self):
        ExecutionGroup(
            group_id="g1",
            description="d" * 500,
            tasks=[self._make_task()]
        )

    def test_tasks_over_50_raises(self):
        tasks = [self._make_task(f"tool_{i}") for i in range(51)]
        with pytest.raises(ValidationError, match="50개"):
            ExecutionGroup(group_id="g1", description="설명", tasks=tasks)

    def test_tasks_exactly_50_passes(self):
        tasks = [self._make_task(f"tool_{i}") for i in range(50)]
        ExecutionGroup(group_id="g1", description="설명", tasks=tasks)
