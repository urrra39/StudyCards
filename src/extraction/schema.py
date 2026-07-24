"""Core data model shared by the extraction pipeline and persistence layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Flashcard:
    """A single concept-level Q&A card.

    ``concept`` is the short name of the idea being tested. It exists for
    two reasons: it forces the LLM to commit to *one* concept per card
    (discouraging multi-part trivia), and it gives the dedup stage a cheap
    first-pass grouping signal.
    """

    question: str
    answer: str
    concept: str
    source_chunk: Optional[int] = None
