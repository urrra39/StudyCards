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


---

# Phase 9 - Production hardening audit

A full end-to-end audit of every module, dependency and code path. Each
item below is a real defect that was found, root-caused and fixed, with a
regression test in `tests/test_regressions.py` pinning it shut.

## Security

### Why escaping lives inside `card_html`, not at the call sites
The review UI renders cards with `unsafe_allow_html=True`. Card text is
LLM output derived from an arbitrary uploaded document, so a PDF containing
`<script>` or an attribute breakout (`" onerror=...`) executed in the
user's session - a stored-XSS path from document upload to script
execution. Escaping was placed inside `card_html` rather than at each call
site because a single missed call site reopens the hole; now the unsafe
string can only reach the DOM through one escaped function.

### Why API keys never become cache keys
Model discovery is memoized on a SHA-256 fingerprint of the key rather than
the key itself, so the secret is not retained in a display-facing cache
identifier.

## Correctness

### Why `MemoryModel` keeps an id index
`apply_review(card_id, ...)` indexed `self.cards[card_id]` positionally.
That is only correct when ids happen to be contiguous from zero; with any
other id set it silently updated *the wrong card* and produced quietly
wrong evaluation numbers. A `_by_id` dict plus `get()` makes the lookup
match the parameter's meaning, and an unknown id now raises `KeyError`
instead of returning bad data.

### Why `record_review` builds its result in-transaction
It previously re-read the row after commit and used a bare `assert` to
prove it existed - which both re-queried needlessly and vanishes entirely
under `python -O`. The returned object is now constructed from the values
actually written inside the transaction.

