"""Classify aggregated activity groups into content pillars using an LLM."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ghost_writer_mcp.config import GhostWriterConfig
from ghost_writer_mcp.llm_client import LLMClient
from ghost_writer_mcp.scanner.activity import ActivityItem
from ghost_writer_mcp.scanner.aggregator import ActivityGroup

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedActivity:
    activity: ActivityItem
    pillar: str
    content_score: float
    suggested_angle: str
    format_suggestion: str


class ContentClassifier:
    """Evaluates activity groups for LinkedIn post potential."""

    def __init__(self, config: GhostWriterConfig) -> None:
        self.config = config
        self.llm = LLMClient(config.llm)
        self.classifier_model = config.llm.classifier_model
        self.pillars = config.content.pillars

    def classify_groups(
        self, groups: list[ActivityGroup], retries: int = 2
    ) -> list[ClassifiedActivity]:
        """Classify aggregated groups and return sorted by score descending."""
        if not groups:
            return []

        system_prompt = self._build_system_prompt()
        user_prompt = self._format_groups(groups)

        for attempt in range(1, retries + 1):
            response_text = self.llm.complete(
                model=self.classifier_model,
                system=system_prompt,
                user_message=user_prompt,
                max_tokens=4096,
            )

            classified = self._parse_response(response_text, groups)
            if classified:
                classified.sort(key=lambda c: c.content_score, reverse=True)
                return classified
            logger.warning("Attempt %d/%d returned no results, retrying...", attempt, retries)

        return []

    # Keep backward compat for tests
    def classify_batch(
        self, activities: list[ActivityItem]
    ) -> list[ClassifiedActivity]:
        """Classify raw activities (wraps each in a trivial group)."""
        groups = [
            ActivityGroup(
                repo_full_name=a.repo_full_name,
                title=a.title,
                description=a.description[:300],
                activity_count=1,
                total_additions=a.additions,
                total_deletions=a.deletions,
                activity_types={a.activity_type},
                representative=a,
            )
            for a in activities
        ]
        return self.classify_groups(groups)

    def _build_system_prompt(self) -> str:
        """Read the classifier prompt template and inject pillar definitions."""
        prompt_path = Path(__file__).parent / "prompts" / "classifier.md"
        template = prompt_path.read_text()

        pillar_lines = []
        for pillar in self.pillars:
            signals = ", ".join(pillar.repo_signals) if pillar.repo_signals else "any"
            pillar_lines.append(
                f"- **{pillar.name}** (weight {pillar.weight}): "
                f"{pillar.description} [signals: {signals}]"
            )

        pillars_text = "\n".join(pillar_lines) if pillar_lines else "No pillars defined."
        return template.replace("{pillars}", pillars_text)

    def _format_groups(self, groups: list[ActivityGroup]) -> str:
        """Format groups as a compact numbered list for the prompt."""
        lines = []
        for i, g in enumerate(groups, start=1):
            types = "/".join(sorted(g.activity_types))
            lines.append(
                f"{i}. [{types}] {g.repo_full_name}: {g.title}\n"
                f"   {g.description[:200]}\n"
                f"   {g.activity_count} commit(s), +{g.total_additions} -{g.total_deletions}"
            )
        return "\n\n".join(lines)

    def _parse_response(
        self, response_text: str, groups: list[ActivityGroup]
    ) -> list[ClassifiedActivity]:
        """Extract JSON from the response and map back to groups."""
        # Strip qwen3 <think>...</think> reasoning blocks
        clean = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

        # Handle ```json ... ``` fenced blocks
        match = re.search(r"```json\s*(.*?)\s*```", clean, re.DOTALL)
        json_text = match.group(1) if match else clean

        try:
            items = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM response as JSON: %s", exc)
            return []

        if not isinstance(items, list):
            items = [items]

        results: list[ClassifiedActivity] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if idx is None or not (1 <= idx <= len(groups)):
                continue
            group = groups[idx - 1]
            results.append(
                ClassifiedActivity(
                    activity=group.representative,
                    pillar=item.get("pillar", "unknown"),
                    content_score=float(item.get("content_score", 0)),
                    suggested_angle=item.get("suggested_angle", ""),
                    format_suggestion=item.get("format_suggestion", ""),
                )
            )

        return results
