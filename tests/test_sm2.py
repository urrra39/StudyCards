"""Hand-computed SM-2 unit tests — same rigor as AdaptivPrep BKT pins.

Every numeric expectation below was derived from the original SuperMemo
formulas by hand (shown in comments) before being coded. If a test fails,
the implementation drifted — do not "fix" the expected value.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.scheduler.sm2 import (
    DEFAULT_EASE_FACTOR,
    MIN_EASE_FACTOR,
    CardState,
    ease_factor_delta,
    new_card,
    next_interval,
    review,
    update_ease_factor,
)


# ---------------------------------------------------------------------------
# Hand-derived EF deltas:  Δ = 0.1 − (5−q)·(0.08 + (5−q)·0.02)
# ---------------------------------------------------------------------------
# q=5: 0.1 − 0                    =  0.10
# q=4: 0.1 − 1·(0.08+0.02)        =  0.00
# q=3: 0.1 − 2·(0.08+0.04)        = −0.14
# q=2: 0.1 − 3·(0.08+0.06)        = −0.32
# q=1: 0.1 − 4·(0.08+0.08)        = −0.54
# q=0: 0.1 − 5·(0.08+0.10)        = −0.80
HAND_DELTAS = {5: 0.10, 4: 0.00, 3: -0.14, 2: -0.32, 1: -0.54, 0: -0.80}


class TestEaseFactorDelta:
    @pytest.mark.parametrize("quality,expected", list(HAND_DELTAS.items()))
    def test_delta_matches_hand_computation(self, quality, expected):
        assert ease_factor_delta(quality) == pytest.approx(expected)

    def test_rejects_out_of_range_quality(self):
        with pytest.raises(ValueError):
            ease_factor_delta(-1)
        with pytest.raises(ValueError):
            ease_factor_delta(6)


class TestEaseFactorUpdate:
    def test_perfect_recall_from_default(self):
        # 2.5 + 0.10 = 2.60
        assert update_ease_factor(2.5, 5) == pytest.approx(2.6)

    def test_quality_4_is_neutral(self):
        # Δ(4) = 0 → EF unchanged
        assert update_ease_factor(2.5, 4) == pytest.approx(2.5)
        assert update_ease_factor(2.3, 4) == pytest.approx(2.3)

    def test_quality_3_decreases(self):
        # 2.5 + (−0.14) = 2.36
        assert update_ease_factor(2.5, 3) == pytest.approx(2.36)

    def test_floor_at_1_3(self):
        # 1.3 + (−0.80) = 0.5 → clamped to 1.3
        assert update_ease_factor(1.3, 0) == pytest.approx(MIN_EASE_FACTOR)

    def test_near_floor_partial_drop(self):
        # 1.4 + (−0.14) = 1.26 → clamped to 1.3
        assert update_ease_factor(1.4, 3) == pytest.approx(MIN_EASE_FACTOR)

    def test_ef_may_rise_above_initial_2_5(self):
        # Original algorithm has no upper cap — only the 1.3 floor.
        assert update_ease_factor(2.5, 5) == pytest.approx(2.6)


class TestNextInterval:
    def test_i1_is_one_day(self):
        assert next_interval(0, previous_interval=0, ease_factor=2.5) == 1

    def test_i2_is_six_days(self):
        assert next_interval(1, previous_interval=1, ease_factor=2.5) == 6

    def test_i3_uses_ceil_of_product(self):
        # ceil(6 × 2.5) = ceil(15.0) = 15
        assert next_interval(2, previous_interval=6, ease_factor=2.5) == 15

    def test_fractional_interval_rounds_up(self):
        # Original: "If interval is a fraction, round it up to the nearest integer."
        # ceil(6 × 2.6) = ceil(15.6) = 16  (NOT banker's round → 16, and NOT trunc → 15)
        assert next_interval(2, previous_interval=6, ease_factor=2.6) == 16

    def test_another_ceil_case(self):
        # ceil(16 × 2.7) = ceil(43.2) = 44
        assert next_interval(3, previous_interval=16, ease_factor=2.7) == 44

    def test_low_ef_still_grows(self):
        # ceil(10 × 1.3) = ceil(13.0) = 13
        assert next_interval(5, previous_interval=10, ease_factor=1.3) == 13


class TestReviewSequence:
    """End-to-end streak with hand-traced state after every rating."""

    def test_opening_sequence_5_4_5(self):
        # Start: EF=2.5, reps=0, interval=0
        state = new_card(review_date=date(2026, 1, 1))
        assert state.ease_factor == DEFAULT_EASE_FACTOR
        assert state.repetitions == 0

        # Review 1, q=5:
        #   interval = I(1) = 1; reps = 1
        #   EF = 2.5 + 0.10 = 2.60
        r1 = review(state, 5, review_date=date(2026, 1, 1))
        assert r1.state.interval_days == 1
        assert r1.state.repetitions == 1
        assert r1.state.ease_factor == pytest.approx(2.6)
        assert r1.state.due_date == date(2026, 1, 2)
        assert "I(1)" in r1.explanation or "1 day" in r1.explanation

        # Review 2, q=4:
        #   interval = I(2) = 6; reps = 2
        #   EF = 2.6 + 0.00 = 2.60
        r2 = review(r1.state, 4, review_date=date(2026, 1, 2))
        assert r2.state.interval_days == 6
        assert r2.state.repetitions == 2
        assert r2.state.ease_factor == pytest.approx(2.6)
        assert r2.state.due_date == date(2026, 1, 8)

        # Review 3, q=5:
        #   interval = ceil(6 × 2.6) = 16; reps = 3
        #   EF = 2.6 + 0.10 = 2.70
        r3 = review(r2.state, 5, review_date=date(2026, 1, 8))
        assert r3.state.interval_days == 16
        assert r3.state.repetitions == 3
        assert r3.state.ease_factor == pytest.approx(2.7)
        assert r3.state.due_date == date(2026, 1, 8) + timedelta(days=16)
        assert "2.60" in r3.explanation or "2.6" in r3.explanation

    def test_failure_resets_streak_keeps_updated_ef(self):
        # Build to reps=2, EF=2.6, interval=6 (via q=5 then q=4).
        state = new_card(review_date=date(2026, 3, 1))
        state = review(state, 5, review_date=date(2026, 3, 1)).state
        state = review(state, 4, review_date=date(2026, 3, 2)).state
        assert state.repetitions == 2
        assert state.interval_days == 6
        assert state.ease_factor == pytest.approx(2.6)

        # q=0 failure:
        #   EF = 2.6 + (−0.80) = 1.80  (updated, not snapped to 2.5)
        #   reps = 0, interval = 1
        r = review(state, 0, review_date=date(2026, 3, 8))
        assert r.state.repetitions == 0
        assert r.state.interval_days == 1
        assert r.state.ease_factor == pytest.approx(1.8)
        assert "failed" in r.explanation.lower() or "reset" in r.explanation.lower()

    def test_failure_then_recovery_restarts_at_i1(self):
        state = CardState(ease_factor=2.0, repetitions=4, interval_days=30)
        state = review(state, 1, review_date=date(2026, 4, 1)).state
        assert state.repetitions == 0
        assert state.interval_days == 1

        # Next success must be I(1)=1 again, not I(5).
        r = review(state, 5, review_date=date(2026, 4, 2))
        assert r.state.repetitions == 1
        assert r.state.interval_days == 1

    def test_quality_2_is_failure_quality_3_is_pass(self):
        base = CardState(ease_factor=2.5, repetitions=0, interval_days=0)
        fail = review(base, 2, review_date=date(2026, 5, 1))
        assert fail.state.repetitions == 0
        assert fail.state.interval_days == 1

        passed = review(base, 3, review_date=date(2026, 5, 1))
        assert passed.state.repetitions == 1
        assert passed.state.interval_days == 1
        # 2.5 − 0.14 = 2.36
        assert passed.state.ease_factor == pytest.approx(2.36)

    def test_interval_uses_ef_before_update(self):
        # EF enters at 2.3; q=5 would raise EF to 2.4, but I(n) must use 2.3.
        # ceil(10 × 2.3) = ceil(23.0) = 23  (not ceil(10 × 2.4) = 24)
        state = CardState(ease_factor=2.3, repetitions=3, interval_days=10)
        r = review(state, 5, review_date=date(2026, 6, 1))
        assert r.state.interval_days == 23
        assert r.state.ease_factor == pytest.approx(2.4)

    def test_explainability_mentions_rating_ef_and_interval(self):
        # Spec example shape: "ease factor 2.3, last rating 4/5 → next review in …"
        state = CardState(ease_factor=2.3, repetitions=2, interval_days=6)
        r = review(state, 4, review_date=date(2026, 7, 1))
        # ceil(6 × 2.3) = ceil(13.8) = 14; EF unchanged at 2.3 (Δq4=0)
        assert r.state.interval_days == 14
        assert r.state.ease_factor == pytest.approx(2.3)
        assert "4/5" in r.explanation
        assert "2.30" in r.explanation or "2.3" in r.explanation
        assert "14" in r.explanation

    def test_rejects_invalid_quality(self):
        with pytest.raises(ValueError):
            review(new_card(), 7)
