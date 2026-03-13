"""Configuration layer for Ghost Writer MCP.

Loads YAML configuration, resolves environment variables, and validates
through Pydantic models.
"""

import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RepoConfig(BaseModel):
    owner: str
    name: str
    role: str
    content_weight: float = 1.0
    local_path: str | None = None


class GitHubConfig(BaseModel):
    token: str = ""
    host: str = "https://github.com"
    repos: list[RepoConfig]


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    classifier_model: str = "qwen3:8b"
    generator_model: str = "qwen3:8b"
    api_key: str = "ollama"


class SanitisationConfig(BaseModel):
    blocklist: dict[str, list[str]] = {}
    abstractions: dict[str, str] = {}


class ContentPillar(BaseModel):
    name: str
    description: str
    repo_signals: list[str] = []
    weight: float = 1.0


class StyleConfig(BaseModel):
    tone: str = "pragmatic, technically credible"
    language: str = "en"
    max_length: int = 1500
    use_emoji: bool = False
    use_hashtags: bool = True
    hashtag_count: int = 3
    few_shot_posts: list[str] = []


class ContentConfig(BaseModel):
    pillars: list[ContentPillar] = []
    style: StyleConfig = StyleConfig()


class GhostWriterConfig(BaseModel):
    github: GitHubConfig
    llm: LLMConfig
    sanitisation: SanitisationConfig = SanitisationConfig()
    content: ContentConfig = ContentConfig()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")
_CMD_PATTERN = re.compile(r"\$\(([^)]+)\)")


def _resolve_env_vars(value: str) -> str:
    """Replace ``${ENV_VAR}`` and ``$(command)`` placeholders.

    - ``${ENV_VAR}`` → resolved from environment (raises on missing)
    - ``$(command)`` → resolved by running the shell command
    """

    def _env_replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name not in os.environ:
            raise ValueError(
                f"Environment variable '{var_name}' is not set"
            )
        return os.environ[var_name]

    def _cmd_replacer(match: re.Match) -> str:
        cmd = match.group(1)
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise ValueError(f"Command '{cmd}' failed: {result.stderr.strip()}")
        return result.stdout.strip()

    value = _CMD_PATTERN.sub(_cmd_replacer, value)
    value = _ENV_VAR_PATTERN.sub(_env_replacer, value)
    return value


def _resolve_env_recursive(data):
    """Recursively walk *data* and resolve environment variable placeholders."""
    if isinstance(data, dict):
        return {k: _resolve_env_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_env_recursive(item) for item in data]
    if isinstance(data, str):
        return _resolve_env_vars(data)
    return data


@lru_cache(maxsize=1)
def load_config(config_path: str | None = None) -> GhostWriterConfig:
    """Load, resolve, and validate the Ghost Writer configuration.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.  Defaults to
        ``config.yaml`` in the project root (one level above ``src/``).
    """
    if config_path is None:
        path = Path(__file__).parent.parent / "config.yaml"
    else:
        path = Path(config_path)

    # Load .env file if present (simple key=value, no quotes handling needed)
    env_file = path.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    with open(path, "r") as fh:
        raw = yaml.safe_load(fh)

    resolved = _resolve_env_recursive(raw)
    return GhostWriterConfig(**resolved)
