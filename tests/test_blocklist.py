"""Tests for blocklist scanning and sanitisation — CRITICAL priority."""

from src.store.blocklist import Blocklist


class TestBlocklistScan:
    def test_detects_company_names(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("We deployed Acme Corp's new pipeline.")
        assert len(matches) == 1
        assert matches[0].term == "Acme Corp"
        assert matches[0].category == "company_names"

    def test_detects_client_names(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("Integration with Big Bank is live.")
        assert len(matches) == 1
        assert matches[0].term == "Big Bank"
        assert matches[0].category == "client_names"

    def test_detects_product_names(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("Project Phoenix now supports streaming.")
        assert len(matches) == 1
        assert matches[0].term == "Project Phoenix"
        assert matches[0].category == "product_names"

    def test_detects_infrastructure(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("Connected to prod-db-01.internal for backfill.")
        assert len(matches) == 1
        assert matches[0].term == "prod-db-01.internal"
        assert matches[0].category == "infrastructure"

    def test_detects_people(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("John Doe approved the PR.")
        assert len(matches) == 1
        assert matches[0].term == "John Doe"
        assert matches[0].category == "people"

    def test_case_insensitive(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        matches = bl.scan("acme corp is great, ACME CORP rocks, AcMe CoRp too")
        assert len(matches) == 3

    def test_multiple_categories_in_one_text(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        text = "Acme Corp built Project Phoenix for Big Bank"
        matches = bl.scan(text)
        categories = {m.category for m in matches}
        assert "company_names" in categories
        assert "product_names" in categories
        assert "client_names" in categories

    def test_clean_text_passes(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        assert bl.is_clean("We deployed a new PostgreSQL pipeline using Kafka.")

    def test_is_clean_false_on_match(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        assert not bl.is_clean("Acme Corp is mentioned here.")

    def test_no_false_positives_on_generic_terms(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        generic = (
            "We used PostgreSQL, Redis, Kafka, React, FastAPI, Python, "
            "Docker, Kubernetes, CI/CD pipelines, and event-driven architecture."
        )
        assert bl.is_clean(generic)

    def test_empty_blocklist(self):
        from src.config import SanitisationConfig

        bl = Blocklist(SanitisationConfig())
        assert bl.is_clean("Anything goes here.")
        assert bl.scan("Anything") == []


class TestBlocklistAbstractions:
    def test_applies_abstractions(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        result = bl.apply_abstractions("We built Acme Corp's data platform.")
        assert "Acme Corp" not in result
        assert "a mid-size fintech" in result

    def test_applies_multiple_abstractions(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        text = "Acme Corp built Project Phoenix for Big Bank"
        result = bl.apply_abstractions(text)
        assert "Acme Corp" not in result
        assert "Project Phoenix" not in result
        assert "Big Bank" not in result
        assert "a mid-size fintech" in result
        assert "an internal data platform" in result
        assert "a major financial institution" in result

    def test_abstraction_case_insensitive(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        result = bl.apply_abstractions("acme corp launched something.")
        assert "acme corp" not in result.lower() or "a mid-size fintech" in result

    def test_no_abstractions_on_clean_text(self, test_config):
        bl = Blocklist(test_config.sanitisation)
        original = "Generic technical content about databases."
        result = bl.apply_abstractions(original)
        assert result == original
