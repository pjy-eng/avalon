import jwt
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


SESSION_SECRET = "test-session-secret-with-enough-length"
LIVEKIT_SECRET = "test-livekit-secret-with-enough-length"


def test_health_returns_config_status(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("LIVEKIT_URL", "wss://example")
    monkeypatch.setenv("LIVEKIT_API_KEY", "example-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "example-secret")
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "avalon-online-v2",
        "database": "not_configured",
        "redis": "not_configured",
        "voice": "not_configured",
    }


def test_create_app_serves_index_outside_repo_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    index_response = client.get("/")
    static_response = client.get("/static/style.css")

    assert index_response.status_code == 200
    assert "Avalon Online v2" in index_response.text
    assert static_response.status_code == 200
    assert ".app-shell" in static_response.text


def test_join_room_returns_session_token_and_snapshot():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))

    response = client.post("/api/rooms/ROOM1/join", json={"nickname": " 阿澈 "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["room_id"] == "ROOM1"
    assert payload["player_id"].startswith("p_")
    assert payload["session_token"]
    assert payload["snapshot"]["room"]["room_id"] == "ROOM1"
    assert payload["snapshot"]["you"]["nickname"] == "阿澈"


def test_join_room_rejects_empty_nickname():
    client = TestClient(create_app(Settings()))

    response = client.post("/api/rooms/ROOM1/join", json={"nickname": "   "})

    assert response.status_code in {400, 422}


def test_command_rejects_blank_request_id_without_changing_ready_state():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    response = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": join["session_token"],
            "request_id": "   ",
            "command": {"type": "ready", "ready": True},
        },
    )

    assert response.status_code in {400, 422}
    snapshot = client.app.state.room_service.snapshot("ROOM1", viewer_id=join["player_id"])
    participant = next(item for item in snapshot["participants"] if item["player_id"] == join["player_id"])
    assert participant["ready"] is False


def test_command_start_game_returns_private_player_snapshot_without_secret_tables():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    joins = [
        client.post("/api/rooms/ROOM1/join", json={"nickname": f"玩家{i}"}).json()
        for i in range(1, 6)
    ]

    response = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": joins[0]["session_token"],
            "request_id": "start-1",
            "command": {"type": "start_game"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["you"]["player_id"] == joins[0]["player_id"]
    assert "private_panel" in payload["snapshot"]
    assert "roles" not in payload["snapshot"]
    assert "mission_votes" not in payload["snapshot"]
    assert "team_votes" not in payload["snapshot"]
    assert payload["events"][0]["event_type"] == "game_started"


def test_non_host_start_game_via_http_returns_error_status():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    joins = [
        client.post("/api/rooms/ROOM1/join", json={"nickname": f"玩家{i}"}).json()
        for i in range(1, 6)
    ]

    response = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": joins[1]["session_token"],
            "request_id": "start-by-guest",
            "command": {"type": "start_game"},
        },
    )

    assert response.status_code in {400, 403}
    assert response.json()["detail"]


def test_command_rejects_valid_session_for_missing_participant_as_unauthorized():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"})
    ghost_token = client.app.state.session_service.issue(
        room_id="ROOM1",
        player_id="ghost",
        token_version=1,
    )

    response = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": ghost_token,
            "request_id": "ghost-ready",
            "command": {"type": "ready", "ready": True},
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "当前会话不属于该房间玩家。"


def test_voice_token_returns_disabled_when_livekit_is_not_configured():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    response = client.post(
        "/api/rooms/ROOM1/voice-token",
        json={"session_token": join["session_token"]},
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "reason": "voice_not_configured"}


def test_voice_token_rejects_wrong_room_session():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    response = client.post(
        "/api/rooms/OTHER/voice-token",
        json={"session_token": join["session_token"]},
    )

    assert response.status_code != 200


def test_voice_token_rejects_valid_session_for_missing_participant_as_unauthorized():
    client = TestClient(
        create_app(
            Settings(
                session_secret=SESSION_SECRET,
                livekit_url="wss://livekit.example",
                livekit_api_key="livekit-key",
                livekit_api_secret=LIVEKIT_SECRET,
            )
        )
    )
    client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"})
    ghost_token = client.app.state.session_service.issue(
        room_id="ROOM1",
        player_id="ghost",
        token_version=1,
    )

    response = client.post(
        "/api/rooms/ROOM1/voice-token",
        json={"session_token": ghost_token},
    )

    assert response.status_code == 401
    assert "token" not in response.json()
    assert response.json().get("enabled") is not True


def test_voice_token_returns_livekit_join_token_when_configured():
    client = TestClient(
        create_app(
            Settings(
                session_secret=SESSION_SECRET,
                livekit_url="wss://livekit.example",
                livekit_api_key="livekit-key",
                livekit_api_secret=LIVEKIT_SECRET,
            )
        )
    )
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    response = client.post(
        "/api/rooms/ROOM1/voice-token",
        json={"session_token": join["session_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    token_payload = jwt.decode(payload["token"], LIVEKIT_SECRET, algorithms=["HS256"])
    assert payload["enabled"] is True
    assert payload["url"] == "wss://livekit.example"
    assert payload["room"] == "avalon-ROOM1"
    assert payload["identity"] == join["player_id"]
    assert token_payload["sub"] == join["player_id"]
    assert token_payload["video"]["room"] == "avalon-ROOM1"
    assert token_payload["video"]["canPublish"] is True
