#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/mcp_manager.py

"""MCP 서버 레지스트리 관리 모듈.

서버 등록/제거/검색, 도구 중복 분석, 하드코딩 마이그레이션 등을 담당합니다.
"""

import json
import os
import logging
import subprocess
from datetime import date
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers.json")

_EMPTY_REGISTRY: Dict[str, Any] = {
    "version": "1.0",
    "servers": [],
    "tool_name_aliases": {},
}


def load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    """JSON 레지스트리 파일을 읽어 반환합니다."""
    filepath = path or _REGISTRY_PATH
    if not os.path.exists(filepath):
        return dict(_EMPTY_REGISTRY, servers=[], tool_name_aliases={})
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry: Dict[str, Any], path: Optional[str] = None) -> None:
    """레지스트리를 JSON 파일에 저장합니다."""
    filepath = path or _REGISTRY_PATH
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def get_servers(registry: Dict[str, Any], enabled_only: bool = True) -> List[Dict[str, Any]]:
    """서버 목록을 반환합니다."""
    servers = registry.get("servers", [])
    if enabled_only:
        return [s for s in servers if s.get("enabled", True)]
    return list(servers)


def _find_server(registry: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """이름으로 서버를 찾습니다."""
    for server in registry.get("servers", []):
        if server["name"] == name:
            return server
    return None


def add_server(
    registry: Dict[str, Any],
    name: str,
    package: str,
    package_manager: str = "npm",
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """서버를 레지스트리에 추가합니다. 이름 중복 시 ValueError."""
    if _find_server(registry, name):
        raise ValueError(f"Server '{name}' already exists in registry")

    if command is None:
        command = "npx" if package_manager == "npm" else package

    server_entry = {
        "name": name,
        "package": package,
        "package_manager": package_manager,
        "command": command,
        "args": args or (["-y", package, "."] if package_manager == "npm" else []),
        "env": env,
        "enabled": True,
        "added_at": date.today().isoformat(),
        "description": description,
    }
    registry.setdefault("servers", []).append(server_entry)
    return server_entry


def remove_server(registry: Dict[str, Any], name: str) -> bool:
    """서버를 레지스트리에서 제거합니다. 제거 성공 시 True."""
    servers = registry.get("servers", [])
    for i, s in enumerate(servers):
        if s["name"] == name:
            servers.pop(i)
            return True
    return False


def enable_server(registry: Dict[str, Any], name: str, enabled: bool = True) -> bool:
    """서버를 활성/비활성 전환합니다. 성공 시 True."""
    server = _find_server(registry, name)
    if server is None:
        return False
    server["enabled"] = enabled
    return True


def search_npm(query: str) -> List[Dict[str, str]]:
    """npm에서 MCP 서버 패키지를 검색합니다."""
    try:
        result = subprocess.run(
            ["npm", "search", "--json", f"mcp-server {query}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logging.warning(f"npm search failed: {result.stderr}")
            return []
        packages = json.loads(result.stdout)
        return [
            {
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "version": p.get("version", ""),
            }
            for p in packages[:20]
        ]
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"npm search error: {e}")
        return []


def search_pip(query: str) -> List[Dict[str, str]]:
    """PyPI JSON API로 패키지를 검색합니다."""
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(f"https://pypi.org/pypi/{query}/json")
            if response.status_code != 200:
                return []
            data = response.json()
            info = data.get("info", {})
            return [
                {
                    "name": info.get("name", ""),
                    "description": info.get("summary", ""),
                    "version": info.get("version", ""),
                }
            ]
    except Exception as e:
        logging.error(f"PyPI search error: {e}")
        return []


def search_packages(query: str, manager: str = "all") -> Dict[str, List[Dict[str, str]]]:
    """npm/pip 통합 검색 결과를 반환합니다."""
    results: Dict[str, List[Dict[str, str]]] = {}
    if manager in ("npm", "all"):
        results["npm"] = search_npm(query)
    if manager in ("pip", "all"):
        results["pip"] = search_pip(query)
    return results


async def probe_server_tools(server_config: Dict[str, Any]) -> List[Dict[str, str]]:
    """서버에 임시 연결하여 도구 목록을 조회합니다."""
    resolved_args = _resolve_args(server_config.get("args", []))
    server_params = StdioServerParameters(
        command=server_config["command"],
        args=resolved_args,
        env=server_config.get("env"),
    )
    tools: List[Dict[str, str]] = []
    exit_stack = AsyncExitStack()
    try:
        await exit_stack.__aenter__()
        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        response = await session.list_tools()
        for tool in response.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or tool.name,
            })
    except Exception as e:
        logging.error(f"Failed to probe server '{server_config.get('name', '?')}': {e}")
    finally:
        await exit_stack.aclose()
    return tools


def get_tool_overlap_report(
    new_tools: List[Dict[str, str]],
    existing_tools: Dict[str, str],
) -> List[Dict[str, str]]:
    """새 도구와 기존 도구의 중복을 분석합니다.

    Returns:
        중복 도구 목록 [{"name": ..., "new_desc": ..., "existing_desc": ...}]
    """
    overlaps = []
    for tool in new_tools:
        name = tool["name"]
        if name in existing_tools:
            overlaps.append({
                "name": name,
                "new_desc": tool.get("description", ""),
                "existing_desc": existing_tools[name],
            })
    return overlaps


def _resolve_args(args: List[str]) -> List[str]:
    """args 내 "." 또는 "$CWD"를 os.getcwd()로 치환합니다."""
    cwd = os.getcwd()
    return [cwd if a in (".", "$CWD") else a for a in args]


def migrate_from_hardcoded(path: Optional[str] = None) -> Dict[str, Any]:
    """하드코딩된 config 값을 JSON 레지스트리로 변환합니다."""
    from . import config as cfg

    registry = dict(_EMPTY_REGISTRY)
    registry["servers"] = []
    registry["tool_name_aliases"] = dict(cfg._DEFAULT_TOOL_NAME_ALIASES)

    for s in cfg._DEFAULT_MCP_SERVERS:
        registry["servers"].append({
            "name": s["name"],
            "package": _guess_package(s),
            "package_manager": _guess_manager(s),
            "command": s["command"],
            "args": s["args"],
            "env": s.get("env"),
            "enabled": True,
            "added_at": date.today().isoformat(),
            "description": f"Migrated from hardcoded config: {s['name']}",
        })

    save_registry(registry, path)
    return registry


def _guess_package(server: Dict[str, Any]) -> str:
    """서버 설정에서 패키지 이름을 추측합니다."""
    if server["command"] == "npx" and server["args"]:
        for arg in server["args"]:
            if arg.startswith("@") or "server" in arg:
                return arg
    return server["command"]


def _guess_manager(server: Dict[str, Any]) -> str:
    """서버 설정에서 패키지 매니저를 추측합니다."""
    if server["command"] == "npx":
        return "npm"
    return "pip"
