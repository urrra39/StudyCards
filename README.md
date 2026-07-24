# StudyCards

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-0A1F1C?logo=python&logoColor=D4AF37)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-C5A059)](LICENSE)
[![SM-2](https://img.shields.io/badge/scheduler-SM--2%20exact-D4AF37)](src/scheduler/sm2.py)
[![Tests](https://img.shields.io/badge/tests-216%20passing-162825)](tests/)

**Document → concept-level flashcards → SM-2 spaced repetition**, with a
measured evaluation against a fixed-interval baseline and an old-money
Streamlit atelier for live review.

Upload a PDF or text file. An LLM extracts non-redundant, concept-level Q&A
cards. Reviews are scheduled with a faithful implementation of SuperMemo
SM-2 (ease factor, intervals, quality 0–5). Every rating is persisted with
an explanation of *why* the next interval was chosen.

## Highlights

- **Exact SM-2** — `I(1)=1`, `I(2)=6`, `I(n)=ceil(I(n-1)·EF)`, EF update with
  1.3 floor; hand-computed unit tests pin every formula
- **Extraction pipeline** — paragraph-aware chunking, Anthropic or OpenAI,
  Jaccard dedup + quality filters (no LangChain)
- **Dynamic model discovery** — live model lists from your API key, with
  the full curated 2026 catalog (Claude Sonnet 5, Opus 5, Fable 5, Opus 4.8,
  Opus 4.7, Sonnet 4.6; GPT-5.6 Sol / Terra / Luna, GPT-5.5, 5.5 Pro, 5.4,
  5.4 Pro / mini / nano) and an explicit warning if a pinned model has been
  retired by the provider
- **Old-money interface** — Playfair Display and Cormorant Garamond over deep
  emerald, brass hairline rules, a gilded double-framed review card and a
  monogram masthead; full local serif fallbacks, restyled focus rings,
  `prefers-reduced-motion` support and print styles
- **Evaluation** — synthetic forgetting curves; SM-2 uses **74.8% fewer
  reviews** than a 3-day fixed baseline while holding higher mean
  retrievability ([full numbers](docs/EVALUATION_RESULTS.md))
- **Explainability** — every review stores a human-readable rationale
  (e.g. *ease factor 2.30 × last interval 6d → ceil = 14 days*)

## Architecture

```text
┌─────────────┐   chunk    ┌──────────────┐  CompletionFn  ┌─────────────┐
│  PDF / text │ ─────────► │  Ingestion   │ ──────────────►│  Extraction │
│  upload     │            │  + chunker   │                │  + filter   │
└─────────────┘            └──────────────┘                └──────┬──────┘
                                                                  │ Flashcard[]
                                                                  ▼
┌─────────────┐   rate 0-5 ┌──────────────┐   dual-write   ┌─────────────┐
│  Streamlit  │ ◄────────► │  SM-2        │ ──────────────►│  SQLite     │
│  atelier    │  explain   │  scheduler   │                │  cards +    │
└─────────────┘            └──────────────┘                │  history    │
                                                           └─────────────┘
        ▲
        │  compare
┌───────┴───────┐
│  Evaluation   │  R(t)=exp(-t/S)  ·  SM-2 vs fixed-interval
└───────────────┘
```

| Package | Role |
|---------|------|
| `src/ingestion` | PDF/text load, normalize, overlap chunking |
| `src/extraction` | Prompted LLM cards, dedup, providers, model discovery |
| `src/scheduler` | Exact SM-2 + explainability strings |
| `src/data` | SQLite schema + `CardRepository` |
| `src/evaluation` | Forgetting-curve simulation |
| `src/app` | Old-money Streamlit UI |

Design rationale for every non-obvious choice: **[docs/DECISIONS.md](docs/DECISIONS.md)**.

## Quick start

```bash
git clone https://github.com/urrra39/StudyCards.git
cd StudyCards
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY and/or OPENAI_API_KEY
```

### Run the demo

```bash
streamlit run src/app/streamlit_app.py
```

### Run tests

```bash
python -m pytest tests/ -q
```

### Reproduce the evaluation

```bash
python -m src.evaluation.run_eval
```

Results are written to [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md).

## Evaluation snapshot

| Metric | SM-2 | Fixed 3-day |
|--------|-----:|------------:|
| Total reviews (50 cards × 180 days) | **755** | 3000 |
| Mean daily retrievability | **0.88** | 0.48 |
| Fraction of card-days with R ≥ 0.85 | **0.69** | 0.38 |

SM-2 wins on review count *and* sustained recall under the synthetic
forgetting model. Details and methodology: [docs/EVALUATION_RESULTS.md](docs/EVALUATION_RESULTS.md).

## SM-2 formulas (implemented exactly)

```
I(1) = 1
I(2) = 6
I(n) = ceil(I(n-1) * EF)          for n > 2
EF'  = EF + (0.1 - (5-q)*(0.08 + (5-q)*0.02))
EF'  = max(EF', 1.3)
```

On quality &lt; 3 the repetition streak resets to `I(1)` while the updated EF
is kept (not snapped back to 2.5).

## Project layout

```
src/
  ingestion/    loader + chunker
  extraction/   LLM pipeline, filtering, providers, model discovery
  scheduler/    SM-2
  data/         SQLite persistence
  evaluation/   simulation + CLI
  app/          Streamlit demo + old-money theme
tests/          unit + integration + headless boot
docs/           DECISIONS.md, EVALUATION_RESULTS.md
```

## Roadmap

- **Phase 8 (later):** FSRS as a comparison scheduler against SM-2

## License

MIT © 2026 [urrra39](https://github.com/urrra39)
