#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_model_manager.py

import json
import os
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from . import model_manager


@pytest.fixture
def tmp_config(tmp_path):
    """임시 model_config.json 경로를 반환합니다."""
    config_path = str(tmp_path / "model_config.json")
    config = {
        "version": "1.0",
        "active_provider": "gemini",
        "active_model": "gemini-2.0-flash",
        "providers": {
            "gemini": {
                "enabled": True,
                "api_key_env": "GEMINI_API_KEY",
                "fallback_env": "GOOGLE_API_KEY",
                "default_model": "gemini-2.0-flash",
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
        },
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return config_path


class TestConfigIO:
    def test_load_config_from_file(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        assert config["version"] == "1.0"
        assert config["active_provider"] == "gemini"
        assert "gemini" in config["providers"]

    def test_load_config_default_when_missing(self, tmp_path):
        missing_path = str(tmp_path / "nonexistent.json")
        config = model_manager.load_config(missing_path)
        assert config["active_provider"] == "gemini"
        assert config["active_model"] == "gemini-2.0-flash"

    def test_save_and_reload(self, tmp_path):
        config_path = str(tmp_path / "test_save.json")
        config = {"version": "1.0", "active_provider": "claude", "active_model": "claude-3", "providers": {}}
        model_manager.save_config(config, config_path)
        reloaded = model_manager.load_config(config_path)
        assert reloaded["active_provider"] == "claude"
        assert reloaded["active_model"] == "claude-3"


class TestSetActiveModel:
    def test_set_active_model(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        updated = model_manager.set_active_model("gemini", "gemini-2.0-flash-lite", config, tmp_config)
        assert updated["active_provider"] == "gemini"
        assert updated["active_model"] == "gemini-2.0-flash-lite"
        assert updated["providers"]["gemini"]["default_model"] == "gemini-2.0-flash-lite"

        reloaded = model_manager.load_config(tmp_config)
        assert reloaded["active_model"] == "gemini-2.0-flash-lite"

    def test_set_unknown_provider_raises(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with pytest.raises(ValueError, match="알 수 없는 프로바이더"):
            model_manager.set_active_model("unknown_provider", "some-model", config, tmp_config)

    def test_get_active_model(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        provider, model = model_manager.get_active_model(config)
        assert provider == "gemini"
        assert model == "gemini-2.0-flash"


class TestListProviders:
    def test_list_providers_with_keys(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            providers = model_manager.list_providers(config)
            gemini = next(p for p in providers if p["name"] == "gemini")
            assert gemini["has_api_key"] is True
            assert gemini["enabled"] is True

    def test_list_providers_without_keys(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        env_clean = {
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "XAI_API_KEY": "",
        }
        with patch.dict(os.environ, env_clean, clear=False):
            providers = model_manager.list_providers(config)
            for p in providers:
                assert p["has_api_key"] is False


class TestFetchModels:
    @pytest.mark.asyncio
    async def test_fetch_models_gemini_mock(self, tmp_config):
        config = model_manager.load_config(tmp_config)

        mock_model = MagicMock()
        mock_model.name = "models/gemini-2.0-flash"
        mock_model.display_name = "Gemini 2.0 Flash"
        mock_model.description = "Fast model"

        mock_client = MagicMock()
        mock_client.models.list.return_value = [mock_model]

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            with patch.object(model_manager, "genai") as mock_genai:
                mock_genai.Client.return_value = mock_client
                models = await model_manager.fetch_models_gemini(config)

        assert len(models) == 1
        assert models[0]["id"] == "models/gemini-2.0-flash"
        assert models[0]["name"] == "Gemini 2.0 Flash"

    @pytest.mark.asyncio
    async def test_fetch_models_claude_mock(self, tmp_config):
        config = model_manager.load_config(tmp_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "claude-3-opus", "display_name": "Claude 3 Opus", "description": "Most capable"}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                models = await model_manager.fetch_models_claude(config)

        assert len(models) == 1
        assert models[0]["id"] == "claude-3-opus"

    @pytest.mark.asyncio
    async def test_fetch_models_openai_mock(self, tmp_config):
        config = model_manager.load_config(tmp_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4", "owned_by": "openai"}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                models = await model_manager.fetch_models_openai(config)

        assert len(models) == 1
        assert models[0]["id"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_fetch_models_grok_mock(self, tmp_config):
        config = model_manager.load_config(tmp_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "grok-2", "owned_by": "xai"}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"XAI_API_KEY": "test-key"}, clear=False):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                models = await model_manager.fetch_models_grok(config)

        assert len(models) == 1
        assert models[0]["id"] == "grok-2"

    @pytest.mark.asyncio
    async def test_fetch_models_dispatcher(self, tmp_config):
        config = model_manager.load_config(tmp_config)

        mock_fetcher = AsyncMock(return_value=[{"id": "test-model", "name": "Test", "description": ""}])
        with patch.dict(model_manager._PROVIDER_FETCHERS, {"gemini": mock_fetcher}):
            models = await model_manager.fetch_models("gemini", config)
            assert len(models) == 1
            mock_fetcher.assert_called_once_with(config)

    @pytest.mark.asyncio
    async def test_fetch_models_unknown_provider(self):
        with pytest.raises(ValueError, match="알 수 없는 프로바이더"):
            await model_manager.fetch_models("unknown")


class TestFetchModelsNoApiKey:
    @pytest.mark.asyncio
    async def test_gemini_no_key(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="API 키 미설정"):
                await model_manager.fetch_models_gemini(config)

    @pytest.mark.asyncio
    async def test_claude_no_key(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="API 키 미설정"):
                await model_manager.fetch_models_claude(config)

    @pytest.mark.asyncio
    async def test_openai_no_key(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="API 키 미설정"):
                await model_manager.fetch_models_openai(config)

    @pytest.mark.asyncio
    async def test_grok_no_key(self, tmp_config):
        config = model_manager.load_config(tmp_config)
        with patch.dict(os.environ, {"XAI_API_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="API 키 미설정"):
                await model_manager.fetch_models_grok(config)
