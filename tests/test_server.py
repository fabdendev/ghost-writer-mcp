"""Tests for server logic (repo filtering, error messages, hybrid scanning)."""

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from ghost_writer_mcp.config import GhostWriterConfig, GitHubConfig, RepoConfig, LLMConfig
from ghost_writer_mcp.scanner.activity import ActivityItem


def _make_config(provider="anthropic", repos=None):
    if repos is None:
        repos = [
            RepoConfig(
                owner="org", name="repo-local", role="dev",
                local_path="/tmp/repo-local",
            ),
            RepoConfig(
                owner="org", name="repo-api", role="dev",
            ),
        ]
    return GhostWriterConfig(
        github=GitHubConfig(token="fake-token", repos=repos),
        llm=LLMConfig(provider=provider, api_key="fake"),
    )


def _make_activity(repo="org/repo-local"):
    return ActivityItem(
        repo_full_name=repo,
        activity_type="commit",
        title="feat: test",
        description="test commit",
        diff_summary="1 file(s), +10 -5",
        author="dev",
        created_at=datetime.now(tz=timezone.utc),
        url="https://github.com/org/repo/commit/abc",
        files_changed=[],
        additions=10,
        deletions=5,
    )


def test_llm_error_message_ollama():
    """Error message should mention ollama serve when provider is ollama."""
    from ghost_writer_mcp.server import _llm_error_message

    with patch("src.server.config", _make_config(provider="ollama")):
        msg = _llm_error_message()
        assert "ollama serve" in msg.lower()
        assert "ollama pull" in msg.lower()


def test_llm_error_message_anthropic():
    """Error message should mention API key when provider is anthropic."""
    from ghost_writer_mcp.server import _llm_error_message

    with patch("src.server.config", _make_config(provider="anthropic")):
        msg = _llm_error_message()
        assert "api key" in msg.lower()


def test_scan_repos_local_only():
    """When all repos have local_path, only local scanner is used."""
    from ghost_writer_mcp.server import _scan_repos

    config = _make_config(repos=[
        RepoConfig(owner="org", name="repo", role="dev", local_path="/tmp/repo"),
    ])
    local_result = [_make_activity()]

    with patch("src.server.config", config), \
         patch("src.server._local_scanner") as mock_local:
        mock_local.scan_all.return_value = local_result
        result = _scan_repos(since=datetime.now(tz=timezone.utc))
        assert len(result) == 1
        mock_local.scan_all.assert_called_once()


def test_scan_repos_falls_back_to_github_api():
    """Repos without local_path should trigger GitHub API fallback."""
    from ghost_writer_mcp.server import _scan_repos

    config = _make_config()  # has one repo with local_path, one without
    local_result = [_make_activity("org/repo-local")]
    api_result = [_make_activity("org/repo-api")]

    with patch("src.server.config", config), \
         patch("src.server._local_scanner") as mock_local, \
         patch("src.server._get_github_scanner") as mock_get_gh:
        mock_local.scan_all.return_value = local_result
        mock_gh = MagicMock()
        mock_gh.scan_all.return_value = api_result
        mock_get_gh.return_value = mock_gh

        result = _scan_repos(since=datetime.now(tz=timezone.utc))
        assert len(result) == 2
        mock_get_gh.assert_called_once()
