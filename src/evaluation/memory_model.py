"""Synthetic memory model for scheduler evaluation.

Each card has a stability ``S`` (characteristic memory lifetime in days).
Retrievability decays exponentially between reviews:

    R(t) = exp(−t / S)

where ``t`` is days since the last successful encoding/review.

A successful review (mapped from R → SM-2 quality) grows S; a failure shrinks
it. Growth is larger when R is lower at review time — the classic "desirable
difficulty" effect — so schedules that space reviews earn more stability per
review than massed (fixed short-interval) schedules. That is exactly why a
good spaced scheduler can hold R above a threshold with fewer reviews.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

# Map retrievability → SM-2 quality (deterministic; keeps sims reproducible).
# Boundaries chosen so a review near the target threshold (~0.85) scores 4,
# a deeply overdue card scores ≤2 (failure), and a fresh card scores 5.
_R_TO_Q = (
    (0.95, 5),
    (0.85, 4),
    (0.70, 3),
    (0.50, 2),
    (0.30, 1),
    (0.00, 0),
)


def retrievability(stability: float, days_elapsed: float) -> float:
    """R(t) = exp(−t / S). Clamped away from S≤0 for numerical safety."""
    if stability <= 0:
        return 0.0
    return float(math.exp(-days_elapsed / stability))


def quality_from_retrievability(r: float) -> int:
    """Deterministic R→q mapping used when the scheduler asks for a rating."""
    for threshold, q in _R_TO_Q:
        if r >= threshold:
            return q
    return 0


@dataclass
class MemoryCard:
    """One simulated item."""

    card_id: int
    stability: float
    last_review_day: int = 0
    review_count: int = 0

    def retrievability_on(self, day: int) -> float:
        return retrievability(self.stability, day - self.last_review_day)


@dataclass
class MemoryModel:
    """Population of cards + update rules after a review."""

    cards: List[MemoryCard] = field(default_factory=list)
    success_gain: float = 1.8  # base multiplicative growth on pass
    fail_factor: float = 0.6  # multiplicative shrink on fail
    min_stability: float = 0.8
    max_stability: float = 365.0
    _by_id: Dict[int, MemoryCard] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._reindex()

    def _reindex(self) -> None:
        self._by_id = {c.card_id: c for c in self.cards}

    def get(self, card_id: int) -> MemoryCard:
        """Look up a card by its id.

        Previously this was ``self.cards[card_id]`` -- a positional index
        masquerading as an id lookup. It happened to work only because
        make_population assigns ids 0..n-1 in order; any other population
        would have silently updated the wrong card.
        """
        if card_id not in self._by_id:
            self._reindex()
        try:
            return self._by_id[card_id]
        except KeyError:
            raise KeyError(f"unknown card_id {card_id}") from None

    def apply_review(self, card_id: int, day: int, quality: int) -> float:
        """Update stability from a review; returns R at the moment of review."""
        card = self.get(card_id)
        r = card.retrievability_on(day)
        if quality >= 3:
            # Base reinforcement even at R≈1 (otherwise the first review after
            # encoding grants zero growth and SM-2's I(2)=6d gap guarantees a
            # failure spiral). Desirable-difficulty bonus on top rewards spacing.
            difficulty = 0.30 + 0.70 * (1.0 - r)
            quality_scale = 0.6 + 0.4 * ((quality - 3) / 2.0)  # q3→0.6 … q5→1.0
            growth = 1.0 + self.success_gain * difficulty * quality_scale
            card.stability = min(self.max_stability, card.stability * growth)
        else:
            card.stability = max(self.min_stability, card.stability * self.fail_factor)
        card.last_review_day = day
        card.review_count += 1
        return r


def make_population(
    n_cards: int,
    initial_stability: float = 5.0,
    rng: Optional[np.random.Generator] = None,
    stability_jitter: float = 0.25,
) -> MemoryModel:
    """Create ``n_cards`` with mildly heterogeneous initial stabilities."""
    rng = rng or np.random.default_rng(0)
    cards = []
    for i in range(n_cards):
        jitter = 1.0 + float(rng.uniform(-stability_jitter, stability_jitter))
        cards.append(MemoryCard(card_id=i, stability=initial_stability * jitter))
    return MemoryModel(cards=cards)
