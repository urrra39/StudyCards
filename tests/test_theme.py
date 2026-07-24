"""Tests for the old-money theme module (no Streamlit runtime required)."""
from __future__ import annotations

from src.app.theme import OLD_MONEY_CSS, card_html


class TestThemeCss:
    def test_palette_tokens_present(self):
        for token in ("#0A1F1C", "#D4AF37", "#F9F6F0", "#0F172A", "#162825", "#C5A059"):
            assert token in OLD_MONEY_CSS

    def test_serif_typography_declared(self):
        assert "Playfair Display" in OLD_MONEY_CSS
        assert "Cormorant Garamond" in OLD_MONEY_CSS
        assert "Georgia" in OLD_MONEY_CSS


class TestCardHtml:
    def test_renders_question_and_optional_fields(self):
        html = card_html("What is SM-2?", answer="A spaced-repetition algorithm.", concept="SM-2")
        assert "What is SM-2?" in html
        assert "A spaced-repetition algorithm." in html
        assert "SM-2" in html
        assert 'class="sc-card"' in html

    def test_omits_empty_optional_rows(self):
        html = card_html("Just a question?")
        assert "Just a question?" in html
        # No concept/answer rows when those args are empty.
        assert "text-transform:uppercase" not in html
