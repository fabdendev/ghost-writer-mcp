"""Tests for draft generator with mocked LLM client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ghost_writer_mcp.content.classifier import ClassifiedActivity
from ghost_writer_mcp.content.generator import DraftGenerator, GeneratedDraft
from ghost_writer_mcp.scanner.activity import ActivityItem


def _make_classified_activity():
    activity = ActivityItem(
        repo_full_name="org/ai-repo",
        activity_type="commit",
        title="feat: add retry logic to agent loop",
        description="Added exponential backoff and max retry limits.",
        diff_summary="+80 -10 in 3 files",
        author="fabio",
        created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        url="https://github.com/org/repo/commit/abc",
        files_changed=["src/agent.py"],
        additions=80,
        deletions=10,
    )
    return ClassifiedActivity(
        activity=activity,
        pillar="ai_engineering",
        content_score=8.5,
        suggested_angle="Why retry logic matters more than prompt engineering",
        format_suggestion="tactical_howto",
    )


class TestDraftGenerator:
    @patch("src.content.abstractor.LLMClient")
    @patch("src.content.generator.LLMClient")
    def test_generate_returns_draft(
        self, mock_gen_llm_cls, mock_abs_llm_cls, test_config
    ):
        mock_gen_llm = MagicMock()
        mock_gen_llm_cls.return_value = mock_gen_llm

        generated_post = (
            "Your AI agent doesn't need a better prompt.\n\n"
            "It needs retry logic.\n\n"
            "We added exponential backoff to our agent loop "
            "and task completion went from 70% to 94%.\n\n"
            "Here's what we learned:\n\n"
            "1. Set a max retry limit (we use 3)\n"
            "2. Back off exponentially\n"
            "3. Log every retry for debugging\n\n"
            "The boring infrastructure wins again.\n\n"
            "#AI #Engineering #Agents"
        )
        mock_gen_llm.complete.return_value = generated_post

        # Mock the abstractor's LLM client (for LLM review — returns no flags)
        mock_abs_llm = MagicMock()
        mock_abs_llm_cls.return_value = mock_abs_llm
        mock_abs_llm.complete.return_value = "[]"

        gen = DraftGenerator(test_config)
        gen.llm = mock_gen_llm
        gen.abstractor.llm = mock_abs_llm

        activity = _make_classified_activity()
        draft = gen.generate(activity)

        assert isinstance(draft, GeneratedDraft)
        assert draft.pillar == "ai_engineering"
        assert draft.format == "tactical_howto"
        assert len(draft.body) > 0
        assert draft.title  # first line extracted

    @patch("src.content.abstractor.LLMClient")
    @patch("src.content.generator.LLMClient")
    def test_format_override(
        self, mock_gen_llm_cls, mock_abs_llm_cls, test_config
    ):
        mock_gen_llm = MagicMock()
        mock_gen_llm_cls.return_value = mock_gen_llm
        mock_gen_llm.complete.return_value = "Hot take: agents are overrated."

        mock_abs_llm = MagicMock()
        mock_abs_llm_cls.return_value = mock_abs_llm
        mock_abs_llm.complete.return_value = "[]"

        gen = DraftGenerator(test_config)
        gen.llm = mock_gen_llm
        gen.abstractor.llm = mock_abs_llm

        activity = _make_classified_activity()
        draft = gen.generate(activity, format_override="hot_take")

        assert draft.format == "hot_take"
