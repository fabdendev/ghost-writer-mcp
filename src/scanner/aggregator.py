"""Aggregate raw activities into compact summaries for efficient LLM classification."""

from dataclasses import dataclass, field
from src.scanner.activity import ActivityItem


@dataclass
class ActivityGroup:
    """A group of related activities, summarised for classification."""
    repo_full_name: str
    title: str
    description: str
    activity_count: int
    total_additions: int
    total_deletions: int
    activity_types: set[str] = field(default_factory=set)
    # Keep a reference to the best representative activity for drafting
    representative: ActivityItem | None = None


def aggregate(activities: list[ActivityItem]) -> list[ActivityGroup]:
    """Group activities by repo and related topic, producing compact summaries.

    Strategy:
    1. Group commits by repo
    2. Within each repo, cluster commits that share similar title prefixes
       (e.g. all "feat: gas readings" commits become one group)
    3. Produce a single-line summary per group
    """
    if not activities:
        return []

    # Step 1: group by repo
    by_repo: dict[str, list[ActivityItem]] = {}
    for a in activities:
        by_repo.setdefault(a.repo_full_name, []).append(a)

    groups: list[ActivityGroup] = []

    for repo, items in by_repo.items():
        # Step 2: cluster by title prefix (first 3 words or conventional prefix)
        clusters: dict[str, list[ActivityItem]] = {}
        for item in items:
            key = _cluster_key(item.title)
            clusters.setdefault(key, []).append(item)

        # Step 3: summarise each cluster
        for _key, cluster in clusters.items():
            total_add = sum(a.additions for a in cluster)
            total_del = sum(a.deletions for a in cluster)
            types = {a.activity_type for a in cluster}

            if len(cluster) == 1:
                a = cluster[0]
                title = a.title
                desc = a.description[:300]
            else:
                # Pick the most descriptive title (longest)
                best = max(cluster, key=lambda a: a.additions + a.deletions)
                titles = list(dict.fromkeys(a.title for a in cluster))  # unique, ordered
                title = f"{titles[0]} (+{len(cluster)-1} related commits)"
                desc = " | ".join(titles[:5])

            groups.append(ActivityGroup(
                repo_full_name=repo,
                title=title,
                description=desc,
                activity_count=len(cluster),
                total_additions=total_add,
                total_deletions=total_del,
                activity_types=types,
                representative=best if len(cluster) > 1 else cluster[0],
            ))

    # Sort by total changes descending (bigger changes = more interesting)
    groups.sort(key=lambda g: g.total_additions + g.total_deletions, reverse=True)
    return groups


def _cluster_key(title: str) -> str:
    """Extract a clustering key from a commit title.

    Groups by conventional commit prefix (feat, fix, refactor, etc.)
    combined with the first meaningful word after it.
    """
    title = title.strip().lower()

    # Handle conventional commits: "feat(scope): description" or "feat: description"
    prefixes = ("feat", "fix", "refactor", "chore", "docs", "test", "ci", "build", "perf")
    for prefix in prefixes:
        if title.startswith(prefix):
            # Extract scope or first word after prefix
            rest = title[len(prefix):].lstrip("(").split(")", 1)[-1].lstrip(":").strip()
            first_word = rest.split()[0] if rest.split() else ""
            return f"{prefix}:{first_word}"

    # Handle merge commits
    if title.startswith("merge"):
        return "merge"

    # Default: first 3 words
    words = title.split()[:3]
    return " ".join(words)
