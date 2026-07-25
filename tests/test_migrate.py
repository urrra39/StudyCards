"""Tests for the schema migration mechanism (src/data/migrate.py)."""
from __future__ import annotations

import sqlite3

from src.data.migrate import _read_version, migrate
from src.data.repository import CardRepository
from src.data.schema import SCHEMA_VERSION
from src.extraction.schema import Flashcard


def _table_names(conn: sqlite3.Connection):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


class TestFreshDatabase:
    def test_initialize_stamps_current_version(self, tmp_path):
        CardRepository(tmp_path / "fresh.db")  # constructor calls initialize()
        with sqlite3.connect(tmp_path / "fresh.db") as conn:
            assert _read_version(conn) == SCHEMA_VERSION

    def test_migrate_builds_usable_db_from_nothing(self, tmp_path):
        # migrate() alone (without SCHEMA_SQL) must yield a working schema.
        conn = sqlite3.connect(tmp_path / "scratch.db")
        assert migrate(conn) == SCHEMA_VERSION
        assert {"cards", "review_history", "ingested_documents"} <= _table_names(conn)
        conn.close()


class TestLegacyUpgrade:
    def _make_legacy_v1(self, path) -> sqlite3.Connection:
        """A DB that predates ingested_documents and schema_meta (i.e. v1)."""
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE cards (
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
            CREATE TABLE review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                quality INTEGER NOT NULL,
                ease_factor_before REAL NOT NULL,
                ease_factor_after REAL NOT NULL,
                interval_before INTEGER NOT NULL,
                interval_after INTEGER NOT NULL,
                repetitions_before INTEGER NOT NULL,
                repetitions_after INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                reviewed_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        return conn

    def test_legacy_db_detected_as_v1(self, tmp_path):
        conn = self._make_legacy_v1(tmp_path / "legacy.db")
        assert _read_version(conn) == 1
        conn.close()

    def test_upgrade_adds_missing_table_and_stays_usable(self, tmp_path):
        path = tmp_path / "legacy.db"
        conn = self._make_legacy_v1(path)
        assert "ingested_documents" not in _table_names(conn)
        assert migrate(conn) == SCHEMA_VERSION
        assert "ingested_documents" in _table_names(conn)
        conn.close()

        # The upgraded DB works through the normal repository API.
        repo = CardRepository(path)  # idempotent initialize on migrated DB
        card_id = repo.add_card(
            Flashcard(
                question="Does the upgraded DB still accept new cards?",
                answer="Yes, it remains fully usable.",
                concept="Migration",
            )
        )
        assert repo.get_card(card_id) is not None
        assert repo.was_ingested("deadbeef") is None
        repo.record_ingestion("deadbeef", "old.pdf", 3)
        assert repo.was_ingested("deadbeef") == 3


class TestIdempotency:
    def test_migrate_twice_is_noop(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "idem.db")
        assert migrate(conn) == SCHEMA_VERSION
        assert migrate(conn) == SCHEMA_VERSION  # must not raise
        count = conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0]
        assert count == 1  # exactly one version row, no duplicate stamping
        conn.close()