### Why fence stripping is anchored to the whole string
The old `re.MULTILINE` strip removed *any* ``` line, so a card whose answer
legitimately contained a fenced code block was corrupted. The pattern is
now anchored with `\A`/`\Z` so only a wrapper fence is removed.

### Why one bad chunk no longer kills a document
A provider error mid-document aborted the entire extraction and discarded
every card already produced. Chunk-level failures are now caught, logged
with the chunk index, and skipped.

### Why the chunker has a non-advancing-cut guard
A pathological paragraph could produce a cut that consumed no characters,
spinning forever. If a step fails to shrink the remainder, a hard cut is
taken.

## Reliability

### Why extraction is idempotent per upload
Streamlit reruns the script on every interaction and the uploader keeps its
file. Clicking "Extract flashcards" twice inserted the whole deck twice.
Uploads are now fingerprinted (name + SHA-256 of bytes) in session state,
and a repeat requires an explicit confirmation.

### Why timeouts and retries are explicit
Provider clients were constructed with no timeout, so a hung connection
hung the UI indefinitely. Both clients now take `DEFAULT_TIMEOUT_SECONDS`
and `DEFAULT_MAX_RETRIES`.

### Why SQLite uses WAL and a busy timeout
The demo can have a review write and a deck read in flight together;
`journal_mode=WAL` plus a 5s busy timeout removes "database is locked"
failures under concurrent access.

### Why the boot test picks an ephemeral port
A hardcoded 8765 made an unrelated local listener, or a parallel run, look
like a product failure. The port is now reserved from the OS. Both
Streamlit tests also skip rather than fail when Streamlit is absent, so the
suite stays runnable in a minimal environment.

## Performance

### Why model discovery is cached
`discover_models` ran on every rerun - a live provider HTTP request per
click. It is now `@st.cache_data`-wrapped with a 10 minute TTL.

### Why bulk insert is one transaction
`add_cards` looped over single-row inserts, paying an fsync per card. It is
now one transaction; `add_card` delegates to it so there is a single write
path.

### Why the deck view batch-loads history
Rendering the deck issued one "latest review" query per card (N+1).
`latest_reviews()` returns the whole map in a single grouped query.

## Dependencies

### Why pandas, scikit-learn and matplotlib were removed
All three were declared in `requirements.txt` and imported nowhere in
`src/` or `tests/`. They added large install weight and extra vulnerability
surface for zero functionality. Test-only dependencies moved to
`requirements-dev.txt`.

### Why `pyproject.toml` was added
`import src.*` worked only because of a `sys.path` hack in
`tests/conftest.py`. Real packaging metadata plus `pytest.pythonpath` makes
the import work by configuration; the shim is kept as a fallback.


---

# Phase 10 - Model catalog refresh and full old-money interface

## Why the shipped model defaults were a live outage, not a style nit
The curated fallbacks were `claude-3-7-sonnet-latest`, `claude-3-5-sonnet-latest`,
`claude-3-5-haiku-latest` and `claude-3-opus-20240229`. Anthropic retired the
Claude 3 family from the API by mid-2026, and Claude Sonnet 4 / Opus 4 on
June 15, 2026. A fresh clone with no key therefore presented a dropdown in
which *every* option returned an error. Verified against the provider docs on
2026-07-24, the catalog is now:

- Anthropic: `claude-sonnet-5` (default), `claude-opus-5`, `claude-fable-5`,
  `claude-opus-4-8`, `claude-opus-4-7`, `claude-sonnet-4-6`
- OpenAI: `gpt-5.6-terra` (default), `gpt-5.6-sol`, `gpt-5.6-luna`,
  `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.4-mini`,
  `gpt-5.4-nano`

## Why claude-mythos-5 is not in the fallback list
Mythos 5 is released to a limited set of organizations. Putting it in the
list every user sees before entering a key would mostly generate permission
errors and make the dropdown look broken. If a key does have access, live
discovery surfaces it automatically - which is the entire point of querying
the provider instead of shipping a static list.

## Why the mid-tier model is the default rather than the frontier model
Extraction is a chunked, high-volume workload - roughly one call per 4000
characters - so the default optimizes cost per card, not peak reasoning.
Sonnet 5 sits close to Opus 4.8 in quality at Sonnet pricing, and Terra is
OpenAI's explicit intelligence/cost balance point. Users can select up.

## Why retirement is detected rather than discovered as a 404
`is_retired_model()` recognizes withdrawn families, retired snapshots are
filtered out of live listings, and a model pinned through `STUDYCARDS_MODEL`
triggers a sidebar warning. A regression test asserts no shipped default is
ever a retired model, so this class of staleness cannot silently return.

## Why `-latest` alias handling was removed
From the 4.6 generation on, Anthropic model IDs are dateless
(`claude-sonnet-5`), so the old "prepend -latest aliases" branch tracked a
naming convention that no longer exists. Both providers now share one
`_order_by_preference` helper.

## Why the aesthetic is CSS, not `config.toml`
Streamlit's theme config reaches colors only. Typography, engraved borders,
the gilded double frame, the monogram roundel and the ornamental rules all
require real CSS, so the theme stays a single injected stylesheet with the
palette expressed as custom properties.

## Why webfonts are progressive enhancement
Every rule declares a full local serif stack (Georgia, Iowan Old Style,
Palatino) ahead of the Google Fonts import. If that request is blocked for
privacy, is offline, or simply fails, the page still renders in the intended
typographic register instead of falling back to sans-serif.

## Why the ornaments are functions with escaping
`monogram_html`, `rule_html` and `plaque_html` are injected with
`unsafe_allow_html` exactly like `card_html`, so they escape their inputs for
the same reason - one escaped choke point per HTML-producing function.

## Why accessibility constraints were treated as non-negotiable
A dark, low-chroma theme is where contrast and focus bugs hide. Focus rings
are restyled in brass rather than removed, all transitions collapse under
`prefers-reduced-motion`, and a print stylesheet renders cards on white.
Tests assert `outline: none` never appears in the sheet.


---

# Phase 11 - Launchability

## Why the app bootstraps its own repository root
`streamlit run src/app/streamlit_app.py` failed with
`ModuleNotFoundError: No module named 'src'`. The cause is not a bad command:
Streamlit puts the *script's own directory* (`src/app`) on `sys.path` and
never adds the working directory, so the `src` package was genuinely not
importable no matter which folder the user launched from.

Three fixes were possible - require `pip install -e .`, require a
`PYTHONPATH` export, or have the script derive its own root from `__file__`.
The first two push environment setup onto anyone who downloads the project,
and a demo that needs a preparatory export is a demo that will fail in front
of an audience. So the script inserts `Path(__file__).resolve().parents[2]`
into `sys.path` before any `src` import. It works from any directory, on
Windows and POSIX, with or without an install, and `pyproject.toml` still
provides the clean packaging path for anyone who wants it.

The `# noqa: E402` markers on the imports below the bootstrap are
intentional: the imports *must* follow it, so the lint rule is wrong here
rather than the code.

## Why two tests guard it
A regression test executes the real app body with only `src/app` on
`sys.path`, from an unrelated working directory, against a stubbed
`streamlit` - reproducing the exact failure conditions without requiring
Streamlit to be installed. A second test asserts the bootstrap textually
precedes the first top-level `from src.` import, because a correct
`sys.path` insert placed after the imports would be silently useless.

## Phase 12 - Motion design system

