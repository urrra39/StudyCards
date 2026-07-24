"""Document loading: PDF and plain-text sources normalized to clean text.

The loader is deliberately format-thin: it produces a single normalized
string and leaves all segmentation decisions to the chunker, so the two
concerns can be tested independently.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Union

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".txt", ".md"})


class UnsupportedFormatError(ValueError):
    """Raised when a file extension is not one we know how to ingest."""


def load_document(source: Union[str, Path, bytes], filename: str = "") -> str:
    """Load a document into normalized plain text.

    Args:
        source: A filesystem path, or raw bytes (e.g. a Streamlit upload).
        filename: Required when ``source`` is bytes, to determine the format.

    Returns:
        Normalized text (see :func:`normalize_text`).

    Raises:
        UnsupportedFormatError: For extensions outside SUPPORTED_EXTENSIONS.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        data = path.read_bytes()
    else:
        suffix = Path(filename).suffix.lower()
        data = source

    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Unsupported format {suffix!r}; expected one of {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if suffix == ".pdf":
        raw = _extract_pdf_text(data)
    else:
        # errors="replace" so a stray non-UTF-8 byte degrades to U+FFFD
        # instead of failing the whole upload.
        raw = data.decode("utf-8", errors="replace")

    return normalize_text(raw)


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from PDF bytes, page by page.

    pypdf (pure Python, no native deps) was chosen over pdfplumber because we
    only need running text, not table geometry — and it keeps the install
    footprint small for Streamlit Cloud.
    """
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    # Double newline between pages so page boundaries survive as paragraph
    # breaks, which the chunker treats as preferred split points.
    return "\n\n".join(pages)


def normalize_text(text: str) -> str:
    """Clean up extraction artifacts without altering content.

    Three transformations, each targeting a specific PDF artifact:
    1. De-hyphenate words split across line breaks ("infor-\\nmation") —
       common in justified academic PDFs and poison for LLM extraction.
    2. Collapse runs of 3+ newlines to exactly 2 (one paragraph break).
    3. Collapse horizontal whitespace runs (PDF column extraction often
       emits long space runs where columns were).
    """
    # Normalize newlines first so later patterns only need to match `\n`.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
