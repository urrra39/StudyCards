"""Descriptive metrics computed from a user's REAL logged reviews.

This is the honest counterpart to the synthetic ``simulate`` evaluation:
* ``simulate`` measures how SM-2 *would* behave under a modelled forgetting
  curve - it tests the scheduler, not a human.
* ``from_history`` reads the actual ``review_history`` a user accumulated and
  reports descriptive statistics about it, plus a consistency replay that
  re-derives each SM-2 transition and flags any stored row that disagrees with
  the scheduler (catches data corruption or scheduler drift).

Neither claims to measure human memory; see docs/EVALUATION_RESULTS.md.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Union

from src.data.repository import CardRepository, StoredReview
from src.scheduler.sm2 import CardState, review

PathLike = Union[str, Path]


@dataclass(frozen=True)
class HistoryReport:
    total_cards: int
    total_reviews: int
    mean_quality: float
    mean_interval_after: float
    fail_rate: float           # fraction of reviews with quality < 3
    schedule_mismatches: int   # stored transitions that disagree with SM-2

    def as_dict(self) -> dict:
        return asdict(self)


def _replay_matches(r: StoredReview) -> bool:
    """Recompute the SM-2 transition for one review and compare to what was
    stored. Compares EF/reps/interval; due_date depends on the exact review
    date (history rounds to seconds) so it is intentionally not checked."""
    before = CardState(
        ease_factor=r.ease_factor_before,
        repetitions=r.repetitions_before,
        interval_days=r.interval_before,
        due_date=None,
    )
    new = review(before, r.quality).state
    return (
        abs(new.ease_factor - r.ease_factor_after) < 1e-9
        and new.repetitions == r.repetitions_after
        and new.interval_days == r.interval_after
    )


def report_from_db(db_path: PathLike) -> HistoryReport:
    """Open the SQLite DB at ``db_path`` and summarise its real review log."""
    repo = CardRepository(db_path)
    cards = repo.list_cards()
    reviews: List[StoredReview] = []
    for card in cards:
        reviews.extend(repo.list_reviews(card.id))

    total_reviews = len(reviews)
    if total_reviews == 0:
        return HistoryReport(
            total_cards=len(cards),
            total_reviews=0,
            mean_quality=0.0,
            mean_interval_after=0.0,
            fail_rate=0.0,
            schedule_mismatches=0,
        )

    mean_quality = sum(r.quality for r in reviews) / total_reviews
    mean_interval_after = sum(r.interval_after for r in reviews) / total_reviews
    fails = sum(1 for r in reviews if r.quality < 3)
    mismatches = sum(0 if _replay_matches(r) else 1 for r in reviews)

    return HistoryReport(
        total_cards=len(cards),
        total_reviews=total_reviews,
        mean_quality=mean_quality,
        mean_interval_after=mean_interval_after,
        fail_rate=fails / total_reviews,
        schedule_mismatches=mismatches,
    )


def render_report(report: HistoryReport) -> str:
    """Short ASCII summary for CLI output."""
    return (
        f"cards={report.total_cards} reviews={report.total_reviews} "
        f"mean_quality={report.mean_quality:.2f} "
        f"mean_interval_after={report.mean_interval_after:.2f} "
        f"fail_rate={report.fail_rate:.2%} "
        f"schedule_mismatches={report.schedule_mismatches}"
    )
