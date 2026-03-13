"""Unified LLM client supporting Anthropic and Ollama (OpenAI-compatible)."""

import httpx

from src.config import LLMConfig

_DEFAULT_TIMEOUT = 120  # seconds


class LLMClient:
    """Thin wrapper that normalises Anthropic and OpenAI-compatible APIs."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._provider = config.provider

        if self._provider == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=config.api_key,
                timeout=_DEFAULT_TIMEOUT,
            )
        else:
            # Ollama and any OpenAI-compatible provider
            import openai

            self._client = openai.OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=_DEFAULT_TIMEOUT,
            )
            self._check_ollama(config.base_url)

    def _check_ollama(self, base_url: str) -> None:
        """Verify Ollama is reachable. Raises with a clear message if not."""
        # base_url is e.g. http://localhost:11434/v1 — check root
        root = base_url.rstrip("/").rsplit("/v1", 1)[0]
        try:
            resp = httpx.get(root, timeout=5)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException):
            raise ConnectionError(
                f"Cannot reach Ollama at {root}. "
                f"Start it with: ollama serve"
            )

    def complete(
        self,
        model: str,
        system: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """Send a system + user message and return the assistant's text."""
        if self._provider == "anthropic":
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        # OpenAI-compatible (Ollama, vLLM, etc.)
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content
