#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_updater.py - PROJECT_ANALYSIS.md 자동 갱신

스냅샷과 변경 사항 데이터를 기반으로 분석 보고서의 특정 섹션을 자동 갱신합니다.
Claude가 이 보고서만 읽으면 전체 프로젝트를 파악할 수 있도록 합니다.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_scanner import load_snapshot, SNAPSHOT_FILENAME

REPORT_FILENAME = "PROJECT_ANALYSIS.md"

# --- 섹션 생성 함수들 ---


def _generate_file_catalog(snapshot: Dict) -> str:
    """스냅샷에서 전체 파일 카탈로그(함수 시그니처 포함) 생성."""
    lines = []
    lines.append("## 11. 파일별 상세 카탈로그 (자동 생성)")
    lines.append("")
    lines.append(f"> 자동 생성 시각: {snapshot.get('scan_time', 'unknown')[:19]}")
    lines.append(f"> Python 파일: {snapshot['summary']['total_py_files']}개 | "
                 f"함수: {snapshot['summary']['total_functions']}개 | "
                 f"클래스: {snapshot['summary']['total_classes']}개 | "
                 f"총 라인: {snapshot['summary']['total_lines']}줄")
    lines.append("")

    # 디렉토리별로 그룹핑
    dir_groups: Dict[str, List] = {}
    for filepath, info in sorted(snapshot["files"].items()):
        dirname = os.path.dirname(filepath) or "."
        dir_groups.setdefault(dirname, []).append((filepath, info))

    for dirname, files in sorted(dir_groups.items()):
        lines.append(f"### {dirname}/")
        lines.append("")

        for filepath, info in files:
            filename = os.path.basename(filepath)
            size = info.get("size_bytes", 0)
            total_lines = info.get("total_lines", "?")
            lines.append(f"#### `{filename}` ({total_lines}줄, {size:,}B)")

            # 모듈 docstring
            if info.get("module_docstring"):
                doc = info["module_docstring"].replace("\n", " ").strip()
                if doc:
                    lines.append(f"> {doc[:200]}")

            # 함수 목록
            functions = info.get("functions", [])
            if functions:
                lines.append("")
                lines.append("| 함수명 | 인자 | 반환 | 설명 |")
                lines.append("|--------|------|------|------|")
                for func in functions:
                    name = func["name"]
                    if name.startswith("_"):
                        continue  # 비공개 함수 건너뛰기
                    prefix = "async " if func.get("async") else ""
                    args = ", ".join(func.get("args", []))
                    if len(args) > 50:
                        args = args[:47] + "..."
                    returns = func.get("returns", "") or "-"
                    doc = func.get("docstring", "") or "-"
                    if len(doc) > 80:
                        doc = doc[:77] + "..."
                    lines.append(f"| `{prefix}{name}` | `{args}` | `{returns}` | {doc} |")

            # 클래스 목록
            classes = info.get("classes", [])
            if classes:
                for cls in classes:
                    lines.append(f"\n**class `{cls['name']}`** (line {cls['line']})")
                    if cls.get("docstring"):
                        lines.append(f"> {cls['docstring'][:150]}")
                    methods = cls.get("methods", [])
                    if methods:
                        lines.append("")
                        lines.append("| 메서드 | 인자 | 설명 |")
                        lines.append("|--------|------|------|")
                        for m in methods:
                            if m["name"].startswith("_") and m["name"] != "__init__":
                                continue
                            args = ", ".join(m.get("args", []))
                            if len(args) > 50:
                                args = args[:47] + "..."
                            doc = m.get("docstring", "") or "-"
                            lines.append(f"| `{m['name']}` | `{args}` | {doc} |")

            # YAML 스펙
            if info.get("type") == "yaml_spec":
                names = info.get("defined_names", [])
                if names:
                    lines.append(f"\n정의된 MCP: `{'`, `'.join(names[:15])}`" +
                                 ("..." if len(names) > 15 else ""))

            # import 목록 (외부 의존성만)
            imports = info.get("imports", [])
            external = [i for i in imports if not i.startswith(".") and not i.startswith("mcp_modules")]
            if external:
                unique = sorted(set(i.split(".")[0] for i in external))
                lines.append(f"\n의존성: `{'`, `'.join(unique[:10])}`")

            lines.append("")

    return "\n".join(lines)


def _generate_dependency_map(snapshot: Dict) -> str:
    """모듈 간 의존성 맵 생성."""
    lines = []
    lines.append("## 12. 모듈 간 의존성 맵 (자동 생성)")
    lines.append("")
    lines.append("```")

    py_files = {
        fp: info for fp, info in snapshot["files"].items()
        if fp.endswith(".py") and "imports" in info
    }

    for filepath in sorted(py_files):
        info = py_files[filepath]
        imports = info.get("imports", [])
        # 프로젝트 내부 import만 필터
        internal = [
            i for i in imports
            if i.startswith(".") or i.startswith("orchestrator") or i.startswith("mcp_modules")
        ]
        if internal:
            basename = os.path.basename(filepath)
            deps = ", ".join(sorted(set(internal)))
            lines.append(f"  {basename} → {deps}")

    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def update_report(project_root: str) -> str:
    """PROJECT_ANALYSIS.md의 자동 생성 섹션(11, 12)을 갱신."""
    root = Path(project_root).resolve()
    report_path = root / REPORT_FILENAME
    snapshot = load_snapshot(str(root))

    if snapshot is None:
        return "스냅샷이 없습니다. 먼저 `python -m claude_tools scan`을 실행하세요."

    # 새 섹션 생성
    catalog = _generate_file_catalog(snapshot)
    dep_map = _generate_dependency_map(snapshot)
    auto_section = f"\n---\n\n{catalog}\n---\n\n{dep_map}"

    # 기존 보고서 읽기
    if report_path.exists():
        content = report_path.read_text(encoding="utf-8")
    else:
        content = "# test02 프로젝트 분석 보고서\n"

    # 기존 자동 생성 섹션 제거 (## 11. ~ 파일 끝)
    pattern = r"\n---\n\n## 11\. 파일별 상세 카탈로그.*"
    content = re.sub(pattern, "", content, flags=re.DOTALL)

    # 새 섹션 추가
    content = content.rstrip() + "\n" + auto_section

    report_path.write_text(content, encoding="utf-8")
    return str(report_path)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    result = update_report(root)
    print(f"보고서 갱신 완료: {result}")
