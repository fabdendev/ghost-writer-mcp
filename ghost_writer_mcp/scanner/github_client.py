"""GitHub scanner that fetches commit and pull-request activity."""

import logging
from datetime import datetime, timedelta, timezone

from github import Auth, Github

from ghost_writer_mcp.config import GhostWriterConfig
from ghost_writer_mcp.scanner.activity import ActivityItem

logger = logging.getLogger(__name__)

# Max items to fetch per repo to keep API calls reasonable
_MAX_COMMITS_PER_REPO = 30
_MAX_PRS_PER_REPO = 20


class GitHubScanner:
    """Scans configured GitHub repositories for recent activity."""

    def __init__(self, config: GhostWriterConfig) -> None:
        self.config = config
        self.gh = Github(auth=Auth.Token(config.github.token))

    def scan_all(
        self,
        since: datetime | None = None,
        repo_filter: str | None = None,
    ) -> list[ActivityItem]:
        """Scan all configured repos and return activities sorted by date descending.

        Parameters
        ----------
        since:
            Only include activity after this date.  Defaults to 7 days ago.
        repo_filter:
            If set, only scan repos matching this ``owner/name`` string.
        """
        if since is None:
            since = datetime.now(tz=timezone.utc) - timedelta(days=7)

        activities: list[ActivityItem] = []
        for repo_cfg in self.config.github.repos:
            full_name = f"{repo_cfg.owner}/{repo_cfg.name}"
            if repo_filter and full_name != repo_filter:
                continue
            logger.info("Scanning %s (GitHub API)...", full_name)
            activities.extend(self._scan_repo(repo_cfg, since))

        activities.sort(key=lambda a: a.created_at, reverse=True)
        logger.info("Scan complete: %d activities found.", len(activities))
        return activities

    def _scan_repo(self, repo_cfg, since: datetime) -> list[ActivityItem]:
        """Fetch commits and merged PRs for a single repository."""
        try:
            repo = self.gh.get_repo(f"{repo_cfg.owner}/{repo_cfg.name}")
            items: list[ActivityItem] = []
            items.extend(self._fetch_commits(repo, repo_cfg, since))
            items.extend(self._fetch_pull_requests(repo, repo_cfg, since))
            return items
        except Exception as exc:
            logger.warning("Failed to scan %s/%s: %s", repo_cfg.owner, repo_cfg.name, exc)
            return []

    def _fetch_commits(self, repo, repo_cfg, since: datetime) -> list[ActivityItem]:
        """Return an ActivityItem for recent commits since *since*."""
        items: list[ActivityItem] = []
        count = 0
        for commit in repo.get_commits(since=since):
            if count >= _MAX_COMMITS_PER_REPO:
                break
            count += 1

            first_line = (commit.commit.message or "").split("\n", 1)[0]
            author = commit.author.login if commit.author else "unknown"

            # Use commit message stats only — skip per-file detail to save API calls
            stats = commit.stats
            diff_summary = (
                f"{stats.total} file(s), "
                f"+{stats.additions} -{stats.deletions}"
            )

            items.append(
                ActivityItem(
                    repo_full_name=f"{repo_cfg.owner}/{repo_cfg.name}",
                    activity_type="commit",
                    title=first_line,
                    description=commit.commit.message or "",
                    diff_summary=diff_summary,
                    author=author,
                    created_at=commit.commit.author.date,
                    url=commit.html_url,
                    files_changed=[],  # skip to save API calls
                    additions=stats.additions,
                    deletions=stats.deletions,
                )
            )
        return items

    def _fetch_pull_requests(
        self, repo, repo_cfg, since: datetime
    ) -> list[ActivityItem]:
        """Return an ActivityItem for every merged PR updated since *since*."""
        items: list[ActivityItem] = []
        count = 0
        for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
            # PRs are sorted by updated desc — stop early once we're past our window
            if pr.updated_at and pr.updated_at < since:
                break
            if count >= _MAX_PRS_PER_REPO:
                break
            count += 1

            if not pr.merged or not pr.merged_at or pr.merged_at < since:
                continue

            diff_summary = (
                f"+{pr.additions} -{pr.deletions} in {pr.changed_files} files"
            )

            items.append(
                ActivityItem(
                    repo_full_name=f"{repo_cfg.owner}/{repo_cfg.name}",
                    activity_type="pull_request",
                    title=pr.title,
                    description=pr.body or "",
                    diff_summary=diff_summary,
                    author=pr.user.login,
                    created_at=pr.merged_at,
                    url=pr.html_url,
                    files_changed=[],  # skip to save API calls
                    additions=pr.additions,
                    deletions=pr.deletions,
                )
            )
        return items

