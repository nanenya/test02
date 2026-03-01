#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_validator.py - PROJECT_ANALYSIS.md 자동 검증

섹션 2(디렉토리), 섹션 6(테스트), 섹션 7(의존성)을
실제 파일/스냅샷과 비교하여 불일치를 경고합니다.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


SNAPSHOT_FILENAME = ".project_snapshot.json"
REPORT_FILENAME = "PROJECT_ANALYSIS.md"


@dataclass
class ValidationResult:
    section: str
    ok: bool
    details: list = field(default_factory=list)  # 불일치 상세


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _load_snapshot(project_root: Path) -> Optional[dict]:
    snap_path = project_root / SNAPSHOT_FILENAME
    if not snap_path.exists():
        return None
    with open(snap_path, encoding="utf-8") as f:
        return json.load(f)


def _load_report_lines(project_root: Path) -> List[str]:
    report_path = project_root / REPORT_FILENAME
    if not report_path.exists():
        return []
    with open(report_path, encoding="utf-8") as f:
        return f.readlines()


def _extract_section(lines: List[str], heading: str) -> List[str]:
    """주어진 ## 제목으로 시작하는 섹션의 라인들을 반환 (다음 ## 섹션 전까지)."""
    in_section = False
    result = []
    for line in lines:
        if line.startswith("## ") and heading in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            result.append(line)
    return result


# ─────────────────────────────────────────────
# 검증 1: 섹션 7 (의존성)
# ─────────────────────────────────────────────

def validate_dependencies(project_root: Path) -> ValidationResult:
    """requirements.txt의 패키지를 섹션 7 테이블과 비교."""
    req_path = project_root / "requirements.txt"
    if not req_path.exists():
        return ValidationResult("섹션 7 (의존성)", False, ["requirements.txt 파일 없음"])

    # requirements.txt 파싱 — 패키지명만 추출 (버전/주석 제외)
    actual_pkgs: Set[str] = set()
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        # 버전 지정자 제거 (>=, ==, [] 등)
        name = re.split(r"[><=!\[\s]", line)[0].strip().lower()
        if name:
            actual_pkgs.add(name)

    # 섹션 7 테이블에서 패키지명 추출
    report_lines = _load_report_lines(project_root)
    section_lines = _extract_section(report_lines, "7. 의존성")
    doc_pkgs: Set[str] = set()
    for line in section_lines:
        # 마크다운 테이블 행: | pkg | ... | (헤더 구분선 |----|----| 제외)
        m = re.match(r"\|\s*`?([^`|\-][^`|]*)`?\s*\|", line)
        if m:
            raw_name = m.group(1).strip().lower()
            # 버전 지정자 제거
            name = re.split(r"[><=!\[\s]", raw_name)[0].strip()
            if name and name != "패키지":
                doc_pkgs.add(name)

    missing_in_doc = actual_pkgs - doc_pkgs
    extra_in_doc = doc_pkgs - actual_pkgs

    details = []
    if missing_in_doc:
        details.append(f"문서에 누락된 패키지: {', '.join(sorted(missing_in_doc))}")
    if extra_in_doc:
        details.append(f"문서에만 있는 패키지 (requirements에 없음): {', '.join(sorted(extra_in_doc))}")

    return ValidationResult(
        section="섹션 7 (의존성)",
        ok=len(details) == 0,
        details=details if details else [f"일치 ({len(actual_pkgs)}개)"],
    )


# ─────────────────────────────────────────────
# 검증 2: 섹션 2 (디렉토리 구조)
# ─────────────────────────────────────────────

def validate_directory_structure(project_root: Path, snapshot: Optional[dict]) -> ValidationResult:
    """실제 디렉토리 목록과 섹션 2 표기를 비교."""
    if snapshot is None:
        return ValidationResult(
            "섹션 2 (디렉토리)", False,
            ["스냅샷 없음 — `python -m claude_tools scan` 먼저 실행하세요"]
        )

    # 스냅샷 파일 경로에서 1단계 디렉토리 추출
    actual_dirs: Set[str] = set()
    for filepath in snapshot.get("files", {}):
        parts = Path(filepath).parts
        if len(parts) > 1:
            actual_dirs.add(parts[0].rstrip("/"))

    # 섹션 2 코드 블록에서 디렉토리 항목 추출
    report_lines = _load_report_lines(project_root)
    section_lines = _extract_section(report_lines, "2. 디렉토리 구조")
    doc_dirs: Set[str] = set()
    in_block = False
    for line in section_lines:
        stripped = line.rstrip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            continue
        # ├──, └── 형태(트리 문자 + 더블 대시)에서 최상위 디렉토리명만 추출
        # 예: "├── mcp_cache/  # ..." → "mcp_cache"
        # 들여쓰기가 없는 항목(최상위)만 추출: 앞에 │나 공백이 없는 경우
        m = re.match(r"[├└][─\s]+([a-zA-Z0-9_.]+)/", stripped)
        if m:
            doc_dirs.add(m.group(1))

    # 실제 존재하는 디렉토리 확인 (venv 등 제외 디렉토리는 스냅샷에 없을 수 있음)
    # 문서에 명시된 디렉토리가 실제 존재하는지 확인
    actually_exist: Set[str] = set()
    for d in doc_dirs:
        if (project_root / d).is_dir():
            actually_exist.add(d)

    missing_in_doc = actual_dirs - doc_dirs
    not_exist = doc_dirs - actually_exist - actual_dirs

    details = []
    if missing_in_doc:
        details.append(f"문서에 누락된 디렉토리: {', '.join(sorted(missing_in_doc))}")
    if not_exist:
        details.append(f"문서에만 있고 실제 없는 디렉토리: {', '.join(sorted(not_exist))}")

    return ValidationResult(
        section="섹션 2 (디렉토리)",
        ok=len(details) == 0,
        details=details if details else [f"일치 (확인된 디렉토리 {len(actual_dirs)}개)"],
    )


