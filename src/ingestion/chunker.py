"""Paragraph-aware overlap chunking.

CHUNKING STRATEGY
-----------------
Goal: give the LLM chunks that are (a) large enough to contain whole
concepts, (b) small enough to keep extraction focused, and (c) overlapping
enough that a concept straddling a boundary appears intact in at least one
chunk.

Design choices:
* **Paragraph-first packing.** Text is split on blank lines and paragraphs
  are greedily packed into chunks up to ``max_chars``. Splitting mid-sentence
  produces fragments the LLM turns into low-quality or hallucinated cards, so
  we only fall back to a hard character split for pathological paragraphs
  longer than a whole chunk.
* **Character budgets, not tokens.** A tokenizer dependency buys little here:
  the budget only controls granularity, and ~4 chars/token makes 4 000 chars
  ≈ 1 000 tokens — comfortably inside any model's context.
* **Tail overlap.** Each chunk starts with the last ``overlap_chars`` of the
  previous chunk (snapped back to a paragraph boundary when possible). The
  extraction stage deduplicates cards, so the cost of overlap is a few
  duplicate candidates — much cheaper than silently losing a boundary concept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

DEFAULT_MAX_CHARS = 4000
DEFAULT_OVERLAP_CHARS = 400


@dataclass(frozen=True)
class Chunk:
    """One extraction unit handed to the LLM."""

    index: int
    text: str


def chunk_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[Chunk]:
    """Split normalized text into overlapping, paragraph-aligned chunks.

    Args:
        text: Normalized document text (see ``loader.normalize_text``).
        max_chars: Upper bound on chunk length.
        overlap_chars: Approximate tail of the previous chunk repeated at the
            start of the next one. Must be < max_chars.

    Returns:
        Ordered list of chunks covering the full document.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars must satisfy 0 <= overlap < max_chars")

    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [Chunk(index=0, text=text)]

    paragraphs = _split_paragraphs(text, max_chars)

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for para in paragraphs:
        # +2 accounts for the "\n\n" joiner between packed paragraphs.
        added = len(para) + (2 if current else 0)
        if current and current_len + added > max_chars:
            chunks.append("\n\n".join(current))
            carry = _overlap_tail("\n\n".join(current), overlap_chars)
            # Overlap is best-effort: drop it when carry+para would breach
            # max_chars (e.g. a near-budget paragraph after a large carry).
            if carry and len(carry) + 2 + len(para) <= max_chars:
                current = [carry]
                current_len = len(carry)
            else:
                current = []
                current_len = 0
            added = len(para) + (2 if current else 0)
        current.append(para)
        current_len += added
    if current:
        chunks.append("\n\n".join(current))

    return [Chunk(index=i, text=c) for i, c in enumerate(chunks)]


def _split_paragraphs(text: str, max_chars: int) -> List[str]:
    """Split on blank lines; hard-split any paragraph exceeding max_chars."""
    paragraphs: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > max_chars:
            # Prefer breaking at the last sentence end inside the budget;
            # fall back to a raw cut only if there is none.
            window = para[:max_chars]
            matches = list(re.finditer(r"[.!?]\s", window))
            cut = matches[-1].end() if matches else max_chars
            head = para[:cut].strip()
            if head:
                paragraphs.append(head)
            remainder = para[cut:].strip()
            # Guard against a non-advancing cut. If the sentence-boundary cut
            # produced no forward progress (all-whitespace head), fall back to
            # a hard cut so the loop cannot spin forever on pathological input.
            if len(remainder) >= len(para):
                head = para[:max_chars].strip()
                if head:
                    paragraphs.append(head)
                remainder = para[max_chars:].strip()
            para = remainder
        if para:
            paragraphs.append(para)
    return paragraphs


def _overlap_tail(chunk: str, overlap_chars: int) -> str:
    """Take the trailing ~overlap_chars of a chunk for carry-over.

    Snap the start of the tail forward to the nearest paragraph boundary so
    the carried context begins mid-document, not mid-word. If the chunk is a
    single huge paragraph, snap to a word boundary instead.
    """
    if overlap_chars == 0 or len(chunk) <= overlap_chars:
        return chunk if overlap_chars else ""
    tail = chunk[-overlap_chars:]
    para_break = tail.find("\n\n")
    if para_break != -1:
        return tail[para_break + 2 :].strip()
    space = tail.find(" ")
    return tail[space + 1 :].strip() if space != -1 else tail
