from datetime import datetime, timezone
from typing import Any
import uuid


class TableStateMachine:
    """Debounces person detections to prevent flickering table states.

    - FREE / UNKNOWN / NEEDS_CLEANING -> OCCUPIED: person detected consistently for >= seat_threshold_sec.
    - OCCUPIED -> FREE: no person detected consistently for >= leave_threshold_sec.
    """

    def __init__(
        self,
        restaurant_id: str,
        table_id: str,
        seat_threshold_sec: int = 20,
        leave_threshold_sec: int = 60,
        initial_state: str = "free",
    ):
        self.restaurant_id = str(restaurant_id)
        self.table_id = str(table_id)
        self.seat_threshold_sec = max(1, seat_threshold_sec)
        self.leave_threshold_sec = max(1, leave_threshold_sec)

        self.current_state = initial_state
        self.presence_started_at: datetime | None = None
        self.absence_started_at: datetime | None = None
        self.max_party_size = 0

    def update(
        self,
        person_count: int,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
    ) -> dict[str, Any] | None:
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Normalize camera_id
        valid_camera_id = str(camera_id).strip() if camera_id and str(camera_id).strip() else None

        if self.current_state in ("free", "unknown", "needs_cleaning", "reserved"):
            if person_count > 0:
                self.max_party_size = max(self.max_party_size, person_count)
                if self.presence_started_at is None:
                    self.presence_started_at = now

                duration = (now - self.presence_started_at).total_seconds()
                if duration >= self.seat_threshold_sec:
                    # Transition -> OCCUPIED
                    old_state = self.current_state
                    self.current_state = "occupied"
                    self.presence_started_at = None
                    self.absence_started_at = None

                    return {
                        "event_id": str(uuid.uuid4()),
                        "restaurant_id": self.restaurant_id,
                        "table_id": self.table_id,
                        "camera_id": valid_camera_id,
                        "occurred_at": now.isoformat(),
                        "from_state": old_state,
                        "to_state": "occupied",
                        "person_count": max(1, self.max_party_size),
                        "confidence": 0.95,
                    }
            else:
                self.presence_started_at = None
                self.max_party_size = 0

        elif self.current_state == "occupied":
            if person_count == 0:
                if self.absence_started_at is None:
                    self.absence_started_at = now

                duration = (now - self.absence_started_at).total_seconds()
                if duration >= self.leave_threshold_sec:
                    # Transition OCCUPIED -> FREE
                    self.current_state = "free"
                    self.absence_started_at = None
                    self.presence_started_at = None
                    self.max_party_size = 0

                    return {
                        "event_id": str(uuid.uuid4()),
                        "restaurant_id": self.restaurant_id,
                        "table_id": self.table_id,
                        "camera_id": valid_camera_id,
                        "occurred_at": now.isoformat(),
                        "from_state": "occupied",
                        "to_state": "free",
                        "person_count": 0,
                        "confidence": 0.95,
                    }
            else:
                self.absence_started_at = None
                self.max_party_size = max(self.max_party_size, person_count)

        return None
