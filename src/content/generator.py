"""Generate LinkedIn post drafts from classified activities."""

from dataclasses import dataclass
from pathlib import Path

import re

from src.config import GhostWriterConfig
from src.content.abstractor import Abstractor, SanitisationResult
from src.content.classifier import ClassifiedActivity
from src.llm_client import LLMClient

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class GeneratedDraft:
    title: str
    body: str
    pillar: str
    format: str
    safety_check: SanitisationResult
    activity_summary: str


class DraftGenerator:
    """Generates LinkedIn post drafts from classified GitHub activities."""

    def __init__(self, config: GhostWriterConfig) -> None:
        self.config = config
        self.llm = LLMClient(config.llm)
        self.generator_model = config.llm.generator_model
        self.abstractor = Abstractor(config)

    def generate(
        self,
        activity: ClassifiedActivity,
        format_override: str | None = None,
        tone_override: str | None = None,
    ) -> GeneratedDraft:
        """Generate a LinkedIn post draft from a classified activity."""
        format_type = format_override or activity.format_suggestion
        tone = tone_override or self.config.content.style.tone

        # Step 1: Sanitise the activity input
        raw_input = "\n\n".join(
            part
            for part in [
                activity.activity.title,
                activity.activity.description,
                activity.activity.diff_summary,
            ]
            if part
        )
        input_sanitisation = self.abstractor.sanitise(raw_input)

        # Step 2: Build the generation prompt
        system_prompt, user_message = self._build_prompt(
            activity, input_sanitisation.clean_text, format_type, tone
        )

        # Step 3: Generate the post
        raw_text = self.llm.complete(
            model=self.generator_model,
            system=system_prompt,
            user_message=user_message,
            max_tokens=2048,
        )
        # Strip qwen3 <think>...</think> reasoning blocks
        generated_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

        # Step 4: Sanitise the output
        output_sanitisation = self.abstractor.sanitise(generated_text)

        # Step 5: Extract title as first line
        lines = output_sanitisation.clean_text.split("\n", 1)
        title = lines[0].strip()
        body = output_sanitisation.clean_text

        return GeneratedDraft(
            title=title,
            body=body,
            pillar=activity.pillar,
            format=format_type,
            safety_check=output_sanitisation,
            activity_summary=input_sanitisation.clean_text,
        )

    def _build_prompt(
        self,
        activity: ClassifiedActivity,
        sanitised_input: str,
        format_type: str,
        tone: str,
    ) -> tuple[str, str]:
        """Build the system prompt and user message for generation."""
        style = self.config.content.style

        few_shot = ""
        if style.few_shot_posts:
            few_shot = "\n\n---\n\n".join(
                f"**Example {i}:**\n{post}"
                for i, post in enumerate(style.few_shot_posts, 1)
            )
        else:
            few_shot = "No example posts provided."

        # Build author context from repo config
        repo_name = activity.activity.repo_full_name
        repo_cfg = next(
            (r for r in self.config.github.repos
             if f"{r.owner}/{r.name}" == repo_name),
            None,
        )
        author_context = f"Role: {repo_cfg.role}" if repo_cfg else "Senior technical leader"

        template = (_PROMPTS_DIR / "generator.md").read_text()
        system_prompt = (
            template.replace("{tone}", tone)
            .replace("{language}", style.language)
            .replace("{max_length}", str(style.max_length))
            .replace("{use_emoji}", "Yes, use emoji where appropriate" if style.use_emoji else "No emoji")
            .replace("{hashtag_instructions}", self._format_hashtag_instructions())
            .replace("{format}", format_type)
            .replace("{few_shot_posts}", few_shot)
            .replace("{author_context}", author_context)
        )

        user_message = (
            f"## Activity to write about\n\n"
            f"**Type**: {activity.activity.activity_type}\n"
            f"**Suggested angle**: {activity.suggested_angle}\n"
            f"**Content pillar**: {activity.pillar}\n"
            f"**Diff stats**: {activity.activity.diff_summary}\n\n"
            f"### What was done\n\n"
            f"{sanitised_input}"
        )

        return system_prompt, user_message

    def _format_hashtag_instructions(self) -> str:
        """Return hashtag instructions based on style config."""
        style = self.config.content.style
        if not style.use_hashtags:
            return "Do not include hashtags."
        return f"Include exactly {style.hashtag_count} hashtags at the end of the post."
