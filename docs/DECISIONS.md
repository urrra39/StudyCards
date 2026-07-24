# StudyCards — Design Decisions

Compiled rationale from every implementation phase. Per-phase source files
remain in this folder as `KEY_DECISIONS_PHASE*.md`.

---

# Phase 0 — Scaffolding

## Why Python 3.9-compatible pins
The development machine only has Python 3.9.13. That forces upper bounds —
notably `streamlit<1.45` (newer drops 3.9) and `numpy<2.1` — and
`Optional[X]` / `List[X]` typing rather than `|` unions at runtime.

## Why `.gitattributes` forces LF
The repo stores LF regardless of Windows checkout so Streamlit Cloud / CI
and local checkouts behave identically.

## Why both `data/` and `src/data/`
`data/` holds runtime SQLite files (gitignored). `src/data/` is the
persistence package. Awkward but unambiguous: one is never imported.

---

# Phase 1 — Ingestion + chunking

## Why pypdf, not pdfplumber
We only need running prose, not table geometry. pypdf is pure-Python (no
native deps), which keeps the Streamlit Cloud install small and reliable.
Page boundaries are preserved as `\n\n` so the chunker can treat them as
preferred split points.

## Why character budgets instead of tokens
A tokenizer dependency buys little: the budget only controls granularity.
~4 chars/token makes 4 000 chars ≈ 1 000 tokens — comfortably inside any
chat model's context, and the extraction stage is what actually spends
tokens.

## Why paragraph-first packing with hard-split fallback
Mid-sentence splits produce fragment cards the LLM hallucinates answers for.
We only fall back to a character cut (preferring the last sentence end inside
the budget) for pathological paragraphs longer than a whole chunk — common
in poorly-extracted PDFs that lost all line breaks.

## Why overlap is best-effort, not a hard contract
If carry+next-paragraph would breach `max_chars`, we drop the carry rather
than violate the budget. Dedup later makes missing one overlap region cheap;
oversized chunks are expensive (worse extraction focus + higher API cost).

## Why normalization de-hyphenates across newlines
Justified academic PDFs split words as `infor-\nmation`. Leaving those intact
poisons LLM extraction (the model sees a broken token). Real hyphens
(`state-of-the-art`) have no following newline and are preserved.

---

# Phase 2 — Extraction, filtering, model discovery, theme

## Why a `CompletionFn` (str → str) instead of importing SDKs in the pipeline
Keeps the pipeline provider-agnostic and fully unit-testable with stubs.
Anthropic and OpenAI adapters live in `providers.py` and are the only modules
that import vendor SDKs (deferred to `__init__` so tests never need them).

## Why the extraction prompt bans trivia, deixis, and multi-concept cards
Trivia (dates, author names) is memorable without being useful. Deixis
("according to the text") makes cards unusable weeks later without the
document. Multi-concept questions have no clean SM-2 rating ("half right").
These constraints are asserted in unit tests so a prompt regression is caught.

## Why parse errors return `[]` instead of failing the document
One bad completion must not cost the user the other N chunks. The parser
still raises `ExtractionParseError` for callers that want to retry; the
per-chunk wrapper swallows it.

## Why Jaccard-on-content-tokens at threshold 0.6 for dedup
The dominant failure mode is the *same wording* re-extracted from an overlap
region — Jaccard catches that with zero extra dependencies and fully
explainable behavior. True paraphrases are rarer and acceptable to keep for
a v1. Threshold 0.6: overlap duplicates share most content words; distinct
concepts from the same passage rarely exceed ~0.4. Stopwords are stripped so
"What is the X" vs "What is a Y" does not inflate similarity.

## Why quality-gate runs *before* dedup
A low-quality near-duplicate that appears first must not shadow (and remove)
a high-quality later card. Quality-first + first-wins-among-survivors gives
stable, predictable behavior.

## Why model discovery always degrades to a curated fallback
Discovery is a UX nicety. Bad key / offline / missing SDK must never crash
the Streamlit app. The UI can caption `source="fallback"` so users know the
list may be stale. OpenAI listings are filtered to chat/reasoning families
and non-chat variants sharing those prefixes (audio, realtime, embeddings)
are excluded. Anthropic listings prepend curated `-latest` aliases so the
default tracks new snapshots automatically.

## Why CSS injection instead of `.streamlit/config.toml`
config.toml cannot set typography, borders, gradients, or component internals —
everything that sells the old-money aesthetic. A single `st.markdown` CSS
block can. Palette: deep emerald `#0A1F1C`, champagne gold `#D4AF37`, cream
`#F9F6F0`, with Playfair / Cormorant Garamond / Georgia serifs.

---

# Phase 3 — SM-2 scheduler

