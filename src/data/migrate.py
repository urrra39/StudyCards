"""Lightweight forward-only schema migrations for the SQLite database.

Why this exists
---------------
The original schema used ``CREATE TABLE IF NOT EXISTS`` only. That is fine for a
*fresh* database but does nothing for an *existing* one, so a database created
before a new table/column was introduced would never gain it, and code
expecting the new shape would fail at query time.

Design
------
* ``schema_meta`` holds a single integer ``version`` row: the highest migration
  applied to this database.
* ``MIGRATIONS`` maps a target version -> a function that upgrades a database
  from ``version - 1`` to ``version``. They run in ascending order.
* Every migration is idempotent (``IF NOT EXISTS`` etc.) so a half-applied or
  re-run migration cannot corrupt the database.
* This is a deliberately tiny hand-rolled migrator (stdlib only) rather than a
  dependency like Alembic: the schema is small and the project must stay
  zero-config.

Version history
---------------
* v1 - base schema: ``cards`` + ``review_history`` + their indexes.
* v2 - ``ingested_documents`` (cross-session ingest dedup).
"""
from __future__ import annotations

import sqlite3

from src.data.schema import SCHEMA_VERSION


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")


def _read_version(conn: sqlite3.Connection) -> int:
    """Best-effort detection of the version already on disk.

    - schema_meta present -> trust its stored version.
    - no schema_meta but ``cards`` exists -> a legacy DB created before this
      migrator existed; treat it as v1 so later migrations still apply.
    - nothing at all -> brand-new DB at v0.
    """
    if _table_exists(conn, "schema_meta"):
        row = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        return int(row[0]) if row is not None else 0
    return 1 if _table_exists(conn, "cards") else 0


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_meta")
    conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (version,))


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    """Base schema. Mirrors SCHEMA_SQL's core tables so ``migrate`` alone can
    build a usable database from nothing (used by tests and any future
    non-Streamlit entry point)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            concept TEXT NOT NULL,
            source_chunk INTEGER,
            ease_factor REAL NOT NULL DEFAULT 2.5,
            repetitions INTEGER NOT NULL DEFAULT 0,
            interval_days INTEGER NOT NULL DEFAULT 0,
            due_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL,
            quality INTEGER NOT NULL CHECK (quality BETWEEN 0 AND 5),
            ease_factor_before REAL NOT NULL,
            ease_factor_after REAL NOT NULL,
            interval_before INTEGER NOT NULL,
            interval_after INTEGER NOT NULL,
            repetitions_before INTEGER NOT NULL,
            repetitions_after INTEGER NOT NULL,
            explanation TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_cards_due_date ON cards(due_date);
        CREATE INDEX IF NOT EXISTS idx_history_card_id ON review_history(card_id);
        CREATE INDEX IF NOT EXISTS idx_history_reviewed_at ON review_history(reviewed_at);
        """
    )


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Add the cross-session ingest dedup table. This is the concrete example
    of a table that legacy databases (created before Phase 16) are missing."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingested_documents (
            fingerprint TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            card_count INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );
        """
    )


# target version -> upgrade function (applied in ascending order)
MIGRATIONS = {
    1: _migrate_to_v1,
    2: _migrate_to_v2,
}


def migrate(conn: sqlite3.Connection) -> int:
    """Bring ``conn`` up to ``SCHEMA_VERSION``. Returns the resulting version.

    Idempotent: running it on an already-current database is a no-op that still
    guarantees ``schema_meta`` exists and is stamped. Safe on every startup.
    Each migration + its version bump commit together, so an interrupted run
    never leaves a half-migrated database marked as complete.
    """
    current = _read_version(conn)
    _ensure_meta(conn)
    for version in range(current + 1, SCHEMA_VERSION + 1):
        MIGRATIONS[version](conn)
        _set_version(conn, version)
        conn.commit()
    if current >= SCHEMA_VERSION:
        # Nothing to apply (e.g. a fresh DB already built by SCHEMA_SQL, or a
        # repeat call); make sure the version row is present and correct.
        _set_version(conn, current)
        conn.commit()
    return _read_version(conn)
