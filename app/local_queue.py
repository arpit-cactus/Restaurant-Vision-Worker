import sqlite3
from typing import Any


class SQLiteEventQueue:
    """Persistent local SQLite buffer for offline reliability and guaranteed delivery."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Performance and reliability pragmas
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_events (
                    event_id TEXT PRIMARY KEY,
                    restaurant_id TEXT NOT NULL,
                    camera_id TEXT,
                    table_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    person_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letter_events (
                    event_id TEXT PRIMARY KEY,
                    restaurant_id TEXT,
                    camera_id TEXT,
                    table_id TEXT,
                    occurred_at TEXT,
                    from_state TEXT,
                    to_state TEXT,
                    person_count INTEGER,
                    confidence REAL,
                    failure_reason TEXT,
                    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def enqueue(self, event_data: dict[str, Any]) -> None:
        raw_cam_id = event_data.get("camera_id")
        cam_id = str(raw_cam_id).strip() if raw_cam_id and str(raw_cam_id).strip() else None

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
                    cam_id,
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
                       from_state, to_state, person_count, confidence, retry_count
                FROM pending_events
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            events: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                # CRITICAL: Backend requires valid UUID or None, never empty string ""
                cam = item.get("camera_id")
                item["camera_id"] = str(cam).strip() if cam and str(cam).strip() else None
                events.append(item)
            return events

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

    def increment_retries(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in event_ids)
            conn.execute(
                f"UPDATE pending_events SET retry_count = retry_count + 1 WHERE event_id IN ({placeholders})",
                event_ids,
            )
            conn.commit()

    def mark_failed(self, event_ids: list[str], reason: str) -> None:
        """Moves permanently rejected/invalid events to dead-letter queue so they do not block future events."""
        if not event_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in event_ids)
            conn.execute(
                f"""
                INSERT OR REPLACE INTO dead_letter_events (
                    event_id, restaurant_id, camera_id, table_id, occurred_at,
                    from_state, to_state, person_count, confidence, failure_reason
                )
                SELECT event_id, restaurant_id, camera_id, table_id, occurred_at,
                       from_state, to_state, person_count, confidence, ?
                FROM pending_events WHERE event_id IN ({placeholders})
                """,
                [reason] + event_ids,
            )
            conn.execute(
                f"DELETE FROM pending_events WHERE event_id IN ({placeholders})",
                event_ids,
            )
            conn.commit()

    def count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pending_events")
            return cursor.fetchone()[0]

    def dead_letter_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM dead_letter_events")
            return cursor.fetchone()[0]
