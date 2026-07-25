"""Deck export helpers (stdlib only).

Two formats:
* JSON - full fidelity (all card fields, optionally review history). Intended
  for backup / programmatic re-import.
* TSV  - Anki-friendly ``question<TAB>answer<TAB>concept``. Anki's "Basic"
  note type imports tab-separated files directly.

These operate on the repository's ``StoredCard`` / ``StoredReview`` dataclasses,
so callers pass exactly what ``list_cards`` / ``list_reviews`` return. No
secrets (API keys etc.) ever touch these structures, so exports are safe to
hand to a user as a download.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Optional, Sequence

from src.data.repository import StoredCard, StoredReview


def _card_to_dict(card: StoredCard) -> dict:
    return {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "concept": card.concept,
        "source_chunk": card.source_chunk,
        "ease_factor": card.ease_factor,
        "repetitions": card.repetitions,
        "interval_days": card.interval_days,
        "due_date": card.due_date.isoformat() if card.due_date else None,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


def _review_to_dict(r: StoredReview) -> dict:
    return {
        "id": r.id,
        "card_id": r.card_id,
        "quality": r.quality,
        "ease_factor_before": r.ease_factor_before,
        "ease_factor_after": r.ease_factor_after,
        "interval_before": r.interval_before,
        "interval_after": r.interval_after,
        "repetitions_before": r.repetitions_before,
        "repetitions_after": r.repetitions_after,
        "explanation": r.explanation,
        "reviewed_at": r.reviewed_at.isoformat(),
    }


def cards_to_json(
    cards: Sequence[StoredCard],
    reviews: Optional[Sequence[StoredReview]] = None,
    *,
    indent: int = 2,
) -> str:
    """Serialize cards (and optionally reviews) to a JSON string.

    ``ensure_ascii=False`` keeps Cyrillic / Uzbek text human-readable in the
    export rather than escaping it to \\uXXXX.
    """
    payload = {"cards": [_card_to_dict(c) for c in cards]}
    if reviews is not None:
        payload["reviews"] = [_review_to_dict(r) for r in reviews]
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def _flatten(text: str) -> str:
    """Collapse any whitespace run (incl. tabs/newlines) to a single space so
    each card stays on exactly one TSV line (Anki = one note per line)."""
    return " ".join(text.split())


def cards_to_tsv(cards: Sequence[StoredCard], *, include_concept: bool = True) -> str:
    """Tab-separated ``question<TAB>answer[<TAB>concept]`` with a header row."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
    header = ["question", "answer"] + (["concept"] if include_concept else [])
    writer.writerow(header)
    for c in cards:
        row = [_flatten(c.question), _flatten(c.answer)]
        if include_concept:
            row.append(_flatten(c.concept))
        writer.writerow(row)
    return buf.getvalue()
