"""SQLite schema for flashcards and full review history.

Design notes:
* ``review_history`` is the source of truth for *what happened*; ``cards``
  holds the *current* SM-2 state for fast due-date queries. Every review
  writes both in one transaction so they cannot diverge.
* Dates are ISO-8601 text (``YYYY-MM-DD`` / ``YYYY-MM-DDTHH:MM:SS``) —
  SQLite has no native date type, and text sorts correctly for range scans.
* ``ON DELETE CASCADE`` on history so removing a card never leaves orphans.
"""
from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question        TEXT    NOT NULL,
    answer          TEXT    NOT NULL,
    concept         TEXT    NOT NULL,
    source_chunk    INTEGER,
    ease_factor     REAL    NOT NULL DEFAULT 2.5,
    repetitions     INTEGER NOT NULL DEFAULT 0,
    interval_days   INTEGER NOT NULL DEFAULT 0,
    due_date        TEXT,                          -- ISO date YYYY-MM-DD
    created_at      TEXT    NOT NULL,              -- ISO datetime
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS review_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id              INTEGER NOT NULL,
    quality              INTEGER NOT NULL CHECK (quality BETWEEN 0 AND 5),
    ease_factor_before   REAL    NOT NULL,
    ease_factor_after    REAL    NOT NULL,
    interval_before      INTEGER NOT NULL,
    interval_after       INTEGER NOT NULL,
    repetitions_before   INTEGER NOT NULL,
    repetitions_after    INTEGER NOT NULL,
    explanation          TEXT    NOT NULL,
    reviewed_at          TEXT    NOT NULL,         -- ISO datetime
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

-- Documents already imported, keyed by a content hash of the upload. This is
-- what makes ingestion idempotent ACROSS sessions and restarts: the old
-- in-memory guard forgot everything on a Streamlit rerun, so re-uploading the
-- same PDF silently doubled the deck. ``fingerprint`` is name + sha256(bytes).
CREATE TABLE IF NOT EXISTS ingested_documents (
    fingerprint   TEXT    PRIMARY KEY,
    filename      TEXT    NOT NULL,
    card_count    INTEGER NOT NULL,
    imported_at   TEXT    NOT NULL              -- ISO datetime
);

CREATE INDEX IF NOT EXISTS idx_cards_due_date ON cards(due_date);
CREATE INDEX IF NOT EXISTS idx_history_card_id ON review_history(card_id);
CREATE INDEX IF NOT EXISTS idx_history_reviewed_at ON review_history(reviewed_at);
"""
