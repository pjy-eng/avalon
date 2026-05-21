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
