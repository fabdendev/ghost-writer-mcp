"""Tests for configuration loading and validation."""

import os
import pytest
import yaml

from src.config import (
    GhostWriterConfig,
    _resolve_env_vars,
    _resolve_env_recursive,
    load_config,
)


class TestEnvVarResolution:
    def test_resolves_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        assert _resolve_env_vars("${MY_TOKEN}") == "secret123"

    def test_resolves_multiple_env_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "5432")
        result = _resolve_env_vars("${HOST}:${PORT}")
        assert result == "localhost:5432"

    def test_raises_on_missing_env_var(self):
        # Ensure the var doesn't exist
        os.environ.pop("DEFINITELY_NOT_SET_XYZ", None)
        with pytest.raises(ValueError, match="DEFINITELY_NOT_SET_XYZ"):
            _resolve_env_vars("${DEFINITELY_NOT_SET_XYZ}")

    def test_passthrough_without_env_vars(self):
        assert _resolve_env_vars("plain string") == "plain string"

    def test_resolves_shell_command(self):
        result = _resolve_env_vars("$(echo hello)")
        assert result == "hello"

    def test_raises_on_failed_command(self):
        with pytest.raises(ValueError, match="failed"):
            _resolve_env_vars("$(false)")

    def test_recursive_resolution(self, monkeypatch):
        monkeypatch.setenv("KEY", "value")
        data = {
            "top": "${KEY}",
            "nested": {"deep": "${KEY}"},
            "list": ["${KEY}", "static"],
            "number": 42,
        }
        resolved = _resolve_env_recursive(data)
        assert resolved["top"] == "value"
        assert resolved["nested"]["deep"] == "value"
        assert resolved["list"] == ["value", "static"]
        assert resolved["number"] == 42


class TestLoadConfig:
    def test_loads_valid_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTH_KEY", "sk-test")

        config_data = {
            "github": {
                "token": "${GH_TOKEN}",
                "repos": [
                    {
                        "owner": "org",
                        "name": "repo",
                        "role": "architect",
                    }
                ],
            },
            "llm": {
                "api_key": "${ANTH_KEY}",
            },
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        # Clear lru_cache from previous calls
        load_config.cache_clear()

        cfg = load_config(str(config_file))
        assert cfg.github.token == "ghp_test"
        assert cfg.llm.api_key == "sk-test"
        assert cfg.github.repos[0].owner == "org"
        assert cfg.llm.provider == "ollama"  # default

    def test_pydantic_validates_required_fields(self):
        with pytest.raises(Exception):
            # Missing required github and llm fields
            GhostWriterConfig()

    def test_defaults_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTH_KEY", "sk-test")

        config_data = {
            "github": {
                "token": "${GH_TOKEN}",
                "repos": [{"owner": "o", "name": "r", "role": "dev"}],
            },
            "llm": {"api_key": "${ANTH_KEY}"},
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        load_config.cache_clear()
        cfg = load_config(str(config_file))

        assert cfg.sanitisation.blocklist == {}
        assert cfg.content.style.max_length == 1500
        assert cfg.content.style.use_emoji is False
        assert cfg.content.pillars == []
