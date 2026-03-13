"""Shared fixtures for Ghost Writer MCP tests."""

import pytest

from ghost_writer_mcp.config import (
    GhostWriterConfig,
    GitHubConfig,
    LLMConfig,
    RepoConfig,
    SanitisationConfig,
    ContentConfig,
    ContentPillar,
    StyleConfig,
)
from ghost_writer_mcp.store.database import Database


@pytest.fixture
def test_config():
    """A GhostWriterConfig with dummy values for testing."""
    return GhostWriterConfig(
        github=GitHubConfig(
            token="ghp_fake_test_token_1234567890",
            repos=[
                RepoConfig(
                    owner="test-org",
                    name="test-repo",
                    role="Lead architect",
                    content_weight=1.0,
                ),
            ],
        ),
        llm=LLMConfig(
            provider="anthropic",
            classifier_model="test-classifier-model",
            generator_model="test-generator-model",
            api_key="sk-ant-fake-test-key",
        ),
        sanitisation=SanitisationConfig(
            blocklist={
                "company_names": ["Acme Corp", "AcmeCo"],
                "client_names": ["Big Bank", "ClientX"],
                "product_names": ["Project Phoenix"],
                "infrastructure": ["prod-db-01.internal", "10.0."],
                "people": ["John Doe"],
            },
            abstractions={
                "Acme Corp": "a mid-size fintech",
                "Project Phoenix": "an internal data platform",
                "Big Bank": "a major financial institution",
            },
        ),
        content=ContentConfig(
            pillars=[
                ContentPillar(
                    name="ai_engineering",
                    description="Building AI agents, LLM integration",
                    repo_signals=["agent", "llm", "anthropic"],
                    weight=1.0,
                ),
                ContentPillar(
                    name="data_architecture",
                    description="Data pipelines, ETL, database design",
                    repo_signals=["pipeline", "etl", "database"],
                    weight=0.8,
                ),
            ],
            style=StyleConfig(
                tone="pragmatic, technically credible",
                language="en",
                max_length=1500,
                use_emoji=False,
                use_hashtags=True,
                hashtag_count=3,
                few_shot_posts=["Example post about engineering."],
            ),
        ),
    )


@pytest.fixture
def test_db(tmp_path):
    """A Database backed by a temporary SQLite file."""
    db = Database(db_path=str(tmp_path / "test.db"))
    db.init_db()
    return db
