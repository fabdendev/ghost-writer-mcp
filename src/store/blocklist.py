"""Blocklist scanning and abstraction utilities for sanitisation."""

import re
from dataclasses import dataclass

from src.config import SanitisationConfig


@dataclass
class BlocklistMatch:
    term: str
    position: int
    category: str


class Blocklist:
    """Pre-compiled blocklist scanner with abstraction support."""

    def __init__(self, config: SanitisationConfig) -> None:
        self._config = config
        self._abstractions = config.abstractions

        # Build a lookup from lowercase term -> category
        self._term_to_category: dict[str, str] = {}
        all_terms: list[str] = []
        for category, terms in config.blocklist.items():
            for t in terms:
                self._term_to_category[t.lower()] = category
            all_terms.extend(terms)

        # Sort by length descending for greedy matching
        all_terms.sort(key=len, reverse=True)

        if all_terms:
            self._pattern = re.compile(
                "|".join(re.escape(t) for t in all_terms), re.IGNORECASE
            )
        else:
            self._pattern = None

    def scan(self, text: str) -> list[BlocklistMatch]:
        """Find all blocklist matches in *text*."""
        if self._pattern is None:
            return []

        matches: list[BlocklistMatch] = []
        for m in self._pattern.finditer(text):
            matched_term = m.group()
            category = self._term_to_category.get(matched_term.lower(), "unknown")
            matches.append(
                BlocklistMatch(
                    term=matched_term,
                    position=m.start(),
                    category=category,
                )
            )
        return matches

    def apply_abstractions(self, text: str) -> str:
        """Replace each key in the abstractions dict with its value (case-insensitive)."""
        result = text
        for original, replacement in self._abstractions.items():
            result = re.sub(re.escape(original), replacement, result, flags=re.IGNORECASE)
        return result

    def is_clean(self, text: str) -> bool:
        """Return True if no blocklist terms are found in *text*."""
        return len(self.scan(text)) == 0
