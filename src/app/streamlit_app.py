"""StudyCards Streamlit demo - document to flashcards to SM-2 reviews.

Run it:
    streamlit run src/app/streamlit_app.py

Headless boot check (no browser):
    python -c "from src.app.streamlit_app import main; print('import ok')"
    streamlit run src/app/streamlit_app.py --server.headless true
"""
from __future__ import annotations

import hashlib
import html
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

# --------------------------------------------------------------------------
# Repository-root bootstrap. MUST run before any "from src..." import.
#
# "streamlit run" puts the *script's own directory* (src/app) on sys.path -
# not the working directory - so "import src" raised ModuleNotFoundError even
# when launched correctly from the repo root. Deriving the root from
# __file__ makes the app launchable from any directory, on any OS, without
# requiring an editable install or a PYTHONPATH export.
# --------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st  # noqa: E402  (must follow the sys.path bootstrap)
from dotenv import load_dotenv  # noqa: E402

from src.app.theme import (  # noqa: E402
    card_html,
    inject_theme,
    monogram_html,
    rule_html,
)
from src.data.repository import CardRepository, StoredCard  # noqa: E402
from src.extraction.key_check import check_balance  # noqa: E402
from src.extraction.model_discovery import (  # noqa: E402
    ModelList,
    discover_models,
    is_retired_model,
)
from src.extraction.pipeline import extract_flashcards  # noqa: E402
from src.extraction.providers import make_completion_fn  # noqa: E402
from src.ingestion.chunker import chunk_text  # noqa: E402
from src.ingestion.loader import UnsupportedFormatError, load_document  # noqa: E402

load_dotenv()

logger = logging.getLogger(__name__)

ROOT = _REPO_ROOT
DEFAULT_DB = Path(os.getenv("STUDYCARDS_DB_PATH", str(ROOT / "data" / "studycards.db")))

PROVIDERS = {
    "Anthropic": "anthropic",
    "OpenAI": "openai",
}
# Reverse map (slug -> display label) for status messages.
PROVIDERS_INV = {slug: label for label, slug in PROVIDERS.items()}
# Human-facing company names, mirrored from key_check so the UI has one import.
COMPANIES = {"anthropic": "Anthropic", "openai": "OpenAI"}
# Where to send a user whose key is real but out of credit.
BILLING_URLS = {
    "anthropic": "https://console.anthropic.com/settings/billing",
    "openai": "https://platform.openai.com/settings/organization/billing",
}

# Placeholder values shipped in .env.example must never be treated as real keys.
_PLACEHOLDER_KEY_PREFIXES = ("sk-ant-your", "sk-your")

QUALITY_LABELS = [
    "0 Blackout",
    "1 Wrong, remembered",
    "2 Wrong, easy",
    "3 Hard",
    "4 Hesitated",
    "5 Perfect",
]


def _is_placeholder_key(value: str) -> bool:
    return value.startswith(_PLACEHOLDER_KEY_PREFIXES)


def _repo() -> CardRepository:
    if "repo" not in st.session_state:
        st.session_state.repo = CardRepository(DEFAULT_DB)
    return st.session_state.repo


@st.cache_data(show_spinner=False, ttl=600)
def _cached_models(provider: str, key_fingerprint: str, _api_key: str) -> ModelList:
    """Model discovery, memoized per (provider, key_fingerprint).

    Streamlit reruns the whole script on every widget interaction, so the
    uncached version fired a live provider HTTP request on *every click*.

    ``_api_key`` is prefixed with an underscore ON PURPOSE: Streamlit hashes
    every argument into the cache key UNLESS its name starts with ``_``, so the
    raw secret is passed through for the actual call but never becomes part of
    the cache identifier. Only ``(provider, key_fingerprint)`` vary the entry,
    which is what keeps the secret out of the cache even under ``persist``.
    """
    return discover_models(provider, _api_key)


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16] if api_key else ""


