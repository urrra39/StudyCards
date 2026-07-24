"""End-to-end extraction pipeline: document text -> filtered flashcards."""
from __future__ import annotations

from typing import Callable, List, Optional

from src.extraction.extractor import (
    MAX_CARDS_PER_CHUNK,
    CompletionFn,
    extract_cards_from_chunk,
)
from src.extraction.filtering import JACCARD_THRESHOLD, filter_cards
from src.extraction.schema import Flashcard
from src.ingestion.chunker import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_text


def extract_flashcards(
    text: str,
    complete: CompletionFn,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    on_progress: Optional[Callable[[int, int], None]] = None,
    max_cards_per_chunk: int = MAX_CARDS_PER_CHUNK,
    dedup_threshold: float = JACCARD_THRESHOLD,
) -> List[Flashcard]:
    """Chunk -> extract per chunk -> global quality filter + dedup.

    Dedup runs globally (across all chunks), not per chunk: the whole point
    of chunk overlap is that boundary concepts appear twice, and only a
    global pass can remove that second copy.

    Args:
        on_progress: Optional callback (done_chunks, total_chunks) so the UI
            can show live progress during multi-chunk extraction.
    """
    chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
    total = len(chunks)
    if total == 0:
        # Report completion so a UI progress bar does not hang at 0%.
        if on_progress:
            on_progress(0, 0)
        return []

    candidates: List[Flashcard] = []
    for i, chunk in enumerate(chunks):
        candidates.extend(
            extract_cards_from_chunk(
                chunk.text, chunk.index, complete, max_cards=max_cards_per_chunk
            )
        )
        # Progress is reported even when a chunk yields nothing, so a run of
        # empty chunks still advances the bar.
        if on_progress:
            on_progress(i + 1, total)
    return filter_cards(candidates, threshold=dedup_threshold)
