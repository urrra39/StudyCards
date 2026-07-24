"""Integration tests for SQLite persistence + SM-2 review recording."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.repository import CardRepository
from src.extraction.schema import Flashcard


@pytest.fixture
def repo(tmp_path) -> CardRepository:
    return CardRepository(tmp_path / "test.db")


def _sample_card(**kwargs) -> Flashcard:
    base = dict(
        question="What does the ease factor control in SM-2?",
        answer="It scales how quickly review intervals grow.",
        concept="Ease factor",
        source_chunk=0,
    )
    base.update(kwargs)
    return Flashcard(**base)


class TestSchemaAndInsert:
    def test_initialize_is_idempotent(self, repo: CardRepository):
        repo.initialize()
        repo.initialize()
        assert repo.count_cards() == 0

    def test_add_and_get_card(self, repo: CardRepository):
        card_id = repo.add_card(_sample_card(), now=datetime(2026, 1, 1, 12, 0, 0))
        stored = repo.get_card(card_id)
        assert stored is not None
        assert stored.question.startswith("What does the ease factor")
        assert stored.ease_factor == 2.5
        assert stored.repetitions == 0
        assert stored.interval_days == 0
        assert stored.due_date == date(2026, 1, 1)
        assert stored.source_chunk == 0

    def test_add_cards_bulk(self, repo: CardRepository):
        ids = repo.add_cards(
            [
                _sample_card(concept="A", question="Question A is long enough?"),
                _sample_card(concept="B", question="Question B is long enough?"),
            ]
        )
        assert len(ids) == 2
        assert repo.count_cards() == 2
        assert ids[0] != ids[1]


class TestDueCards:
    def test_lists_cards_due_on_or_before(self, repo: CardRepository):
        early = repo.add_card(
            _sample_card(question="Early card question here?"),
            due_date=date(2026, 1, 1),
            now=datetime(2026, 1, 1),
        )
        late = repo.add_card(
            _sample_card(question="Late card question here??"),
            due_date=date(2026, 1, 10),
            now=datetime(2026, 1, 1),
        )
        due = repo.list_due_cards(on=date(2026, 1, 5))
        due_ids = [c.id for c in due]
        assert early in due_ids
        assert late not in due_ids


class TestRecordReview:
    def test_updates_card_and_appends_history(self, repo: CardRepository):
        card_id = repo.add_card(_sample_card(), now=datetime(2026, 2, 1, 9, 0, 0))

        # First successful review: I(1)=1, EF=2.6
        rev = repo.record_review(
            card_id,
            quality=5,
            review_date=date(2026, 2, 1),
            now=datetime(2026, 2, 1, 9, 5, 0),
        )
        card = repo.get_card(card_id)
        assert card is not None
        assert card.interval_days == 1
        assert card.repetitions == 1
        assert card.ease_factor == pytest.approx(2.6)
        assert card.due_date == date(2026, 2, 2)

        assert rev.quality == 5
        assert rev.interval_before == 0
        assert rev.interval_after == 1
        assert rev.ease_factor_before == pytest.approx(2.5)
        assert rev.ease_factor_after == pytest.approx(2.6)
        assert "5/5" in rev.explanation
        assert repo.count_reviews() == 1

    def test_full_history_preserved_across_reviews(self, repo: CardRepository):
        card_id = repo.add_card(_sample_card(), now=datetime(2026, 3, 1))
        repo.record_review(card_id, 5, review_date=date(2026, 3, 1), now=datetime(2026, 3, 1))
        repo.record_review(card_id, 4, review_date=date(2026, 3, 2), now=datetime(2026, 3, 2))
        repo.record_review(card_id, 5, review_date=date(2026, 3, 8), now=datetime(2026, 3, 8))

        history = repo.list_reviews(card_id)
        assert len(history) == 3
        # Hand-traced: after 5,4,5 → intervals 1, 6, 16
        assert [h.interval_after for h in history] == [1, 6, 16]
        assert [h.quality for h in history] == [5, 4, 5]

        card = repo.get_card(card_id)
        assert card is not None
        assert card.interval_days == 16
        assert card.repetitions == 3
        assert card.ease_factor == pytest.approx(2.7)

    def test_failure_recorded_with_reset_interval(self, repo: CardRepository):
        card_id = repo.add_card(_sample_card(), now=datetime(2026, 4, 1))
        repo.record_review(card_id, 5, review_date=date(2026, 4, 1), now=datetime(2026, 4, 1))
        repo.record_review(card_id, 4, review_date=date(2026, 4, 2), now=datetime(2026, 4, 2))
        fail = repo.record_review(
            card_id, 0, review_date=date(2026, 4, 8), now=datetime(2026, 4, 8)
        )

        assert fail.interval_after == 1
        assert fail.repetitions_after == 0
        assert fail.ease_factor_after == pytest.approx(1.8)
        assert repo.get_card(card_id).repetitions == 0

    def test_missing_card_raises(self, repo: CardRepository):
        with pytest.raises(KeyError):
            repo.record_review(999, 4)

    def test_delete_cascades_history(self, repo: CardRepository):
        card_id = repo.add_card(_sample_card(), now=datetime(2026, 5, 1))
        repo.record_review(card_id, 5, review_date=date(2026, 5, 1), now=datetime(2026, 5, 1))
        assert repo.count_reviews() == 1
        repo.delete_card(card_id)
        assert repo.count_cards() == 0
        assert repo.count_reviews() == 0
        assert repo.list_reviews(card_id) == []