The brief was "ultra old-money, best animations for everything". Those two
goals pull in opposite directions: inherited wealth reads as *restraint*, and
most "best animation" showcases read as a demo reel. The resolution was to
build a small, strictly enforced motion vocabulary rather than to decorate each
widget individually.

**Five verbs, no more.** `rise` (content settles up out of a slight blur),
`draw` (hairlines are drawn outward from their centre), `gild` (a slow light
sweep across gold), `turn` (a card tips into view in perspective), and
`breathe` (a long, low pulse on the single primary action). Two supporting
keyframes, `fade` and `seal`, exist for the canvas and the monogram stamp.
Anything that cannot be expressed with those verbs does not get animated.

**Two easing tokens.** `--ease-silk` and `--ease-drape` are both settle curves;
neither overshoots. Bounce and elastic easings are banned, and a test asserts
that the classic `cubic-bezier(0.68, ...)` back-ease never reappears.

**Durations are long.** 600-900ms, where typical UI motion is 150-250ms. Slow
motion is the whole point: nothing here appears to be in a hurry. Interactive
feedback (`:active`) stays at 90ms so the interface never feels laggy to touch.

**The accessibility trap, and why a test guards it.** Every entrance animation
uses `animation-fill-mode: both` and starts at `opacity: 0`. The reflexive
reduced-motion snippet - `animation: none !important` - would therefore leave
the entire application invisible for anyone with the OS setting enabled. The
block instead *substitutes* a 0.001ms `sc-fade`, so motion is removed while
content is guaranteed to paint. `test_reduced_motion_neutralizes_rather_than_disables`
fails if anyone ever "simplifies" this back to `animation: none`. The gradient
`h1` likewise restores `-webkit-text-fill-color` there, since transparent fill
plus a cancelled animation is another invisible-text failure mode.

**Rejected:** scroll-linked reveals (Streamlit re-renders whole subtrees, so
they would re-fire on every interaction and become nauseating), parallax, and
any JavaScript. The theme remains a single CSS string with no runtime cost.

### Phase 12a - The Atelier panel, and one caption removed

The sidebar was still the most restrained surface in the app while being the
one the user looks at longest. It now carries the fullest gold: a leafed,
slowly gilding title, gold labels with a faint glow, and gold-bordered fields
that warm on hover. The gradient title needs the same reduced-motion guard as
the main `h1` - transparent text fill plus a cancelled animation is invisible
text - so the fallback selector was widened to cover it, with a test.

The caption "Showing recommended defaults (key missing or listing
unavailable)" was deleted rather than restyled. It appeared on every cold
start, apologised for a state that is not a failure - the curated fallbacks are
current frontier models - and put a parenthetical error message directly under
the most prominent control. The live-catalog caption stays, because a model
count is genuinely new information. A test asserts the string never returns.

## Phase 13 - One room, and an honest key check

**The sidebar was the wrong colour.** It sat in slate blue against an emerald
canvas, which read as two products bolted together rather than one interior.
The panel is now the darkest green in the palette with a faint gold wash at the
top corner and a gold seam down its edge. `--slate` survives as a token because
it is still the right colour for deep shadows; it is simply no longer a
background.

**The key check exists because the dropdown lies by design.** Model discovery
degrades to curated fallbacks on every failure path, which is correct for the
dropdown - a user should always have something selectable - but it means a
revoked key and a dropped connection look identical: a healthy-looking list of
models either way. `src/extraction/key_check.py` answers what the dropdown
cannot: is the key real, who issued it, and what does it unlock.

The design decision that matters is that **"rejected" and "could not check" are
never collapsed into one answer.** Telling someone their key is fake because
their wifi dropped is an expensive lie - people revoke and regenerate working
keys over it. So the verdict is classified from the provider's error text:
authentication markers (401, 403, `invalid_api_key`, `revoked`,
`authentication_error`) produce THE API KEY IS NOT REAL OR REVOKED, while
anything else - connection refused, SDK missing, provider outage - reports
honestly that the check could not be completed and the key may still be valid.
Two tests pin this in both directions.

Two further verdicts are decided locally, with no network call at all: the
untouched `.env.example` placeholder, and a key whose prefix shows it was
issued by the *other* provider (`sk-ant-` while OpenAI is selected). That last
one is the most common setup mistake, and it deserves a specific instruction
rather than a generic rejection.

**No second network call.** `interpret_listing()` is split out from
`check_api_key()` so the UI derives its verdict from the listing it already
fetched and cached for the dropdown. Verification is therefore free.

## Phase 14 - A button, a token, and a wallet check

