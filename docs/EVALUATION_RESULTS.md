# Evaluation Results — SM-2 vs Fixed-Interval Baseline

Synthetic forgetting-curve simulation (exponential retrievability
`R(t) = exp(-t / S)` with desirable-difficulty stability updates).

## Setup

| Parameter | Value |
|-----------|------:|
| Cards | 50 |
| Horizon | 180 days |
| Target threshold | R >= 0.85 |
| Fixed-interval baseline | every 3 days |
| RNG seed | 42 |

## Numeric comparison

| Metric | SM-2 | Fixed-3d | Winner |
|--------|-----:|----------------------------------------:|:------:|
| Total reviews | 755 | 3000 | SM-2 (-74.8%) |
| Reviews / card | 15.1 | 60.0 | SM-2 |
| Mean daily R | 0.8821 | 0.4765 | SM-2 |
| Median daily R | 0.8992 | 0.2865 | SM-2 |
| Fraction of card-days with R >= 0.85 | 0.6930 | 0.3802 | SM-2 |
| Mean R at review time | 0.8371 | 0.4124 | (informational) |
| Threshold coverage per review | 0.0459 | 0.0063 | SM-2 |

## Verdict

SM-2 used **755** reviews vs **3000** for the
fixed-interval baseline (**74.8% fewer**), while keeping
mean daily retrievability at **0.8821**
(baseline **0.4765**) and the fraction of card-days
above the R>=0.85 threshold at
**0.6930**
(baseline **0.3802**).

Threshold coverage earned per review favors SM-2
(0.0459 vs 0.0063), which is the efficiency claim the
evaluation was designed to test.

## Reproduce

```bash
python -m src.evaluation.run_eval
```
