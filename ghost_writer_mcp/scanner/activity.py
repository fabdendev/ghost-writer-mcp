"""Data model for a single piece of GitHub activity."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ActivityItem:
    repo_full_name: str
    activity_type: str  # "commit" or "pull_request"
    title: str
    description: str
    diff_summary: str
    author: str
    created_at: datetime
    url: str
    files_changed: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
