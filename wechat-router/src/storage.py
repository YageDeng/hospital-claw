"""SQLite database operations and message deduplication."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Set

from .utils import compute_content_hash, retry

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL CHECK(type IN ('contact', 'group')),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id),
    sender          TEXT,
    content_type    TEXT NOT NULL CHECK(content_type IN (
        'text', 'image', 'file', 'link', 'voice', 'video', 'sticker', 'other'
    )),
    text_content    TEXT,
    timestamp_ocr   TEXT,
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_hash    TEXT UNIQUE,
    raw_screenshot  TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL REFERENCES messages(id),
    file_type   TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_name   TEXT,
    saved_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class StorageManager:
    """Manages SQLite storage for captured messages."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_or_create_contact(self, name: str, contact_type: str) -> int:
        """Return the contact id, creating the record if it doesn't exist."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM contacts WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]

        cursor = conn.execute(
            "INSERT INTO contacts (name, type) VALUES (?, ?)",
            (name, contact_type),
        )
        conn.commit()
        logger.debug("Created contact: %s (%s)", name, contact_type)
        return cursor.lastrowid

    def insert_message(
        self,
        contact_name: str,
        contact_type: str,
        sender: Optional[str],
        content_type: str,
        text_content: Optional[str] = None,
        timestamp_ocr: Optional[str] = None,
        raw_screenshot: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a message, skipping duplicates. Returns message id or None if duplicate."""
        content_hash = compute_content_hash(
            contact_name, sender, text_content, timestamp_ocr
        )
        contact_id = self.get_or_create_contact(contact_name, contact_type)
        conn = self._get_conn()

        def _do_insert():
            try:
                cursor = conn.execute(
                    """INSERT INTO messages
                       (contact_id, sender, content_type, text_content,
                        timestamp_ocr, content_hash, raw_screenshot)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (contact_id, sender, content_type, text_content,
                     timestamp_ocr, content_hash, raw_screenshot),
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

        result = retry(_do_insert, max_attempts=3, backoff_base=0.5)
        if result:
            logger.debug("Stored message (id=%d) from %s in %s",
                         result, sender, contact_name)
        else:
            logger.debug("Duplicate message skipped for %s", contact_name)
        return result

    def insert_attachment(
        self,
        message_id: int,
        file_type: str,
        file_path: str,
        file_name: Optional[str] = None,
    ) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO attachments (message_id, file_type, file_path, file_name)
               VALUES (?, ?, ?, ?)""",
            (message_id, file_type, file_path, file_name),
        )
        conn.commit()
        return cursor.lastrowid

    def get_recent_hashes(self, contact_name: str, limit: int = 200) -> set[str]:
        """Return recent content hashes for a contact to speed up dedup checks."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT m.content_hash FROM messages m
               JOIN contacts c ON m.contact_id = c.id
               WHERE c.name = ?
               ORDER BY m.captured_at DESC LIMIT ?""",
            (contact_name, limit),
        ).fetchall()
        return {row["content_hash"] for row in rows}

    def get_messages(self, contact_name: Optional[str] = None,
                     limit: int = 50) -> list[dict]:
        """Retrieve recent messages, optionally filtered by contact name."""
        conn = self._get_conn()
        if contact_name:
            rows = conn.execute(
                """SELECT m.*, c.name as contact_name, c.type as contact_type
                   FROM messages m JOIN contacts c ON m.contact_id = c.id
                   WHERE c.name = ?
                   ORDER BY m.captured_at DESC LIMIT ?""",
                (contact_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT m.*, c.name as contact_name, c.type as contact_type
                   FROM messages m JOIN contacts c ON m.contact_id = c.id
                   ORDER BY m.captured_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
