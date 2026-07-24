# Key decisions — Phase 1 (ingestion + chunking)

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
