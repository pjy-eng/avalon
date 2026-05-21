from __future__ import annotations

from app.infrastructure.db import ParticipantRecord, create_schema, make_engine, session_scope
from app.infrastructure.redis_store import InMemoryTTLStore
from app.infrastructure.repositories import RoomRepository


def make_test_engine():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)
    return engine


def get_room_bundle(engine, room_id: str) -> dict:
    with session_scope(engine) as session:
        return RoomRepository(session).get_room_bundle(room_id)


def test_room_repository_upserts_and_reads_room_participants_and_game():
    engine = make_test_engine()

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_room("ROOM1", ruleset="avalon_5", status="lobby")
        repository.upsert_participant(
            "ROOM1",
            player_id="p1",
            nickname="阿澈",
            seat=1,
            participant_type="player",
            token_version=1,
        )
        repository.upsert_game(
            "ROOM1",
            phase="team_building",
            state={"leader": "p1", "team": ["p1"]},
        )

    bundle = get_room_bundle(engine, "ROOM1")

    assert bundle["room"] == {
        "room_id": "ROOM1",
        "ruleset": "avalon_5",
        "status": "lobby",
    }
    assert bundle["participants"] == [
        {
            "participant_id": "ROOM1:p1",
            "room_id": "ROOM1",
            "player_id": "p1",
            "nickname": "阿澈",
            "seat": 1,
            "participant_type": "player",
            "token_version": 1,
        }
    ]
    assert bundle["game"] == {
        "room_id": "ROOM1",
        "phase": "team_building",
        "state": {"leader": "p1", "team": ["p1"]},
    }


def test_room_repository_returns_participants_ordered_by_seat():
    engine = make_test_engine()

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_room("ROOM1", ruleset="avalon_7", status="lobby")
        repository.upsert_participant("ROOM1", "p3", "三号", 3, "player", 1)
        repository.upsert_participant("ROOM1", "p1", "一号", 1, "player", 1)
        repository.upsert_participant("ROOM1", "p2", "二号", 2, "player", 1)

    bundle = get_room_bundle(engine, "ROOM1")

    assert [participant["player_id"] for participant in bundle["participants"]] == [
        "p1",
        "p2",
        "p3",
    ]


def test_room_repository_preserves_full_length_participant_id():
    engine = make_test_engine()
    room_id = "R" * 64
    player_id = "P" * 64
    expected_participant_id = f"{room_id}:{player_id}"

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_room(room_id, ruleset="avalon_5", status="lobby")
        repository.upsert_participant(
            room_id,
            player_id=player_id,
            nickname="长 ID 玩家",
            seat=1,
            participant_type="player",
            token_version=1,
        )

    bundle = get_room_bundle(engine, room_id)

    assert ParticipantRecord.__table__.c.participant_id.type.length >= 160
    assert len(bundle["participants"][0]["participant_id"]) == 129
    assert bundle["participants"][0]["participant_id"] == expected_participant_id


def test_room_repository_upsert_updates_existing_records():
    engine = make_test_engine()

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_room("ROOM1", ruleset="avalon_5", status="lobby")
        repository.upsert_participant("ROOM1", "p1", "旧昵称", 1, "player", 1)
        repository.upsert_game("ROOM1", "lobby", {"round": 0})

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_room("ROOM1", ruleset="avalon_5", status="running")
        repository.upsert_participant("ROOM1", "p1", "新昵称", 1, "player", 2)
        repository.upsert_game("ROOM1", "quest_vote", {"round": 1, "team": ["p1"]})

    bundle = get_room_bundle(engine, "ROOM1")

    assert bundle["room"]["status"] == "running"
    assert bundle["participants"][0]["nickname"] == "新昵称"
    assert bundle["participants"][0]["token_version"] == 2
    assert bundle["game"] == {
        "room_id": "ROOM1",
        "phase": "quest_vote",
        "state": {"round": 1, "team": ["p1"]},
    }


def test_room_repository_missing_room_bundle_has_empty_shape():
    engine = make_test_engine()

    assert get_room_bundle(engine, "MISSING") == {
        "room": None,
        "participants": [],
        "game": None,
    }


def test_room_repository_missing_room_ignores_orphaned_participants_and_game():
    engine = make_test_engine()

    with session_scope(engine) as session:
        repository = RoomRepository(session)
        repository.upsert_participant("ROOM1", "p1", "一号", 1, "player", 1)
        repository.upsert_game("ROOM1", "team_building", {"leader": "p1"})

    assert get_room_bundle(engine, "ROOM1") == {
        "room": None,
        "participants": [],
        "game": None,
    }


def test_in_memory_ttl_store_set_once_get_and_delete():
    now = 1000.0
    store = InMemoryTTLStore(clock=lambda: now)

    assert store.set_once("request:req-1", "accepted", ttl_seconds=60) is True
    assert store.set_once("request:req-1", "duplicate", ttl_seconds=60) is False
    assert store.get("request:req-1") == "accepted"

    store.delete("request:req-1")

    assert store.get("request:req-1") is None


def test_in_memory_ttl_store_allows_set_once_after_expiry():
    current_time = 10.0

    def clock() -> float:
        return current_time

    store = InMemoryTTLStore(clock=clock)

    assert store.set_once("rate:p1", "1", ttl_seconds=5) is True
    current_time = 16.0

    assert store.get("rate:p1") is None
    assert store.set_once("rate:p1", "2", ttl_seconds=5) is True
    assert store.get("rate:p1") == "2"


def test_in_memory_ttl_store_non_positive_ttl_does_not_store_value():
    store = InMemoryTTLStore(clock=lambda: 1.0)

    assert store.set_once("rate:p1", "1", ttl_seconds=0) is False
    assert store.get("rate:p1") is None


def test_in_memory_ttl_store_non_positive_ttl_preserves_existing_value():
    store = InMemoryTTLStore(clock=lambda: 1.0)

    assert store.set_once("idem:x", "accepted", ttl_seconds=60) is True
    assert store.set_once("idem:x", "bad", ttl_seconds=0) is False
    assert store.get("idem:x") == "accepted"
    assert store.set_once("idem:x", "new", ttl_seconds=60) is False
