"""Tests for GitHub scanner with mocked PyGithub."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ghost_writer_mcp.scanner.activity import ActivityItem
from ghost_writer_mcp.scanner.github_client import GitHubScanner


class TestGitHubScanner:
    def _make_mock_commit(self, message="fix: something", login="fabio"):
        commit = MagicMock()
        commit.commit.message = message
        commit.author = MagicMock()
        commit.author.login = login
        commit.commit.author.date = datetime(2026, 3, 10, tzinfo=timezone.utc)
        commit.html_url = "https://github.com/org/repo/commit/abc123"
        commit.stats.total = 3
        commit.stats.additions = 20
        commit.stats.deletions = 5

        f1 = MagicMock()
        f1.filename = "src/main.py"
        f2 = MagicMock()
        f2.filename = "tests/test_main.py"
        commit.files = [f1, f2]

        return commit

    def _make_mock_pr(self, title="feat: new feature", merged=True, login="fabio"):
        pr = MagicMock()
        pr.title = title
        pr.body = "Added a new feature with tests."
        pr.merged = merged
        pr.merged_at = datetime(2026, 3, 9, tzinfo=timezone.utc)
        pr.updated_at = datetime(2026, 3, 9, tzinfo=timezone.utc)
        pr.user.login = login
        pr.html_url = "https://github.com/org/repo/pull/42"
        pr.additions = 150
        pr.deletions = 30
        pr.changed_files = 5

        f1 = MagicMock()
        f1.filename = "src/feature.py"
        pr.get_files.return_value = [f1]

        return pr

    @patch("src.scanner.github_client.Github")
    def test_scan_all_returns_activities(self, mock_github_cls, test_config):
        mock_gh = MagicMock()
        mock_github_cls.return_value = mock_gh

        mock_repo = MagicMock()
        mock_gh.get_repo.return_value = mock_repo
        mock_repo.get_commits.return_value = [self._make_mock_commit()]
        mock_repo.get_pulls.return_value = [self._make_mock_pr()]

        scanner = GitHubScanner(test_config)
        scanner.gh = mock_gh

        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        activities = scanner.scan_all(since=since)

        assert len(activities) == 2
        assert all(isinstance(a, ActivityItem) for a in activities)

    @patch("src.scanner.github_client.Github")
    def test_commit_parsed_correctly(self, mock_github_cls, test_config):
        mock_gh = MagicMock()
        mock_github_cls.return_value = mock_gh

        mock_repo = MagicMock()
        mock_gh.get_repo.return_value = mock_repo
        mock_repo.get_commits.return_value = [
            self._make_mock_commit("feat: add caching\n\nAdded Redis caching layer")
        ]
        mock_repo.get_pulls.return_value = []

        scanner = GitHubScanner(test_config)
        scanner.gh = mock_gh

        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        activities = scanner.scan_all(since=since)

        assert len(activities) == 1
        assert activities[0].activity_type == "commit"
        assert activities[0].title == "feat: add caching"
        assert activities[0].additions == 20

    @patch("src.scanner.github_client.Github")
    def test_unmerged_prs_excluded(self, mock_github_cls, test_config):
        mock_gh = MagicMock()
        mock_github_cls.return_value = mock_gh

        mock_repo = MagicMock()
        mock_gh.get_repo.return_value = mock_repo
        mock_repo.get_commits.return_value = []
        mock_repo.get_pulls.return_value = [self._make_mock_pr(merged=False)]

        scanner = GitHubScanner(test_config)
        scanner.gh = mock_gh

        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        activities = scanner.scan_all(since=since)

        assert len(activities) == 0

    @patch("src.scanner.github_client.Github")
    def test_failed_repo_doesnt_crash(self, mock_github_cls, test_config):
        mock_gh = MagicMock()
        mock_github_cls.return_value = mock_gh
        mock_gh.get_repo.side_effect = Exception("404 Not Found")

        scanner = GitHubScanner(test_config)
        scanner.gh = mock_gh

        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        activities = scanner.scan_all(since=since)

        assert activities == []
