"""Local git scanner — reads commit history directly from local repos."""

import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ghost_writer_mcp.config import GhostWriterConfig, RepoConfig
from ghost_writer_mcp.scanner.activity import ActivityItem

logger = logging.getLogger(__name__)

_STAT_RE = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?"
)


class LocalGitScanner:
    """Scans local git repos using `git log`. No API calls, instant results."""

    def __init__(self, config: GhostWriterConfig) -> None:
        self.config = config

    def scan_all(
        self,
        since: datetime | None = None,
        repo_filter: str | None = None,
    ) -> list[ActivityItem]:
        """Scan local repos for activity.

        Parameters
        ----------
        since:
            Only include commits after this date.  Defaults to 7 days ago.
        repo_filter:
            If set, only scan the repo whose local_path matches this value
            (resolved to an absolute path).  Useful when the caller is
            inside one of the configured repos.
        """
        if since is None:
            since = datetime.now(tz=timezone.utc) - timedelta(days=7)

        activities: list[ActivityItem] = []
        for repo_cfg in self.config.github.repos:
            local_path = self._resolve_path(repo_cfg)
            if local_path is None:
                continue
            if not (local_path / ".git").exists():
                continue
            if repo_filter and local_path.resolve() != Path(repo_filter).resolve():
                continue

            logger.info("Scanning %s...", local_path.name)
            activities.extend(self._scan_repo(repo_cfg, local_path, since))

        activities.sort(key=lambda a: a.created_at, reverse=True)
        logger.info("Scan complete: %d activities found.", len(activities))
        return activities

    def _resolve_path(self, repo_cfg: RepoConfig) -> Path | None:
        if repo_cfg.local_path:
            p = Path(repo_cfg.local_path).expanduser()
            if p.exists():
                return p
        return None

    def _scan_repo(
        self, repo_cfg: RepoConfig, local_path: Path, since: datetime
    ) -> list[ActivityItem]:
        since_str = since.strftime("%Y-%m-%d")
        # Format: HASH<NUL>AUTHOR<NUL>DATE<NUL>SUBJECT<NUL>COMMIT_END
        # --shortstat adds a stats line after each commit block
        fmt = "%H%x00%an%x00%aI%x00%s%x00COMMIT_END"
        try:
            result = subprocess.run(
                ["git", "log", f"--since={since_str}", f"--format={fmt}", "--shortstat"],
                cwd=local_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return []

        if result.returncode != 0:
            return []

        return self._parse_git_log(result.stdout, repo_cfg)

    def _parse_git_log(
        self, raw_output: str, repo_cfg: RepoConfig
    ) -> list[ActivityItem]:
        items: list[ActivityItem] = []
        full_name = f"{repo_cfg.owner}/{repo_cfg.name}"

        # Split on COMMIT_END — each block is: "<fields>\nCOMMIT_END\n <shortstat>\n"
        blocks = raw_output.split("COMMIT_END")

        for i, block in enumerate(blocks[:-1]):  # last block is trailing empty
            # The commit fields are in this block
            fields_part = block.strip()
            if not fields_part:
                continue

            parts = fields_part.split("\x00")
            if len(parts) < 4:
                continue

            commit_hash = parts[0].strip()
            # Handle case where stats from PREVIOUS commit are prepended
            hash_match = re.search(r"([0-9a-f]{40})$", commit_hash)
            if not hash_match:
                continue
            commit_hash = hash_match.group(1)

            author = parts[1].strip()
            date_str = parts[2].strip()
            subject = parts[3].strip()

            # Stats are at the START of the NEXT block (before the next commit's fields)
            additions, deletions, files_changed = 0, 0, 0
            if i + 1 < len(blocks):
                next_block = blocks[i + 1]
                stat_match = _STAT_RE.search(next_block)
                if stat_match:
                    files_changed = int(stat_match.group(1))
                    additions = int(stat_match.group(2) or 0)
                    deletions = int(stat_match.group(3) or 0)

            try:
                created_at = datetime.fromisoformat(date_str)
            except ValueError:
                continue

            diff_summary = f"{files_changed} file(s), +{additions} -{deletions}"

            items.append(
                ActivityItem(
                    repo_full_name=full_name,
                    activity_type="commit",
                    title=subject,
                    description=subject,
                    diff_summary=diff_summary,
                    author=author,
                    created_at=created_at,
                    url=f"{self.config.github.host.rstrip('/')}/{full_name}/commit/{commit_hash}",
                    files_changed=[],
                    additions=additions,
                    deletions=deletions,
                )
            )

        return items
