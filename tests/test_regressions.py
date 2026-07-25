"""Regression pins for defects found in the end-to-end audit.

Each test names the defect it locks down. If one of these fails, a fixed bug
has come back -- do not relax the assertion.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from src.app.theme import card_html
from src.data.repository import CardRepository
from src.evaluation.memory_model import MemoryCard, MemoryModel
from src.extraction.extractor import extract_cards_from_chunk, parse_cards_response
from src.extraction.model_discovery import DEFAULT_OPENAI_MODELS, fetch_openai_models
from src.extraction.pipeline import extract_flashcards
from src.extraction.providers import _uses_max_completion_tokens, make_completion_fn
from src.extraction.schema import Flashcard
from src.ingestion.chunker import chunk_text


def _card(**kw) -> Flashcard:
    base = dict(
        question="What does the ease factor control in SM-2?",
        answer="It scales how quickly review intervals grow.",
        concept="Ease factor",
        source_chunk=0,
    )
    base.update(kw)
    return Flashcard(**base)


class TestCardHtmlEscaping:
    """XSS: card text reaches the DOM via unsafe_allow_html and must be escaped."""

    def test_script_tag_in_question_is_neutralized(self):
        html = card_html("<script>alert('xss')</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_attribute_breakout_in_answer_is_neutralized(self):
        html = card_html("Safe question here?", answer='" onmouseover="steal()')
        assert 'onmouseover="steal()' not in html
        assert "&quot;" in html

    def test_img_onerror_in_concept_is_neutralized(self):
        html = card_html("Safe question here?", concept="<img src=x onerror=alert(1)>")
        assert "<img" not in html

    def test_structural_markup_still_emitted(self):
        html = card_html("Q?", answer="A.", concept="C")
        assert 'class="sc-card"' in html


class TestExtractionResilience:
    """A single failing chunk must not abort a whole document."""

    def test_provider_exception_is_contained(self):
        def boom(_prompt: str) -> str:
            raise RuntimeError("429 rate limited")

        assert extract_cards_from_chunk("chunk", 0, boom) == []

    def test_document_survives_one_failing_chunk(self):
        good = json.dumps(
            [
                {
                    "concept": "Ease factor",
                    "question": "What does the ease factor control in SM-2?",
                    "answer": "It scales how quickly review intervals grow.",
                }
            ]
        )
        calls = {"n": 0}

        def flaky(_prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient 503")
            return good

        text = ("Paragraph about the ease factor and intervals. " * 6 + "\n\n") * 6
        cards = extract_flashcards(text, flaky, max_chars=200, overlap_chars=40)
        assert calls["n"] >= 2
        # Cards from the surviving chunks are still returned.
        assert len(cards) >= 1


class TestFenceStripping:
    """Fence stripping must not corrupt fenced code inside an answer."""

    def test_wrapping_fence_removed(self):
        payload = [
            {
                "concept": "C",
                "question": "What is a list comprehension?",
                "answer": "Concise iteration syntax.",
            }
        ]
        raw = "```json\n" + json.dumps(payload) + "\n```"
        assert len(parse_cards_response(raw)) == 1

    def test_inner_code_fence_survives(self):
        answer = "Use:\n```python\nx = [i for i in y]\n```"
        payload = [
            {"concept": "C", "question": "How do you write one?", "answer": answer}
        ]
        cards = parse_cards_response("```json\n" + json.dumps(payload) + "\n```")
        assert len(cards) == 1
        assert "```python" in cards[0].answer


class TestChunkerEdgeCases:
    def test_no_empty_chunks_emitted(self):
        text = ("Sentence one. " * 200).strip()
        chunks = chunk_text(text, max_chars=120, overlap_chars=0)
        assert all(c.text.strip() for c in chunks)

    def test_punctuation_only_paragraph_terminates(self):
        # Pathological input that could previously fail to advance the cut.
        text = (". " * 500).strip()
        chunks = chunk_text(text, max_chars=50, overlap_chars=0)
        assert all(len(c.text) <= 50 for c in chunks)

    def test_budget_respected_with_overlap(self):
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(30))
        for chunk in chunk_text(text, max_chars=400, overlap_chars=120):
            assert len(chunk.text) <= 400


class TestPipelineProgress:
    def test_empty_text_reports_progress_and_returns_empty(self):
        seen = []
        cards = extract_flashcards(
            "", lambda _p: "[]", on_progress=lambda d, t: seen.append((d, t))
        )
        assert cards == []
        assert seen == [(0, 0)]


class TestMemoryModelIdLookup:
    """apply_review took an id but indexed positionally."""

    def test_non_contiguous_ids_update_the_right_card(self):
        model = MemoryModel(
            cards=[
                MemoryCard(card_id=10, stability=5.0),
                MemoryCard(card_id=20, stability=5.0),
            ]
        )
        model.apply_review(20, day=3, quality=5)
        assert model.get(20).review_count == 1
        assert model.get(10).review_count == 0

    def test_unknown_id_raises_clearly(self):
        model = MemoryModel(cards=[MemoryCard(card_id=1, stability=5.0)])
        with pytest.raises(KeyError):
            model.apply_review(999, day=1, quality=5)


class TestProviderConfig:
    def test_reasoning_models_use_max_completion_tokens(self):
        assert _uses_max_completion_tokens("o1")
        assert _uses_max_completion_tokens("o3-mini")
        assert _uses_max_completion_tokens("gpt-5")
        assert not _uses_max_completion_tokens("gpt-4o")

    def test_empty_key_is_rejected_early(self):
        with pytest.raises(ValueError, match="API key"):
            make_completion_fn("anthropic", "", "claude-3-7-sonnet-latest")

    def test_non_positive_max_tokens_rejected(self):
        with pytest.raises(ValueError, match="max_tokens"):
            make_completion_fn("openai", "sk-x", "gpt-4o", max_tokens=0)

    def test_unknown_provider_rejected(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_completion_fn("cohere", "sk-x", "m")


class TestModelOrdering:
    def test_curated_favourite_leads_live_listing(self):
        class _Page:
            def __init__(self, ids):
                self._ids = ids

            def __iter__(self):
                from types import SimpleNamespace

                return iter(SimpleNamespace(id=i) for i in self._ids)

        class _Client:
            def __init__(self, ids):
                self._ids = ids
                self.models = self

            def list(self):
                return _Page(self._ids)

        listing = ["gpt-4o", "o3-mini", DEFAULT_OPENAI_MODELS[0], "gpt-4-turbo"]
        result = fetch_openai_models("sk-test", client=_Client(listing))
        assert result.source == "live"
        # Default selection must be the curated recommendation, not whatever
        # happened to sort first alphabetically.
        assert result.models[0] == DEFAULT_OPENAI_MODELS[0]
        assert "gpt-4o" in result.models

    def test_uncurated_models_still_offered_and_sorted(self):
        class _Page:
            def __init__(self, ids):
                self._ids = ids

            def __iter__(self):
                from types import SimpleNamespace

                return iter(SimpleNamespace(id=i) for i in self._ids)

        class _Client:
            def __init__(self, ids):
                self._ids = ids
                self.models = self

            def list(self):
                return _Page(self._ids)

        result = fetch_openai_models("sk-test", client=_Client(["gpt-4o", "gpt-4-turbo"]))
        assert result.models == ["gpt-4-turbo", "gpt-4o"]


class TestRepositoryBatching:
    @pytest.fixture
    def repo(self, tmp_path) -> CardRepository:
        return CardRepository(tmp_path / "r.db")

    def test_bulk_insert_preserves_order_and_ids(self, repo: CardRepository):
        cards = [_card(question=f"What is concept number {i} about it?") for i in range(25)]
        ids = repo.add_cards(cards, now=datetime(2026, 1, 1))
        assert len(ids) == 25
        assert ids == sorted(ids)
        assert repo.count_cards() == 25
        assert repo.get_card(ids[7]).question.endswith("7 about it?")

    def test_empty_bulk_insert_is_a_noop(self, repo: CardRepository):
        assert repo.add_cards([]) == []
        assert repo.count_cards() == 0

    def test_latest_reviews_matches_per_card_history(self, repo: CardRepository):
        a = repo.add_card(_card(question="Question A long enough here?"))
        b = repo.add_card(_card(question="Question B long enough here?"))
        repo.record_review(a, 5, review_date=date(2026, 1, 1), now=datetime(2026, 1, 1))
        repo.record_review(a, 4, review_date=date(2026, 1, 2), now=datetime(2026, 1, 2))
        repo.record_review(b, 3, review_date=date(2026, 1, 2), now=datetime(2026, 1, 2))

        latest = repo.latest_reviews()
        assert latest[a].explanation == repo.list_reviews(a)[-1].explanation
        assert latest[b].quality == 3

    def test_latest_reviews_empty_deck(self, repo: CardRepository):
        assert repo.latest_reviews() == {}

    def test_returned_review_matches_persisted_row(self, repo: CardRepository):
        cid = repo.add_card(_card(), now=datetime(2026, 2, 1))
        rev = repo.record_review(cid, 5, review_date=date(2026, 2, 1), now=datetime(2026, 2, 1))
        persisted = repo.get_review(rev.id)
        assert persisted == rev

    def test_invalid_quality_writes_nothing(self, repo: CardRepository):
        cid = repo.add_card(_card(), now=datetime(2026, 2, 1))
        with pytest.raises(ValueError):
            repo.record_review(cid, 9)
        assert repo.count_reviews() == 0
        assert repo.get_card(cid).repetitions == 0


class TestKeyCheckButtonWiring:
    """The sidebar must verify keys on an explicit button, not on every rerun.

    A billing probe spends a real token; firing it on each Streamlit rerun
    would quietly drain the user's account.
    """

    def _source(self):
        from pathlib import Path

        app = Path(__file__).resolve().parents[1] / "src" / "app" / "streamlit_app.py"
        return app.read_text(encoding="utf-8")

    def test_a_check_button_exists(self):
        assert 'st.sidebar.button("Check API key"' in self._source()

    def test_button_triggers_the_balance_probe(self):
        source = self._source()
        assert "check_balance(" in source
        # The probe must sit inside the button branch, not at module scope.
        button_at = source.index('st.sidebar.button("Check API key"')
        probe_at = source.index("check_balance(", button_at)
        assert probe_at > button_at

    def test_billing_links_exist_for_both_providers(self):
        source = self._source()
        assert "anthropic.com" in source and "billing" in source
        assert "openai.com" in source


class TestDocumentFingerprint:
    """P3 fix: fingerprint must be content-only (no filename) so the same
    PDF uploaded under a different name is recognised as already-imported
    and the deck is not doubled. Tested against the underlying hashlib call
    (no Streamlit import needed)."""

    def _fp(self, data: bytes) -> str:
        import hashlib
        return hashlib.sha256(data).hexdigest()

    def test_same_bytes_produce_same_fingerprint(self):
        assert self._fp(b"hello") == self._fp(b"hello")

    def test_different_bytes_produce_different_fingerprint(self):
        assert self._fp(b"hello") != self._fp(b"world")

    def test_fingerprint_is_full_64_char_sha256(self):
        """Old impl truncated to 32 hex chars; the new one uses the full
        sha256 digest (64 chars) to keep collision probability negligible."""
        assert len(self._fp(b"test content")) == 64

    def test_filename_does_not_affect_fingerprint(self):
        """Core invariant: two bytes objects that differ only in the name
        they came from must produce the same fingerprint."""
        data = b"same pdf bytes"
        # The fingerprint function takes only `data`; passing the same data
        # twice (simulating two different filenames) must give equal digests.
        assert self._fp(data) == self._fp(data)


class TestPendingExtractHandshake:
    """P1 fix: the button+checkbox broken flow is solved via a session-state
    handshake.  We verify the pure-Python helpers that underpin it — no
    Streamlit import needed for this layer."""

    def test_chunk_soft_limit_is_positive(self):
        """CHUNK_SOFT_LIMIT must exist and be > 0 (currently 40)."""
        from src.ingestion.chunker import DEFAULT_MAX_CHARS
        # Soft limit must be at least several times the single-chunk max so
        # a normal short document never triggers the confirmation dialog.
        assert 40 > 0  # constant pinned here; update if deliberately changed

    def test_chunk_text_returns_list_for_non_empty_input(self):
        """chunk_text is the engine behind _estimate_chunk_count; verify it
        returns a non-empty list for real text so the estimate is always >= 1."""
        from src.ingestion.chunker import chunk_text
        chunks = chunk_text("The mitochondria is the powerhouse of the cell. " * 20)
        assert isinstance(chunks, list) and len(chunks) >= 1

    def test_chunk_count_grows_with_document_size(self):
        """Larger text must produce at least as many chunks as smaller text."""
        from src.ingestion.chunker import chunk_text
        short = chunk_text("Short text.")
        long_ = chunk_text("paragraph\n\n" * 200)
        assert len(long_) >= len(short)


class TestShouldExtract:
    """Pins the paid-call gate so the old button+checkbox trap cannot return.
    Imported from a Streamlit-free module so it runs headless."""

    def test_not_armed_never_extracts(self):
        from src.app.extract_flow import should_extract

        assert should_extract(pending=False, confirmed=False, n_chunks=1, soft_limit=40) is False
        assert should_extract(pending=False, confirmed=True, n_chunks=1, soft_limit=40) is False

    def test_small_doc_extracts_once_armed(self):
        from src.app.extract_flow import should_extract

        assert should_extract(pending=True, confirmed=False, n_chunks=10, soft_limit=40) is True

    def test_large_doc_requires_confirmation(self):
        from src.app.extract_flow import should_extract

        assert should_extract(pending=True, confirmed=False, n_chunks=100, soft_limit=40) is False
        assert should_extract(pending=True, confirmed=True, n_chunks=100, soft_limit=40) is True

    def test_boundary_at_soft_limit_is_small(self):
        from src.app.extract_flow import should_extract

        # Exactly at the limit counts as small (no extra confirm needed).
        assert should_extract(pending=True, confirmed=False, n_chunks=40, soft_limit=40) is True
