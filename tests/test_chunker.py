"""Tests for paragraph-aware overlap chunking."""
import pytest

from src.ingestion.chunker import Chunk, chunk_text


def make_paragraphs(n: int, size: int = 200) -> str:
    """n distinct paragraphs of ~size chars each, individually identifiable."""
    return "\n\n".join(f"Paragraph {i:03d}. " + ("word " * ((size - 20) // 5)) for i in range(n))


class TestChunkText:
    def test_empty_input_yields_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []

    def test_short_text_is_single_chunk(self):
        text = "One small paragraph."
        # Explicit overlap: default 400 would be invalid against max_chars=100.
        assert chunk_text(text, max_chars=100, overlap_chars=20) == [
            Chunk(index=0, text=text)
        ]

    def test_chunks_respect_max_chars(self):
        text = make_paragraphs(20)
        for chunk in chunk_text(text, max_chars=500, overlap_chars=100):
            assert len(chunk.text) <= 500

    def test_full_coverage_no_paragraph_lost(self):
        text = make_paragraphs(20)
        chunks = chunk_text(text, max_chars=500, overlap_chars=100)
        combined = "\n".join(c.text for c in chunks)
        for i in range(20):
            assert f"Paragraph {i:03d}." in combined

    def test_indices_are_sequential(self):
        chunks = chunk_text(make_paragraphs(20), max_chars=500, overlap_chars=50)
        assert [c.index for c in chunks] == list(range(len(chunks)))

    def test_overlap_carries_tail_content(self):
        text = make_paragraphs(20)
        chunks = chunk_text(text, max_chars=500, overlap_chars=250)
        assert len(chunks) >= 2
        # The start of chunk N must repeat content from chunk N-1.
        for prev, curr in zip(chunks, chunks[1:]):
            head = curr.text[:250]
            assert head.split("\n\n")[0] in prev.text

    def test_zero_overlap_produces_disjoint_chunks(self):
        text = make_paragraphs(10)
        chunks = chunk_text(text, max_chars=500, overlap_chars=0)
        seen = set()
        for chunk in chunks:
            first_para = chunk.text.split("\n\n")[0]
            assert first_para not in seen
            seen.update(chunk.text.split("\n\n"))

    def test_giant_paragraph_hard_split_at_sentence(self):
        # One paragraph 3x the budget, with sentence boundaries available.
        text = ("This is sentence number one. " * 60).strip()
        chunks = chunk_text(text, max_chars=400, overlap_chars=0)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) <= 400
            # sentence-preferred splitting means no chunk starts mid-word
            assert not chunk.text[0].islower() or chunk.text.startswith("word")

    def test_invalid_parameters_raise(self):
        with pytest.raises(ValueError):
            chunk_text("text", max_chars=0)
        with pytest.raises(ValueError):
            chunk_text("text", max_chars=100, overlap_chars=100)
        with pytest.raises(ValueError):
            chunk_text("text", max_chars=100, overlap_chars=-1)
