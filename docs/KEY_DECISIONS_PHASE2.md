# Key decisions — Phase 2 (extraction + filtering + model discovery + theme)

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
