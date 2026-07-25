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

Language handling: tokenization is Unicode-aware and language-agnostic, so
content words in Uzbek, Russian, or any script are compared on equal footing
with English. Stopword removal is a *refinement* on top of that, not the
foundation - similarity still works for a language whose function words we do
not list. We keep a small, high-confidence multilingual (en + ru + uz) stopword
set; anything not in it simply counts as a content word.
"""
from __future__ import annotations

import re
import unicodedata
from typing import FrozenSet, List

from src.extraction.schema import Flashcard

JACCARD_THRESHOLD = 0.6
MIN_QUESTION_CHARS = 12
MIN_ANSWER_CHARS = 3
MAX_ANSWER_CHARS = 800

# High-confidence function words across the three languages this tool is used
# with. Removing them sharpens similarity ("what is the" vs "what is a" must not
# read as overlap), but similarity does NOT depend on this list being complete:
# any unlisted word is treated as content, so an unsupported language still
# deduplicates correctly, just slightly less aggressively.
_STOPWORDS = frozenset(
    (
        # English
        "a an the is are was were be been do does did what which who whom how why "
        "when where of in on at to for from with by and or not it its this that "
        "these those can could would should "
        # Russian (Cyrillic; casefolded forms)
        "и в во не что он на я с со как а то все она так его но да ты к у же вы за "
        "бы по ее мне это "
        # Uzbek (Latin)
        "va bilan uchun bu shu u men sen biz ular bir har ham emas yoki agar nima "
        "qanday"
    ).split()
)

# Letters/digits in ANY script (``\w`` minus underscore), allowing internal
# apostrophes so English contractions and Uzbek's Latin apostrophe letters
# (o', g') stay as one token. Applied after normalization.
_TOKEN_RE = re.compile(r"[^\W_]+(?:['\u2019\u02bb][^\W_]+)*", re.UNICODE)


def _normalize(text: str) -> str:
    """Unicode-aware fold for cross-language comparison.

    NFKD-decompose then drop combining marks so accented / diacritic variants
    compare equal, and ``casefold`` for script-aware lowercasing (handles
    Cyrillic and more, which ``str.lower`` on ASCII assumptions would miss).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def _content_tokens(text: str) -> FrozenSet[str]:
    """Language-agnostic content-word token set for similarity comparison."""
    tokens = _TOKEN_RE.findall(_normalize(text))
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
    return not _has_document_deixis(q)


# Optional Uzbek Latin apostrophe (o'/g') in deixis phrases: plain ', curly ',
# or the modifier letter turned comma. Kept tolerant so "bo'limda" matches
# however the apostrophe was typed.
_UZ_APOS = r"['\u2019\u02bb`]?"

# Document-deixis phrases: a question that only makes sense while looking at the
# source ("according to the text") is useless as a standalone flashcard. These
# are deliberately WHOLE PHRASES, never bare words like "text"/"текст"/"shu",
# so a normal conceptual question that merely contains a common word is NOT
# rejected. This keeps the RU/UZ additions high-precision.
_DEIXIS_RE = re.compile(
    r"\b(?:"
    # English
    r"according to the (?:text|passage|document|author)"
    r"|in this (?:section|chapter|text|passage)"
    # Russian
    r"|согласно (?:тексту|документу|отрывку|автору|параграфу)"
    r"|в (?:этом|данном) (?:тексте|отрывке|разделе|параграфе)"
    r"|в (?:этой|данной) (?:главе|части)"
    # Uzbek (Latin)
    r"|matn(?:ga|da) (?:ko" + _UZ_APOS + r"ra|asosan)"
    r"|(?:ushbu|mazkur|shu) (?:bo" + _UZ_APOS + r"lim|bob|matn|paragraf)(?:da|ida)"
    r")\b",
    flags=re.IGNORECASE,
)


def _has_document_deixis(question: str) -> bool:
    """True if the question leaks document deixis in EN, RU, or UZ."""
    return _DEIXIS_RE.search(question) is not None


def find_near_duplicates(
    cards: List[Flashcard], threshold: float = JACCARD_THRESHOLD
) -> List[tuple]:
    """Report-only: pairs of cards whose questions exceed the dedup threshold.

    Uses the same ``question_similarity`` as ``dedup_cards`` so the Library's
    "near-duplicates" view matches what extraction would actually collapse. It
    only *reports* (index_a, index_b, score) pairs; it never merges, because
    merging two cards would have to discard one card's SM-2 schedule.
    """
    pairs: List[tuple] = []
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            score = question_similarity(cards[i].question, cards[j].question)
            if score >= threshold:
                pairs.append((i, j, score))
    return pairs


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
