import pytest

from app.application.sessions import RoomSessionService, SessionError


def test_room_session_round_trips_player_identity():
    service = RoomSessionService(secret="test-secret")

    token = service.issue(room_id="ROOM7", player_id="p1", token_version=1)
    claims = service.verify(token, expected_room_id="ROOM7")

    assert claims.room_id == "ROOM7"
    assert claims.player_id == "p1"
    assert claims.token_version == 1


def test_room_session_rejects_wrong_room():
    service = RoomSessionService(secret="test-secret")
    token = service.issue(room_id="ROOM7", player_id="p1", token_version=1)

    with pytest.raises(SessionError, match="房间会话不属于当前房间"):
        service.verify(token, expected_room_id="ROOM8")
