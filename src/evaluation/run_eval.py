"""CLI entrypoint: run the evaluation and write numeric results to docs/."""
from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.simulate import compare_schedulers

ROOT = Path(__file__).resolve().parents[2]
OUT_MD = ROOT / "docs" / "EVALUATION_RESULTS.md"
OUT_JSON = ROOT / "docs" / "evaluation_results.json"

# Default scenario — chosen so both schedulers face the same memory model
# and the comparison is meaningful (see KEY_DECISIONS_PHASE5.md).
DEFAULTS = dict(
    n_cards=50,
    horizon_days=180,
    threshold=0.85,
    fixed_interval_days=3,
    seed=42,
)


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide, returning ``default`` when the denominator is zero.

    A degenerate scenario (``n_cards=0``, ``horizon_days=0``, or a baseline
    that never schedules a review) previously crashed the whole report with
    ZeroDivisionError instead of rendering zeros.
    """
    if not denominator:
        return default
    return numerator / denominator


def render_markdown(results: dict, params: dict) -> str:
    sm2 = results["sm2"]
    fixed = results["fixed"]
    review_reduction = 1.0 - _safe_ratio(sm2.total_reviews, fixed.total_reviews, 1.0)
    sm2_eff = _safe_ratio(sm2.fraction_days_above_threshold, sm2.reviews_per_card)
    fixed_eff = _safe_ratio(fixed.fraction_days_above_threshold, fixed.reviews_per_card)

    def win(a: float, b: float) -> str:
        return "SM-2" if a >= b else "Fixed"

    return f"""# Evaluation Results — SM-2 vs Fixed-Interval Baseline

Synthetic forgetting-curve simulation (exponential retrievability
`R(t) = exp(-t / S)` with desirable-difficulty stability updates).

## Setup

| Parameter | Value |
|-----------|------:|
| Cards | {params['n_cards']} |
| Horizon | {params['horizon_days']} days |
| Target threshold | R >= {params['threshold']} |
| Fixed-interval baseline | every {params['fixed_interval_days']} days |
| RNG seed | {params['seed']} |

## Numeric comparison

| Metric | SM-2 | Fixed-{params['fixed_interval_days']}d | Winner |
|--------|-----:|----------------------------------------:|:------:|
| Total reviews | {sm2.total_reviews} | {fixed.total_reviews} | SM-2 (-{review_reduction:.1%}) |
| Reviews / card | {sm2.reviews_per_card:.1f} | {fixed.reviews_per_card:.1f} | SM-2 |
| Mean daily R | {sm2.mean_retrievability:.4f} | {fixed.mean_retrievability:.4f} | {win(sm2.mean_retrievability, fixed.mean_retrievability)} |
| Median daily R | {sm2.median_retrievability:.4f} | {fixed.median_retrievability:.4f} | {win(sm2.median_retrievability, fixed.median_retrievability)} |
| Fraction of card-days with R >= {params['threshold']} | {sm2.fraction_days_above_threshold:.4f} | {fixed.fraction_days_above_threshold:.4f} | {win(sm2.fraction_days_above_threshold, fixed.fraction_days_above_threshold)} |
| Mean R at review time | {sm2.mean_r_at_review:.4f} | {fixed.mean_r_at_review:.4f} | (informational) |
| Threshold coverage per review | {sm2_eff:.4f} | {fixed_eff:.4f} | {win(sm2_eff, fixed_eff)} |

## Verdict

SM-2 used **{sm2.total_reviews}** reviews vs **{fixed.total_reviews}** for the
fixed-interval baseline (**{review_reduction:.1%} fewer**), while keeping
mean daily retrievability at **{sm2.mean_retrievability:.4f}**
(baseline **{fixed.mean_retrievability:.4f}**) and the fraction of card-days
above the R>={params['threshold']} threshold at
**{sm2.fraction_days_above_threshold:.4f}**
(baseline **{fixed.fraction_days_above_threshold:.4f}**).

Threshold coverage earned per review favors SM-2
({sm2_eff:.4f} vs {fixed_eff:.4f}), which is the efficiency claim the
evaluation was designed to test.

## Reproduce

```bash
python -m src.evaluation.run_eval
```
"""


def main() -> None:
    params = dict(DEFAULTS)
    results = compare_schedulers(**params)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(results, params), encoding="utf-8")
    payload = {
        "params": params,
        "results": {k: v.as_dict() for k, v in results.items()},
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Avoid Windows cp1252 console issues: print a short ASCII summary.
    sm2, fixed = results["sm2"], results["fixed"]
    print(
        f"SM-2 reviews={sm2.total_reviews} mean_R={sm2.mean_retrievability:.4f} "
        f"frac_above={sm2.fraction_days_above_threshold:.4f}"
    )
    print(
        f"Fixed reviews={fixed.total_reviews} mean_R={fixed.mean_retrievability:.4f} "
        f"frac_above={fixed.fraction_days_above_threshold:.4f}"
    )
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
