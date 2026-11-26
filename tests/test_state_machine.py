from datetime import datetime, timedelta, timezone
import pytest
from app.state_machine import TableStateMachine


def test_table_state_debounce_free_to_occupied():
    sm = TableStateMachine(
        restaurant_id="rest_1",
        table_id="table_1",
        seat_threshold_sec=20,
        leave_threshold_sec=60,
    )
    t0 = datetime.now(timezone.utc)

    # At t=0, person detected -> no event yet (debouncing)
    event = sm.update(person_count=2, timestamp=t0)
    assert event is None
    assert sm.current_state == "free"

    # At t=10s, person still detected -> still no event (< 20s)
    t10 = t0 + timedelta(seconds=10)
    event = sm.update(person_count=3, timestamp=t10)
    assert event is None
    assert sm.current_state == "free"

    # At t=20s, threshold reached -> event emitted!
    t20 = t0 + timedelta(seconds=20)
    event = sm.update(person_count=3, timestamp=t20)
    assert event is not None
    assert event["to_state"] == "occupied"
    assert event["from_state"] == "free"
    assert event["person_count"] == 3
    assert sm.current_state == "occupied"


def test_table_state_debounce_occupied_to_free():
    sm = TableStateMachine(
        restaurant_id="rest_1",
        table_id="table_1",
        seat_threshold_sec=20,
        leave_threshold_sec=60,
    )
    t0 = datetime.now(timezone.utc)
    # Transition to occupied
    sm.update(person_count=2, timestamp=t0)
    sm.update(person_count=2, timestamp=t0 + timedelta(seconds=20))
    assert sm.current_state == "occupied"

    # Table becomes empty at t=25s
    t25 = t0 + timedelta(seconds=25)
    event = sm.update(person_count=0, timestamp=t25)
    assert event is None
    assert sm.current_state == "occupied"

    # At t=60s empty (35s duration) -> still occupied (< 60s leave threshold)
    t60 = t0 + timedelta(seconds=60)
    event = sm.update(person_count=0, timestamp=t60)
    assert event is None

    # At t=85s (60s after empty) -> transition to free!
    t85 = t25 + timedelta(seconds=60)
    event = sm.update(person_count=0, timestamp=t85)
    assert event is not None
    assert event["to_state"] == "free"
    assert sm.current_state == "free"
