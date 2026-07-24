"""StudyCards Streamlit demo - document to flashcards to SM-2 reviews.

Run it:
    streamlit run src/app/streamlit_app.py

Headless boot check (no browser):
    python -c "from src.app.streamlit_app import main; print('import ok')"
    streamlit run src/app/streamlit_app.py --server.headless true
"""
from __future__ import annotations

import hashlib
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
def _cached_models(provider: str, key_fingerprint: str, api_key: str) -> ModelList:
    """Model discovery, memoized per (provider, key).

    Streamlit reruns the whole script on every widget interaction, so the
    uncached version fired a live provider HTTP request on *every click*.
    The fingerprint (not the raw key) is what varies the cache entry, so the
    secret is never used as a display-facing cache key.
    """
    return discover_models(provider, api_key)


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

    provider_label = st.sidebar.selectbox("Provider", list(PROVIDERS.keys()))
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
    models = _cached_models(provider, _key_fingerprint(api_key), api_key)
    model = st.sidebar.selectbox(
        "Model",
        models.models,
        help="Live listing from your key when available.",
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

    verdict = st.session_state.get("key_check")
    # Discard a stale result once the key or provider changes underneath it.
    if verdict is not None and verdict.company and verdict.company != COMPANIES.get(provider):
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


def _document_fingerprint(name: str, data: bytes) -> str:
    """Stable id for an upload, used to make extraction idempotent."""
    digest = hashlib.sha256(data).hexdigest()[:32]
    return f"{name}:{digest}"


def _render_upload(cfg: dict) -> None:
    st.markdown(rule_html("I - Ingest"), unsafe_allow_html=True)
    st.caption(
        "Upload a PDF or plain-text study sheet. Concept-level cards are "
        "extracted, deduplicated, and scheduled."
    )

    uploaded = st.file_uploader("Document", type=["pdf", "txt", "md"])
    if uploaded is None:
        return

    raw_bytes = uploaded.getvalue()
    fingerprint = _document_fingerprint(uploaded.name, raw_bytes)
    already_done = st.session_state.get("ingested_docs", {})

    if fingerprint in already_done:
        st.info(
            f"This document was already imported in this session "
            f"({already_done[fingerprint]} cards added). "
            "Re-extracting would create duplicates."
        )
        if not st.button("Extract again anyway"):
            return
    elif not st.button("Extract flashcards", type="primary"):
        return

    if not cfg["api_key"]:
        st.error("Enter an API key in the sidebar (or set it in `.env`).")
        return
    if not cfg.get("model"):
        st.error("Select a model in the sidebar.")
        return

    try:
        text = load_document(raw_bytes, filename=uploaded.name)
    except UnsupportedFormatError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - a corrupt PDF must not crash the app
        logger.exception("document load failed")
        st.error(f"Could not read that file: {exc}")
        return

    if not text.strip():
        st.warning("No extractable text found in that file.")
        return

    progress = st.progress(0.0, text="Extracting...")
    status = st.empty()

    def on_progress(done: int, total: int) -> None:
        fraction = done / total if total else 1.0
        progress.progress(min(fraction, 1.0), text=f"Chunk {done}/{total}")
        status.caption(f"Extracting concepts from chunk {done} of {total}...")

    try:
        complete = make_completion_fn(cfg["provider"], cfg["api_key"], cfg["model"])
        cards = extract_flashcards(text, complete, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 - surface provider errors in the UI
        logger.exception("extraction failed")
        st.error(f"Extraction failed: {exc}")
        return
    finally:
        progress.empty()
        status.empty()

    if not cards:
        st.warning("No concept-level cards survived quality filtering.")
        return

    ids = _repo().add_cards(cards, now=datetime.now())
    st.session_state.setdefault("ingested_docs", {})[fingerprint] = len(ids)
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
                f"**{card.concept}** &nbsp;&middot;&nbsp; due {card.due_date} "
                f"&nbsp;&middot;&nbsp; ease {card.ease_factor:.2f}",
                unsafe_allow_html=True,
            )
            st.caption(card.question)
            last = latest.get(card.id)
            if last is not None:
                st.caption(f"Last: {last.explanation}")


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
