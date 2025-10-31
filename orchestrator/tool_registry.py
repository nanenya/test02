#!/usr/bin/env python3

import os
import importlib
import inspect
import logging
from typing import Dict, Any, Callable
from . import config

TOOLS: Dict[str, Callable] = {}
TOOL_DESCRIPTIONS: Dict[str, str] = {}

def load_tools():
    """mcp_modules 디렉토리에서 모든 MCP를 동적으로 로드합니다."""
    for filename in os.listdir(config.MCP_DIRECTORY):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"{config.MCP_DIRECTORY}.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for name, func in inspect.getmembers(module, inspect.isfunction):
                    if not name.startswith("_"):
                        TOOLS[name] = func
                        description = func.__doc__.strip() if func.__doc__ else name
                        TOOL_DESCRIPTIONS[name] = description
                        logging.info(f"Tool loaded: {name}")
            except Exception as e:
                logging.error(f"Failed to load module {module_name}: {e}")

def get_tool(name: str) -> Callable:
    """이름으로 MCP 함수를 가져옵니다."""
    return TOOLS.get(name)

def get_all_tool_descriptions() -> Dict[str, str]:
    """모든 MCP의 이름과 설명을 반환합니다."""
    return TOOL_DESCRIPTIONS

# 애플리케이션 시작 시 MCP 로드
load_tools()
