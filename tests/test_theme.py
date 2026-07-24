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


class TestThemeComponents:
    """The ornamental components are also HTML-injected, so they must escape."""

    def test_monogram_renders_initials_and_tagline(self):
        from src.app.theme import monogram_html

        html = monogram_html("SC", established="Est. MMXXVI")
        assert "SC" in html
        assert "Est. MMXXVI" in html
        assert 'class="sc-monogram"' in html

    def test_monogram_escapes_input(self):
        from src.app.theme import monogram_html

        html = monogram_html("<img src=x onerror=alert(1)>")
        assert "<img" not in html

    def test_rule_renders_with_and_without_label(self):
        from src.app.theme import rule_html

        assert "<span>Review</span>" in rule_html("Review")
        assert "<span>" not in rule_html()

    def test_rule_escapes_label(self):
        from src.app.theme import rule_html

        assert "<script>" not in rule_html("<script>alert(1)</script>")

    def test_plaque_renders_label_value_and_note(self):
        from src.app.theme import plaque_html

        html = plaque_html("Due today", "12", note="across 3 decks")
        assert "Due today" in html
        assert "12" in html
        assert "across 3 decks" in html

    def test_plaque_omits_note_row_when_absent(self):
        from src.app.theme import plaque_html

        assert "opacity:0.7" not in plaque_html("Deck", "0")

    def test_plaque_escapes_all_fields(self):
        from src.app.theme import plaque_html

        html = plaque_html('a"b', "<b>x</b>", note="<script>y</script>")
        assert "<b>" not in html
        assert "<script>" not in html
        assert "&quot;" in html


class TestThemeQuality:
    def test_local_serif_fallbacks_declared(self):
        # The webfont import is progressive enhancement only; the app must
        # still look correct offline or with Google Fonts blocked.
        assert "Iowan Old Style" in OLD_MONEY_CSS
        assert "Palatino Linotype" in OLD_MONEY_CSS

    def test_reduced_motion_is_respected(self):
        assert "prefers-reduced-motion" in OLD_MONEY_CSS

    def test_focus_indicators_are_not_removed(self):
        # Restyling focus is fine; removing it is an accessibility defect.
        assert "focus-visible" in OLD_MONEY_CSS
        assert "outline: none" not in OLD_MONEY_CSS

    def test_print_styles_present(self):
        assert "@media print" in OLD_MONEY_CSS


class TestMotionSystem:
    """The animation vocabulary is part of the product; pin it."""

    ANIMATIONS = (
        "sc-rise",
        "sc-fade",
        "sc-draw",
        "sc-gild",
        "sc-turn",
        "sc-breathe",
        "sc-seal",
    )

    def test_every_keyframe_is_defined(self):
        for name in self.ANIMATIONS:
            assert f"@keyframes {name}" in OLD_MONEY_CSS, name

    def test_every_keyframe_is_actually_used(self):
        for name in self.ANIMATIONS:
            assert OLD_MONEY_CSS.count(name) >= 2, f"{name} defined but never applied"

    def test_easing_curves_are_declared_as_tokens(self):
        assert "--ease-silk" in OLD_MONEY_CSS
        assert "--ease-drape" in OLD_MONEY_CSS

    def test_no_bouncy_or_elastic_easing(self):
        # House style: motion settles, never overshoots.
        assert "cubic-bezier(0.68" not in OLD_MONEY_CSS
        assert "elastic" not in OLD_MONEY_CSS.lower()

    def test_entrance_animations_use_both_fill_mode(self):
        assert "var(--ease-drape) both" in OLD_MONEY_CSS

    def test_reduced_motion_neutralizes_rather_than_disables(self):
        """The critical accessibility bug this theme could have.

        Entrance animations start at opacity 0 with fill-mode ``both``. If
        reduced-motion set ``animation: none``, every animated element would
        stay invisible forever. The block must instead swap in a near-instant
        fade, so content is always painted.
        """
        start = OLD_MONEY_CSS.index("prefers-reduced-motion")
        end = OLD_MONEY_CSS.index("@media print")
        block = OLD_MONEY_CSS[start:end]
        assert "animation-name: sc-fade !important" in block
        assert "animation: none" not in block

    def test_gradient_text_has_reduced_motion_fallback(self):
        block = OLD_MONEY_CSS[OLD_MONEY_CSS.index("prefers-reduced-motion"):]
        assert "-webkit-text-fill-color: var(--cream)" in block

    def test_print_stylesheet_disables_motion(self):
        block = OLD_MONEY_CSS[OLD_MONEY_CSS.index("@media print"):]
        assert "animation: none !important" in block


class TestSidebarChrome:
    """The Atelier panel carries the fullest gold treatment."""

    def test_sidebar_title_is_gilded(self):
        assert '[data-testid="stSidebar"] h2' in OLD_MONEY_CSS
        assert "sc-gild 6s" in OLD_MONEY_CSS

    def test_sidebar_gradient_title_has_reduced_motion_fallback(self):
        """Transparent text fill plus a cancelled animation means invisible text."""
        block = OLD_MONEY_CSS[OLD_MONEY_CSS.index("prefers-reduced-motion"):]
        assert 'h1, [data-testid="stSidebar"] h2' in block

    def test_fallback_model_caption_is_gone(self):
        """Curated defaults are good models; no apology belongs under them."""
        from pathlib import Path

        app = Path(__file__).resolve().parents[1] / "src" / "app" / "streamlit_app.py"
        source = app.read_text(encoding="utf-8")
        assert "Showing recommended defaults" not in source
        assert "listing unavailable" not in source


class TestStrengthenedMotion:
    """The richer animation layer added for the atelier build."""

    NEW_KEYFRAMES = ("sc-sheen", "sc-pulse", "sc-glow", "sc-shake", "sc-float")

    def _css(self):
        from src.app.theme import OLD_MONEY_CSS

        return OLD_MONEY_CSS

    def test_new_keyframes_are_all_defined(self):
        css = self._css()
        for name in self.NEW_KEYFRAMES:
            assert f"@keyframes {name}" in css, f"{name} is not defined"

    def test_new_keyframes_are_all_used(self):
        css = self._css()
        for name in self.NEW_KEYFRAMES:
            # Defined once and applied at least once = at least two mentions.
            assert css.count(name) >= 2, f"{name} is defined but never applied"

    def test_success_and_error_verdicts_animate_differently(self):
        css = self._css()
        assert "sc-glow" in css  # success swells
        assert "sc-shake" in css  # error settles with one shake

    def test_shake_is_a_single_settle_not_a_loop(self):
        """An error nudge must play once; a looping shake would be gaudy."""
        css = self._css()
        assert "sc-shake 520ms var(--ease-silk) 400ms 1" in css

    def test_motion_stays_calm_no_bounce(self):
        """Old money does not bounce: no elastic easing sneaks in with the new work."""
        css = self._css()
        assert "cubic-bezier(0.68" not in css
        assert "elastic" not in css

    def test_reduced_motion_still_neutralises_everything(self):
        """The new keyframes must fall under the global reduced-motion override."""
        css = self._css()
        assert "prefers-reduced-motion" in css
        assert "animation-name: sc-fade !important" in css
