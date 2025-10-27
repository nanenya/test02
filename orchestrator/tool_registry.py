#!/usr/bin/env python3

import os
import importlib
import inspect
from typing import Dict, Any, Callable

MCP_DIRECTORY = "mcp_modules"
TOOLS: Dict[str, Callable] = {}
TOOL_DESCRIPTIONS: Dict[str, str] = {}

def load_tools():
    """mcp_modules 디렉토리에서 모든 MCP를 동적으로 로드합니다."""
    for filename in os.listdir(MCP_DIRECTORY):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"{MCP_DIRECTORY}.{filename[:-3]}"
            module = importlib.import_module(module_name)
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("_"):
                    TOOLS[name] = func
                    description = func.__doc__.strip() if func.__doc__ else name #f"'{name}' 도구에 대한 설명이 없습니다."
                    TOOL_DESCRIPTIONS[name] = description # func.__doc__.strip()
                    print(f"✅ Tool loaded: {name}")

def get_tool(name: str) -> Callable:
    """이름으로 MCP 함수를 가져옵니다."""
    return TOOLS.get(name)

def get_all_tool_descriptions() -> str:
    """Gemini 프롬프트에 사용할 모든 MCP의 설명 문자열을 생성합니다."""
    return "\n".join(
        f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()
    )

# 애플리케이션 시작 시 한 번만 로드
load_tools()
