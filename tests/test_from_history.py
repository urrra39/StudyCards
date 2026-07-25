"""Tests for the real-history evaluation report (src/evaluation/from_history.py)."""
from __future__ import annotations

from src.data.repository import CardRepository
from src.evaluation.from_history import report_from_db
from src.extraction.schema import Flashcard


def _seed_reviews(path) -> None:
    repo = CardRepository(path)
    cid = repo.add_card(
        Flashcard(
            question="What does the ease factor control in SM-2?",
            answer="How quickly intervals grow.",
            concept="Ease factor",
        )
    )
    # A pass, a pass, and a fail (quality < 3).
    repo.record_review(cid, 5)
    repo.record_review(cid, 4)
    repo.record_review(cid, 1)


class TestHistoryReport:
    def test_empty_db_reports_zeros(self, tmp_path):
        CardRepository(tmp_path / "empty.db")
        report = report_from_db(tmp_path / "empty.db")
        assert report.total_reviews == 0
        assert report.fail_rate == 0.0
        assert report.schedule_mismatches == 0

    def test_counts_and_means(self, tmp_path):
        path = tmp_path / "h.db"
        _seed_reviews(path)
        report = report_from_db(path)
        assert report.total_cards == 1
        assert report.total_reviews == 3
        assert abs(report.mean_quality - (5 + 4 + 1) / 3) < 1e-9
        # exactly one review had quality < 3
        assert abs(report.fail_rate - 1 / 3) < 1e-9

    def test_replay_matches_recorded_transitions(self, tmp_path):
        # Reviews written by the real recorder must replay with zero mismatches.
        path = tmp_path / "h.db"
        _seed_reviews(path)
        report = report_from_db(path)
        assert report.schedule_mismatches == 0

    def test_as_dict_exposes_all_fields(self, tmp_path):
        path = tmp_path / "h.db"
        _seed_reviews(path)
        data = report_from_db(path).as_dict()
        assert set(data) == {
            "total_cards", "total_reviews", "mean_quality",
            "mean_interval_after", "fail_rate", "schedule_mismatches",
        }
