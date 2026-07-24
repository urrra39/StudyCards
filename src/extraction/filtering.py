"""Deduplication and quality filtering of candidate flashcards.

Overlapping chunks (see chunker) plus LLM nondeterminism mean the raw
candidate set contains near-duplicates. All rules here are deterministic and
local — no LLM calls — so this stage is fully unit-testable and free.

Dedup approach: token-set Jaccard similarity on normalized question text.
An embedding model would catch paraphrases better, but Jaccard at 0.6 already
catches the dominant failure mode (the *same* wording re-extracted from an
overlap region) with zero extra dependencies and completely explainable
behavior. Threshold 0.6 was chosen because true duplicates from overlap
regions share most content words, while distinct concepts from the same
passage rarely exceed ~0.4.
"""
from __future__ import annotations

import re
from typing import FrozenSet, List

from src.extraction.schema import Flashcard

JACCARD_THRESHOLD = 0.6
MIN_QUESTION_CHARS = 12
MIN_ANSWER_CHARS = 3
MAX_ANSWER_CHARS = 800

# Common English stopwords: excluded from Jaccard so similarity reflects
# content words. "What is the" matching "What is a" must not count as overlap.
_STOPWORDS = frozenset(
    "a an the is are was were be been do does did what which who whom how why when "
    "where of in on at to for from with by and or not it its this that these those "
    "can could would should".split()
)


def _content_tokens(text: str) -> FrozenSet[str]:
    """Lowercased content-word token set for similarity comparison."""
    tokens = re.findall(r"[a-z0-9']+", text.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS)


def question_similarity(a: str, b: str) -> float:
    """Jaccard similarity over content tokens of two questions (0..1)."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 1.0 if ta == tb else 0.0
    return len(ta & tb) / len(ta | tb)


def passes_quality(card: Flashcard) -> bool:
    """Deterministic quality gate for a single card.

    Rejects:
    * questions/answers below minimum length (fragments, "N/A" answers);
    * answers that merely restate the question (the classic LLM cop-out);
    * answers so long they defeat active recall (> MAX_ANSWER_CHARS);
    * questions that leak document deixis ("according to the text").
    """
    q, a = card.question.strip(), card.answer.strip()
    if len(q) < MIN_QUESTION_CHARS or len(a) < MIN_ANSWER_CHARS:
        return False
    if len(a) > MAX_ANSWER_CHARS:
        return False
    if question_similarity(q, a) >= 0.9 and _content_tokens(q) == _content_tokens(a):
        return False
    deixis = re.search(
        r"\b(according to the (text|passage|document|author)|in this (section|chapter|text|passage))\b",
        q,
        flags=re.IGNORECASE,
    )
    return deixis is None


def dedup_cards(cards: List[Flashcard], threshold: float = JACCARD_THRESHOLD) -> List[Flashcard]:
    """Drop near-duplicate cards, keeping the first occurrence.

    First-wins (rather than best-wins) keeps behavior order-stable and
    predictable; chunks are processed in document order, so the kept card is
    the one extracted from the concept's primary location.
    """
    kept: List[Flashcard] = []
    for card in cards:
        if any(question_similarity(card.question, k.question) >= threshold for k in kept):
            continue
        kept.append(card)
    return kept


def filter_cards(cards: List[Flashcard], threshold: float = JACCARD_THRESHOLD) -> List[Flashcard]:
    """Full post-processing: quality gate first, then dedup.

    Quality-first ordering matters: a low-quality card must not shadow
    (dedup away) a high-quality near-duplicate that appears later.
    """
    return dedup_cards([c for c in cards if passes_quality(c)], threshold=threshold)
