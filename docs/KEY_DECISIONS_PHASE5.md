# Key decisions — Phase 5 (evaluation)

## Why exponential retrievability `R = exp(−t / S)`
It is the standard closed-form forgetting curve used in the spaced-repetition
literature (and the conceptual ancestor of FSRS stability). One parameter
(S) is enough to make scheduling differences visible, and it is analytically
checkable (`R(S)=1/e`) in unit tests.

## Why desirable-difficulty growth on success (with a base term)
`S ← S · (1 + gain · (0.30 + 0.70·(1−R)) · quality_scale)`. The 0.30 floor
matters: without it, a review at R≈1 (the first review after encoding)
grants *zero* growth, SM-2's subsequent I(2)=6d gap guarantees a failure,
and the scheduler collapses into a daily reset spiral. The (1−R) term on
top still rewards spacing — that is what beats massed fixed intervals.

## Why deterministic R→q mapping (not Bernoulli sampling)
Reproducibility for CI and for the committed `docs/EVALUATION_RESULTS.md`.
A stochastic recall model is easy to add later; it must not be required to
demonstrate the scheduling claim.

## Why the headline metric is "threshold coverage per review"
Raw mean R favors over-reviewing. Raw review count favors under-reviewing.
Coverage-per-review = (fraction of card-days with R≥threshold) / (reviews
per card) captures the portfolio claim: SM-2 keeps memory above a target
with fewer reviews than a naive fixed interval.

## Why fixed-interval = 3 days
Short enough to be a credible "I review everything every few days" student
baseline, long enough that the review-count gap vs SM-2 is dramatic over a
180-day horizon. The comparison is not sensitive to 2 vs 4 in direction.
