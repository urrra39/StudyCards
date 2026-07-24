"""SQLite persistence: cards + review history as the source of truth."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, List, Optional, Union

from src.data.schema import SCHEMA_SQL
from src.extraction.schema import Flashcard
from src.scheduler.sm2 import CardState, review

PathLike = Union[str, Path]


@dataclass(frozen=True)
class StoredCard:
    """A flashcard row joined with its current SM-2 scheduling state."""

    id: int
    question: str
    answer: str
    concept: str
    source_chunk: Optional[int]
    ease_factor: float
    repetitions: int
    interval_days: int
    due_date: Optional[date]
    created_at: datetime
    updated_at: datetime

    def to_card_state(self) -> CardState:
        return CardState(
            ease_factor=self.ease_factor,
            repetitions=self.repetitions,
            interval_days=self.interval_days,
            due_date=self.due_date,
        )


@dataclass(frozen=True)
class StoredReview:
    """One immutable row from ``review_history``."""

    id: int
    card_id: int
    quality: int
    ease_factor_before: float
    ease_factor_after: float
    interval_before: int
    interval_after: int
    repetitions_before: int
    repetitions_after: int
    explanation: str
    reviewed_at: datetime


def _parse_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _card_from_row(row: sqlite3.Row) -> StoredCard:
    return StoredCard(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        concept=row["concept"],
        source_chunk=row["source_chunk"],
        ease_factor=row["ease_factor"],
        repetitions=row["repetitions"],
        interval_days=row["interval_days"],
        due_date=_parse_date(row["due_date"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


def _review_from_row(row: sqlite3.Row) -> StoredReview:
    return StoredReview(
        id=row["id"],
        card_id=row["card_id"],
        quality=row["quality"],
        ease_factor_before=row["ease_factor_before"],
        ease_factor_after=row["ease_factor_after"],
        interval_before=row["interval_before"],
        interval_after=row["interval_after"],
        repetitions_before=row["repetitions_before"],
        repetitions_after=row["repetitions_after"],
        explanation=row["explanation"],
        reviewed_at=_parse_datetime(row["reviewed_at"]),
    )


class CardRepository:
    """Thin SQLite repository. One connection per operation (safe for Streamlit)."""

    def __init__(self, db_path: PathLike):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create tables/indexes if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def add_card(
        self,
        card: Flashcard,
        *,
        due_date: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """Insert one card with default SM-2 state. Returns the new row id."""
        when = now or datetime.now()
        due = due_date or when.date()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO cards (
                    question, answer, concept, source_chunk,
                    ease_factor, repetitions, interval_days, due_date,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 2.5, 0, 0, ?, ?, ?)
                """,
                (
                    card.question,
                    card.answer,
                    card.concept,
                    card.source_chunk,
                    due.isoformat(),
                    when.isoformat(timespec="seconds"),
                    when.isoformat(timespec="seconds"),
                ),
            )
            return int(cur.lastrowid)

    def add_cards(self, cards: List[Flashcard], *, now: Optional[datetime] = None) -> List[int]:
        """Bulk-insert cards; returns ids in the same order."""
        return [self.add_card(c, now=now) for c in cards]

    def get_card(self, card_id: int) -> Optional[StoredCard]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _card_from_row(row) if row else None

    def list_cards(self) -> List[StoredCard]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cards ORDER BY id").fetchall()
        return [_card_from_row(r) for r in rows]

    def list_due_cards(self, on: Optional[date] = None) -> List[StoredCard]:
        """Cards whose ``due_date`` is on or before ``on`` (default: today)."""
        day = (on or date.today()).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM cards
                WHERE due_date IS NULL OR due_date <= ?
                ORDER BY due_date ASC, id ASC
                """,
                (day,),
            ).fetchall()
        return [_card_from_row(r) for r in rows]

    def record_review(
        self,
        card_id: int,
        quality: int,
        *,
        review_date: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> StoredReview:
        """Apply SM-2, update the card, and append an immutable history row.

        Card state and history are written in a single transaction so a crash
        mid-review cannot leave them inconsistent.
        """
        when = now or datetime.now()
        day = review_date or when.date()

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
            if row is None:
                raise KeyError(f"card id {card_id} not found")

            stored = _card_from_row(row)
            result = review(stored.to_card_state(), quality, review_date=day)
            new = result.state

            conn.execute(
                """
                UPDATE cards SET
                    ease_factor = ?,
                    repetitions = ?,
                    interval_days = ?,
                    due_date = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new.ease_factor,
                    new.repetitions,
                    new.interval_days,
                    new.due_date.isoformat() if new.due_date else None,
                    when.isoformat(timespec="seconds"),
                    card_id,
                ),
            )
            cur = conn.execute(
                """
                INSERT INTO review_history (
                    card_id, quality,
                    ease_factor_before, ease_factor_after,
                    interval_before, interval_after,
                    repetitions_before, repetitions_after,
                    explanation, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    quality,
                    result.previous_ease_factor,
                    new.ease_factor,
                    result.previous_interval_days,
                    new.interval_days,
                    result.previous_repetitions,
                    new.repetitions,
                    result.explanation,
                    when.isoformat(timespec="seconds"),
                ),
            )
            history_id = int(cur.lastrowid)

        stored_review = self.get_review(history_id)
        assert stored_review is not None
        return stored_review

    def get_review(self, review_id: int) -> Optional[StoredReview]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_history WHERE id = ?", (review_id,)
            ).fetchone()
        return _review_from_row(row) if row else None

    def list_reviews(self, card_id: int) -> List[StoredReview]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM review_history
                WHERE card_id = ?
                ORDER BY reviewed_at ASC, id ASC
                """,
                (card_id,),
            ).fetchall()
        return [_review_from_row(r) for r in rows]

    def count_cards(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0])

    def count_reviews(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM review_history").fetchone()[0])

    def delete_card(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
