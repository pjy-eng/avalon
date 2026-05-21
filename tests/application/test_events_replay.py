import pytest

from app.application.events import AppEvent
from app.infrastructure.db import create_schema, make_engine, session_scope
from app.infrastructure.repositories import EventRepository


def make_test_engine():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return engine


def append_event(engine, event: AppEvent) -> None:
    with session_scope(engine) as session:
        EventRepository(session).append(event)


def list_room_events(engine, room_id: str) -> list[AppEvent]:
    with session_scope(engine) as session:
        return EventRepository(session).list_room_events(room_id)


def test_event_repository_persists_command_decision_and_security_events():
    engine = make_test_engine()
    events = [
        AppEvent(
            event_type="command.join_room",
            room_id="ROOM1",
            actor_id="p1",
            request_id="req-join",
            payload={"nickname": "阿澈", "host": True},
        ),
        AppEvent(
            event_type="decision.accepted",
            room_id="ROOM1",
            actor_id=None,
            request_id="req-decision",
            payload={"command": "join_room", "reason": "room_open"},
        ),
        AppEvent(
            event_type="security.rate_limited",
            room_id="ROOM1",
            actor_id="p2",
            request_id=None,
            payload={"limit": 10, "window_seconds": 60},
        ),
    ]

    with session_scope(engine) as session:
        repository = EventRepository(session)
        for event in events:
            repository.append(event)

    persisted = list_room_events(engine, "ROOM1")

    assert persisted == events
    assert [event.payload for event in persisted] == [event.payload for event in events]


def test_event_repository_lists_only_requested_room_events():
    engine = make_test_engine()
    room1_event = AppEvent(
        event_type="command.join_room",
        room_id="ROOM1",
        actor_id="p1",
        request_id="req-room1",
        payload={"nickname": "玩家1"},
    )
    room2_event = AppEvent(
        event_type="command.join_room",
        room_id="ROOM2",
        actor_id="p2",
        request_id="req-room2",
        payload={"nickname": "玩家2"},
    )

    append_event(engine, room1_event)
    append_event(engine, room2_event)

    assert list_room_events(engine, "ROOM1") == [room1_event]


def test_session_scope_rolls_back_appended_events_on_exception():
    engine = make_test_engine()
    event = AppEvent(
        event_type="command.join_room",
        room_id="ROOM1",
        actor_id="p1",
        request_id="req-rollback",
        payload={"nickname": "回滚测试"},
    )

    with pytest.raises(RuntimeError, match="boom"):
        with session_scope(engine) as session:
            EventRepository(session).append(event)
            raise RuntimeError("boom")

    assert list_room_events(engine, "ROOM1") == []
