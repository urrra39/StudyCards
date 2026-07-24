"""SM-2 spaced-repetition scheduler — faithful to Wozniak's original formulas.

Reference: https://www.super-memory.com/english/ol/sm2.htm (Algorithm SM-2)

Formulas implemented exactly:
    I(1) = 1
    I(2) = 6
    I(n) = ceil(I(n-1) * EF)   for n > 2   # "round it up to the nearest integer"
    EF'  = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    EF'  = max(EF', 1.3)

On q < 3 the repetition sequence restarts at I(1) while the (updated) EF is
kept — "without changing the E-Factor" means we do *not* reset EF to 2.5;
EF still receives its usual per-review update from q.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3
QUALITY_MIN = 0
QUALITY_MAX = 5


@dataclass(frozen=True)
class CardState:
    """Scheduling state for one card (pure data — persistence is Phase 4)."""

    ease_factor: float = DEFAULT_EASE_FACTOR
    repetitions: int = 0  # successful reviews in the current streak (n in I(n))
    interval_days: int = 0  # days until next review; 0 = never reviewed / due now
    due_date: Optional[date] = None


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of applying one quality rating to a card."""

    state: CardState
    quality: int
    previous_ease_factor: float
    previous_interval_days: int
    previous_repetitions: int
    explanation: str


def ease_factor_delta(quality: int) -> float:
    """EF adjustment term: ``0.1 - (5-q)*(0.08 + (5-q)*0.02)``."""
    if not QUALITY_MIN <= quality <= QUALITY_MAX:
        raise ValueError(f"quality must be in [{QUALITY_MIN}, {QUALITY_MAX}], got {quality}")
    q_diff = 5 - quality
    return 0.1 - q_diff * (0.08 + q_diff * 0.02)


def update_ease_factor(ease_factor: float, quality: int) -> float:
    """Apply the SM-2 EF update and enforce the 1.3 floor."""
    updated = ease_factor + ease_factor_delta(quality)
    return max(updated, MIN_EASE_FACTOR)


def next_interval(repetitions_before: int, previous_interval: int, ease_factor: float) -> int:
    """Compute I(n) using the EF *before* this review's EF update.

    ``repetitions_before`` is the streak count entering this review. A passing
    review (q >= 3) advances to repetitions_before+1, whose interval is:
        0 → I(1) = 1
        1 → I(2) = 6
        ≥2 → ceil(previous_interval * EF)
    """
    if repetitions_before == 0:
        return 1
    if repetitions_before == 1:
        return 6
    # Original wording: "If interval is a fraction, round it up".
    return max(1, math.ceil(previous_interval * ease_factor))


def explain_review(
    *,
    quality: int,
    previous_ef: float,
    new_ef: float,
    previous_interval: int,
    new_interval: int,
    previous_repetitions: int,
    new_repetitions: int,
    failed: bool,
) -> str:
    """Human-readable rationale for the chosen next interval (explainability)."""
    if failed:
        return (
            f"rating {quality}/5 (failed recall) → repetition streak reset; "
            f"ease factor {previous_ef:.2f} → {new_ef:.2f}; "
            f"next review in {new_interval} day{'s' if new_interval != 1 else ''}"
        )
    if previous_repetitions == 0:
        reason = "first successful review → I(1) = 1 day"
    elif previous_repetitions == 1:
        reason = "second successful review → I(2) = 6 days"
    else:
        reason = (
            f"ease factor {previous_ef:.2f} × last interval {previous_interval}d "
            f"→ ceil = {new_interval} days"
        )
    return (
        f"rating {quality}/5 → {reason}; "
        f"ease factor {previous_ef:.2f} → {new_ef:.2f} "
        f"(streak {previous_repetitions} → {new_repetitions})"
    )


def review(
    state: CardState,
    quality: int,
    review_date: Optional[date] = None,
) -> ReviewResult:
    """Apply one SM-2 review and return the updated state plus explanation.

    Args:
        state: Current scheduling state.
        quality: Recall quality on the 0–5 SuperMemo scale.
        review_date: Calendar date of this review (defaults to today). Used only
            to compute ``due_date = review_date + interval``; the algorithm
            itself is day-count based.
    """
    if not QUALITY_MIN <= quality <= QUALITY_MAX:
        raise ValueError(f"quality must be in [{QUALITY_MIN}, {QUALITY_MAX}], got {quality}")

    when = review_date or date.today()
    prev_ef = state.ease_factor
    prev_interval = state.interval_days
    prev_reps = state.repetitions

    # EF always updates from q; the failure path keeps that updated EF
    # (does not snap back to 2.5) — matching Wozniak's "without changing
    # the E-Factor" as "don't reset EF", not "don't update EF".
    new_ef = update_ease_factor(prev_ef, quality)

    failed = quality < 3
    if failed:
        new_reps = 0
        new_interval = 1
    else:
        new_interval = next_interval(prev_reps, prev_interval, prev_ef)
        new_reps = prev_reps + 1

    new_state = CardState(
        ease_factor=new_ef,
        repetitions=new_reps,
        interval_days=new_interval,
        due_date=when + timedelta(days=new_interval),
    )
    explanation = explain_review(
        quality=quality,
        previous_ef=prev_ef,
        new_ef=new_ef,
        previous_interval=prev_interval,
        new_interval=new_interval,
        previous_repetitions=prev_reps,
        new_repetitions=new_reps,
        failed=failed,
    )
    return ReviewResult(
        state=new_state,
        quality=quality,
        previous_ease_factor=prev_ef,
        previous_interval_days=prev_interval,
        previous_repetitions=prev_reps,
        explanation=explanation,
    )


def new_card(review_date: Optional[date] = None) -> CardState:
    """Fresh card: EF 2.5, due immediately (interval 0, due = today)."""
    when = review_date or date.today()
    return CardState(due_date=when)
