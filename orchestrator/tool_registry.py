#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/tool_registry.py

import os
import importlib
import inspect
from typing import Dict, Any, Callable

MCP_DIRECTORY = "mcp_modules"
TOOLS: Dict[str, Callable] = {}
TOOL_DESCRIPTIONS: Dict[str, str] = {}

def load_tools():
    """mcp_modules 디렉토리에서 모든 MCP를 동적으로 로드합니다."""
    # (수정) 디렉토리가 없을 경우 생성
    if not os.path.exists(MCP_DIRECTORY):
        os.makedirs(MCP_DIRECTORY)
        print(f"경고: '{MCP_DIRECTORY}' 디렉토리가 없어 생성했습니다. 도구가 로드되지 않았습니다.")
        return

    for filename in os.listdir(MCP_DIRECTORY):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"{MCP_DIRECTORY}.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for name, func in inspect.getmembers(module, inspect.isfunction):
                    if not name.startswith("_"):
                        TOOLS[name] = func
                        description = func.__doc__.strip() if func.__doc__ else name 
                        TOOL_DESCRIPTIONS[name] = description 
                        print(f"Tool loaded: {name}")
            except ImportError as e:
                print(f"모듈 로드 실패: {module_name} ({e})")


def get_tool(name: str) -> Callable:
    """이름으로 MCP 함수를 가져옵니다."""
    return TOOLS.get(name)

def get_all_tool_descriptions() -> str:
    """Gemini 프롬프트에 사용할 모든 MCP의 설명 문자열을 생성합니다."""
    return "\n".join(
        f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()
    )

# 애플리케이션 시작 시 한 번만 로드 (api.py의 @app.on_event("startup")로 이동됨)
# load_tools()
