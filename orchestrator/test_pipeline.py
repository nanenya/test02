#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_pipeline.py
"""4층 파이프라인 신규 모듈 테스트."""

import json
import pytest
import tempfile
from pathlib import Path


# ── pipeline_db ───────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    from orchestrator.pipeline_db import init_db
    init_db(path=db_path)
    return db_path


def test_pipeline_db_init(tmp_db):
    """DB 초기화 후 기본 통계가 0인지 확인합니다."""
    from orchestrator.pipeline_db import get_template_stats
    stats = get_template_stats(path=tmp_db)
    assert stats["total_templates"] == 0
    assert stats["plan_cache_entries"] == 0


def test_design_crud(tmp_db):
    """설계 생성 → 확인 → 조회 흐름을 검증합니다."""
    from orchestrator.pipeline_db import create_design, confirm_design, get_design, get_active_design

    did = create_design("conv-1", "test query", '{"goal":"g"}', path=tmp_db)
    assert did > 0

    d = get_design(did, path=tmp_db)
    assert d["status"] == "pending_confirm"

    confirm_design(did, path=tmp_db)
    d2 = get_design(did, path=tmp_db)
    assert d2["status"] == "confirmed"
    assert d2["confirmed_at"] is not None

    active = get_active_design("conv-1", path=tmp_db)
    assert active is not None
    assert active["id"] == did


def test_task_plan_cache(tmp_db):
    """계획 캐시 저장 → 조회 → use_count 증가를 검증합니다."""
    from orchestrator.pipeline_db import save_task_plan_cache, get_task_plan_cache

    plans = [{"action": "파일 읽기", "tool_hints": ["read_file"]}]
    sig = "abc123"
    save_task_plan_cache(sig, ["파일", "읽기"], plans, path=tmp_db)

    result = get_task_plan_cache(sig, path=tmp_db)
    assert result is not None
    assert result[0]["action"] == "파일 읽기"

    # 두 번째 조회 시 use_count 증가 확인
    with __import__("orchestrator.pipeline_db", fromlist=["get_db"]).get_db(tmp_db) as conn:
        row = conn.execute(
            "SELECT use_count FROM task_plan_cache WHERE task_signature=?", (sig,)
        ).fetchone()
    assert row["use_count"] == 2


def test_execution_template_lifecycle(tmp_db):
    """템플릿 저장 → 조회 → 비활성화 → 자동 비활성화 임계값 테스트."""
    from orchestrator.pipeline_db import (
        save_execution_template, list_templates, disable_template,
        enable_template, get_template_stats, increment_template_fail,
        find_best_template, auto_disable_failing_templates,
    )

    group = {"group_id": "g1", "description": "테스트", "tasks": [
        {"tool_name": "read_file", "arguments": {"path": "test.txt"}, "model_preference": "standard"}
    ]}
    tid = save_execution_template(
        "test:read", "파일 읽기 테스트", ["파일", "읽기", "read_file"], group, path=tmp_db
    )
    assert tid > 0

    templates = list_templates(path=tmp_db)
    assert len(templates) == 1

    # 기본 검색
    found = find_best_template(["파일", "읽기", "read_file", "csv"], path=tmp_db)
    assert found is not None
    assert found["id"] == tid

    # 비활성화 후 검색 불가
    disable_template(tid, path=tmp_db)
    not_found = find_best_template(["파일", "읽기", "read_file", "csv"], path=tmp_db)
    assert not_found is None

    enable_template(tid, path=tmp_db)

    # 실패율 임계값 테스트 (3회 실패 / 총 4회 = 75% → 임계 60% 초과)
    # success_count=1 (저장 시 초기화), fail_count 추가
    for _ in range(3):
        increment_template_fail(tid, path=tmp_db)  # auto_disable 포함

    templates_after = list_templates(path=tmp_db)
    # 3실패 / 4총 = 75% > 60% → 자동 비활성화
    assert all(t.get("is_active") == 0 or t["id"] != tid for t in templates_after)


