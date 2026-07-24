"""Tests for quality filtering and Jaccard deduplication — no LLM calls."""
from __future__ import annotations

from src.extraction.filtering import (
    JACCARD_THRESHOLD,
    dedup_cards,
    filter_cards,
    passes_quality,
    question_similarity,
)
from src.extraction.schema import Flashcard


def card(q: str, a: str = "A correct, complete answer.", concept: str = "C") -> Flashcard:
    return Flashcard(question=q, answer=a, concept=concept)


class TestQuestionSimilarity:
    def test_identical_questions_are_1(self):
        assert question_similarity("What is ease factor?", "What is ease factor?") == 1.0

    def test_unrelated_questions_are_low(self):
        assert question_similarity(
            "What is the ease factor in SM-2?",
            "How does photosynthesis produce glucose?",
        ) < 0.3

    def test_near_duplicates_exceed_threshold(self):
        # Dominant failure mode: same wording re-extracted from an overlap region.
        a = "What does the ease factor control in the SM-2 algorithm?"
        b = "What does the ease factor control in SM-2?"
        assert question_similarity(a, b) >= JACCARD_THRESHOLD

    def test_stopwords_do_not_inflate_similarity(self):
        # "What is the X" vs "What is a Y" must not look similar just from glue words.
        sim = question_similarity("What is the mitochondria?", "What is a chloroplast?")
        assert sim < JACCARD_THRESHOLD


class TestPassesQuality:
    def test_accepts_well_formed_card(self):
        assert passes_quality(card("What does the ease factor control in SM-2?"))

    def test_rejects_short_question(self):
        assert not passes_quality(card("Too short?", "A solid answer here."))

    def test_rejects_short_answer(self):
        assert not passes_quality(card("What is spaced repetition used for?", "ok"))

    def test_rejects_overlong_answer(self):
        assert not passes_quality(
            card("What is spaced repetition used for?", "x" * 801)
        )

    def test_rejects_answer_that_restates_question(self):
        q = "What is spaced repetition scheduling?"
        assert not passes_quality(card(q, q))

    def test_rejects_document_deixis(self):
        assert not passes_quality(
            card(
                "According to the text, what is the ease factor?",
                "It scales interval growth.",
            )
        )
        assert not passes_quality(
            card(
                "In this section, how does SM-2 update intervals?",
                "By multiplying the previous interval by the ease factor.",
            )
        )


class TestDedupAndFilter:
    def test_dedup_keeps_first_of_near_duplicates(self):
        first = card(
            "What does the ease factor control in the SM-2 algorithm?",
            concept="EF-first",
        )
        second = card(
            "What does the ease factor control in SM-2?",
            concept="EF-second",
        )
        kept = dedup_cards([first, second])
        assert len(kept) == 1
        assert kept[0].concept == "EF-first"

    def test_dedup_keeps_distinct_concepts(self):
        cards = [
            card("What does the ease factor control in SM-2?"),
            card("Why does SM-2 reset the interval after a failed recall?"),
        ]
        assert len(dedup_cards(cards)) == 2

    def test_filter_drops_low_quality_before_dedup(self):
        # Quality-first: a short junk card must not shadow a good near-duplicate.
        junk = card("Too short?", "x")
        good = card(
            "What does the ease factor control in SM-2?",
            "It scales how quickly review intervals grow.",
        )
        # Near-dup of `good` that would lose a first-wins fight against junk
        # if quality ran after dedup.
        also_good = card(
            "What does the ease factor control in the SM-2 algorithm?",
            "It scales interval growth for each card.",
        )
        result = filter_cards([junk, good, also_good])
        assert len(result) == 1
        assert result[0].question.startswith("What does the ease factor")
        assert result[0] is not junk
