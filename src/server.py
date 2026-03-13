"""Ghost Writer MCP Server — turns GitHub activity into LinkedIn posts."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastmcp import FastMCP

from src.config import load_config
from src.content.classifier import ContentClassifier
from src.content.generator import DraftGenerator
from src.llm_client import LLMClient
from src.scanner.activity import ActivityItem
from src.scanner.aggregator import aggregate
from src.scanner.github_client import GitHubScanner
from src.scanner.local_git import LocalGitScanner
from src.store.database import Database

logger = logging.getLogger(__name__)

mcp = FastMCP("Ghost Writer")

config = load_config()
db = Database()
db.init_db()
_local_scanner = LocalGitScanner(config)
_github_scanner: GitHubScanner | None = None


def _get_github_scanner() -> GitHubScanner:
    """Lazily initialise the GitHub API scanner (requires a token)."""
    global _github_scanner
    if _github_scanner is None:
        if not config.github.token:
            raise ValueError(
                "GitHub token required for repos without local_path. "
                "Set github.token in config.yaml or the GITHUB_PAT env var."
            )
        _github_scanner = GitHubScanner(config)
    return _github_scanner


def _scan_repos(
    since: datetime, repo_filter: str | None = None
) -> list[ActivityItem]:
    """Scan repos using local git where possible, falling back to GitHub API."""
    local_activities = _local_scanner.scan_all(since=since, repo_filter=repo_filter)

    # Check if any configured repos lack local_path — those need GitHub API
    scanned_local = {a.repo_full_name for a in local_activities}
    need_api = []
    for repo_cfg in config.github.repos:
        full_name = f"{repo_cfg.owner}/{repo_cfg.name}"
        if repo_filter and repo_cfg.local_path != repo_filter and repo_cfg.name != repo_filter:
            continue
        if full_name not in scanned_local:
            need_api.append(full_name)

    if need_api:
        try:
            gh_scanner = _get_github_scanner()
            for repo_name in need_api:
                api_activities = gh_scanner.scan_all(
                    since=since, repo_filter=repo_name
                )
                local_activities.extend(api_activities)
        except ValueError as exc:
            logger.warning("GitHub API fallback failed: %s", exc)

    local_activities.sort(key=lambda a: a.created_at, reverse=True)
    return local_activities

# LLM-dependent components are lazily initialised so the MCP server
# can start even when Ollama is not yet running.
_classifier: ContentClassifier | None = None
_generator: DraftGenerator | None = None
_edit_llm: LLMClient | None = None


def _ensure_llm() -> tuple[ContentClassifier, DraftGenerator, LLMClient]:
    """Initialise LLM components on first use."""
    global _classifier, _generator, _edit_llm
    if _classifier is None:
        _classifier = ContentClassifier(config)
        _generator = DraftGenerator(config)
        _edit_llm = LLMClient(config.llm)
    return _classifier, _generator, _edit_llm


# Keep classified activities in memory between scan and generate calls
_last_scan_results: list = []

def _llm_error_message() -> str:
    """Return a user-friendly error message based on the configured provider."""
    if config.llm.provider == "ollama":
        model = config.llm.classifier_model
        return (
            f"Ollama is not running. Start it with `ollama serve` "
            f"and make sure the model is pulled (`ollama pull {model}`)."
        )
    return (
        f"Failed to connect to {config.llm.provider}. "
        f"Check your API key and network connection."
    )


def _detect_repo_filter() -> str | None:
    """If cwd is inside one of the configured repos, return its local_path."""
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None
    for repo_cfg in config.github.repos:
        if repo_cfg.local_path:
            repo_path = Path(repo_cfg.local_path).expanduser().resolve()
            if cwd == repo_path or repo_path in cwd.parents:
                return str(repo_path)
    return None


@mcp.tool()
def scan_activity(days: int = 7, repo: str | None = None) -> str:
    """Scan configured GitHub repos for recent activity and rank by content potential.

    Args:
        days: Number of days to look back (default: 7)
        repo: Optional repo name to scan (e.g. "my-project"). If omitted, all configured repos are scanned.

    Returns:
        A formatted list of top content candidates with index numbers for drafting.
    """
    global _last_scan_results

    # Match repo name to its local_path
    repo_filter = None
    if repo:
        for repo_cfg in config.github.repos:
            if repo_cfg.name == repo or f"{repo_cfg.owner}/{repo_cfg.name}" == repo:
                repo_filter = repo_cfg.local_path
                break
        if repo_filter is None:
            names = [r.name for r in config.github.repos]
            return f"Repo '{repo}' not found in config. Available: {', '.join(names)}"

    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    activities = _scan_repos(since=since, repo_filter=repo_filter)

    if not activities:
        scope = f"repo '{repo}'" if repo else "configured repos"
        return f"No activity found in the last {days} days across {scope}."

    try:
        classifier, _, _ = _ensure_llm()
    except ConnectionError:
        return _llm_error_message()

    # Aggregate raw commits into compact groups before sending to LLM
    groups = aggregate(activities)
    classified = classifier.classify_groups(groups[:15])
    _last_scan_results = classified

    # Save to database
    activity_dicts = [
        {
            "repo_full_name": c.activity.repo_full_name,
            "activity_type": c.activity.activity_type,
            "title": c.activity.title,
            "description": c.activity.description[:500],
            "diff_summary": c.activity.diff_summary,
            "pillar": c.pillar,
            "content_score": c.content_score,
        }
        for c in classified
    ]
    db.save_activities(activity_dicts)

    # Format top 10 for display
    top = classified[:10]
    lines = [f"## Content Candidates (last {days} days)\n"]
    for i, c in enumerate(top, start=1):
        lines.append(
            f"**{i}.** [{c.pillar}] {c.activity.title}\n"
            f"   Repo: {c.activity.repo_full_name} | "
            f"Type: {c.activity.activity_type} | "
            f"Score: {c.content_score}/10\n"
            f"   Angle: {c.suggested_angle}\n"
            f"   Format: {c.format_suggestion}\n"
        )

    lines.append(
        f"\n*{len(classified)} activities scanned, showing top {len(top)}.*\n"
        f"Use `generate_draft` with an activity index (1-{len(top)}) to create a post."
    )
    return "\n".join(lines)


@mcp.tool()
def generate_draft(
    activity_index: int,
    format: str | None = None,
    tone: str | None = None,
) -> str:
    """Generate a LinkedIn post draft from a scanned activity.

    Args:
        activity_index: Index of the activity from scan results (1-based)
        format: Override format (tactical_howto, hot_take, war_story, til, deep_dive)
        tone: Override tone for this specific post

    Returns:
        The generated draft with safety check results.
    """
    if not _last_scan_results:
        return "No scan results available. Run `scan_activity` first."

    if activity_index < 1 or activity_index > len(_last_scan_results):
        return f"Invalid index. Choose between 1 and {len(_last_scan_results)}."

    try:
        _, generator, _ = _ensure_llm()
    except ConnectionError:
        return _llm_error_message()

    activity = _last_scan_results[activity_index - 1]
    draft = generator.generate(activity, format_override=format, tone_override=tone)

    # Save to database
    draft_id = db.save_draft(
        title=draft.title,
        body=draft.body,
        pillar=draft.pillar,
        format=draft.format,
        source_activity_ids=[],
    )

    # Build safety summary
    safety_lines = []
    if draft.safety_check.gate1_matches:
        safety_lines.append(
            f"Gate 1: {len(draft.safety_check.gate1_matches)} blocklist "
            f"term(s) replaced"
        )
    if draft.safety_check.gate2_flags:
        safety_lines.append(
            f"Gate 2: {len(draft.safety_check.gate2_flags)} LLM flag(s): "
            + ", ".join(f["term"] for f in draft.safety_check.gate2_flags if isinstance(f, dict))
        )
    safety_summary = "\n".join(safety_lines) if safety_lines else "All clear"

    return (
        f"## Draft #{draft_id} — {draft.pillar} ({draft.format})\n\n"
        f"{draft.body}\n\n"
        f"---\n"
        f"**Safety check:** {safety_summary}\n"
        f"**Status:** pending — review and use `edit_draft` to refine, "
        f"or approve manually."
    )


@mcp.tool()
def list_drafts(status: str | None = None) -> str:
    """List saved drafts, optionally filtered by status.

    Args:
        status: Filter by status (pending, approved, published, rejected). Omit for all.

    Returns:
        A formatted list of drafts.
    """
    drafts = db.list_drafts(status=status)

    if not drafts:
        label = f" with status '{status}'" if status else ""
        return f"No drafts found{label}."

    lines = [f"## Drafts ({len(drafts)} total)\n"]
    for d in drafts:
        preview = (d["body"] or "")[:100].replace("\n", " ")
        lines.append(
            f"**#{d['id']}** [{d['status']}] {d['title']}\n"
            f"   Pillar: {d['pillar']} | Format: {d['format']} | "
            f"Created: {d['created_at']}\n"
            f"   Preview: {preview}...\n"
        )
    return "\n".join(lines)


@mcp.tool()
def edit_draft(draft_id: int, instruction: str) -> str:
    """Edit an existing draft using natural language instructions.

    Args:
        draft_id: The ID of the draft to edit.
        instruction: What to change (e.g., "make it more provocative", "shorten to 500 chars").

    Returns:
        The updated draft.
    """
    draft = db.get_draft(draft_id)
    if not draft:
        return f"Draft #{draft_id} not found."

    try:
        _, generator, edit_llm = _ensure_llm()
    except ConnectionError:
        return _llm_error_message()

    new_body = edit_llm.complete(
        model=config.llm.generator_model,
        system=(
            "You are editing a LinkedIn post draft. Apply the user's instruction "
            "and return ONLY the updated post text. Keep the same general structure "
            "and tone unless told otherwise. Never include company names, client "
            "names, or confidential details."
        ),
        user_message=(
            f"## Current draft\n\n{draft['body']}\n\n"
            f"## Instruction\n\n{instruction}"
        ),
        max_tokens=2048,
    ).strip()

    # Re-sanitise the edited draft
    abstractor = generator.abstractor
    safety = abstractor.sanitise(new_body)
    new_body = safety.clean_text

    # Extract new title
    title = new_body.split("\n", 1)[0].strip()

    db.update_draft(draft_id, title=title, body=new_body)

    safety_lines = []
    if safety.gate1_matches:
        safety_lines.append(f"Gate 1: {len(safety.gate1_matches)} term(s) replaced")
    if safety.gate2_flags:
        safety_lines.append(f"Gate 2: {len(safety.gate2_flags)} LLM flag(s)")
    safety_summary = "\n".join(safety_lines) if safety_lines else "All clear"

    return (
        f"## Draft #{draft_id} (updated)\n\n"
        f"{new_body}\n\n"
        f"---\n"
        f"**Safety check:** {safety_summary}"
    )


def main() -> None:
    """Entry point for running the MCP server directly."""
    mcp.run()
