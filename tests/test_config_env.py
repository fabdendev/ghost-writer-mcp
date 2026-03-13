"""Tests for .env file loading and config edge cases."""

import os


from src.config import load_config


def test_loads_env_file(tmp_path):
    """Config should load variables from .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_GW_TOKEN=my-secret-token\n")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "github:\n"
        "  token: '${TEST_GW_TOKEN}'\n"
        "  repos:\n"
        "    - owner: org\n"
        "      name: repo\n"
        "      role: dev\n"
        "llm:\n"
        "  provider: ollama\n"
    )

    # Clear cache and env to test fresh
    load_config.cache_clear()
    os.environ.pop("TEST_GW_TOKEN", None)

    try:
        cfg = load_config(str(config_file))
        assert cfg.github.token == "my-secret-token"
    finally:
        load_config.cache_clear()
        os.environ.pop("TEST_GW_TOKEN", None)


def test_env_file_comments_ignored(tmp_path):
    """.env comments and empty lines should be skipped."""
    env_file = tmp_path / ".env"
    env_file.write_text("# This is a comment\n\nTEST_GW_VAL=hello\n")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "github:\n"
        "  token: '${TEST_GW_VAL}'\n"
        "  repos:\n"
        "    - owner: org\n"
        "      name: repo\n"
        "      role: dev\n"
        "llm:\n"
        "  provider: ollama\n"
    )

    load_config.cache_clear()
    os.environ.pop("TEST_GW_VAL", None)

    try:
        cfg = load_config(str(config_file))
        assert cfg.github.token == "hello"
    finally:
        load_config.cache_clear()
        os.environ.pop("TEST_GW_VAL", None)


def test_env_does_not_override_existing(tmp_path):
    """.env should use setdefault — existing env vars win."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_GW_EXISTING=from-env-file\n")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "github:\n"
        "  token: '${TEST_GW_EXISTING}'\n"
        "  repos:\n"
        "    - owner: org\n"
        "      name: repo\n"
        "      role: dev\n"
        "llm:\n"
        "  provider: ollama\n"
    )

    load_config.cache_clear()
    os.environ["TEST_GW_EXISTING"] = "from-real-env"

    try:
        cfg = load_config(str(config_file))
        assert cfg.github.token == "from-real-env"
    finally:
        load_config.cache_clear()
        os.environ.pop("TEST_GW_EXISTING", None)


def test_default_host():
    """GitHubConfig should default to github.com."""
    from src.config import GitHubConfig, RepoConfig

    cfg = GitHubConfig(repos=[RepoConfig(owner="org", name="repo", role="dev")])
    assert cfg.host == "https://github.com"
