#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
change_tracker.py - 이전 스냅샷 대비 변경 사항 감지

이 스크립트의 출력만 읽으면 Claude가 "무엇이 변했는지"를 즉시 파악할 수 있습니다.
개별 파일을 읽을 필요가 없어 토큰 소모를 대폭 줄입니다.
"""

import ast
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .project_scanner import (
    SNAPSHOT_FILENAME,
    load_snapshot,
    save_snapshot,
    scan_project,
    _get_file_hash,
)

CHANGES_FILENAME = ".project_changes.json"


def detect_changes(project_root: str) -> Dict[str, Any]:
    """이전 스냅샷과 현재 상태를 비교하여 변경 사항을 반환."""
    root = Path(project_root).resolve()
    old_snapshot = load_snapshot(str(root))

    if old_snapshot is None:
        # 스냅샷이 없으면 먼저 생성
        save_snapshot(str(root))
        return {
            "status": "first_scan",
            "message": "첫 스캔입니다. 스냅샷을 생성했습니다. 다음 실행부터 변경 감지가 가능합니다.",
            "scan_time": datetime.now().isoformat(),
        }

    current_snapshot = scan_project(str(root))

    old_files = old_snapshot.get("files", {})
    new_files = current_snapshot.get("files", {})

    added = []
    removed = []
    modified = []

    # 추가/변경 감지
    for filepath, new_info in new_files.items():
        if filepath not in old_files:
            added.append({
                "path": filepath,
                "type": _get_file_type(filepath),
                "summary": _summarize_new_file(new_info),
            })
        else:
            old_info = old_files[filepath]
            if new_info.get("hash") != old_info.get("hash"):
                diff_detail = _diff_file_info(filepath, old_info, new_info, root)
                modified.append(diff_detail)

    # 삭제 감지
    for filepath in old_files:
        if filepath not in new_files:
            removed.append({
                "path": filepath,
                "type": _get_file_type(filepath),
            })

    changes = {
        "scan_time": datetime.now().isoformat(),
        "previous_scan": old_snapshot.get("scan_time", "unknown"),
        "added_files": added,
        "removed_files": removed,
        "modified_files": modified,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "total_changes": len(added) + len(removed) + len(modified),
        },
    }

    return changes


def _get_file_type(filepath: str) -> str:
    if filepath.endswith(".py"):
        return "python"
    elif filepath.endswith((".yaml", ".yml")):
        return "yaml"
    elif filepath.endswith(".md"):
        return "markdown"
    return "other"


def _summarize_new_file(info: Dict) -> str:
    """새 파일의 간단한 요약 생성."""
    parts = []
    if "module_docstring" in info and info["module_docstring"]:
        parts.append(info["module_docstring"][:100])
    funcs = info.get("functions", [])
    if funcs:
        names = [f["name"] for f in funcs[:5]]
        parts.append(f"함수: {', '.join(names)}" + ("..." if len(funcs) > 5 else ""))
    classes = info.get("classes", [])
    if classes:
        names = [c["name"] for c in classes[:3]]
        parts.append(f"클래스: {', '.join(names)}")
    if info.get("total_lines"):
        parts.append(f"{info['total_lines']}줄")
    return " | ".join(parts) if parts else "내용 없음"


def _diff_file_info(
    filepath: str,
    old_info: Dict,
    new_info: Dict,
    root: Path,
) -> Dict[str, Any]:
    """변경된 파일의 차이점을 분석."""
    diff = {
        "path": filepath,
        "type": _get_file_type(filepath),
        "changes": [],
    }

    # 라인 수 변화
    old_lines = old_info.get("total_lines", 0)
    new_lines = new_info.get("total_lines", 0)
    if old_lines != new_lines:
        delta = new_lines - old_lines
        sign = "+" if delta > 0 else ""
        diff["changes"].append(f"라인 수: {old_lines} → {new_lines} ({sign}{delta})")

    # Python 파일이면 함수/클래스 변경 감지
    if filepath.endswith(".py"):
        old_funcs = {f["name"] for f in old_info.get("functions", [])}
        new_funcs = {f["name"] for f in new_info.get("functions", [])}

        added_funcs = new_funcs - old_funcs
        removed_funcs = old_funcs - new_funcs

        if added_funcs:
            diff["changes"].append(f"함수 추가: {', '.join(sorted(added_funcs))}")
        if removed_funcs:
            diff["changes"].append(f"함수 제거: {', '.join(sorted(removed_funcs))}")

        old_classes = {c["name"] for c in old_info.get("classes", [])}
        new_classes = {c["name"] for c in new_info.get("classes", [])}

        added_classes = new_classes - old_classes
        removed_classes = old_classes - new_classes

        if added_classes:
            diff["changes"].append(f"클래스 추가: {', '.join(sorted(added_classes))}")
        if removed_classes:
            diff["changes"].append(f"클래스 제거: {', '.join(sorted(removed_classes))}")

        # 기존 함수 시그니처 변경 감지
        old_func_map = {f["name"]: f for f in old_info.get("functions", [])}
        new_func_map = {f["name"]: f for f in new_info.get("functions", [])}
        for name in old_funcs & new_funcs:
            old_f = old_func_map[name]
            new_f = new_func_map[name]
            if old_f.get("args") != new_f.get("args") or old_f.get("returns") != new_f.get("returns"):
                diff["changes"].append(
                    f"시그니처 변경: {name}({', '.join(old_f.get('args', []))}) → {name}({', '.join(new_f.get('args', []))})"
                )

    if not diff["changes"]:
        diff["changes"].append("내용 변경 (상세 분석 필요)")

    return diff


def save_changes(project_root: str) -> Tuple[str, Dict]:
    """변경 사항을 감지하고 JSON으로 저장한 뒤, 새 스냅샷으로 갱신."""
    changes = detect_changes(project_root)
    output_path = os.path.join(project_root, CHANGES_FILENAME)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)

    # 스냅샷 갱신 (다음 비교를 위해)
    if changes.get("status") != "first_scan":
        save_snapshot(project_root)

    return output_path, changes


def print_changes_summary(changes: Dict):
    """변경 사항을 사람이 읽기 좋은 형태로 출력."""
    if changes.get("status") == "first_scan":
        print(changes["message"])
        return

    s = changes["summary"]
    print(f"=== 변경 사항 요약 (이전: {changes['previous_scan'][:19]}) ===")
    print(f"  추가: {s['added']}개 | 수정: {s['modified']}개 | 삭제: {s['removed']}개")
    print()

    if changes["added_files"]:
        print("--- 추가된 파일 ---")
        for f in changes["added_files"]:
            print(f"  + {f['path']}  ({f['summary']})")

    if changes["modified_files"]:
        print("--- 수정된 파일 ---")
        for f in changes["modified_files"]:
            print(f"  * {f['path']}")
            for c in f["changes"]:
                print(f"      {c}")

    if changes["removed_files"]:
        print("--- 삭제된 파일 ---")
        for f in changes["removed_files"]:
            print(f"  - {f['path']}")

    if s["total_changes"] == 0:
        print("  변경 사항 없음.")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    output_path, changes = save_changes(root)
    print_changes_summary(changes)
    print(f"\n변경 기록 저장: {output_path}")
