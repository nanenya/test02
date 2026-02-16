#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/config.py

import os

MCP_DIRECTORY = "mcp_modules"

# 유지할 로컬 커스텀 모듈 (MCP 서버로 대체하지 않는 모듈)
LOCAL_MODULES = [
    "user_interaction_atomic",
    "user_interaction_composite",
    "code_execution_atomic",
    "code_execution_composite",
]

# MCP 공식 서버 설정
MCP_SERVERS = [
    {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", os.getcwd()],
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

# 기존 도구명 → MCP 도구명 매핑 (하위 호환성)
TOOL_NAME_ALIASES = {
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
