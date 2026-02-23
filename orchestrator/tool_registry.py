#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/tool_registry.py

import os
import importlib
import inspect
import logging
from typing import Dict, Any, Callable, List, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import config

# 로컬 도구 저장소
TOOLS: Dict[str, Callable] = {}
TOOL_DESCRIPTIONS: Dict[str, str] = {}

# MCP 서버 세션 및 도구 저장소
_exit_stack: Optional[AsyncExitStack] = None
_mcp_sessions: Dict[str, ClientSession] = {}
_mcp_tools: Dict[str, dict] = {}  # tool_name -> {"session": session, "description": str}

# 다중 제공자 추적
_tool_providers: Dict[str, List[dict]] = {}  # tool_name -> [{"server": name, "session": session, "description": str}]
_tool_server_preferences: Dict[str, str] = {}  # tool_name -> preferred server_name


def _load_local_modules():
    """LOCAL_MODULES에 정의된 커스텀 모듈만 로드합니다."""
    for module_name in config.LOCAL_MODULES:
        full_module_name = f"{config.MCP_DIRECTORY}.{module_name}"
        try:
            module = importlib.import_module(full_module_name)
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    TOOLS[name] = func
                    description = func.__doc__.strip() if func.__doc__ else name
                    TOOL_DESCRIPTIONS[name] = description
                    logging.info(f"Local tool loaded: {name}")
        except Exception as e:
            logging.error(f"Failed to load module {full_module_name}: {e}")


async def _connect_mcp_server(exit_stack: AsyncExitStack, server_config: dict):
    """단일 MCP 서버에 연결하고 도구를 등록합니다."""
    server_name = server_config["name"]
    server_params = StdioServerParameters(
        command=server_config["command"],
        args=server_config["args"],
        env=server_config.get("env"),
    )

    try:
        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        _mcp_sessions[server_name] = session

        response = await session.list_tools()
        for tool in response.tools:
            tool_entry = {
                "session": session,
                "server": server_name,
                "description": tool.description or tool.name,
                "input_schema": tool.inputSchema,
            }

            # 첫 번째 등록이면 기본 도구로 설정
            if tool.name not in _mcp_tools:
                _mcp_tools[tool.name] = tool_entry
                TOOL_DESCRIPTIONS[tool.name] = tool.description or tool.name

            # 다중 제공자 추적에 추가
            _tool_providers.setdefault(tool.name, []).append({
                "server": server_name,
                "session": session,
                "description": tool.description or tool.name,
            })

            logging.info(f"MCP tool loaded from [{server_name}]: {tool.name}")

        logging.info(
            f"MCP server [{server_name}] connected with "
            f"{len(response.tools)} tools"
        )
    except Exception as e:
        logging.error(f"Failed to connect MCP server [{server_name}]: {e}")


async def initialize():
    """모든 로컬 모듈과 MCP 서버를 초기화합니다."""
    global _exit_stack

    # 로컬 모듈 로드
    _load_local_modules()

    # MCP 서버 연결
    _exit_stack = AsyncExitStack()
    await _exit_stack.__aenter__()

    failed_servers = []
    for server_config in config.MCP_SERVERS:
        before = len(_mcp_sessions)
        await _connect_mcp_server(_exit_stack, server_config)
        if len(_mcp_sessions) == before:
            failed_servers.append(server_config["name"])

    if failed_servers:
        if len(failed_servers) == len(config.MCP_SERVERS):
            logging.warning(
                f"All MCP servers failed to connect: {failed_servers}"
            )
        else:
            logging.warning(
                f"{len(failed_servers)} MCP server(s) failed to connect: {failed_servers}"
            )

    logging.info(
        f"Tool registry initialized: "
        f"{len(TOOLS)} local tools, {len(_mcp_tools)} MCP tools"
    )


async def shutdown():
    """MCP 서버 연결을 정리합니다."""
    global _exit_stack
    if _exit_stack:
        await _exit_stack.aclose()
        _exit_stack = None
    _mcp_sessions.clear()
    _mcp_tools.clear()
    _tool_providers.clear()
    _tool_server_preferences.clear()
    logging.info("Tool registry shutdown complete")


def get_tool(name: str) -> Optional[Callable]:
    """이름으로 도구 함수를 가져옵니다.

    로컬 도구는 직접 함수를 반환하고,
    MCP 도구는 session.call_tool()을 감싸는 async wrapper를 반환합니다.
    별칭(alias)도 지원합니다.
    선호 서버가 설정되어 있으면 해당 서버의 세션을 사용합니다.
    """
    # 1. 로컬 도구에서 먼저 검색
    if name in TOOLS:
        return TOOLS[name]

    # 2. 별칭 적용
    resolved_name = config.TOOL_NAME_ALIASES.get(name, name)

    # 3. MCP 도구에서 검색
    if resolved_name in _mcp_tools:
        # 선호 서버 확인
        preferred_server = _tool_server_preferences.get(resolved_name)
        session = None

        if preferred_server and resolved_name in _tool_providers:
            for provider in _tool_providers[resolved_name]:
                if provider["server"] == preferred_server:
                    session = provider["session"]
                    break

        if session is None:
            session = _mcp_tools[resolved_name]["session"]

        async def mcp_tool_wrapper(**kwargs):
            result = await session.call_tool(resolved_name, arguments=kwargs)
            # MCP 결과에서 텍스트 컨텐츠 추출
            if result.content:
                texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        texts.append(content.text)
                return "\n".join(texts) if texts else str(result.content)
            return str(result)

        return mcp_tool_wrapper

    return None


def get_tool_providers(name: str) -> List[dict]:
    """해당 도구를 제공하는 모든 서버 정보를 반환합니다."""
    resolved_name = config.TOOL_NAME_ALIASES.get(name, name)
    return _tool_providers.get(resolved_name, [])


def set_tool_preference(tool_name: str, server_name: str) -> bool:
    """특정 도구의 선호 서버를 설정합니다."""
    resolved_name = config.TOOL_NAME_ALIASES.get(tool_name, tool_name)
    providers = _tool_providers.get(resolved_name, [])
    if not any(p["server"] == server_name for p in providers):
        return False
    _tool_server_preferences[resolved_name] = server_name
    return True


def get_duplicate_tools() -> Dict[str, List[str]]:
    """2개 이상의 서버가 제공하는 도구 목록을 반환합니다.

    Returns:
        {tool_name: [server1, server2, ...]}
    """
    duplicates = {}
    for tool_name, providers in _tool_providers.items():
        if len(providers) >= 2:
            duplicates[tool_name] = [p["server"] for p in providers]
    return duplicates


def get_all_tool_descriptions() -> Dict[str, str]:
    """모든 도구(로컬 + MCP)의 이름과 설명을 반환합니다."""
    return TOOL_DESCRIPTIONS


def get_filtered_tool_descriptions(allowed_skills=None) -> Dict[str, str]:
    """allowed_skills 필터를 적용한 도구 이름/설명 딕셔너리 반환.
    allowed_skills가 None 또는 빈 리스트이면 전체 반환."""
    if not allowed_skills:
        return TOOL_DESCRIPTIONS
    return {k: v for k, v in TOOL_DESCRIPTIONS.items() if k in allowed_skills}
