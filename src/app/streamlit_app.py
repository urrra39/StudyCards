"""StudyCards Streamlit demo — document → flashcards → SM-2 reviews.

Headless boot check (no browser):
    python -c "from src.app.streamlit_app import main; print('import ok')"
    streamlit run src/app/streamlit_app.py --server.headless true
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import streamlit as st
from dotenv import load_dotenv

from src.app.theme import card_html, inject_theme
from src.data.repository import CardRepository
from src.extraction.model_discovery import discover_models
from src.extraction.pipeline import extract_flashcards
from src.extraction.providers import make_completion_fn
from src.ingestion.loader import UnsupportedFormatError, load_document

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path(os.getenv("STUDYCARDS_DB_PATH", str(ROOT / "data" / "studycards.db")))

PROVIDERS = {
    "Anthropic": "anthropic",
    "OpenAI": "openai",
}


def _repo() -> CardRepository:
    if "repo" not in st.session_state:
        st.session_state.repo = CardRepository(DEFAULT_DB)
    return st.session_state.repo


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
    api_key = st.sidebar.text_input(
        "API key",
        value=env_key if env_key and not env_key.startswith("sk-ant-your") and not env_key.startswith("sk-your") else "",
        type="password",
        help="Loaded from .env when present. Never committed.",
    )

    # Dynamic model discovery — degrades to curated fallbacks offline / no key.
    models = discover_models(provider, api_key)
    model = st.sidebar.selectbox(
        "Model",
        models.models,
        help="Live listing from your key when available.",
    )
    if models.source == "fallback":
        st.sidebar.caption("Showing recommended defaults (key missing or listing unavailable).")
    else:
        st.sidebar.caption(f"Live catalog — {len(models.models)} models.")

    return {"provider": provider, "api_key": api_key, "model": model}


def _render_upload(cfg: dict) -> None:
    st.markdown("### Ingest")
    st.caption("Upload a PDF or plain-text study sheet. Concept-level cards are extracted, deduplicated, and scheduled.")

    uploaded = st.file_uploader("Document", type=["pdf", "txt", "md"])
    if uploaded is None:
        return

    if st.button("Extract flashcards", type="primary"):
        if not cfg["api_key"]:
            st.error("Enter an API key in the sidebar (or set it in `.env`).")
            return
        try:
            text = load_document(uploaded.getvalue(), filename=uploaded.name)
        except UnsupportedFormatError as exc:
            st.error(str(exc))
            return
        if not text.strip():
            st.warning("No extractable text found in that file.")
            return

        progress = st.progress(0.0, text="Extracting…")
        status = st.empty()

        def on_progress(done: int, total: int) -> None:
            progress.progress(done / max(total, 1), text=f"Chunk {done}/{total}")
            status.caption(f"Extracting concepts from chunk {done} of {total}…")

        try:
            complete = make_completion_fn(cfg["provider"], cfg["api_key"], cfg["model"])
            cards = extract_flashcards(text, complete, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001 — surface provider errors in the UI
            st.error(f"Extraction failed: {exc}")
            return
        finally:
            progress.empty()
            status.empty()

        if not cards:
            st.warning("No concept-level cards survived quality filtering.")
            return

        repo = _repo()
        ids = repo.add_cards(cards, now=datetime.now())
        st.success(f"Added {len(ids)} flashcards to your deck.")
        st.session_state["last_extract_count"] = len(ids)


def _render_review() -> None:
    st.markdown("### Review")
    repo = _repo()
    due = repo.list_due_cards(on=date.today())
    total = repo.count_cards()

    c1, c2, c3 = st.columns(3)
    c1.metric("Deck size", total)
    c2.metric("Due today", len(due))
    c3.metric("Reviews logged", repo.count_reviews())

    if not due:
        st.info("Nothing due today. Upload a document or check back tomorrow.")
        return

    # Persist the active card across reruns until it is rated.
    if "active_card_id" not in st.session_state or st.session_state.active_card_id not in {
        c.id for c in due
    }:
        st.session_state.active_card_id = due[0].id
        st.session_state.show_answer = False

    card = repo.get_card(st.session_state.active_card_id)
    if card is None:
        st.warning("Card disappeared — refreshing.")
        st.session_state.pop("active_card_id", None)
        st.rerun()
        return

    st.markdown(
        card_html(card.question, answer="" if not st.session_state.get("show_answer") else card.answer, concept=card.concept),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("show_answer"):
        if st.button("Reveal answer"):
            st.session_state.show_answer = True
            st.rerun()
        return

    st.caption(
        f"Current ease {card.ease_factor:.2f} · streak {card.repetitions} · "
        f"last interval {card.interval_days}d · due {card.due_date}"
    )

    st.markdown("Rate your recall (SM-2 quality 0–5):")
    labels = [
        "0 Blackout",
        "1 Wrong, remembered",
        "2 Wrong, easy",
        "3 Hard",
        "4 Hesitated",
        "5 Perfect",
    ]
    cols = st.columns(6)
    for q, (col, label) in enumerate(zip(cols, labels)):
        if col.button(label, key=f"q{q}"):
            result = repo.record_review(card.id, q, review_date=date.today())
            st.session_state["last_explanation"] = result.explanation
            st.session_state["last_due"] = repo.get_card(card.id).due_date
            st.session_state.show_answer = False
            st.session_state.pop("active_card_id", None)
            st.rerun()

    if st.session_state.get("last_explanation"):
        st.markdown("#### Why this interval?")
        st.info(st.session_state["last_explanation"])
        if st.session_state.get("last_due"):
            st.caption(f"Next review date: **{st.session_state['last_due']}**")


def _render_deck() -> None:
    with st.expander("Full deck & history", expanded=False):
        repo = _repo()
        cards = repo.list_cards()
        if not cards:
            st.caption("Deck is empty.")
            return
        for card in cards:
            st.markdown(f"**{card.concept}** — due {card.due_date} · EF {card.ease_factor:.2f}")
            st.caption(card.question)
            history = repo.list_reviews(card.id)
            if history:
                last = history[-1]
                st.caption(f"Last: {last.explanation}")


def main() -> None:
    st.set_page_config(
        page_title="StudyCards",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    st.title("StudyCards")
    st.caption("Document-to-flashcard atelier · SM-2 spaced repetition")

    cfg = _sidebar_config()
    _render_upload(cfg)
    st.markdown("---")
    _render_review()
    _render_deck()


if __name__ == "__main__":
    main()
