#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tests/conftest.py
"""
Pytest 설정 파일.

테스트 실행 시 프로젝트의 루트 디렉토리를 Python 경로에 추가하여
'mcp_modules' 패키지를 찾을 수 있도록 합니다.
"""

import sys
from pathlib import Path

# 현재 파일(conftest.py)의 부모 디렉토리(tests/)의 부모 디렉토리(프로젝트 루트)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print(f"Pytest가 프로젝트 루트를 추가했습니다: {PROJECT_ROOT}")