# ─────────────────────────────────────────────
# 검증 3: 섹션 6 (테스트 현황)
# ─────────────────────────────────────────────

def validate_test_section(project_root: Path, snapshot: Optional[dict]) -> ValidationResult:
    """실제 테스트 파일 목록과 섹션 6 테이블을 비교. pytest 개수도 대조.
    섹션 6이 DB 관리 안내만 있고 테이블이 없으면 DB 위임 모드로 처리."""
    # 실제 test_*.py 파일 목록
    if snapshot is not None:
        actual_files: Set[str] = {
            Path(fp).name
            for fp in snapshot.get("files", {})
            if Path(fp).name.startswith("test_") and fp.endswith(".py")
        }
    else:
        # 스냅샷 없으면 직접 glob
        actual_files = {p.name for p in project_root.rglob("test_*.py")
                        if "venv" not in str(p)}

    # 섹션 6 테이블에서 테스트 파일명 추출
    report_lines = _load_report_lines(project_root)
    section_lines = _extract_section(report_lines, "6. 테스트")
    doc_files: Set[str] = set()
    doc_test_count: Optional[int] = None
    db_managed = False

    for line in section_lines:
        # DB 관리 안내 노트 감지
        if "DB 관리" in line or "tracker tests" in line:
            db_managed = True
        # 테이블 행에서 파일명 추출: | `path/file.py` | ...
        m = re.search(r"`(?:orchestrator/)?(test_\w+\.py)`", line)
        if m:
            doc_files.add(m.group(1))
        # 테스트 개수 추출: "전체 NNN개 통과"
        cm = re.search(r"전체\s+(\d+)개\s+통과", line)
        if cm:
            doc_test_count = int(cm.group(1))

    # 섹션 6이 DB 관리 모드이고 테이블 항목이 없으면 검증 생략
    if db_managed and not doc_files:
        return ValidationResult(
            section="섹션 6 (테스트)",
            ok=True,
            details=[f"DB 위임 모드 — test_status 테이블 관리 ({len(actual_files)}개 파일 감지)"],
        )

    missing_in_doc = actual_files - doc_files
    extra_in_doc = doc_files - actual_files

    details = []
    if missing_in_doc:
        details.append(f"문서에 누락된 테스트 파일: {', '.join(sorted(missing_in_doc))}")
    if extra_in_doc:
        details.append(f"문서에만 있는 테스트 파일 (실제 없음): {', '.join(sorted(extra_in_doc))}")

    # pytest --collect-only로 실제 테스트 개수 확인
    actual_test_count: Optional[int] = None
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "--tb=no"],
            capture_output=True, text=True, cwd=str(project_root), timeout=30
        )
        # "324 tests collected" 또는 "no tests ran" 패턴
        m = re.search(r"(\d+)\s+test", result.stdout + result.stderr)
        if m:
            actual_test_count = int(m.group(1))
    except Exception:
        pass  # pytest 실행 실패는 무시

    if doc_test_count is not None and actual_test_count is not None:
        if doc_test_count != actual_test_count:
            details.append(
                f"테스트 개수 불일치 — 문서: {doc_test_count}개, 실제: {actual_test_count}개"
            )

    if not details:
        count_info = f"{actual_test_count}개" if actual_test_count else "확인 불가"
        details = [f"일치 ({len(actual_files)}개 파일, {count_info} 테스트)"]

    return ValidationResult(
        section="섹션 6 (테스트)",
        ok=not any("불일치" in d or "누락" in d or "없음" in d for d in details),
        details=details,
    )


# ─────────────────────────────────────────────
# 전체 검증 실행
# ─────────────────────────────────────────────

def validate_all(project_root: str) -> List[ValidationResult]:
    root = Path(project_root).resolve()
    snapshot = _load_snapshot(root)

    results = [
        validate_dependencies(root),
        validate_directory_structure(root, snapshot),
        validate_test_section(root, snapshot),
    ]

    print("=== PROJECT_ANALYSIS.md 검증 결과 ===")
    any_fail = False
    for r in results:
        icon = "[✓]" if r.ok else "[✗]"
        if not r.ok:
            any_fail = True
        print(f"{icon} {r.section}")
        for detail in r.details:
            print(f"    - {detail}")

    if any_fail:
        print("\n⚠  불일치가 발견되었습니다. PROJECT_ANALYSIS.md를 수동으로 갱신하세요.")
    else:
        print("\n✓  모든 섹션이 실제 파일과 일치합니다.")

    # test_status 테이블 자동 갱신
    _sync_test_status(root, snapshot)

    return results


def _sync_test_status(root: Path, snapshot: Optional[dict]) -> None:
    """실제 테스트 파일 목록을 test_status 테이블에 upsert합니다."""
    try:
        from .project_tracker import upsert_test_status, init_tables
        init_tables()

        if snapshot is not None:
            actual_files = {
                Path(fp).name: fp
                for fp in snapshot.get("files", {})
                if Path(fp).name.startswith("test_") and fp.endswith(".py")
            }
        else:
            actual_files = {
                p.name: str(p.relative_to(root))
                for p in root.rglob("test_*.py")
                if "venv" not in str(p)
            }

        for test_file in actual_files:
            upsert_test_status(test_file=test_file)

        if actual_files:
            print(f"  [DB] test_status 테이블 갱신: {len(actual_files)}개 파일")
    except Exception as e:
        print(f"  [DB] test_status 갱신 실패 (무시): {e}")
