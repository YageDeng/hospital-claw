"""Persistent SQLite storage for real-time monitored messages.

Thread-safe: uses a per-thread connection via check_same_thread=False
and a threading lock around writes. Reads are safe without locking in WAL mode.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    username    TEXT NOT NULL,
    chat_name   TEXT NOT NULL,
    is_group    INTEGER NOT NULL DEFAULT 0,
    sender      TEXT,
    msg_type    TEXT NOT NULL,
    content     TEXT,
    image_url   TEXT,
    rich_content TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_dedup
    ON messages(timestamp, username, msg_type);

CREATE INDEX IF NOT EXISTS idx_msg_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_username ON messages(username);
CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_name);

CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER REFERENCES messages(id),
    timestamp   INTEGER NOT NULL,
    username    TEXT NOT NULL,
    media_type  TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_name   TEXT,
    file_size   INTEGER,
    md5         TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_att_msg
    ON attachments(timestamp, username);
CREATE INDEX IF NOT EXISTS idx_att_type
    ON attachments(media_type);
"""


class MessageStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._write_lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        self._migrate()

    def _migrate(self):
        """Run schema migrations for existing databases."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(attachments)").fetchall()}
        if 'message_id' not in cols:
            try:
                self._conn.execute(
                    "ALTER TABLE attachments ADD COLUMN message_id INTEGER REFERENCES messages(id)")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
        try:
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_att_msg_id ON attachments(message_id)")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _find_message_id(self, timestamp: int, username: str) -> int | None:
        """Look up the messages.id for a given (timestamp, username) pair."""
        row = self._conn.execute(
            "SELECT id FROM messages WHERE timestamp = ? AND username = ? LIMIT 1",
            (timestamp, username),
        ).fetchone()
        return row['id'] if row else None

    # ---- Write operations (locked) ----

    def insert(self, msg_data: dict) -> bool:
        """Insert a message, returning True if inserted, False if duplicate."""
        with self._write_lock:
            try:
                cursor = self._conn.execute(
                    """INSERT OR IGNORE INTO messages
                       (timestamp, username, chat_name, is_group, sender,
                        msg_type, content, image_url, rich_content)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        msg_data.get('timestamp', 0),
                        msg_data.get('username', ''),
                        msg_data.get('chat', ''),
                        1 if msg_data.get('is_group') else 0,
                        msg_data.get('sender', ''),
                        msg_data.get('type', ''),
                        msg_data.get('content', ''),
                        msg_data.get('image_url', ''),
                        json.dumps(msg_data.get('rich_content') or msg_data.get('rich') or None,
                                   ensure_ascii=False) if (msg_data.get('rich_content') or msg_data.get('rich')) else None,
                    ),
                )
                self._conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error:
                return False

    def update_image(self, timestamp: int, username: str, image_url: str):
        with self._write_lock:
            try:
                self._conn.execute(
                    "UPDATE messages SET image_url = ? WHERE timestamp = ? AND username = ?",
                    (image_url, timestamp, username),
                )
                self._conn.commit()
            except sqlite3.Error:
                pass

    def update_rich(self, timestamp: int, username: str, rich: dict):
        with self._write_lock:
            try:
                self._conn.execute(
                    "UPDATE messages SET rich_content = ? WHERE timestamp = ? AND username = ?",
                    (json.dumps(rich, ensure_ascii=False), timestamp, username),
                )
                self._conn.commit()
            except sqlite3.Error:
                pass

    def insert_attachment(self, timestamp: int, username: str, media_type: str,
                          file_path: str, file_name: str = None,
                          file_size: int = None, md5: str = None) -> bool:
        """Record a saved media file linked to its parent message."""
        with self._write_lock:
            try:
                existing = self._conn.execute(
                    "SELECT id FROM attachments WHERE timestamp = ? AND username = ? AND media_type = ? AND file_path = ?",
                    (timestamp, username, media_type, file_path),
                ).fetchone()
                if existing:
                    return False
                message_id = self._find_message_id(timestamp, username)
                self._conn.execute(
                    """INSERT INTO attachments
                       (message_id, timestamp, username, media_type, file_path, file_name, file_size, md5)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (message_id, timestamp, username, media_type, file_path, file_name, file_size, md5),
                )
                self._conn.commit()
                return True
            except sqlite3.Error:
                return False

    def get_attachments(self, message_id: int = None, timestamp: int = None,
                        username: str = None, media_type: str = None,
                        limit: int = 100) -> list[dict]:
        """Query attachments, optionally filtered by message_id or other fields."""
        clauses = []
        params = []
        if message_id is not None:
            clauses.append("a.message_id = ?")
            params.append(message_id)
        if timestamp is not None:
            clauses.append("a.timestamp = ?")
            params.append(timestamp)
        if username:
            clauses.append("a.username = ?")
            params.append(username)
        if media_type:
            clauses.append("a.media_type = ?")
            params.append(media_type)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""SELECT a.*, m.chat_name, m.msg_type, m.sender
                  FROM attachments a
                  LEFT JOIN messages m ON a.message_id = m.id
                  {where} ORDER BY a.timestamp DESC LIMIT ?"""
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def backfill_chat_name(self, username: str, chat_name: str):
        """Update chat_name for all messages where it was stored as the raw username."""
        if not username or not chat_name or username == chat_name:
            return
        with self._write_lock:
            try:
                self._conn.execute(
                    "UPDATE messages SET chat_name = ? WHERE username = ? AND chat_name = ?",
                    (chat_name, username, username),
                )
                self._conn.commit()
            except sqlite3.Error:
                pass

    # ---- Read operations ----

    def get_recent(self, limit: int = 500) -> list[dict]:
        """Get the most recent messages for SSE replay on startup."""
        rows = self._conn.execute(
            """SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_msg(r) for r in reversed(rows)]

    def get_history(self, limit: int = 100, offset: int = 0,
                    username: str = None, chat_name: str = None,
                    start_time: int = None, end_time: int = None) -> list[dict]:
        """Paginated history query, newest first."""
        clauses = []
        params = []
        if username:
            clauses.append("username = ?")
            params.append(username)
        if chat_name:
            clauses.append("chat_name LIKE ?")
            params.append(f"%{chat_name}%")
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM messages {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def search(self, keyword: str, limit: int = 50, offset: int = 0,
               chat_name: str = None) -> list[dict]:
        """Search messages by content keyword."""
        clauses = ["content LIKE ?"]
        params = [f"%{keyword}%"]
        if chat_name:
            clauses.append("chat_name LIKE ?")
            params.append(f"%{chat_name}%")

        where = f"WHERE {' AND '.join(clauses)}"
        sql = f"SELECT * FROM messages {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def get_stats(self) -> dict:
        """Return DB statistics."""
        row = self._conn.execute(
            "SELECT COUNT(*) as total, MIN(timestamp) as earliest, MAX(timestamp) as latest FROM messages"
        ).fetchone()

        chat_rows = self._conn.execute(
            """SELECT chat_name, COUNT(*) as cnt
               FROM messages GROUP BY chat_name ORDER BY cnt DESC LIMIT 50"""
        ).fetchall()

        att_row = self._conn.execute(
            "SELECT COUNT(*) as total FROM attachments"
        ).fetchone()

        att_type_rows = self._conn.execute(
            """SELECT media_type, COUNT(*) as cnt
               FROM attachments GROUP BY media_type ORDER BY cnt DESC"""
        ).fetchall()

        total = row['total'] or 0
        return {
            'total_messages': total,
            'total_attachments': att_row['total'] or 0,
            'attachment_types': {r['media_type']: r['cnt'] for r in att_type_rows},
            'earliest': row['earliest'],
            'latest': row['latest'],
            'earliest_str': datetime.fromtimestamp(row['earliest']).strftime('%Y-%m-%d %H:%M') if row['earliest'] else None,
            'latest_str': datetime.fromtimestamp(row['latest']).strftime('%Y-%m-%d %H:%M') if row['latest'] else None,
            'chats': [{'name': r['chat_name'], 'count': r['cnt']} for r in chat_rows],
        }

    # ---- Internal ----

    _TYPE_ICONS = {
        '文本': '💬', '图片': '🖼️', '语音': '🎤', '名片': '👤',
        '视频': '🎬', '表情': '😀', '位置': '📍', '链接/文件': '🔗',
        '通话': '📞', '系统': '⚙️', '撤回': '↩️',
    }

    @staticmethod
    def _row_to_msg(row) -> dict:
        """Convert a sqlite3.Row to the msg_data dict format used by SSE."""
        msg_type = row['msg_type'] or ''
        d = {
            'time': datetime.fromtimestamp(row['timestamp']).strftime('%H:%M:%S') if row['timestamp'] else '',
            'timestamp': row['timestamp'],
            'chat': row['chat_name'],
            'username': row['username'],
            'is_group': bool(row['is_group']),
            'sender': row['sender'] or '',
            'type': msg_type,
            'type_icon': MessageStore._TYPE_ICONS.get(msg_type, '📨'),
            'content': row['content'] or '',
        }
        if row['image_url']:
            d['image_url'] = row['image_url']
        if row['rich_content']:
            try:
                d['rich'] = json.loads(row['rich_content'])
            except (json.JSONDecodeError, TypeError):
                pass
        return d