def _render_key_verdict(verdict, provider: str) -> None:
    """Show the outcome of a key check, one branch per possible verdict."""
    if verdict.status in {"valid", "funded"}:
        st.sidebar.success(verdict.message)
        if verdict.models:
            with st.sidebar.expander(f"Models unlocked by this {verdict.company} key"):
                for name in verdict.models:
                    st.write(f"- {name}")
    elif verdict.status == "no_balance":
        # The key is genuine; the account simply has no credit. Point straight
        # at the provider's billing page rather than a generic error.
        st.sidebar.error(verdict.message)
        billing = BILLING_URLS.get(provider)
        if billing:
            st.sidebar.markdown(f"[Add credits at {COMPANIES.get(provider)}]({billing})")
    elif verdict.status == "invalid":
        st.sidebar.error(verdict.message)
    elif verdict.status in {"mismatch", "placeholder", "empty"}:
        st.sidebar.warning(verdict.message)
    elif verdict.status == "unreachable":
        st.sidebar.info(verdict.message)


def _sidebar_config() -> dict:
    st.sidebar.markdown("## Atelier")
    st.sidebar.caption("Credentials & model")

    # STUDYCARDS_PROVIDER (env) chooses the initially selected provider; the
    # dropdown can still override it. Unknown/empty values fall back to index 0.
    provider_labels = list(PROVIDERS.keys())
    env_provider = os.getenv("STUDYCARDS_PROVIDER", "").strip().lower()
    provider_index = next(
        (i for i, label in enumerate(provider_labels) if PROVIDERS[label] == env_provider),
        0,
    )
    provider_label = st.sidebar.selectbox("Provider", provider_labels, index=provider_index)
    provider = PROVIDERS[provider_label]

    env_key = (
        os.getenv("ANTHROPIC_API_KEY", "")
        if provider == "anthropic"
        else os.getenv("OPENAI_API_KEY", "")
    )
    prefill = env_key if env_key and not _is_placeholder_key(env_key) else ""
    api_key = st.sidebar.text_input(
        "API key",
        value=prefill,
        type="password",
        help="Loaded from .env when present. Never committed.",
    ).strip()

    # Dynamic model discovery - degrades to curated fallbacks offline / no key.
    models = _cached_models(provider, _key_fingerprint(api_key), api_key)  # api_key is not hashed (leading _ in signature)
    # STUDYCARDS_MODEL (env) preselects a model when the key can actually reach
    # it; otherwise we leave the curated default (index 0) selected.
    env_model = os.getenv("STUDYCARDS_MODEL", "").strip()
    model_index = models.models.index(env_model) if env_model in models.models else 0
    model = st.sidebar.selectbox(
        "Model",
        models.models,
        index=model_index,
        help="Live listing from your key when available. Preselect with STUDYCARDS_MODEL.",
    )
    # ---- Key check -------------------------------------------------------
    # The dropdown always looks healthy because discovery falls back silently,
    # so verification is explicit and user-triggered. A billing probe spends a
    # real token, so it must never fire on every rerun - only on the button.
    if st.sidebar.button("Check API key", use_container_width=True):
        with st.sidebar:
            with st.spinner(f"Testing your {PROVIDERS_INV.get(provider, provider)} key..."):
                # A single cheap round trip proves the key is real, funded, and
                # says what it unlocks. check_balance runs every local guard
                # first, so a placeholder or wrong-provider key never bills.
                st.session_state["key_check"] = check_balance(provider, api_key, model)
                # Remember exactly which key+provider this verdict describes so
                # editing the key (even to another key of the SAME provider)
                # invalidates a now-misleading "Verified / funded" banner.
                st.session_state["key_check_for"] = (provider, _key_fingerprint(api_key))

    verdict = st.session_state.get("key_check")
    # Discard a stale result once the key OR provider changes underneath it.
    # Provider is checked via company (guards a verdict carried across a
    # provider switch); the (provider, fingerprint) tuple additionally catches
    # a new key pasted under the same provider.
    checked_for = st.session_state.get("key_check_for")
    current_for = (provider, _key_fingerprint(api_key))
    if verdict is not None and verdict.company and verdict.company != COMPANIES.get(provider):
        verdict = None
    if verdict is not None and checked_for is not None and checked_for != current_for:
        verdict = None
    if verdict is not None:
        _render_key_verdict(verdict, provider)

    # A model pinned via STUDYCARDS_MODEL can quietly go out of service.
    if model and is_retired_model(model):
        st.sidebar.warning(
            f"`{model}` has been retired by the provider and will return errors. "
            "Pick a current model above."
        )

    return {"provider": provider, "api_key": api_key, "model": model}


