"""Tests for content classifier with mocked LLM client."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.content.classifier import ClassifiedActivity, ContentClassifier
from src.scanner.activity import ActivityItem


def _make_activity(title="feat: add agent loop", repo="org/ai-repo"):
    return ActivityItem(
        repo_full_name=repo,
        activity_type="commit",
        title=title,
        description="Implemented the main agent loop with retry logic.",
        diff_summary="+100 -20",
        author="fabio",
        created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        url="https://github.com/org/repo/commit/abc",
        files_changed=["src/agent.py", "tests/test_agent.py"],
        additions=100,
        deletions=20,
    )


class TestContentClassifier:
    @patch("src.content.classifier.LLMClient")
    def test_classify_batch_returns_sorted(self, mock_llm_cls, test_config):
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        response_data = [
            {
                "index": 1,
                "pillar": "ai_engineering",
                "content_score": 8.5,
                "suggested_angle": "How to build reliable agent loops",
                "format_suggestion": "tactical_howto",
            },
            {
                "index": 2,
                "pillar": "data_architecture",
                "content_score": 4.0,
                "suggested_angle": "ETL pipeline patterns",
                "format_suggestion": "til",
            },
        ]
        mock_llm.complete.return_value = json.dumps(response_data)

        classifier = ContentClassifier(test_config)
        classifier.llm = mock_llm

        activities = [
            _make_activity("feat: agent loop"),
            _make_activity("fix: etl pipeline", "org/data-repo"),
        ]

        results = classifier.classify_batch(activities)

        assert len(results) == 2
        assert all(isinstance(r, ClassifiedActivity) for r in results)
        assert results[0].content_score >= results[1].content_score
        assert results[0].pillar == "ai_engineering"

    @patch("src.content.classifier.LLMClient")
    def test_handles_json_in_fenced_block(self, mock_llm_cls, test_config):
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        response_data = [
            {
                "index": 1,
                "pillar": "ai_engineering",
                "content_score": 7.0,
                "suggested_angle": "Test angle",
                "format_suggestion": "hot_take",
            }
        ]

        mock_llm.complete.return_value = f"```json\n{json.dumps(response_data)}\n```"

        classifier = ContentClassifier(test_config)
        classifier.llm = mock_llm

        results = classifier.classify_batch([_make_activity()])
        assert len(results) == 1

    @patch("src.content.classifier.LLMClient")
    def test_handles_invalid_json(self, mock_llm_cls, test_config):
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        mock_llm.complete.return_value = "not valid json at all"

        classifier = ContentClassifier(test_config)
        classifier.llm = mock_llm

        results = classifier.classify_batch([_make_activity()])
        assert results == []

    def test_empty_activities(self, test_config):
        classifier = ContentClassifier(test_config)
        assert classifier.classify_batch([]) == []
