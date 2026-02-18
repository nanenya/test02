#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/config.py

import json
import os
import logging
from typing import Any, Dict, List

MCP_DIRECTORY = "mcp_modules"

# 유지할 로컬 커스텀 모듈 (MCP 서버로 대체하지 않는 모듈)
LOCAL_MODULES = [
    "user_interaction_atomic",
    "user_interaction_composite",
    "code_execution_atomic",
    "code_execution_composite",
    "file_attributes",
    "file_management",
    "file_content_operations",
    "file_system_composite",
    "git_version_control",
    "web_network_atomic",
]

# --- 하드코딩 기본값 (fallback용) ---

_DEFAULT_MCP_SERVERS = [
    {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": None,
    },
    {
        "name": "git",
        "command": "mcp-server-git",
        "args": [],
        "env": None,
    },
    {
        "name": "fetch",
        "command": "mcp-server-fetch",
        "args": [],
        "env": None,
    },
]

_DEFAULT_TOOL_NAME_ALIASES = {
    # filesystem 서버
    "read_file": "read_file",
    "write_file": "write_file",
    "create_directory": "create_directory",
    "list_directory": "list_directory",
    "move": "move_file",
    "find_files": "search_files",
    "get_file_size": "get_file_info",
    "path_exists": "get_file_info",
    "is_file": "get_file_info",
    "is_directory": "get_file_info",
    # git 서버
    "git_status": "git_status",
    "git_add": "git_add",
    "git_commit": "git_commit",
    "git_push": "git_push",
    "git_pull": "git_pull",
    "git_log": "git_log",
    "git_diff": "git_diff",
    "git_clone": "git_clone",
    "git_init": "git_init",
    "git_create_branch": "git_create_branch",
    "git_list_branches": "git_list_branches",
    # fetch 서버
    "fetch_url_content": "fetch",
    "api_get_request": "fetch",
    "api_post_request": "fetch",
    "download_file_from_url": "fetch",
}

_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers.json")


def _resolve_args(args: List[str]) -> List[str]:
    """args 내 "." 또는 "$CWD"를 os.getcwd()로 치환합니다."""
    cwd = os.getcwd()
    return [cwd if a in (".", "$CWD") else a for a in args]


def load_mcp_config() -> tuple:
    """MCP 서버 설정을 로드합니다.

    Returns:
        (servers_list, aliases_dict) 튜플
    """
    if os.path.exists(_REGISTRY_PATH):
        try:
            with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
                registry = json.load(f)
            servers = []
            for s in registry.get("servers", []):
                if not s.get("enabled", True):
                    continue
                servers.append({
                    "name": s["name"],
                    "command": s["command"],
                    "args": _resolve_args(s.get("args", [])),
                    "env": s.get("env"),
                })
            aliases = registry.get("tool_name_aliases", dict(_DEFAULT_TOOL_NAME_ALIASES))
            logging.info(f"MCP config loaded from {_REGISTRY_PATH}: {len(servers)} servers")
            return servers, aliases
        except Exception as e:
            logging.warning(f"Failed to load {_REGISTRY_PATH}, using defaults: {e}")

    # fallback: 하드코딩 기본값
    servers = []
    for s in _DEFAULT_MCP_SERVERS:
        servers.append({
            "name": s["name"],
            "command": s["command"],
            "args": _resolve_args(s["args"]),
            "env": s.get("env"),
        })
    return servers, dict(_DEFAULT_TOOL_NAME_ALIASES)


# 모듈 로드 시 설정
MCP_SERVERS, TOOL_NAME_ALIASES = load_mcp_config()


# --- AI 모델 설정 ---

def load_model_config() -> tuple:
    """model_config.json에서 현재 활성 프로바이더/모델을 읽습니다.

    Returns:
        (provider, model) 튜플. 파일이 없으면 기본값 ("gemini", "gemini-2.0-flash").
    """
    from .model_manager import load_config, get_active_model
    config = load_config()
    return get_active_model(config)


ACTIVE_PROVIDER, ACTIVE_MODEL = load_model_config()
