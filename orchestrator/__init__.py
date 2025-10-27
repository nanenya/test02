#!/usr/bin/env python3

import logging

# orchestrator 패키지가 처음 import될 때 로깅 기본 설정을 수행
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("🚀 Orchestrator package has been initialized.")
