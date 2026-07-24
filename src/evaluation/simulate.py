"""Simulation harness: run SM-2 vs. fixed-interval against a memory model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Protocol

import numpy as np

from src.evaluation.memory_model import (
    MemoryModel,
    make_population,
    quality_from_retrievability,
)
from src.scheduler.sm2 import CardState, review


class Scheduler(Protocol):
    def is_due(self, card_id: int, day: int) -> bool: ...
    def on_reviewed(self, card_id: int, day: int, quality: int) -> None: ...


@dataclass
class FixedIntervalScheduler:
    """Naive baseline: review every ``interval_days`` regardless of performance."""

    n_cards: int
    interval_days: int = 3
    next_due: Dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # All cards due on day 0 (same as SM-2 fresh cards).
        self.next_due = {i: 0 for i in range(self.n_cards)}

    def is_due(self, card_id: int, day: int) -> bool:
        return day >= self.next_due[card_id]

    def on_reviewed(self, card_id: int, day: int, quality: int) -> None:
        # Ignores quality by design — that is what makes it the naive baseline.
        self.next_due[card_id] = day + self.interval_days


@dataclass
class SM2Scheduler:
    """Wraps the production SM-2 implementation for day-indexed simulation."""

    n_cards: int
    states: Dict[int, CardState] = field(default_factory=dict)
    _epoch: date = field(default_factory=lambda: date(2026, 1, 1))

    def __post_init__(self) -> None:
        self.states = {i: CardState(due_date=self._epoch) for i in range(self.n_cards)}

    def _day_to_date(self, day: int) -> date:
        return self._epoch + timedelta(days=day)

    def is_due(self, card_id: int, day: int) -> bool:
        due = self.states[card_id].due_date
        return due is None or due <= self._day_to_date(day)

    def on_reviewed(self, card_id: int, day: int, quality: int) -> None:
        result = review(self.states[card_id], quality, review_date=self._day_to_date(day))
        self.states[card_id] = result.state


@dataclass
class SimMetrics:
    name: str
    horizon_days: int
    n_cards: int
    total_reviews: int
    mean_retrievability: float
    median_retrievability: float
    fraction_days_above_threshold: float
    mean_r_at_review: float
    threshold: float
    reviews_per_card: float

    def as_dict(self) -> dict:
        return {
            "scheduler": self.name,
            "horizon_days": self.horizon_days,
            "n_cards": self.n_cards,
            "threshold": self.threshold,
            "total_reviews": self.total_reviews,
            "reviews_per_card": round(self.reviews_per_card, 2),
            "mean_retrievability": round(self.mean_retrievability, 4),
            "median_retrievability": round(self.median_retrievability, 4),
            "fraction_days_above_threshold": round(self.fraction_days_above_threshold, 4),
            "mean_r_at_review": round(self.mean_r_at_review, 4),
        }


def run_simulation(
    scheduler: Scheduler,
    model: MemoryModel,
    *,
    horizon_days: int,
    threshold: float,
    name: str,
) -> SimMetrics:
    """Day-by-day simulation. Reviews fire when ``scheduler.is_due``.

    Daily R for every card is recorded *before* that day's reviews, so the
    fraction-above-threshold metric reflects sustained memory, not momentary
    post-review spikes.
    """
    n = len(model.cards)
    daily_r: List[float] = []
    r_at_review: List[float] = []
    total_reviews = 0

    for day in range(horizon_days):
        for card in model.cards:
            daily_r.append(card.retrievability_on(day))

        for card_id in range(n):
            if not scheduler.is_due(card_id, day):
                continue
            r = model.cards[card_id].retrievability_on(day)
            q = quality_from_retrievability(r)
            r_at_review.append(r)
            model.apply_review(card_id, day, q)
            scheduler.on_reviewed(card_id, day, q)
            total_reviews += 1

    arr = np.asarray(daily_r, dtype=float)
    review_arr = np.asarray(r_at_review, dtype=float) if r_at_review else np.array([0.0])
    return SimMetrics(
        name=name,
        horizon_days=horizon_days,
        n_cards=n,
        total_reviews=total_reviews,
        mean_retrievability=float(arr.mean()),
        median_retrievability=float(np.median(arr)),
        fraction_days_above_threshold=float((arr >= threshold).mean()),
        mean_r_at_review=float(review_arr.mean()),
        threshold=threshold,
        reviews_per_card=total_reviews / n,
    )


def compare_schedulers(
    *,
    n_cards: int = 50,
    horizon_days: int = 180,
    threshold: float = 0.85,
    fixed_interval_days: int = 3,
    seed: int = 42,
) -> Dict[str, SimMetrics]:
    """Run SM-2 and fixed-interval on identically initialized populations."""
    rng = np.random.default_rng(seed)

    sm2_model = make_population(n_cards, rng=rng)
    # Fresh RNG state consumed above; rebuild an identical population for fairness.
    rng2 = np.random.default_rng(seed)
    fixed_model = make_population(n_cards, rng=rng2)

    sm2 = run_simulation(
        SM2Scheduler(n_cards),
        sm2_model,
        horizon_days=horizon_days,
        threshold=threshold,
        name="SM-2",
    )
    fixed = run_simulation(
        FixedIntervalScheduler(n_cards, interval_days=fixed_interval_days),
        fixed_model,
        horizon_days=horizon_days,
        threshold=threshold,
        name=f"Fixed-{fixed_interval_days}d",
    )
    return {"sm2": sm2, "fixed": fixed}
