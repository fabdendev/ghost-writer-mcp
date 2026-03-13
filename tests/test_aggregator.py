"""Tests for commit aggregation and clustering."""

from datetime import datetime, timezone

from ghost_writer_mcp.scanner.activity import ActivityItem
from ghost_writer_mcp.scanner.aggregator import aggregate, _cluster_key


def _make_activity(title, repo="org/repo", additions=10, deletions=5):
    return ActivityItem(
        repo_full_name=repo,
        activity_type="commit",
        title=title,
        description=title,
        diff_summary=f"1 file(s), +{additions} -{deletions}",
        author="dev",
        created_at=datetime.now(tz=timezone.utc),
        url="https://github.com/org/repo/commit/abc",
        files_changed=[],
        additions=additions,
        deletions=deletions,
    )


def test_empty_input():
    assert aggregate([]) == []


def test_single_activity_returns_one_group():
    activities = [_make_activity("feat: add login")]
    groups = aggregate(activities)
    assert len(groups) == 1
    assert groups[0].activity_count == 1
    assert groups[0].representative is not None


def test_related_commits_grouped():
    activities = [
        _make_activity("feat: add login page"),
        _make_activity("feat: add login validation"),
        _make_activity("feat: add login tests"),
    ]
    groups = aggregate(activities)
    # All share prefix "feat:add" so should cluster together
    assert len(groups) == 1
    assert groups[0].activity_count == 3


def test_different_prefixes_separate():
    activities = [
        _make_activity("feat: add login"),
        _make_activity("fix: broken auth"),
    ]
    groups = aggregate(activities)
    assert len(groups) == 2


def test_different_repos_separate():
    activities = [
        _make_activity("feat: add login", repo="org/frontend"),
        _make_activity("feat: add login", repo="org/backend"),
    ]
    groups = aggregate(activities)
    assert len(groups) == 2


def test_sorted_by_total_changes():
    activities = [
        _make_activity("feat: small change", additions=5, deletions=2),
        _make_activity("feat: big change", additions=500, deletions=100),
    ]
    groups = aggregate(activities)
    assert groups[0].total_additions > groups[1].total_additions


def test_non_conventional_commits_cluster_by_first_words():
    activities = [
        _make_activity("Update billing logic for edge cases"),
        _make_activity("Update billing logic for holidays"),
    ]
    groups = aggregate(activities)
    # Both share first 3 words "update billing logic" so should cluster
    assert len(groups) == 1


def test_cluster_key_conventional_commit():
    assert _cluster_key("feat: add user auth") == "feat:add"
    assert _cluster_key("fix(api): broken endpoint") == "fix:broken"
    assert _cluster_key("refactor: clean up imports") == "refactor:clean"


def test_cluster_key_merge_commit():
    assert _cluster_key("Merge pull request #42") == "merge"
    assert _cluster_key("Merge branch 'main'") == "merge"


def test_cluster_key_plain_commit():
    assert _cluster_key("Update S3 bucket encryption") == "update s3 bucket"


def test_group_summary_includes_related_count():
    activities = [
        _make_activity("feat: add page A", additions=100),
        _make_activity("feat: add page B", additions=50),
    ]
    groups = aggregate(activities)
    assert "+1 related commits" in groups[0].title