**The check is now a button, not a side effect.** Phase 13 verified the key
automatically on every rerun. That was wrong: verification costs a network
round trip, and the balance probe added here costs a real token. Anything that
spends money must be a deliberate act, so the sidebar now carries an explicit
"Check API key" button and nothing fires until it is pressed. The result is
held in session state and shown until the key or provider changes underneath
it.

**Why a one-token probe at all.** Listing models proves a key is authentic but
says nothing about whether the account can pay. A real key with a zero balance
lists models perfectly and then fails every extraction at request time. So the
button sends the smallest request the APIs allow - a one-word prompt capped at
a single output token - purely to read the outcome. It is the cheapest
truthful answer to "will this key actually work".

**Three failure meanings, three different answers.** The probe's error text is
classified into disjoint buckets, because the right user action differs in each
case:
- billing / quota markers (`insufficient_quota`, `credit balance is too low`,
  `402`, ...) -> INSUFFICIENT BALANCE OR BUY CREDITS FROM YOUR OPENAI /
  ANTHROPIC, with the company named from the selected provider and a direct
  link to that provider's billing page. The key is real; the wallet is empty.
- authentication markers (401, 403, `invalid_api_key`, `revoked`, ...) ->
  THE API KEY IS NOT REAL OR REVOKED, unchanged from Phase 13.
- anything else (connection refused, SDK missing, outage) -> an honest "could
  not reach the provider; the key may still be funded". Offline is never
  reported as empty, exactly as a dropped connection is never reported as fake.

Billing and auth are deliberately checked in that order, so a 402/quota error
is never swallowed by a broad auth match. `check_balance` never raises - a
billing probe must not be able to take the app down - and every local guard
(empty, placeholder, wrong-provider prefix) runs first so a bad key never
reaches the paid endpoint.

## Phase 14a - A louder, still-disciplined motion layer

The user asked for stronger animation. Five keyframes were added and, per the
house rule, each is defined once and applied at least twice:
- `sc-sheen` - a resting brass sheen crossing every button on a slow loop, so
  the metal looks polished before it is touched.
- `sc-pulse` - an expanding gold ring around the focused button while a rerun
  is in flight, so a key check reads as working rather than frozen.
- `sc-glow` - a gold luminance swell on success alerts (the funded / valid
  verdict).
- `sc-shake` - a single restrained settle-shake on error alerts (invalid / no
  balance). It plays once; a looping shake would be gaudy.
- `sc-float` - a barely-there hover on displayed review cards at rest.

The discipline from Phase 12 holds: no elastic or bounce easing, every new
keyframe collapses under `prefers-reduced-motion` via the global override, and
print disables all motion. Six new theme tests and three wiring tests pin all
of this; the suite is at 194 passing, 2 Streamlit skips offline.

## Phase 15 - Naming the swap, and a bug it uncovered

**The mismatch message now tells the user what to do, not just what is wrong.**
When someone pastes an Anthropic key while OpenAI is selected - and, crucially,
does not realise it - the old wording ("switch the provider above") assumed they
knew which key they had pasted. The message now names the issuer AND gives the
direct instruction keyed to the selected provider: "This looks like an Anthropic
key, but OpenAI is selected. PUT OPENAI'S API KEY, or switch the provider
above." The reverse case yields "PUT ANTHROPIC'S API KEY". The swap is caught
locally from the key prefix (sk-ant- vs sk-/sk-proj-), so no token is spent and
no network call is made to tell the user they used the wrong key.

**A real bug surfaced while doing this.** The mismatch verdict used to report
`company` as the *issuer* (the wrong provider). But the sidebar discards any
held verdict whose company no longer matches the selected provider - its guard
against showing a stale result after the provider dropdown changes. Together,
those two meant a mismatch verdict was created and then immediately thrown away:
the warning would never actually appear after pressing Check. Fixed by having
the mismatch verdict report the SELECTED provider as its company (the issuer is
named in the message and recorded in `detail`), which is also the more correct
semantics. A regression test pins it: a mismatch's company must equal the
selected provider.

The rest of the deep pass confirmed the surrounding invariants still hold: every
module compiles; balancing runs its local guards (empty / placeholder /
wrong-provider) before spending a token; billing, auth, and transport failures
remain three disjoint verdicts; and no verification path can raise. Suite at 197
passing, 2 Streamlit skips offline.

## Phase 16 - Closing a static-review pass (real defects)

An external static/XSS/regex review surfaced concrete defects; all P1/P2 and
the actionable P3s are fixed here.

- **[P1] Library XSS.** The deck view printed the LLM-derived `concept` through
  an `unsafe_allow_html=True` markdown call without escaping - the exact sink
  `card_html()` was hardened against, missed at this second call site. Now
  `html.escape(card.concept)`. (Same treatment left the entity separators
  intact.)
