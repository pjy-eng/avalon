from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

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
            host_guest_connect_payload = host_ws.receive_json()

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
    assert host_guest_connect_payload["type"] == "state"
    host_online = {
        item["player_id"]: item["online"]
        for item in host_guest_connect_payload["snapshot"]["online_state"]["players"]
    }
    assert host_online[joins[0]["player_id"]] is True
    assert host_online[joins[1]["player_id"]] is True
    assert host_payload["type"] == "state"
    assert guest_payload["type"] == "state"
    assert host_payload["snapshot"]["you"]["player_id"] == joins[0]["player_id"]
    assert guest_payload["snapshot"]["you"]["player_id"] == joins[1]["player_id"]
    assert host_payload["snapshot"]["private_panel"] != guest_payload["snapshot"]["private_panel"]


def test_ws_kicked_lobby_player_is_disconnected_before_later_broadcasts():
    client = make_client()
    joins = join_players(client, count=6)

    with client.websocket_connect("/ws/ROOM1") as host_ws:
        assert hello(host_ws, joins[0]["session_token"])["type"] == "state"
        with client.websocket_connect("/ws/ROOM1") as guest_ws:
            assert hello(guest_ws, joins[1]["session_token"])["type"] == "state"
            assert host_ws.receive_json()["type"] == "state"

            host_ws.send_json(
                {
                    "type": "command",
                    "request_id": "kick-guest",
                    "command": {"type": "kick_player", "target_id": joins[1]["player_id"]},
                }
            )
            guest_payload = guest_ws.receive_json()
            host_after_kick = host_ws.receive_json()

            assert guest_payload["type"] == "removed"
            assert guest_payload["reason"] == "participant_kicked"
            assert host_after_kick["type"] == "state"
            assert joins[1]["player_id"] not in {
                item["player_id"] for item in host_after_kick["snapshot"]["participants"]
            }

            with pytest.raises(WebSocketDisconnect):
                guest_ws.receive_json()

            host_ws.send_json(
                {
                    "type": "command",
                    "request_id": "ready-after-kick",
                    "command": {"type": "ready", "ready": True},
                }
            )
            host_after_ready = host_ws.receive_json()
            host_ws.send_json(
                {
                    "type": "command",
                    "request_id": "start-after-kick",
                    "command": {"type": "start_game"},
                }
            )
            host_after_start = host_ws.receive_json()

    assert host_after_ready["type"] == "state"
    assert host_after_start["type"] == "state"
    assert host_after_start["snapshot"]["phase_summary"]["phase"] == "TEAM_PROPOSAL"


def test_http_kick_disconnects_guest_ws_and_broadcasts_remaining_state():
    client = make_client()
    joins = join_players(client, count=6)

    with client.websocket_connect("/ws/ROOM1") as guest_ws:
        assert hello(guest_ws, joins[1]["session_token"])["type"] == "state"
        with client.websocket_connect("/ws/ROOM1") as observer_ws:
            assert hello(observer_ws, joins[2]["session_token"])["type"] == "state"
            assert guest_ws.receive_json()["type"] == "state"

            response = client.post(
                "/api/rooms/ROOM1/command",
                json={
                    "session_token": joins[0]["session_token"],
                    "request_id": "http-kick-guest",
                    "command": {"type": "kick_player", "target_id": joins[1]["player_id"]},
                },
            )

            assert response.status_code == 200
            assert joins[1]["player_id"] not in client.app.state.connection_manager.online_counts("ROOM1")

            guest_payload = guest_ws.receive_json()
            observer_after_kick = observer_ws.receive_json()

            assert guest_payload["type"] == "removed"
            assert guest_payload["reason"] == "participant_kicked"
            assert observer_after_kick["type"] == "state"
            assert joins[1]["player_id"] not in {
                item["player_id"] for item in observer_after_kick["snapshot"]["participants"]
            }

            with pytest.raises(WebSocketDisconnect):
                guest_ws.receive_json()

            observer_ws.send_json(
                {
                    "type": "command",
                    "request_id": "observer-ready-after-http-kick",
                    "command": {"type": "ready", "ready": True},
                }
            )
            observer_after_ready = observer_ws.receive_json()

    assert observer_after_ready["type"] == "state"
    assert observer_after_ready["snapshot"]["you"]["player_id"] == joins[2]["player_id"]


def test_ws_same_player_multiple_connections_receive_broadcasts_after_old_connection_closes():
    client = make_client()
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    with client.websocket_connect("/ws/ROOM1") as old_ws:
        assert hello(old_ws, join["session_token"])["type"] == "state"
        with client.websocket_connect("/ws/ROOM1") as new_ws:
            assert hello(new_ws, join["session_token"])["type"] == "state"
            old_after_new_connect = old_ws.receive_json()

            new_ws.send_json(
                {
                    "type": "command",
                    "request_id": "ready-1",
                    "command": {"type": "ready", "ready": True},
                }
            )
            new_payload = new_ws.receive_json()

            old_ws.close()
            new_after_old_close = new_ws.receive_json()
            new_ws.send_json(
                {
                    "type": "command",
                    "request_id": "ready-2",
                    "command": {"type": "ready", "ready": False},
                }
            )
            remaining_payload = new_ws.receive_json()

    assert old_after_new_connect["type"] == "state"
    assert new_payload["type"] == "state"
    assert new_after_old_close["type"] == "state"
    assert remaining_payload["type"] == "state"
    old_connect_online = next(
        item
        for item in old_after_new_connect["snapshot"]["online_state"]["players"]
        if item["player_id"] == join["player_id"]
    )
    assert old_connect_online["connection_count"] == 2
    new_close_online = next(
        item
        for item in new_after_old_close["snapshot"]["online_state"]["players"]
        if item["player_id"] == join["player_id"]
    )
    assert new_close_online["online"] is True
    assert new_close_online["connection_count"] == 1
    assert new_payload["snapshot"]["you"]["player_id"] == join["player_id"]
    assert remaining_payload["snapshot"]["you"]["player_id"] == join["player_id"]
    participant = next(
        item for item in remaining_payload["snapshot"]["participants"] if item["player_id"] == join["player_id"]
    )
    assert participant["ready"] is False


def test_ws_broadcasts_online_state_when_players_connect_and_disconnect():
    client = make_client()
    joins = join_players(client, count=5)

    with client.websocket_connect("/ws/ROOM1") as host_ws:
        host_initial = hello(host_ws, joins[0]["session_token"])
        assert host_initial["snapshot"]["online_state"]["players"][0]["online"] is True

        with client.websocket_connect("/ws/ROOM1") as guest_ws:
            guest_initial = hello(guest_ws, joins[1]["session_token"])
            host_after_guest_connect = host_ws.receive_json()

        host_after_guest_disconnect = host_ws.receive_json()

    assert guest_initial["type"] == "state"
    connected = {
        item["player_id"]: item["online"]
        for item in host_after_guest_connect["snapshot"]["online_state"]["players"]
    }
    disconnected = {
        item["player_id"]: item["online"]
        for item in host_after_guest_disconnect["snapshot"]["online_state"]["players"]
    }
    assert connected[joins[0]["player_id"]] is True
    assert connected[joins[1]["player_id"]] is True
    assert disconnected[joins[0]["player_id"]] is True
    assert disconnected[joins[1]["player_id"]] is False