## Why `math.ceil`, not `round`
Wozniak's original SM-2 text says: "If interval is a fraction, round it up
to the nearest integer." Many popular ports silently use banker's `round()`,
which under-schedules (e.g. ceil(13.2)=14 vs round(13.2)=13). We pin ceil
with hand-computed cases so a future "simplify to round()" PR fails the suite.

## Why interval uses EF *before* the update
Schedule the next gap with the EF that described the item *entering* this
review, then revise EF from today's quality for *future* reviews. Using the
post-update EF would let a single perfect recall inflate the gap it just
earned. Test `test_interval_uses_ef_before_update` pins this.

## Why failures still update EF (but do not reset it to 2.5)
"Start repetitions from the beginning without changing the E-Factor" means
do not snap EF back to the default 2.5; the usual EF' formula still runs.
A blackout (q=0) should make the card permanently harder (lower EF), not
merely restart the 1→6→… ladder at the old ease. Streak resets to I(1)=1.

## Why explainability is a structured string on `ReviewResult`
Generating the sentence at review time (from the same inputs the scheduler
used) guarantees the UI cannot drift from the math. Persistence stores it
on every history row.

## Why `CardState` is a frozen dataclass with no DB knowledge
Keeps the algorithm pure and unit-testable with hand values. SQLite mapping
is Phase 4's job.

---

# Phase 4 — SQLite persistence

## Why dual write: `cards` current state + `review_history` immutable log
`cards` answers "what's due today?" via the due_date index. `review_history`
answers "why is this interval what it is?" Every `record_review` updates
both in one transaction so they cannot diverge after a crash.

## Why the repository calls `scheduler.review` rather than re-implementing SM-2
A single source of truth for the formulas. Integration tests that pin
intervals 1→6→16 after ratings 5,4,5 fail if either layer drifts.

## Why ISO-8601 text for dates
SQLite has no real date type. Text `YYYY-MM-DD` sorts correctly for
`due_date <= ?` range scans and round-trips through `date.fromisoformat`.

## Why one connection per operation
Streamlit reruns on every widget click; a long-lived connection in
`st.session_state` is a footgun. Short-lived connections with
`PRAGMA foreign_keys=ON` are cheap and correct under concurrent tabs.

## Why explanations are stored on every history row
Explainability must survive page reloads. Storing the sentence freezes the
UX copy the user actually saw.

---

# Phase 5 — Evaluation

## Why exponential retrievability `R = exp(-t / S)`
Standard closed-form forgetting curve; one parameter; analytically
checkable (`R(S)=1/e`) in unit tests.

## Why desirable-difficulty growth with a base term
`S ← S · (1 + gain · (0.30 + 0.70·(1−R)) · quality_scale)`. The 0.30 floor
matters: without it, a review at R≈1 grants zero growth, SM-2's I(2)=6d gap
guarantees a failure spiral. The (1−R) term still rewards spacing.

## Why deterministic R→q mapping
Reproducibility for CI and for the committed `EVALUATION_RESULTS.md`.

## Why the headline metric is threshold coverage per review
Raw mean R favors over-reviewing; raw review count favors under-reviewing.
Coverage-per-review captures the claim: keep memory above a target with
fewer reviews than a naive fixed interval.

## Why fixed-interval = 3 days
A credible student baseline; the review-count gap vs SM-2 is dramatic over
180 days. Direction is not sensitive to 2 vs 4.

---

# Phase 6 — Streamlit demo

## Why one page, not a multipage app
Upload → extract → review is a single loop. Multipage navigation would break
the "rate and see due date update live" flow.

## Why `CardRepository` is cached in `st.session_state`
Avoids re-running schema init on every click while still opening a fresh
SQLite connection per operation.

## Why model discovery runs on every sidebar render
Keys change as the user types. Discovery is a single HTTP call with hard
fallbacks — fine to repeat. A caption shows live vs fallback.

## Why headless boot is a real HTTP check
Import-only tests miss config/`set_page_config` ordering and port binding
failures. We spawn `streamlit run --server.headless`, wait for HTTP 200,
then terminate.

---

# Phase 8 (deferred) — FSRS comparison
Left for later: add FSRS as a second scheduler in the evaluation harness
and in the UI, without removing the faithful SM-2 implementation.

---

# Phase 7 — Documentation

## Why DECISIONS.md is a compile, not a rewrite
Admissions readers want one URL. Keeping per-phase notes as the source of
truth and concatenating them into `DECISIONS.md` avoids drift between the
"what we decided in the moment" files and the portfolio document.

## Why the README leads with the evaluation table
A flashcard demo is common; a measured SM-2-vs-baseline result with pinned
formulas is not. The numbers are the differentiator for MIT/NUS readers.
