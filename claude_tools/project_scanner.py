#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_scanner.py - 프로젝트 구조 및 코드 스냅샷 생성기

이 스크립트가 생성하는 .snapshot.json을 읽으면
Claude가 개별 소스 파일을 읽지 않아도 프로젝트를 파악할 수 있습니다.
"""

import ast
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# 스캔 제외 디렉토리/파일
EXCLUDE_DIRS = {
    "venv", ".venv", "node_modules", "__pycache__", ".git",
    ".pytest_cache", ".mypy_cache", "backup", "temp", ".tox",
}
EXCLUDE_FILES = {".env", ".DS_Store"}
SNAPSHOT_FILENAME = ".project_snapshot.json"


def _get_file_hash(path: Path) -> str:
    """파일의 MD5 해시 (변경 감지용)."""
    h = hashlib.md5()
    try:
        h.update(path.read_bytes())
    except Exception:
        return ""
    return h.hexdigest()


def _extract_python_info(path: Path) -> Dict[str, Any]:
    """Python 파일에서 함수/클래스 시그니처와 docstring을 추출."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception as e:
        return {"error": str(e)}

    module_doc = ast.get_docstring(tree) or ""

    functions = []
    classes = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _extract_function_info(node, source)
            functions.append(func_info)

        elif isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(_extract_function_info(item, source))
            classes.append({
                "name": node.name,
                "docstring": class_doc[:200],
                "methods": methods,
                "line": node.lineno,
            })

    imports = _extract_imports(tree)

    return {
        "module_docstring": module_doc[:300],
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "total_lines": len(source.splitlines()),
    }


def _extract_function_info(node, source: str) -> Dict[str, Any]:
    """함수 노드에서 정보 추출."""
    args_list = []
    for arg in node.args.args:
        annotation = ""
        if arg.annotation:
            annotation = ast.get_source_segment(source, arg.annotation) or ""
        args_list.append(f"{arg.arg}: {annotation}" if annotation else arg.arg)

    # 반환 타입
    returns = ""
    if node.returns:
        returns = ast.get_source_segment(source, node.returns) or ""

    is_async = isinstance(node, ast.AsyncFunctionDef)
    docstring = ast.get_docstring(node) or ""
    # docstring 첫 줄만 (간결하게)
    first_line_doc = docstring.split("\n")[0].strip() if docstring else ""

    return {
        "name": node.name,
        "args": args_list,
        "returns": returns,
        "async": is_async,
        "docstring": first_line_doc,
        "line": node.lineno,
    }


def _extract_imports(tree) -> List[str]:
    """import 문 추출."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}")
    return imports


def _extract_yaml_summary(path: Path) -> Dict[str, Any]:
    """YAML 스펙 파일에서 MCP 이름 목록만 빠르게 추출 (PyYAML 미설치 대비)."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {"error": "읽기 실패"}

    mcp_names = []
    for line in content.splitlines():
        stripped = line.strip()
        if "mcp_name:" in stripped or "name:" in stripped:
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                name = parts[1].strip().strip("'\"")
                if name and not name.startswith("{") and len(name) < 60:
                    mcp_names.append(name)

    return {
        "type": "yaml_spec",
        "defined_names": mcp_names,
        "total_lines": len(content.splitlines()),
    }


def scan_project(project_root: str) -> Dict[str, Any]:
    """프로젝트 전체를 스캔하여 스냅샷 딕셔너리를 반환."""
    root = Path(project_root).resolve()
    snapshot = {
        "scan_time": datetime.now().isoformat(),
        "project_root": str(root),
        "files": {},
        "summary": {
            "total_py_files": 0,
            "total_yaml_files": 0,
            "total_other_files": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_lines": 0,
        },
    }

    for dirpath, dirnames, filenames in os.walk(root):
        # 제외 디렉토리 건너뛰기
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]

        rel_dir = os.path.relpath(dirpath, root)

        for filename in sorted(filenames):
            if filename in EXCLUDE_FILES or filename.startswith("."):
                continue

            filepath = Path(dirpath) / filename
            rel_path = os.path.join(rel_dir, filename) if rel_dir != "." else filename

            file_entry = {
                "size_bytes": filepath.stat().st_size,
                "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                "hash": _get_file_hash(filepath),
            }

            if filename.endswith(".py"):
                py_info = _extract_python_info(filepath)
                file_entry.update(py_info)
                snapshot["summary"]["total_py_files"] += 1
                snapshot["summary"]["total_functions"] += len(py_info.get("functions", []))
                snapshot["summary"]["total_classes"] += len(py_info.get("classes", []))
                snapshot["summary"]["total_lines"] += py_info.get("total_lines", 0)

            elif filename.endswith((".yaml", ".yml")):
                yaml_info = _extract_yaml_summary(filepath)
                file_entry.update(yaml_info)
                snapshot["summary"]["total_yaml_files"] += 1

            elif filename.endswith((".txt", ".md", ".sh", ".ini", ".json")):
                try:
                    content = filepath.read_text(encoding="utf-8")
                    file_entry["total_lines"] = len(content.splitlines())
                    # .md와 .ini는 내용 요약 불필요
                except Exception:
                    pass
                snapshot["summary"]["total_other_files"] += 1
            else:
                snapshot["summary"]["total_other_files"] += 1

            snapshot["files"][rel_path] = file_entry

    return snapshot


def save_snapshot(project_root: str) -> str:
    """프로젝트를 스캔하고 결과를 JSON으로 저장."""
    snapshot = scan_project(project_root)
    output_path = os.path.join(project_root, SNAPSHOT_FILENAME)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return output_path


def load_snapshot(project_root: str) -> Optional[Dict]:
    """저장된 스냅샷을 로드."""
    snapshot_path = os.path.join(project_root, SNAPSHOT_FILENAME)
    if not os.path.exists(snapshot_path):
        return None
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    output = save_snapshot(root)
    print(f"스냅샷 저장 완료: {output}")

    snapshot = load_snapshot(root)
    s = snapshot["summary"]
    print(f"  Python 파일: {s['total_py_files']}개")
    print(f"  YAML 파일: {s['total_yaml_files']}개")
    print(f"  함수: {s['total_functions']}개")
    print(f"  클래스: {s['total_classes']}개")
    print(f"  총 코드 라인: {s['total_lines']}줄")
