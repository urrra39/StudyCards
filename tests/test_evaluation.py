"""Tests for the forgetting-curve model and scheduler comparison."""
from __future__ import annotations

import math

import pytest

from src.evaluation.memory_model import (
    quality_from_retrievability,
    retrievability,
)
from src.evaluation.simulate import compare_schedulers


class TestRetrievability:
    def test_at_time_zero_is_one(self):
        assert retrievability(5.0, 0.0) == pytest.approx(1.0)

    def test_at_stability_is_1_over_e(self):
        assert retrievability(10.0, 10.0) == pytest.approx(1.0 / math.e)

    def test_monotonic_decay(self):
        assert retrievability(5.0, 1.0) > retrievability(5.0, 5.0) > retrievability(5.0, 20.0)


class TestQualityMapping:
    def test_boundaries(self):
        assert quality_from_retrievability(0.99) == 5
        assert quality_from_retrievability(0.90) == 4
        assert quality_from_retrievability(0.75) == 3
        assert quality_from_retrievability(0.55) == 2
        assert quality_from_retrievability(0.10) == 0


class TestCompareSchedulers:
    def test_sm2_uses_fewer_reviews_than_fixed(self):
        results = compare_schedulers(
            n_cards=20, horizon_days=90, threshold=0.85, fixed_interval_days=3, seed=0
        )
        assert results["sm2"].total_reviews < results["fixed"].total_reviews

    def test_sm2_efficiency_beats_fixed(self):
        # Coverage-per-review is the portfolio-grade claim.
        results = compare_schedulers(
            n_cards=30, horizon_days=120, threshold=0.85, fixed_interval_days=3, seed=1
        )
        sm2 = results["sm2"]
        fixed = results["fixed"]
        sm2_eff = sm2.fraction_days_above_threshold / sm2.reviews_per_card
        fixed_eff = fixed.fraction_days_above_threshold / fixed.reviews_per_card
        assert sm2_eff > fixed_eff

    def test_results_are_deterministic_given_seed(self):
        a = compare_schedulers(n_cards=10, horizon_days=60, seed=99)
        b = compare_schedulers(n_cards=10, horizon_days=60, seed=99)
        assert a["sm2"].total_reviews == b["sm2"].total_reviews
        assert a["sm2"].mean_retrievability == pytest.approx(b["sm2"].mean_retrievability)
