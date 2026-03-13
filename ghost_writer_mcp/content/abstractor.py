"""Content sanitisation pipeline combining blocklist scanning and LLM review."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ghost_writer_mcp.config import GhostWriterConfig
from ghost_writer_mcp.llm_client import LLMClient
from ghost_writer_mcp.store.blocklist import Blocklist

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class SanitisationResult:
    clean_text: str
    gate1_matches: list = field(default_factory=list)
    gate2_flags: list = field(default_factory=list)
    is_safe: bool = True


class Abstractor:
    """Two-gate sanitisation: deterministic blocklist then LLM review."""

    def __init__(self, config: GhostWriterConfig) -> None:
        self._config = config
        self.blocklist = Blocklist(config.sanitisation)
        self.llm = LLMClient(config.llm)
        self._classifier_model = config.llm.classifier_model

    def sanitise(self, text: str) -> SanitisationResult:
        """Run both sanitisation gates and return the result."""
        # Gate 1: deterministic blocklist scan + abstraction
        matches = self.blocklist.scan(text)
        clean = self.blocklist.apply_abstractions(text)

        # Gate 2: LLM confidentiality review
        flags = self._llm_review(clean)

        return SanitisationResult(
            clean_text=clean,
            gate1_matches=matches,
            gate2_flags=flags,
            is_safe=len(flags) == 0,
        )

    def _llm_review(self, text: str) -> list[dict]:
        """Send *text* to the classifier model for confidentiality review."""
        reviewer_prompt = (_PROMPTS_DIR / "reviewer.md").read_text()

        raw = self.llm.complete(
            model=self._classifier_model,
            system=reviewer_prompt,
            user_message=text,
            max_tokens=1024,
        ).strip()

        # Strip qwen3 <think>...</think> reasoning blocks
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Strip optional ```json fencing
        fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if fenced:
            raw = fenced.group(1).strip()

        try:
            flags = json.loads(raw)
            if isinstance(flags, list):
                return flags
            return []
        except (json.JSONDecodeError, TypeError):
            return []
