#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/test_config.py

import logging
import pytest
from . import config
from .config import _validate_server_config, _ALLOWED_MCP_COMMANDS


# ── TestValidateServerConfig ──────────────────────────────────────

class TestValidateServerConfig:
    def test_allowed_command_passes(self):
        server = {"name": "fs", "command": "npx", "args": ["-y", "@mcp/server-filesystem", "."]}
        assert _validate_server_config(server) is True

    def test_disallowed_command_returns_false(self, caplog):
        server = {"name": "evil", "command": "bash", "args": []}
        with caplog.at_level(logging.WARNING):
            result = _validate_server_config(server)
        assert result is False
        assert "허용되지 않은 command" in caplog.text

    def test_shell_inject_char_in_args_returns_false(self, caplog):
        server = {"name": "inject", "command": "npx", "args": ["safe", "; rm -rf /"]}
        with caplog.at_level(logging.WARNING):
            result = _validate_server_config(server)
        assert result is False
        assert "위험 문자" in caplog.text

    def test_all_allowed_commands_pass(self):
        for cmd in _ALLOWED_MCP_COMMANDS:
            server = {"name": "s", "command": cmd, "args": []}
            assert _validate_server_config(server) is True

    def test_pipe_char_blocked(self):
        server = {"name": "p", "command": "npx", "args": ["arg | cat /etc/passwd"]}
        assert _validate_server_config(server) is False

    def test_backtick_char_blocked(self):
        server = {"name": "b", "command": "node", "args": ["`id`"]}
        assert _validate_server_config(server) is False

    def test_empty_args_passes(self):
        server = {"name": "git", "command": "mcp-server-git", "args": []}
        assert _validate_server_config(server) is True

    def test_invalid_server_skipped_in_load(self, tmp_path, monkeypatch):
        """load_mcp_config에서 검증 실패 서버는 결과 목록에서 제외된다."""
        import json
        registry = {
            "servers": [
                {"name": "ok", "command": "npx", "args": [], "enabled": True},
                {"name": "bad", "command": "curl", "args": [], "enabled": True},
            ],
            "tool_name_aliases": {},
        }
        registry_path = tmp_path / "mcp_servers.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        monkeypatch.setattr(config, "_REGISTRY_PATH", str(registry_path))
        servers, _ = config.load_mcp_config()
        names = [s["name"] for s in servers]
        assert "ok" in names
        assert "bad" not in names
