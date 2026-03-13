"""Minimal CLI for testing Ghost Writer without an MCP client.

Usage:
    uv run python -m src.cli scan [--days 14] [--repo my-project]
    uv run python -m src.cli generate <index> [--format war_story]
    uv run python -m src.cli list [--status pending]
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from ghost_writer_mcp.config import load_config
from ghost_writer_mcp.content.classifier import ContentClassifier
from ghost_writer_mcp.content.generator import DraftGenerator
from ghost_writer_mcp.scanner.aggregator import aggregate
from ghost_writer_mcp.scanner.local_git import LocalGitScanner
from ghost_writer_mcp.store.database import Database

config = load_config()
db = Database()
db.init_db()

# Module-level cache for scan results (persists between commands in same session)
_classified: list = []


def cmd_scan(args: argparse.Namespace) -> None:
    scanner = LocalGitScanner(config)
    since = datetime.now(tz=timezone.utc) - timedelta(days=args.days)

    repo_filter = None
    if args.repo:
        for repo_cfg in config.github.repos:
            if repo_cfg.name == args.repo or f"{repo_cfg.owner}/{repo_cfg.name}" == args.repo:
                repo_filter = repo_cfg.local_path
                break
        if repo_filter is None:
            names = [r.name for r in config.github.repos]
            print(f"Repo '{args.repo}' not found. Available: {', '.join(names)}")
            return

    activities = scanner.scan_all(since=since, repo_filter=repo_filter)
    if not activities:
        print(f"No activity found in the last {args.days} days.")
        return

    groups = aggregate(activities)
    classifier = ContentClassifier(config)
    classified = classifier.classify_groups(groups[:15])

    _classified.clear()
    _classified.extend(classified)

    for i, c in enumerate(classified[:10], start=1):
        print(
            f"{i}. [{c.pillar}] {c.activity.title}\n"
            f"   Score: {c.content_score}/10 | Format: {c.format_suggestion}\n"
            f"   Angle: {c.suggested_angle}\n"
        )

    print(f"{len(classified)} activities classified. Use 'generate <index>' to draft.")


def cmd_generate(args: argparse.Namespace) -> None:
    if not _classified:
        print("Run 'scan' first.")
        return

    idx = args.index
    if idx < 1 or idx > len(_classified):
        print(f"Invalid index. Choose between 1 and {len(_classified)}.")
        return

    item = _classified[idx - 1]
    generator = DraftGenerator(config)
    draft = generator.generate(item, format_override=args.format)

    draft_id = db.save_draft(
        title=draft.title,
        body=draft.body,
        pillar=draft.pillar,
        format=draft.format,
        source_activity_ids=[],
    )

    print(f"--- Draft #{draft_id} ({draft.pillar} / {draft.format}) ---\n")
    print(draft.body)
    print(f"\n--- Safety: {'CLEAN' if draft.safety_check.is_safe else 'FLAGGED'} ---")
    if draft.safety_check.gate1_matches:
        print(f"Gate 1: {draft.safety_check.gate1_matches}")
    if draft.safety_check.gate2_flags:
        print(f"Gate 2: {draft.safety_check.gate2_flags}")


def cmd_list(args: argparse.Namespace) -> None:
    drafts = db.list_drafts(status=args.status)
    if not drafts:
        print("No drafts found.")
        return
    for d in drafts:
        preview = (d["body"] or "")[:80].replace("\n", " ")
        print(f"#{d['id']} [{d['status']}] {d['title']}")
        print(f"   {preview}...\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ghost Writer — turn git activity into LinkedIn drafts"
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Scan repos and classify activity")
    p_scan.add_argument("--days", type=int, default=7)
    p_scan.add_argument("--repo", type=str, default=None)

    p_gen = sub.add_parser("generate", help="Generate a draft from scan results")
    p_gen.add_argument("index", type=int)
    p_gen.add_argument("--format", type=str, default=None)

    p_list = sub.add_parser("list", help="List saved drafts")
    p_list.add_argument("--status", type=str, default=None)

    args = parser.parse_args()
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
