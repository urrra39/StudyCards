"""Old-money visual theme for the Streamlit app.

A single CSS injection (rather than a Streamlit theme config file) because
config.toml theming cannot touch typography, borders, gradients, or component
internals — everything that actually sells the aesthetic.

Palette:
    Deep emerald   #0A1F1C  (app background)
    Dark slate     #0F172A  (sidebar / secondary surfaces)
    Soft pine      #162825  (card surfaces)
    Champagne gold #D4AF37 / muted brass #C5A059  (accents, borders)
    Cream parchment #F9F6F0 (primary text)
"""
from __future__ import annotations

OLD_MONEY_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500&family=Cormorant+Garamond:wght@500;600&display=swap');

:root {
    --emerald: #0A1F1C;
    --slate: #0F172A;
    --pine: #162825;
    --gold: #D4AF37;
    --brass: #C5A059;
    --cream: #F9F6F0;
}

/* ---- App canvas ---- */
.stApp {
    background: radial-gradient(ellipse at top, #0D2622 0%, var(--emerald) 55%);
    color: var(--cream);
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--slate) 0%, #0B1220 100%);
    border-right: 1px solid rgba(212, 175, 55, 0.35);
}

/* ---- Typography: serif headers, warm body ---- */
h1, h2, h3, h4 {
    font-family: 'Playfair Display', Georgia, 'Times New Roman', serif !important;
    color: var(--cream) !important;
    letter-spacing: 0.02em;
}
h1 {
    border-bottom: 1px solid var(--brass);
    padding-bottom: 0.35em;
}
.stMarkdown, p, label, .stCaption {
    font-family: 'Cormorant Garamond', Georgia, serif;
    color: var(--cream);
}

/* ---- Luxury buttons: subtle gold gradient, brass border ---- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    background: linear-gradient(160deg, rgba(212,175,55,0.16), rgba(197,160,89,0.05));
    color: var(--gold);
    border: 1px solid var(--brass);
    border-radius: 2px;                 /* crisp corners read as engraved, not app-like */
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    transition: all 0.25s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    border-color: var(--gold);
    box-shadow: 0 0 14px rgba(212, 175, 55, 0.35);
    color: var(--cream);
}

/* ---- Glassmorphic card surfaces ---- */
[data-testid="stMetric"], .sc-card {
    background: linear-gradient(150deg, rgba(22,40,37,0.85), rgba(15,23,42,0.65));
    backdrop-filter: blur(6px);
    border: 1px solid rgba(212, 175, 55, 0.4);
    border-radius: 4px;
    padding: 1.1rem 1.3rem;
    box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35);
}
[data-testid="stMetricValue"] {
    color: var(--gold) !important;
    font-family: 'Playfair Display', Georgia, serif !important;
}
[data-testid="stMetricLabel"] {
    color: var(--cream) !important;
    opacity: 0.75;
}

/* ---- Inputs ---- */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div {
    background-color: var(--pine) !important;
    color: var(--cream) !important;
    border: 1px solid rgba(197, 160, 89, 0.5) !important;
    border-radius: 2px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 8px rgba(212, 175, 55, 0.3) !important;
}

/* ---- Expanders & dividers ---- */
[data-testid="stExpander"] {
    border: 1px solid rgba(212, 175, 55, 0.3);
    border-radius: 4px;
    background: rgba(22, 40, 37, 0.5);
}
hr {
    border-color: rgba(197, 160, 89, 0.4) !important;
}

/* ---- File uploader ---- */
[data-testid="stFileUploaderDropzone"] {
    background: rgba(22, 40, 37, 0.7);
    border: 1px dashed var(--brass);
    border-radius: 4px;
}
</style>
"""


def inject_theme() -> None:
    """Apply the old-money theme. Call once at the top of every page."""
    import streamlit as st  # deferred so non-UI code can import this module

    st.markdown(OLD_MONEY_CSS, unsafe_allow_html=True)


def card_html(question: str, answer: str = "", concept: str = "") -> str:
    """Render a flashcard as a themed HTML block (used with unsafe_allow_html)."""
    concept_row = (
        f'<div style="color:#C5A059;font-size:0.8em;letter-spacing:0.12em;'
        f'text-transform:uppercase;margin-bottom:0.4em;">{concept}</div>'
        if concept
        else ""
    )
    answer_row = (
        f'<div style="margin-top:0.8em;color:#F9F6F0;opacity:0.9;">{answer}</div>'
        if answer
        else ""
    )
    return (
        '<div class="sc-card" style="margin-bottom:1rem;">'
        f"{concept_row}"
        f'<div style="font-family:Playfair Display,Georgia,serif;font-size:1.15em;'
        f'color:#F9F6F0;">{question}</div>'
        f"{answer_row}"
        "</div>"
    )
