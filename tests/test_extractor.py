"""Tests for the LLM extraction stage — all completions are stubs."""
import json

import pytest

from src.extraction.extractor import (
    ExtractionParseError,
    build_extraction_prompt,
    extract_cards_from_chunk,
    parse_cards_response,
)

VALID_CARDS = [
    {"concept": "Ease factor", "question": "What does the ease factor control in SM-2?",
     "answer": "It scales how quickly review intervals grow for a card."},
    {"concept": "Quality rating", "question": "Why does SM-2 reset intervals on ratings below 3?",
     "answer": "A failed recall means the memory trace is too weak for long intervals."},
]


class TestBuildPrompt:
    def test_prompt_embeds_chunk_and_budget(self):
        prompt = build_extraction_prompt("CHUNK-BODY-HERE", max_cards=5)
        assert "CHUNK-BODY-HERE" in prompt
        assert "at most 5 flashcards" in prompt

    def test_prompt_bans_trivia_and_deixis(self):
        # These constraints are the core of the extraction design; losing
        # them from the prompt silently degrades card quality.
        prompt = build_extraction_prompt("x")
        assert "CONCEPT-LEVEL" in prompt
        assert "SELF-CONTAINED" in prompt
        assert "NO REDUNDANCY" in prompt


class TestParseCardsResponse:
    def test_parses_clean_json_array(self):
        cards = parse_cards_response(json.dumps(VALID_CARDS), source_chunk=3)
        assert len(cards) == 2
        assert cards[0].concept == "Ease factor"
        assert cards[0].source_chunk == 3

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps(VALID_CARDS) + "\n```"
        assert len(parse_cards_response(raw)) == 2

    def test_extracts_array_from_surrounding_prose(self):
        raw = "Here are the cards:\n" + json.dumps(VALID_CARDS) + "\nLet me know!"
        assert len(parse_cards_response(raw)) == 2

    def test_empty_array_is_valid(self):
        assert parse_cards_response("[]") == []

    def test_skips_malformed_entries_keeps_valid(self):
        data = [VALID_CARDS[0], "not-a-dict", {"question": "", "answer": "orphan"}]
        cards = parse_cards_response(json.dumps(data))
        assert len(cards) == 1

    def test_missing_concept_falls_back_to_question_prefix(self):
        data = [{"question": "What is spaced repetition?", "answer": "A scheduling method."}]
        cards = parse_cards_response(json.dumps(data))
        assert cards[0].concept == "What is spaced repetition?"

    def test_no_array_raises(self):
        with pytest.raises(ExtractionParseError):
            parse_cards_response("I could not find any concepts.")

    def test_invalid_json_raises(self):
        with pytest.raises(ExtractionParseError):
            parse_cards_response("[{'single': 'quotes'}]")

    def test_non_array_json_raises(self):
        with pytest.raises(ExtractionParseError):
            parse_cards_response('{"question": "q", "answer": "a"}')


class TestExtractCardsFromChunk:
    def test_happy_path_uses_completion_fn(self):
        prompts_seen = []

        def stub_complete(prompt: str) -> str:
            prompts_seen.append(prompt)
            return json.dumps(VALID_CARDS)

        cards = extract_cards_from_chunk("chunk body", 7, stub_complete)
        assert len(cards) == 2
        assert all(c.source_chunk == 7 for c in cards)
        assert "chunk body" in prompts_seen[0]

    def test_unparseable_response_returns_empty_not_raise(self):
        # One bad completion must not kill a multi-chunk document run.
        cards = extract_cards_from_chunk("chunk", 0, lambda _: "total garbage")
        assert cards == []
