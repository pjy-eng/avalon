import pytest

from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService
from app.domain.types import CommandError, Phase, RulesetName


def make_gateway() -> CommandGateway:
    sessions = RoomSessionService(secret="test-secret")
    rooms = RoomService(session_service=sessions)
    return CommandGateway(room_service=rooms, session_service=sessions)


def test_join_room_issues_session_token():
    gateway = make_gateway()

    result = gateway.handle_join(room_id="ROOM1", nickname="阿澈")

    assert result.player_id.startswith("p_")
    assert result.session_token
    assert result.snapshot["room"]["room_id"] == "ROOM1"


def test_start_game_requires_host_session():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    with pytest.raises(CommandError, match="只有房主可以开局"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=guest.session_token,
            command={"type": "start_game"},
            request_id="r1",
        )


def test_start_game_creates_friend_flexible_game_after_five_players():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    assert result.snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value
    assert result.snapshot["room"]["ruleset"] == RulesetName.FRIEND_FLEXIBLE.value


def test_join_after_game_started_is_rejected_without_changing_participants():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )
    before_snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)

    with pytest.raises(CommandError, match="游戏开始后不能加入房间"):
        gateway.handle_join(room_id="ROOM1", nickname="玩家6")

    after_snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)
    assert after_snapshot["room"]["status"] == "game"
    assert after_snapshot["room"]["player_count"] == 5
    assert after_snapshot["participants"] == before_snapshot["participants"]


def test_non_host_cannot_reuse_seen_request_id_to_bypass_start_game_host_check():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    with pytest.raises(CommandError, match="只有房主可以开局"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[1].session_token,
            command={"type": "start_game"},
            request_id="start-1",
        )


def test_ready_command_marks_participant_ready_in_lobby_snapshot():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )

    participants = {participant["player_id"]: participant for participant in result.snapshot["participants"]}
    assert result.snapshot["room"]["status"] == "lobby"
    assert result.snapshot["phase_summary"]["phase"] == Phase.LOBBY.value
    assert participants[host.player_id]["ready"] is False
    assert participants[guest.player_id]["ready"] is True


def test_reset_requires_host_and_returns_room_to_lobby_with_participants_retained():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    for index, join in enumerate(joins):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "ready", "ready": True},
            request_id=f"ready-{index}",
        )
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    with pytest.raises(CommandError, match="只有房主可以重置房间"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[1].session_token,
            command={"type": "reset"},
            request_id="reset-guest",
        )

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "reset"},
        request_id="reset-host",
    )

    assert result.snapshot["room"]["status"] == "lobby"
    assert result.snapshot["phase_summary"]["phase"] == Phase.LOBBY.value
    assert [participant["player_id"] for participant in result.snapshot["participants"]] == [
        join.player_id for join in joins
    ]
    assert result.snapshot["room"]["host_id"] == joins[0].player_id
    assert all(participant["ready"] is False for participant in result.snapshot["participants"])


def test_reusing_request_id_for_different_host_command_does_not_execute_reset():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="x",
    )

    with pytest.raises(CommandError, match="重复请求编号对应不同操作"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[0].session_token,
            command={"type": "reset"},
            request_id="x",
        )

    snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)
    assert snapshot["room"]["status"] == "game"
    assert snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value


def test_repeating_same_request_id_and_command_returns_snapshot_without_new_event():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")
    first_result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )
    event_count = len(gateway.room_service.get_room("ROOM1").events)

    second_result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )

    assert len(gateway.room_service.get_room("ROOM1").events) == event_count
    assert second_result.events == []
    participants = {participant["player_id"]: participant for participant in second_result.snapshot["participants"]}
    assert first_result.events[0].event_type == "participant_ready_changed"
    assert participants[host.player_id]["ready"] is False
    assert participants[guest.player_id]["ready"] is True
