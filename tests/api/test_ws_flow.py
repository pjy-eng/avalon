from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


SESSION_SECRET = "test-session-secret-with-enough-length"


def make_client() -> TestClient:
    return TestClient(create_app(Settings(session_secret=SESSION_SECRET)))


def join_players(client: TestClient, room_id: str = "ROOM1", count: int = 5) -> list[dict]:
    return [
        client.post(f"/api/rooms/{room_id}/join", json={"nickname": f"玩家{i}"}).json()
        for i in range(1, count + 1)
    ]


def hello(websocket, session_token: str) -> dict:
    websocket.send_json({"type": "hello", "session_token": session_token})
    return websocket.receive_json()


def assert_player_not_ready_and_no_seen_request_ids(client: TestClient, room_id: str, player_id: str) -> None:
    room = client.app.state.room_service.get_room(room_id)
    participant = next(item for item in room.participants if item.player_id == player_id)
    assert participant.ready is False
    assert room.seen_request_ids == {}


def test_ws_first_message_requires_session_token():
    client = make_client()

    with client.websocket_connect("/ws/ROOM1") as websocket:
        websocket.send_json({"type": "hello"})

        assert websocket.receive_json() == {
            "type": "error",
            "message": "第一条消息必须包含 session_token。",
        }


def test_ws_rejects_wrong_room_session():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/OTHER") as websocket:
        websocket.send_json({"type": "hello", "session_token": join["session_token"]})

        assert websocket.receive_json() == {
            "type": "error",
            "message": "房间会话不属于当前房间。",
        }


def test_ws_ping_pong():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as websocket:
        assert hello(websocket, join["session_token"])["type"] == "state"

        websocket.send_json({"type": "ping"})

        assert websocket.receive_json() == {"type": "pong"}


def test_ws_start_game_returns_private_player_snapshot_without_secret_tables():
    client = make_client()
    joins = join_players(client)

    with client.websocket_connect("/ws/ROOM1") as websocket:
        assert hello(websocket, joins[0]["session_token"])["type"] == "state"

        websocket.send_json(
            {
                "type": "command",
                "request_id": "start-1",
                "command": {"type": "start_game"},
            }
        )
        payload = websocket.receive_json()

    assert payload["type"] == "state"
    snapshot = payload["snapshot"]
    assert snapshot["phase_summary"]["phase"] == "TEAM_PROPOSAL"
    assert snapshot["you"]["player_id"] == joins[0]["player_id"]
    assert "private_panel" in snapshot
    assert "roles" not in snapshot
    assert "mission_votes" not in snapshot
    assert "team_votes" not in snapshot


def test_ws_blank_request_id_does_not_enter_gateway_or_change_ready_state():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as websocket:
        assert hello(websocket, join["session_token"])["type"] == "state"

        websocket.send_json(
            {
                "type": "command",
                "request_id": "   ",
                "command": {"type": "ready", "ready": True},
            }
        )

        payload = websocket.receive_json()

    assert payload["type"] == "error"
    assert payload["message"]
    assert_player_not_ready_and_no_seen_request_ids(client, "ROOM1", join["player_id"])


def test_ws_long_request_id_does_not_enter_gateway_or_change_ready_state():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as websocket:
        assert hello(websocket, join["session_token"])["type"] == "state"

        websocket.send_json(
            {
                "type": "command",
                "request_id": "x" * 129,
                "command": {"type": "ready", "ready": True},
            }
        )

        payload = websocket.receive_json()

    assert payload["type"] == "error"
    assert payload["message"]
    assert_player_not_ready_and_no_seen_request_ids(client, "ROOM1", join["player_id"])


def test_ws_non_string_request_id_does_not_enter_gateway_or_change_ready_state():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as websocket:
        assert hello(websocket, join["session_token"])["type"] == "state"

        websocket.send_json(
            {
                "type": "command",
                "request_id": 123,
                "command": {"type": "ready", "ready": True},
            }
        )

        payload = websocket.receive_json()

    assert payload["type"] == "error"
    assert payload["message"]
    assert_player_not_ready_and_no_seen_request_ids(client, "ROOM1", join["player_id"])


def test_ws_broadcasts_per_player_state_after_command():
    client = make_client()
    joins = join_players(client)

    with client.websocket_connect("/ws/ROOM1") as host_ws:
        host_initial = hello(host_ws, joins[0]["session_token"])
        with client.websocket_connect("/ws/ROOM1") as guest_ws:
            guest_initial = hello(guest_ws, joins[1]["session_token"])

            host_ws.send_json(
                {
                    "type": "command",
                    "request_id": "start-1",
                    "command": {"type": "start_game"},
                }
            )
            host_payload = host_ws.receive_json()
            guest_payload = guest_ws.receive_json()

    assert host_initial["snapshot"]["you"]["player_id"] == joins[0]["player_id"]
    assert guest_initial["snapshot"]["you"]["player_id"] == joins[1]["player_id"]
    assert host_payload["type"] == "state"
    assert guest_payload["type"] == "state"
    assert host_payload["snapshot"]["you"]["player_id"] == joins[0]["player_id"]
    assert guest_payload["snapshot"]["you"]["player_id"] == joins[1]["player_id"]
    assert host_payload["snapshot"]["private_panel"] != guest_payload["snapshot"]["private_panel"]


def test_ws_same_player_multiple_connections_receive_broadcasts_after_old_connection_closes():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as old_ws:
        assert hello(old_ws, join["session_token"])["type"] == "state"
        with client.websocket_connect("/ws/ROOM1") as new_ws:
            assert hello(new_ws, join["session_token"])["type"] == "state"

            new_ws.send_json(
                {
                    "type": "command",
                    "request_id": "ready-1",
                    "command": {"type": "ready", "ready": True},
                }
            )
            old_payload = old_ws.receive_json()
            new_payload = new_ws.receive_json()

            old_ws.close()
            new_ws.send_json(
                {
                    "type": "command",
                    "request_id": "ready-2",
                    "command": {"type": "ready", "ready": False},
                }
            )
            remaining_payload = new_ws.receive_json()

    assert old_payload["type"] == "state"
    assert new_payload["type"] == "state"
    assert remaining_payload["type"] == "state"
    assert old_payload["snapshot"]["you"]["player_id"] == join["player_id"]
    assert new_payload["snapshot"]["you"]["player_id"] == join["player_id"]
    assert remaining_payload["snapshot"]["you"]["player_id"] == join["player_id"]
    participant = next(
        item for item in remaining_payload["snapshot"]["participants"] if item["player_id"] == join["player_id"]
    )
    assert participant["ready"] is False
