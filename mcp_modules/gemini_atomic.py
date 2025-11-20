#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mcp_modules/gemini_atomic.py

import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from typing import Optional

# 로거 설정
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 모델 설정
DEFAULT_MODEL = "gemini-1.5-flash-latest"

def ask_gemini(
    prompt: str, 
    system_instruction: Optional[str] = None, 
    model_name: str = "auto",
    temperature: float = 0.7
) -> str:
    """
    Gemini AI 모델에게 질문하고 응답을 받습니다.
    CLI, Orchestrator, 다른 MCP에서 공통으로 사용할 수 있는 Atomic function입니다.

    Args:
        prompt (str): AI에게 보낼 사용자 질문 또는 작업 내용.
        system_instruction (str, optional): 시스템 페르소나 설정 (shared/prompt_manager 사용 권장).
        model_name (str, optional): 사용할 모델 ('auto', 'high', 'standard' 또는 구체적 모델명).
        temperature (float, optional): 창의성 조절 (0.0 ~ 1.0).

    Returns:
        str: AI의 응답 텍스트.
    """
    logger.info(f"Gemini 요청: {prompt[:50]}... (Model: {model_name})")
    
    # 모델 선택 로직
    target_model_name = DEFAULT_MODEL
    if model_name == "high":
        target_model_name = os.getenv("GEMINI_HIGH_PERF_MODEL", "gemini-1.5-pro-latest")
    elif model_name == "standard" or model_name == "auto":
        target_model_name = os.getenv("GEMINI_STANDARD_MODEL", "gemini-1.5-flash-latest")
    elif model_name:
        target_model_name = model_name

    try:
        # 시스템 프롬프트 적용을 위한 모델 생성
        model = genai.GenerativeModel(
            model_name=target_model_name,
            system_instruction=system_instruction
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature
            )
        )
        
        if response.text:
            logger.info("Gemini 응답 수신 성공.")
            return response.text.strip()
        else:
            logger.warning("Gemini 응답이 비어 있습니다.")
            return "응답을 생성하지 못했습니다."

    except Exception as e:
        logger.error(f"Gemini API 호출 중 오류 발생: {e}")
        return f"AI 요청 처리 중 오류가 발생했습니다: {e}"