def test_tool_gap_log(tmp_db):
    """도구 부재 로그 기록을 검증합니다."""
    from orchestrator.pipeline_db import log_tool_gap
    from orchestrator.tool_discoverer import get_gap_report

    log_tool_gap("missing_tool", "not_found", note="test", path=tmp_db)
    log_tool_gap("found_tool", "found_in_registry", mcp_server_name="fs", path=tmp_db)

    # get_gap_report는 기본 DB를 참조하므로 직접 쿼리로 검증
    from orchestrator.pipeline_db import get_db
    with get_db(tmp_db) as conn:
        rows = conn.execute("SELECT * FROM tool_gap_log ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["required_tool"] == "missing_tool"
    assert rows[1]["resolution_type"] == "found_in_registry"


def test_pipeline_cursor(tmp_db):
    """파이프라인 커서 UPSERT를 검증합니다."""
    from orchestrator.pipeline_db import set_cursor, get_cursor, clear_cursor

    set_cursor("conv-x", "design_pending", design_id=1, path=tmp_db)
    c = get_cursor("conv-x", path=tmp_db)
    assert c["phase"] == "design_pending"
    assert c["design_id"] == 1

    # UPSERT
    set_cursor("conv-x", "executing", design_id=1, task_id=2, plan_id=3, path=tmp_db)
    c2 = get_cursor("conv-x", path=tmp_db)
    assert c2["phase"] == "executing"
    assert c2["task_id"] == 2

    clear_cursor("conv-x", path=tmp_db)
    c3 = get_cursor("conv-x", path=tmp_db)
    assert c3["phase"] == "idle"


# ── llm_router ────────────────────────────────────────────────────────────────

def test_llm_router_tiers():
    """단계별 기본 티어와 복잡도 오버라이드를 검증합니다."""
    from orchestrator.llm_router import get_tier

    assert get_tier("design_generation", "simple") == "high"
    assert get_tier("task_decomposition", "simple") == "standard"
    assert get_tier("task_decomposition", "complex") == "high"
    assert get_tier("exec_group_build", "medium") == "standard"
    assert get_tier("tool_implementation", "simple") == "high"


def test_llm_router_budget_downgrade():
    """예산 초과 시 high → standard 강등을 검증합니다."""
    from orchestrator.llm_router import get_tier

    # 예산 미초과
    assert get_tier("design_generation", "complex", budget_usd=0.05) == "high"
    # 예산 초과 → standard
    assert get_tier("design_generation", "complex", budget_usd=0.15) == "standard"


def test_llm_router_force_override():
    """force 파라미터가 모든 로직을 override함을 검증합니다."""
    from orchestrator.llm_router import get_tier

    assert get_tier("design_generation", "complex", force="standard") == "standard"
    assert get_tier("task_decomposition", "simple", force="high") == "high"


def test_llm_router_complexity_inference():
    """쿼리 기반 복잡도 추정을 검증합니다."""
    from orchestrator.llm_router import infer_complexity_from_query

    assert infer_complexity_from_query("안녕") == "simple"
    # 2단어 → simple (<=5 단어 기준)
    assert infer_complexity_from_query("파일 읽어줘") == "simple"
    # 6단어 초과, 복잡 키워드 없음 → medium
    assert infer_complexity_from_query("파일을 열고 읽어서 변환한 후 결과를 출력해줘") == "medium"
    # 복잡 키워드 포함 → complex
    assert infer_complexity_from_query("전체 시스템 아키텍처를 설계하고 마이그레이션 계획을 수립해줘") == "complex"


# ── tool_discoverer ───────────────────────────────────────────────────────────

def test_is_code_safe():
    """위험 코드 패턴 정적 검사를 검증합니다."""
    from orchestrator.tool_discoverer import _is_code_safe

    safe = "def add(a, b): return a + b"
    ok, _ = _is_code_safe(safe)
    assert ok is True

    danger_cases = [
        "import os; os.system('ls')",
        "import subprocess",
        "eval('1+1')",
        "exec('print(1)')",
        "__import__('os')",
        "open('file.txt', 'w')",
        "import shutil; shutil.rmtree('/')",
    ]
    for code in danger_cases:
        ok, reason = _is_code_safe(code)
        assert ok is False, f"위험 코드가 안전하다고 판정됨: {code!r}"
        assert reason, "reason이 비어 있음"


def test_run_safe_whitelist():
    """화이트리스트 외 명령 차단을 검증합니다."""
    from orchestrator.tool_discoverer import _run_safe

    result = _run_safe(["bash", "-c", "echo hacked"])
    assert result is None

    result2 = _run_safe(["python3", "--version"])
    # python3는 화이트리스트에 없음
    assert result2 is None


def test_run_safe_injection():
    """셸 인젝션 문자가 포함된 인자를 차단합니다."""
    from orchestrator.tool_discoverer import _run_safe

    assert _run_safe(["npm", "search", "test; rm -rf /"]) is None
    assert _run_safe(["npm", "search", "test | cat /etc/passwd"]) is None
    assert _run_safe(["npm", "search", "test & echo hacked"]) is None


def test_find_tools_for_step():
    """등록된 도구 검색을 검증합니다."""
    from orchestrator.tool_discoverer import find_tools_for_step
    from orchestrator import tool_registry

    # 실제 도구가 등록된 경우와 없는 경우
    mapping = find_tools_for_step(["nonexistent_tool_xyz", "hashline_read"])
    assert mapping["nonexistent_tool_xyz"] is None
    # hashline_read는 DB 로드 전이므로 None일 수 있음 (환경 의존)


# ── template_engine ───────────────────────────────────────────────────────────

def test_template_engine_empty_db(tmp_db):
    """빈 DB에서 템플릿 검색 시 None을 반환합니다."""
    from orchestrator.template_engine import find_best_template_scored

    result = find_best_template_scored(["파일", "읽기"], ["read_file"], path=tmp_db)
    assert result is None


def test_template_engine_scoring(tmp_db):
    """스코어링이 올바르게 동작하는지 검증합니다."""
    from orchestrator.pipeline_db import save_execution_template, find_best_template
    from orchestrator.template_engine import find_best_template_scored

    group = {"group_id": "g1", "description": "CSV 파일 읽기", "tasks": [
        {"tool_name": "read_file", "arguments": {"path": "data.csv"}, "model_preference": "standard"}
    ]}
    tid = save_execution_template(
        "csv:read", "CSV 읽기", ["파일", "읽기", "csv", "read_file", "데이터"], group, path=tmp_db
    )
    # success_count를 5로 늘려 스코어 상향
    for _ in range(4):
        save_execution_template("csv:read", "", ["파일", "읽기", "csv", "read_file", "데이터"],
                                group, path=tmp_db)

    # 향상된 스코어링으로 검색
    result = find_best_template_scored(
        ["파일", "읽기", "csv", "데이터", "변환"],
        ["read_file", "write_file"],
        path=tmp_db,
    )
    assert result is not None
    assert result["id"] == tid


# ── pipeline_manager helpers ──────────────────────────────────────────────────

def test_make_task_signature():
    """같은 태스크 제목+설명은 같은 시그니처를 반환합니다."""
    from orchestrator.pipeline_manager import _make_task_signature

    sig1 = _make_task_signature("CSV 파싱", "CSV 파일을 파싱하여 DB에 저장합니다")
    sig2 = _make_task_signature("CSV 파싱", "CSV 파일을 파싱하여  DB에 저장합니다")  # 공백 2개
    sig3 = _make_task_signature("다른 작업", "다른 설명")

    assert sig1 == sig2  # 정규화로 동일
    assert sig1 != sig3
    assert len(sig1) == 24
