import json
import sqlite3
from typing import Any
from uuid import UUID


class SQLiteEventQueue:
    """Persistent local SQLite buffer for offline reliability."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_events (
                    event_id TEXT PRIMARY KEY,
                    restaurant_id TEXT,
                    camera_id TEXT,
                    table_id TEXT,
                    occurred_at TEXT,
                    from_state TEXT,
                    to_state TEXT,
                    person_count INTEGER,
                    confidence REAL,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def enqueue(self, event_data: dict[str, Any]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO pending_events (
                    event_id, restaurant_id, camera_id, table_id, occurred_at,
                    from_state, to_state, person_count, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_data["event_id"]),
                    str(event_data["restaurant_id"]),
                    str(event_data.get("camera_id") or ""),
                    str(event_data["table_id"]),
                    str(event_data["occurred_at"]),
                    str(event_data["from_state"]),
                    str(event_data["to_state"]),
                    int(event_data["person_count"]),
                    float(event_data["confidence"]),
                ),
            )
            conn.commit()

    def get_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT event_id, restaurant_id, camera_id, table_id, occurred_at,
                       from_state, to_state, person_count, confidence
                FROM pending_events
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def remove(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in event_ids)
            conn.execute(
                f"DELETE FROM pending_events WHERE event_id IN ({placeholders})",
                event_ids,
            )
            conn.commit()

    def count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pending_events")
            return cursor.fetchone()[0]
