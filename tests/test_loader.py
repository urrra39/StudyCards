"""Tests for document loading and text normalization."""
import io

import pytest
from pypdf import PdfWriter

from src.ingestion.loader import UnsupportedFormatError, load_document, normalize_text


class TestNormalizeText:
    def test_dehyphenates_line_break_splits(self):
        assert normalize_text("infor-\nmation theory") == "information theory"

    def test_preserves_real_hyphens(self):
        # A hyphen not followed by a newline is meaningful and must survive.
        assert normalize_text("state-of-the-art") == "state-of-the-art"

    def test_collapses_excess_blank_lines(self):
        assert normalize_text("para one\n\n\n\npara two") == "para one\n\npara two"

    def test_collapses_horizontal_whitespace(self):
        assert normalize_text("wide    gap\tand tab") == "wide gap and tab"

    def test_strips_leading_trailing(self):
        assert normalize_text("\n\n  centered  \n\n") == "centered"

    def test_normalizes_windows_newlines(self):
        assert normalize_text("line one\r\n\r\nline two") == "line one\n\nline two"


class TestLoadDocument:
    def test_loads_txt_bytes(self):
        text = load_document(b"hello   world", filename="notes.txt")
        assert text == "hello world"

    def test_loads_md_from_path(self, tmp_path):
        p = tmp_path / "notes.md"
        p.write_text("# Title\n\nBody text", encoding="utf-8")
        assert load_document(p) == "# Title\n\nBody text"

    def test_rejects_unsupported_extension(self):
        with pytest.raises(UnsupportedFormatError):
            load_document(b"data", filename="slides.pptx")

    def test_pdf_route_handles_textless_pages(self):
        # A generated blank-page PDF exercises the pypdf path end-to-end;
        # extract_text() returning nothing must yield "" and not crash.
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        assert load_document(buf.getvalue(), filename="empty.pdf") == ""

    def test_tolerates_invalid_utf8(self):
        # Latin-1 byte in a .txt upload must degrade, not raise.
        text = load_document(b"caf\xe9 notes", filename="notes.txt")
        assert "caf" in text and "notes" in text
