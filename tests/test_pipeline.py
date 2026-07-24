"""End-to-end pipeline test with a stubbed CompletionFn (no network)."""
from __future__ import annotations

import json

from src.extraction.pipeline import extract_flashcards
from src.extraction.schema import Flashcard


def test_pipeline_chunks_extracts_filters_and_dedups():
    # Two near-identical paragraphs force overlap → two extractions of the
    # same concept → global dedup must collapse them to one card.
    para = (
        "The ease factor in SM-2 scales how quickly review intervals grow. "
        "A higher ease factor means longer gaps after successful recalls. "
    )
    text = (para + "\n\n") * 6  # long enough to produce multiple chunks

    responses = {
        0: [
            {
                "concept": "Ease factor",
                "question": "What does the ease factor control in SM-2?",
                "answer": "It scales how quickly review intervals grow after successful recalls.",
            },
            {
                "concept": "Junk",
                "question": "Too short?",
                "answer": "x",
            },
        ],
        # Near-duplicate of card 0 — should be removed by global dedup.
        1: [
            {
                "concept": "Ease factor again",
                "question": "What does the ease factor control in the SM-2 algorithm?",
                "answer": "It scales interval growth for each card.",
            },
            {
                "concept": "Reset",
                "question": "Why does SM-2 reset the interval after a failed recall?",
                "answer": "A failed recall means the memory is too weak for long intervals.",
            },
        ],
    }
    call_count = {"n": 0}

    def stub(prompt: str) -> str:
        idx = min(call_count["n"], max(responses))
        call_count["n"] += 1
        return json.dumps(responses.get(idx, responses[1]))

    cards = extract_flashcards(text, stub, max_chars=180, overlap_chars=40)
    assert call_count["n"] >= 2
    assert all(isinstance(c, Flashcard) for c in cards)
    # Junk filtered; near-duplicate collapsed; distinct "Reset" kept.
    questions = [c.question for c in cards]
    assert any("ease factor" in q.lower() for q in questions)
    assert any("failed recall" in q.lower() for q in questions)
    assert len(cards) == 2
