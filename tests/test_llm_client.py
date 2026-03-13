"""Tests for LLM client provider switching."""

from unittest.mock import patch, MagicMock

from ghost_writer_mcp.config import LLMConfig
from ghost_writer_mcp.llm_client import LLMClient


def test_anthropic_provider_creates_anthropic_client():
    config = LLMConfig(provider="anthropic", api_key="sk-ant-fake")
    mock_anthropic = MagicMock()
    mock_client_instance = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client_instance

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        client = LLMClient(config)
        assert client._provider == "anthropic"
        mock_anthropic.Anthropic.assert_called_once()


def test_ollama_provider_creates_openai_client():
    config = LLMConfig(provider="ollama", base_url="http://localhost:11434/v1", api_key="ollama")
    mock_openai = MagicMock()
    mock_client_instance = MagicMock()
    mock_openai.OpenAI.return_value = mock_client_instance

    with patch.dict("sys.modules", {"openai": mock_openai}), \
         patch.object(LLMClient, "_check_ollama"):
        client = LLMClient(config)
        assert client._provider == "ollama"
        mock_openai.OpenAI.assert_called_once()


def test_complete_anthropic_path():
    config = LLMConfig(provider="anthropic", api_key="sk-ant-fake")
    mock_anthropic = MagicMock()
    mock_client_instance = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Generated text")]
    mock_client_instance.messages.create.return_value = mock_msg
    mock_anthropic.Anthropic.return_value = mock_client_instance

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        client = LLMClient(config)
        result = client.complete(
            model="test-model", system="You are helpful.", user_message="Hello",
        )
        assert result == "Generated text"
        call_kwargs = mock_client_instance.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful."


def test_complete_openai_path():
    config = LLMConfig(provider="ollama", base_url="http://localhost:11434/v1", api_key="ollama")
    mock_openai = MagicMock()
    mock_client_instance = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Generated text"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client_instance.chat.completions.create.return_value = mock_response
    mock_openai.OpenAI.return_value = mock_client_instance

    with patch.dict("sys.modules", {"openai": mock_openai}), \
         patch.object(LLMClient, "_check_ollama"):
        client = LLMClient(config)
        result = client.complete(
            model="qwen3:8b", system="You are helpful.", user_message="Hello",
        )
        assert result == "Generated text"
        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["messages"][0]["role"] == "system"
