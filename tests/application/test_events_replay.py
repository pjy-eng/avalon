import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import AppEvent
from app.infrastructure.db import EventRecord, create_schema, make_engine, session_scope
from app.infrastructure.repositories import EventRepository


def make_test_engine(database_url: str = "sqlite+pysqlite:///:memory:"):
    engine = make_engine(database_url)
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


def test_database_assigns_record_ids_across_independent_sessions(tmp_path):
    engine = make_test_engine(f"sqlite+pysqlite:///{tmp_path / 'events.db'}")
    first_event = AppEvent(
        event_type="command.join_room",
        room_id="ROOM1",
        actor_id="p1",
        request_id="req-first",
        payload={"nickname": "玩家1"},
    )
    second_event = AppEvent(
        event_type="command.join_room",
        room_id="ROOM1",
        actor_id="p2",
        request_id="req-second",
        payload={"nickname": "玩家2"},
    )
    first_session = Session(engine)
    second_session = Session(engine)

    try:
        EventRepository(first_session).append(first_event)
        EventRepository(second_session).append(second_event)

        first_session.commit()
        second_session.commit()
    finally:
        first_session.close()
        second_session.close()

    with session_scope(engine) as session:
        records = session.scalars(select(EventRecord).order_by(EventRecord.record_id)).all()
        persisted_ids = [(record.record_id, record.event_id) for record in records]

    assert persisted_ids == [
        (1, first_event.event_id),
        (2, second_event.event_id),
    ]
    assert list_room_events(engine, "ROOM1") == [first_event, second_event]


def test_make_engine_uses_psycopg_for_plain_postgresql_urls():
    engine = make_engine("postgresql://user:pass@localhost:5432/avalon")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.dialect.driver == "psycopg"
