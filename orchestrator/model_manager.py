#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/model_manager.py

import json
import os
import logging
from typing import Dict, List, Optional, Any

from google import genai

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "model_config.json")

_DEFAULT_CONFIG = {
    "version": "1.0",
    "active_provider": "gemini",
    "active_model": "gemini-2.0-flash-001",
    "providers": {
        "gemini": {
            "enabled": True,
            "api_key_env": "GEMINI_API_KEY",
            "fallback_env": "GOOGLE_API_KEY",
            "default_model": "gemini-2.0-flash-001",
        },
        "claude": {
            "enabled": True,
            "api_key_env": "ANTHROPIC_API_KEY",
            "default_model": "",
        },
        "openai": {
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
            "default_model": "",
        },
        "grok": {
            "enabled": True,
            "api_key_env": "XAI_API_KEY",
            "default_model": "",
        },
        "ollama": {
            "enabled": True,
            "api_key_env": "",
            "base_url_env": "OLLAMA_BASE_URL",
            "default_base_url": "http://localhost:11434",
            "default_model": "qwen2.5-coder:7b",
            "high_model": "qwen2.5-coder:7b",
            "standard_model": "qwen2.5-coder:3b",
        },
    },
}


def load_config(path: str = _CONFIG_PATH) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"model_config.json 로드 실패, 기본값 사용: {e}")
    return dict(_DEFAULT_CONFIG)


def save_config(config: Dict[str, Any], path: str = _CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_active_model(config: Optional[Dict[str, Any]] = None) -> tuple:
    if config is None:
        config = load_config()
    return config.get("active_provider", "gemini"), config.get("active_model", "gemini-2.0-flash-001")


def set_active_model(provider: str, model: str, config: Optional[Dict[str, Any]] = None, path: str = _CONFIG_PATH) -> Dict[str, Any]:
    if config is None:
        config = load_config(path)
    if provider not in config.get("providers", {}):
        raise ValueError(f"알 수 없는 프로바이더: {provider}")
    config["active_provider"] = provider
    config["active_model"] = model
    config["providers"][provider]["default_model"] = model
    save_config(config, path)
    return config


def list_providers(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if config is None:
        config = load_config()
    result = []
    for name, info in config.get("providers", {}).items():
        api_key_env = info.get("api_key_env", "")
        fallback_env = info.get("fallback_env", "")
        if name == "ollama":
            # Ollama는 API 키 불필요, 서버 가동 여부로 판단
            base_url = os.getenv(info.get("base_url_env", ""), info.get("default_base_url", "http://localhost:11434"))
            result.append({
                "name": name,
                "enabled": info.get("enabled", True),
                "api_key_env": "",
                "has_api_key": True,  # 키 불필요
                "default_model": info.get("default_model", ""),
                "base_url": base_url,
                "high_model": info.get("high_model", "qwen2.5-coder:7b"),
                "standard_model": info.get("standard_model", "qwen2.5-coder:3b"),
            })
            continue
        has_key = bool(os.getenv(api_key_env)) or bool(os.getenv(fallback_env)) if fallback_env else bool(os.getenv(api_key_env))
        result.append({
            "name": name,
            "enabled": info.get("enabled", True),
            "api_key_env": api_key_env,
            "has_api_key": has_key,
            "default_model": info.get("default_model", ""),
        })
    return result


def _get_api_key(provider_info: Dict[str, Any]) -> Optional[str]:
    key = os.getenv(provider_info.get("api_key_env", ""))
    if not key:
        fallback = provider_info.get("fallback_env", "")
        if fallback:
            key = os.getenv(fallback)
    return key


async def fetch_models_gemini(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    if config is None:
        config = load_config()
    provider_info = config.get("providers", {}).get("gemini", {})
    api_key = _get_api_key(provider_info)
    if not api_key:
        raise ValueError(f"API 키 미설정 (환경변수: {provider_info.get('api_key_env', 'GEMINI_API_KEY')})")

    client = genai.Client(api_key=api_key)
    models = []
    for model in client.models.list():
        models.append({
            "id": model.name,
            "name": model.display_name if hasattr(model, "display_name") else model.name,
            "description": model.description if hasattr(model, "description") else "",
        })
    return models


async def fetch_models_claude(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    if config is None:
        config = load_config()
    provider_info = config.get("providers", {}).get("claude", {})
    api_key = _get_api_key(provider_info)
    if not api_key:
        raise ValueError(f"API 키 미설정 (환경변수: {provider_info.get('api_key_env', 'ANTHROPIC_API_KEY')})")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        models.append({
            "id": m.get("id", ""),
            "name": m.get("display_name", m.get("id", "")),
            "description": m.get("description", ""),
        })
    return models


async def fetch_models_openai(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    if config is None:
        config = load_config()
    provider_info = config.get("providers", {}).get("openai", {})
    api_key = _get_api_key(provider_info)
    if not api_key:
        raise ValueError(f"API 키 미설정 (환경변수: {provider_info.get('api_key_env', 'OPENAI_API_KEY')})")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        models.append({
            "id": m.get("id", ""),
            "name": m.get("id", ""),
            "description": m.get("owned_by", ""),
        })
    return models


async def fetch_models_grok(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    if config is None:
        config = load_config()
    provider_info = config.get("providers", {}).get("grok", {})
    api_key = _get_api_key(provider_info)
    if not api_key:
        raise ValueError(f"API 키 미설정 (환경변수: {provider_info.get('api_key_env', 'XAI_API_KEY')})")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        models.append({
            "id": m.get("id", ""),
            "name": m.get("id", ""),
            "description": m.get("owned_by", ""),
        })
    return models


async def fetch_models_ollama(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Ollama /api/tags 엔드포인트에서 설치된 모델 목록을 조회합니다."""
    if config is None:
        config = load_config()
    provider_info = config.get("providers", {}).get("ollama", {})
    base_url = os.getenv(
        provider_info.get("base_url_env", "OLLAMA_BASE_URL"),
        provider_info.get("default_base_url", "http://localhost:11434"),
    )

    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base_url}/api/tags")
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("models", []):
        models.append({
            "id": m.get("name", ""),
            "name": m.get("name", ""),
            "description": f"size: {m.get('size', 0) // 1024 // 1024}MB",
        })
    return models


_PROVIDER_FETCHERS = {
    "gemini": fetch_models_gemini,
    "claude": fetch_models_claude,
    "openai": fetch_models_openai,
    "grok": fetch_models_grok,
    "ollama": fetch_models_ollama,
}


async def fetch_models(provider: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    fetcher = _PROVIDER_FETCHERS.get(provider)
    if not fetcher:
        raise ValueError(f"알 수 없는 프로바이더: {provider}")
    return await fetcher(config)
