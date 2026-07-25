"""Round-trip / shape tests for deck export (src/data/export.py)."""
from __future__ import annotations

import json

from src.data.export import cards_to_json, cards_to_tsv
from src.data.repository import CardRepository
from src.extraction.schema import Flashcard


def _seed(repo: CardRepository) -> None:
    repo.add_card(
        Flashcard(
            question="What does the ease factor control in SM-2?",
            answer="How quickly intervals grow.",
            concept="Ease factor",
        )
    )
    repo.add_card(
        Flashcard(
            question="Что такое фотосинтез?",
            answer="Процесс в растениях.",
            concept="Фотосинтез",
        )
    )


class TestJsonExport:
    def test_json_round_trip_shape(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        _seed(repo)
        payload = json.loads(cards_to_json(repo.list_cards()))
        assert set(payload.keys()) == {"cards"}
        assert len(payload["cards"]) == 2
        first = payload["cards"][0]
        for key in (
            "id", "question", "answer", "concept", "ease_factor",
            "repetitions", "interval_days", "due_date", "created_at", "updated_at",
        ):
            assert key in first

    def test_json_can_include_reviews(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        _seed(repo)
        card = repo.list_cards()[0]
        repo.record_review(card.id, 5)
        reviews = repo.list_reviews(card.id)
        payload = json.loads(cards_to_json(repo.list_cards(), reviews))
        assert "reviews" in payload
        assert len(payload["reviews"]) == 1
        assert payload["reviews"][0]["quality"] == 5

    def test_json_preserves_unicode_readably(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        _seed(repo)
        text = cards_to_json(repo.list_cards())
        assert "Фотосинтез" in text  # not \uXXXX-escaped


class TestTsvExport:
    def test_tsv_has_header_and_one_line_per_card(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        _seed(repo)
        lines = cards_to_tsv(repo.list_cards()).strip().splitlines()
        assert lines[0].split("\t") == ["question", "answer", "concept"]
        assert len(lines) == 3  # header + 2 cards
        for line in lines[1:]:
            assert len(line.split("\t")) == 3

    def test_tsv_without_concept(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        _seed(repo)
        lines = cards_to_tsv(repo.list_cards(), include_concept=False).strip().splitlines()
        assert lines[0].split("\t") == ["question", "answer"]

    def test_tsv_flattens_newlines(self, tmp_path):
        repo = CardRepository(tmp_path / "e.db")
        repo.add_card(
            Flashcard(
                question="Line one and then more text here?",
                answer="Answer with\na newline in it.",
                concept="Formatting",
            )
        )
        body = cards_to_tsv(repo.list_cards()).strip().splitlines()
        # header + exactly one card row (newline must not split the card).
        assert len(body) == 2