- **[P2] Retired-model regex.** `claude-(sonnet|opus)-4-(0|1)?$` demanded a
  hyphen after `-4`, so bare `claude-sonnet-4` / `claude-opus-4` were NOT
  flagged retired and produced opaque 404s. Now `-4(?:-[01])?$`: the 4.0/4.1
  revisions and the bare families match, while current `-4-6/-4-7/-4-8` do not.
- **[P2] Secret in the cache key.** `_cached_models(provider, fingerprint,
  api_key)` let Streamlit hash the raw key into the cache identifier, making
  the fingerprint redundant and the secret persistable. Renamed the param to
  `_api_key`; Streamlit skips underscore-prefixed args, so only
  `(provider, fingerprint)` vary the entry and the key never enters the cache.
- **[P2] STUDYCARDS_PROVIDER / STUDYCARDS_MODEL ignored.** `.env` promised
  these; only the DB path was read. The sidebar now preselects the provider
  and (when the key can reach it) the model from those vars, matching the docs.
- **[P2] Stale key verdict.** The verdict was only discarded on a provider
  change, so pasting a different key under the SAME provider left a misleading
  "funded" banner. We now remember `(provider, fingerprint)` at check time and
  drop the verdict the moment either changes.
- **[P2] Bill-shock guardrail.** Ingestion is one model call per chunk with no
  ceiling. The UI now estimates chunk count (via the real chunker) and, above a
  soft limit of 40, requires an explicit confirmation before spending.
- **[P2] Cross-session dedup.** The duplicate guard lived in `st.session_state`
  and forgot everything on a rerun, so re-uploading doubled the deck. Added a
  persisted `ingested_documents` table (content-hash key) with
  `was_ingested`/`record_ingestion`; dedup now survives reruns and restarts.
- **[P3] delete_card** returns bool (row actually removed) and finally has a UI
  ("Delete card" in the Library, history dropped via cascade).
- **[P3] Dead `_clear_review_feedback`** is now called when the next card's
  answer is revealed, so a prior card's rating feedback cannot mislabel it.
- **[P3] KeyCheck.ok** now counts both `valid` and `funded` (callers still
  switch on `status` for the finer distinction).

### Documented limitations (not defects, called out for honesty)
- Dedup's Jaccard filter uses English stopwords, so near-duplicate detection is
  weaker for Uzbek/Russian source text. Exact-duplicate and cross-document
  dedup are unaffected; multilingual stopwording is future work.
- `CREATE TABLE IF NOT EXISTS` covers additive schema growth (like this
  phase's new table), but there is no column-level migration engine yet; a
  future breaking column change would need one.
- The evaluation compares SM-2 against a fixed-interval baseline under a
  synthetic forgetting model. It measures scheduling behaviour against a
  model, not real human retention - a methodological ceiling, not a bug.

Suite at 209 passing, 2 Streamlit-only skips offline.

## Phase 17 - Streamlit button+checkbox P1 fix + fingerprint P3

**[P1] Large-document extraction never ran.**
`st.button` returns True only on the single rerun triggered by the click.
When the soft-limit checkbox appeared (>40 chunks) and the user ticked it,
Streamlit fired a fresh rerun - where the button was False again, so the
`if not st.button(...): return` guard exited immediately and extraction
never started. The guardrail intended to *protect* large-doc users was the
exact mechanism that silently blocked them.

Fix: a two-key session-state handshake.
- `pending_extract` is set to the document fingerprint the moment the button
  is clicked; it persists across every subsequent rerun until extraction
  finishes or the user removes the file.
- `extract_confirmed` is set to True when the user ticks the checkbox; it
  also persists, so the extraction step can read it on the rerun that
  actually runs the model calls (the checkbox rerun itself).
- Extraction fires on the first rerun where `pending_extract == fingerprint`
  AND (n_chunks <= CHUNK_SOFT_LIMIT OR `extract_confirmed`). Both keys are
  popped in the `finally` block so a re-upload starts clean.
- Error paths (corrupt file, empty text) also pop `pending_extract` so the
  user is not stuck in a pending state after a failure.

**[P3] Fingerprint included the filename.**
The same PDF uploaded under a different name was treated as a new document
and re-imported, doubling the deck. The fingerprint now uses the full
sha256 of the file *content only* (64 hex chars, up from the truncated 32).
Collision probability is negligible; any two files with identical bytes are
the same document regardless of what they are called.

Suite at 216 passing, 2 Streamlit-only skips offline.