# One LLM call is made per chunk, so chunk count is the cost multiplier. Above
# this soft limit we make the user confirm before spending, but never block
# them outright - some study sheets legitimately are large.
CHUNK_SOFT_LIMIT = 40


def _estimate_chunk_count(text: str) -> int:
    """How many chunks (== paid model calls) this text will produce.

    Uses the real chunker so the estimate matches what extraction actually
    does, rather than a divide-by-char-count approximation that could drift
    from the chunker's paragraph-aware splitting.
    """
    return len(chunk_text(text))


def _document_fingerprint(data: bytes) -> str:
    """Content-only fingerprint for an upload.

    Deliberately excludes the filename so the same PDF uploaded under a
    different name is recognised as already-imported and doesn't double the
    deck. The full sha256 keeps collision probability negligible.
    """
    return hashlib.sha256(data).hexdigest()


def _render_upload(cfg: dict) -> None:
    """Section I: upload a document and extract flashcards from it.

    Streamlit flow control notes
    ----------------------------
    ``st.button`` returns True only on the single rerun immediately after the
    user clicks it.  Any subsequent widget interaction (e.g. ticking the large-
    document confirmation checkbox) triggers a fresh rerun where the button is
    False again, so gating the extraction on ``if not st.button(...)`` would
    exit before the confirmation step could complete.

    We solve this with a two-key session-state handshake:

    - ``pending_extract``: set to the document fingerprint when the user
      clicks an extract button; persists across reruns until extraction
      finishes (or the user uploads a different document).
    - ``extract_confirmed``: set to True when the user ticks the large-doc
      checkbox; persists across reruns so the extraction step can read it
      even though the checkbox widget itself disappears once we start.

    The button press arms the handshake; the checkbox (when needed) pulls the
    trigger; extraction fires on the first rerun where both are True.
    """
    st.markdown(rule_html("I - Ingest"), unsafe_allow_html=True)
    st.caption(
        "Upload a PDF or plain-text study sheet. Concept-level cards are "
        "extracted, deduplicated, and scheduled."
    )

    uploaded = st.file_uploader("Document", type=["pdf", "txt", "md"])
    if uploaded is None:
        st.session_state.pop("pending_extract", None)
        st.session_state.pop("extract_confirmed", None)
        return

    raw_bytes = uploaded.getvalue()
    # Content-only hash: same PDF under a different filename is still the same
    # document (no duplicate deck entries).  P3 fix: filename excluded.
    fingerprint = _document_fingerprint(raw_bytes)
    prior_count = _repo().was_ingested(fingerprint)

    # ------------------------------------------------------------------ #
    # Step 1 — the initial "extract" or "extract again" button.           #
    # Clicking it arms the session-state handshake; it does NOT run the  #
    # extraction itself (that happens below, after confirmation if needed).#
    # ------------------------------------------------------------------ #
    if prior_count is not None:
        st.info(
            f"This document was already imported ({prior_count} cards added). "
            "Re-extracting would create duplicate cards."
        )
        if st.button("Extract again anyway"):
            st.session_state["pending_extract"] = fingerprint
            st.session_state.pop("extract_confirmed", None)
    else:
        if st.button("Extract flashcards", type="primary"):
            st.session_state["pending_extract"] = fingerprint
            st.session_state.pop("extract_confirmed", None)

    # If a *different* document is now loaded, drop the stale pending state.
    if st.session_state.get("pending_extract") != fingerprint:
        return

    # ------------------------------------------------------------------ #
    # Step 2 — sidebar / key validation (safe to repeat on every rerun). #
    # ------------------------------------------------------------------ #
    if not cfg["api_key"]:
        st.error("Enter an API key in the sidebar (or set it in `.env`).")
        return
    if not cfg.get("model"):
        st.error("Select a model in the sidebar.")
        return

    # ------------------------------------------------------------------ #
    # Step 3 — load the document text (cheap, no API call).              #
    # ------------------------------------------------------------------ #
    try:
        text = load_document(raw_bytes, filename=uploaded.name)
    except UnsupportedFormatError as exc:
        st.error(str(exc))
        st.session_state.pop("pending_extract", None)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("document load failed")
        st.error(f"Could not read that file: {exc}")
        st.session_state.pop("pending_extract", None)
        return

    if not text.strip():
        st.warning("No extractable text found in that file.")
        st.session_state.pop("pending_extract", None)
        return

    # ------------------------------------------------------------------ #
    # Step 4 — cost guardrail for large documents.                        #
    #                                                                     #
    # For small docs (n_chunks <= CHUNK_SOFT_LIMIT) we proceed directly.  #
    # For large docs we need explicit confirmation via a checkbox.  The   #
    # checkbox state is persisted in session_state so it survives the     #
    # rerun that checking it triggers (the button would be False by then).#
    # ------------------------------------------------------------------ #
    n_chunks = _estimate_chunk_count(text)
    st.caption(f"Estimated {n_chunks} chunk(s) — about {n_chunks} model call(s) on your key.")

    if n_chunks > CHUNK_SOFT_LIMIT:
        st.warning(
            f"This document is large: roughly {n_chunks} model calls "
            f"(soft limit {CHUNK_SOFT_LIMIT}). Each call bills your API key."
        )
        confirmed = st.checkbox(
            f"Yes, run about {n_chunks} paid model calls",
            value=st.session_state.get("extract_confirmed", False),
            key="extract_confirm_cb",
        )
        if confirmed:
            st.session_state["extract_confirmed"] = True
        if not st.session_state.get("extract_confirmed"):
            return  # waiting for the user to tick the checkbox
    # (no confirmation needed for small docs)

    # ------------------------------------------------------------------ #
    # Step 5 — extraction.  Clears the handshake keys when done.         #
    # ------------------------------------------------------------------ #
    progress = st.progress(0.0, text="Extracting...")
    status = st.empty()

    def on_progress(done: int, total: int) -> None:
        fraction = done / total if total else 1.0
        progress.progress(min(fraction, 1.0), text=f"Chunk {done}/{total}")
        status.caption(f"Extracting concepts from chunk {done} of {total}...")

    try:
        complete = make_completion_fn(cfg["provider"], cfg["api_key"], cfg["model"])
        cards = extract_flashcards(text, complete, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001
        logger.exception("extraction failed")
        st.error(f"Extraction failed: {exc}")
        return
    finally:
        progress.empty()
        status.empty()
        # Always disarm the handshake so a re-upload starts fresh.
        st.session_state.pop("pending_extract", None)
        st.session_state.pop("extract_confirmed", None)

    if not cards:
        st.warning("No concept-level cards survived quality filtering.")
        return

    ids = _repo().add_cards(cards, now=datetime.now())
    _repo().record_ingestion(fingerprint, uploaded.name, len(ids))
    st.session_state["last_extract_count"] = len(ids)
    st.success(f"Added {len(ids)} flashcards to your deck.")


def _clear_review_feedback() -> None:
    """Drop the previous card's explanation so it cannot look like this card's."""
    st.session_state.pop("last_explanation", None)
    st.session_state.pop("last_due", None)
    st.session_state.pop("last_rated_card", None)


def _select_active_card(due: List[StoredCard]) -> StoredCard:
    due_ids = {c.id for c in due}
    active = st.session_state.get("active_card_id")
    if active not in due_ids:
        st.session_state.active_card_id = due[0].id
        st.session_state.show_answer = False
    return next(c for c in due if c.id == st.session_state.active_card_id)


def _render_review() -> None:
    st.markdown(rule_html("II - Review"), unsafe_allow_html=True)
    repo = _repo()
    due = repo.list_due_cards(on=date.today())
    total = repo.count_cards()

    c1, c2, c3 = st.columns(3)
    c1.metric("Deck size", total)
    c2.metric("Due today", len(due))
    c3.metric("Reviews logged", repo.count_reviews())

    # Feedback from the last rating is shown even when the queue empties.
    _render_last_explanation()

    if not due:
        st.info("Nothing due today. Upload a document or check back tomorrow.")
        return

    # `due` already holds full card rows, so reuse them instead of re-querying.
    card = _select_active_card(due)

    st.markdown(
        card_html(
            card.question,
            answer=card.answer if st.session_state.get("show_answer") else "",
            concept=card.concept,
        ),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("show_answer"):
        if st.button("Reveal answer"):
            # Revealing THIS card's answer, so the previous card's rating
            # feedback must not linger and look like it belongs here.
            _clear_review_feedback()
            st.session_state.show_answer = True
            st.rerun()
        return

    st.caption(
        f"Current ease {card.ease_factor:.2f} - streak {card.repetitions} - "
        f"last interval {card.interval_days}d - due {card.due_date}"
    )

    st.markdown("Rate your recall (SM-2 quality 0-5):")
    cols = st.columns(len(QUALITY_LABELS))
    for quality, (col, label) in enumerate(zip(cols, QUALITY_LABELS)):
        if not col.button(label, key=f"q{quality}"):
            continue
        try:
            result = repo.record_review(card.id, quality, review_date=date.today())
        except KeyError:
            # The card was deleted between render and click.
            st.warning("That card no longer exists - loading the next one.")
            st.session_state.pop("active_card_id", None)
            st.rerun()
            return

        updated = repo.get_card(card.id)
        st.session_state["last_explanation"] = result.explanation
        # get_card can legitimately return None (concurrent delete); the old
        # code dereferenced it unconditionally and raised AttributeError.
        st.session_state["last_due"] = updated.due_date if updated else None
        st.session_state["last_rated_card"] = card.concept or card.question
        st.session_state.show_answer = False
        st.session_state.pop("active_card_id", None)
        st.rerun()


def _render_last_explanation() -> None:
    explanation = st.session_state.get("last_explanation")
    if not explanation:
        return
    st.markdown("#### Why this interval?")
    rated = st.session_state.get("last_rated_card")
    if rated:
        st.caption(f"For: {rated}")
    st.info(explanation)
    if st.session_state.get("last_due"):
        st.caption(f"Next review date: **{st.session_state['last_due']}**")


def _render_deck() -> None:
    st.markdown(rule_html("III - Library"), unsafe_allow_html=True)
    with st.expander("Full deck & history", expanded=False):
        repo = _repo()
        cards = repo.list_cards()
        if not cards:
            st.caption("Deck is empty.")
            return
        # One query for every card's latest review instead of N+1.
        latest: Dict[int, object] = repo.latest_reviews()
        for card in cards:
            st.markdown(
                # concept comes from an LLM parsing an arbitrary document, so it
                # is untrusted; escape it before it rides an unsafe_allow_html
                # markdown call (the same XSS surface card_html() closes).
                f"**{html.escape(card.concept)}** &nbsp;&middot;&nbsp; due {card.due_date} "
                f"&nbsp;&middot;&nbsp; ease {card.ease_factor:.2f}",
                unsafe_allow_html=True,
            )
            st.caption(card.question)
            last = latest.get(card.id)
            if last is not None:
                st.caption(f"Last: {last.explanation}")
            # delete_card() existed but had no UI; a wrong card was impossible
            # to remove. Cascade drops its history too.
            if st.button("Delete card", key=f"del_{card.id}"):
                _repo().delete_card(card.id)
                st.session_state.pop("active_card_id", None)
                st.rerun()
            st.divider()


def main() -> None:
    st.set_page_config(
        page_title="StudyCards",
        page_icon="\u25c8",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    st.markdown(
        monogram_html("SC", established="Est. MMXXVI"), unsafe_allow_html=True
    )
    st.title("StudyCards")
    st.caption(
        "A document-to-flashcard atelier - concept extraction, "
        "exact SM-2 scheduling, and a reasoned interval for every review."
    )

    cfg = _sidebar_config()
    _render_upload(cfg)
    _render_review()
    _render_deck()
    st.markdown(rule_html("Fin"), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
