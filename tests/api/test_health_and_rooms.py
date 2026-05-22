from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.voice import NoopVoiceProvider
from app.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[2]
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
    assert "阿瓦隆圆桌" in index_response.text
    assert static_response.status_code == 200
    assert ".app-shell" in static_response.text


def test_index_contains_restored_round_table_mount_points():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    for mount_id in [
        "roomInput",
        "nameInput",
        "joinBtn",
        "joinView",
        "gameView",
        "oddPlayersList",
        "evenPlayersList",
        "roomCode",
        "phaseTitle",
        "scoreText",
        "announcementText",
        "permissionText",
        "actionArea",
        "chatMessages",
        "dealOverlay",
        "infoModal",
        "historyModal",
        "teamModal",
        "assassinModal",
        "playersList",
    ]:
        assert f'id="{mount_id}"' in response.text


def test_frontend_contains_enabled_gameplay_action_handlers():
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    for required in [
        "openTeamModal",
        "submitSelectedTeam",
        "sendCommand({type: \"select_team\", team: appState.selectedTeam})",
        "sendCommand({type: \"team_vote\", vote: \"Approve\"})",
        "sendCommand({type: \"team_vote\", vote: \"Reject\"})",
        "sendCommand({type: \"mission_vote\", vote: \"Success\"})",
        "sendCommand({type: \"mission_vote\", vote: \"Fail\"})",
        "sendCommand({type: \"continue_after_result\"})",
        "openAssassinModal",
        "submitAssassination",
        "sendCommand({type: \"assassinate\", target_id: targetId})",
        "appendRevealRoles",
        "missionResultText",
        "commandPending: null",
        "if (appState.commandPending)",
        "createPendingCommand(command, message.request_id)",
        "phaseBefore",
        "hadReadyPlayersBefore",
        "clearPendingAfterNoopResetDebounce",
        "snapshotAcknowledgesPendingCommand(payload.snapshot)",
        "setCommandPending(null",
        "closeActionModals()",
        "appState.selectedTeam = []",
        "appState.pendingAssassinationTarget = \"\"",
        "snapshot.my_action?.can_submit_fail === false",
        "typeof result.succeeded !== \"boolean\"",
        "aria-pressed",
        "aria-disabled",
    ]:
        assert required in main_js

    assert "if (payload.type === \"state\") {\n      setCommandPending(null" not in main_js
    assert "if (payload.type === \"state\") {\n      setCommandPending(false" not in main_js
    assert "setCommandPending(true)" not in main_js
    assert 'if (pending.type === "reset") {\n    return snapshotPhase === "LOBBY";\n  }' not in main_js

    for stale_label in [
        "选择出征队伍（待接入）",
        "赞成（待接入）",
        "反对（待接入）",
        "任务成功（待接入）",
        "任务失败（待接入）",
        "进入下一轮（待接入）",
        "选择刺杀目标（待接入）",
    ]:
        assert stale_label not in main_js


def test_frontend_contains_chat_and_lobby_governance_handlers():
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    for required in [
        "handleBackButton",
        "sendChatMessage",
        "renderChatControls",
        "appendGovernanceControls",
        "phase(appState.snapshot) === \"LOBBY\" && appState.sessionToken",
        "message.request_id === pending.requestId",
        "message.author_id === pending.actorId",
        "elements.chatInput.value.trim() === pending.command.text",
        "消息不能超过 300 字。",
        "transfer_host",
        "kick_player",
        "leave_room",
        "send_chat",
    ]:
        assert required in main_js

    assert "renderActions(appState.snapshot);\n      renderChatControls(appState.snapshot);" in main_js


def test_frontend_contains_voice_and_private_mark_handlers():
    index_html = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    assert "livekit-client.umd.min.js" in index_html
    assert "async data-livekit-client" in index_html
    assert index_html.index("livekit-client.umd.min.js") < index_html.index('/static/main.js')
    for required in [
        "toggleVoice",
        "loadLiveKitClient",
        "syncVoicePublishing",
        "runVoicePublishingSync",
        "toggleSpeaker",
        "openTagsModal",
        "setPrivateMark",
        "privateMarkKey",
        "liveKitClientUrl",
        "voice_state?.can_publish_audio",
        "voicePublishDesired",
        "voicePublishError",
        "setMicrophoneEnabled(canPublish)",
        "禁麦同步失败，已断开语音以保护投票阶段。",
        "麦克风状态异常，请重连语音",
        "localStorage",
        "openTagsBtn?.addEventListener(\"click\", openTagsModal)",
        "voiceConnectAttempt",
        "isCurrentVoiceAttempt",
        "dataset.livekitFailed",
        "room.disconnect()",
        "classList.toggle(\"voice-connected\", appState.voiceConnected)",
        "classList.toggle(\"voice-blocked\", appState.voiceConnected && !canPublish)",
        "语音未连接，点击连接",
        "语音未连接，连接后当前阶段禁麦",
        "语音已连接，麦克风开启",
        "语音已连接，当前阶段禁麦",
        "elements.voiceBtn.title = voiceTitle",
        "远端语音播放中",
        "远端语音已静音",
        "语音未连接，扬声器偏好保留",
        "语音未连接，扬声器已静音偏好保留",
        "elements.listenBtn.title = speakerTitle",
    ]:
        assert required in main_js


def test_missing_gameplay_doc_tracks_completion_status_and_history():
    doc = (REPO_ROOT / "docs" / "MISSING_GAMEPLAY_FEATURES.md").read_text(encoding="utf-8")

    for required in [
        "v2 Gameplay Completion Status",
        "当前已实现",
        "历史缺失清单",
        "select_team",
        "team_vote",
        "mission_vote",
        "continue_after_result",
        "assassinate",
        "public_timeline",
        "reveal_roles",
        "send_chat",
        "online_state",
        "localStorage",
    ]:
        assert required in doc

    assert "当前 v2 已覆盖第 1-12 步的完整一局链路" in doc
    assert "当前版本不能完成一整局游戏" not in doc


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


class RecordingVoiceProvider:
    def __init__(self):
        self.updates = []

    def issue_join_token(self, room_id, player_id, display_name, can_publish_audio):
        return {"enabled": True, "token": "fake", "can_publish_audio": can_publish_audio}

    def permission_update_payload(self, room_id, player_id, can_publish_audio):
        return {"room_id": room_id, "player_id": player_id, "can_publish_audio": can_publish_audio}

    async def update_participant_permission(self, room_id, player_id, can_publish_audio):
        self.updates.append(
            {
                "room_id": room_id,
                "player_id": player_id,
                "can_publish_audio": can_publish_audio,
            }
        )
        return {"enabled": True}


def test_voice_token_reflects_muted_game_phase_publish_policy():
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
    real_voice_provider = client.app.state.voice_provider
    client.app.state.voice_provider = NoopVoiceProvider()
    joins = [
        client.post("/api/rooms/ROOM1/join", json={"nickname": f"玩家{i}"}).json()
        for i in range(1, 6)
    ]
    start = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": joins[0]["session_token"],
            "request_id": "start-muted-voice",
            "command": {"type": "start_game"},
        },
    ).json()
    leader_id = start["snapshot"]["phase_summary"]["leader_id"]
    required = start["snapshot"]["phase_summary"]["required_team_size"]
    players = start["snapshot"].get("participants") or start["snapshot"]["players"]
    team = [participant["player_id"] for participant in players[:required]]
    leader = next(join for join in joins if join["player_id"] == leader_id)

    vote_phase = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": leader["session_token"],
            "request_id": "select-muted-voice",
            "command": {"type": "select_team", "team": team},
        },
    ).json()["snapshot"]

    assert vote_phase["phase_summary"]["phase"] == "TEAM_VOTE"
    assert vote_phase["voice_state"]["can_publish_audio"] is False
    client.app.state.voice_provider = real_voice_provider

    response = client.post(
        "/api/rooms/ROOM1/voice-token",
        json={"session_token": leader["session_token"]},
    )

    assert response.status_code == 200
    token_payload = jwt.decode(response.json()["token"], LIVEKIT_SECRET, algorithms=["HS256"])
    assert token_payload["video"]["canPublish"] is False
    assert token_payload["video"]["canPublishSources"] == []


def test_http_commands_sync_livekit_permissions_when_phase_mutes_audio():
    client = TestClient(create_app(Settings(session_secret=SESSION_SECRET)))
    voice_provider = RecordingVoiceProvider()
    client.app.state.voice_provider = voice_provider
    joins = [
        client.post("/api/rooms/ROOM1/join", json={"nickname": f"玩家{i}"}).json()
        for i in range(1, 6)
    ]
    start = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": joins[0]["session_token"],
            "request_id": "start-voice-sync",
            "command": {"type": "start_game"},
        },
    ).json()
    leader_id = start["snapshot"]["phase_summary"]["leader_id"]
    required = start["snapshot"]["phase_summary"]["required_team_size"]
    players = start["snapshot"].get("participants") or start["snapshot"]["players"]
    team = [participant["player_id"] for participant in players[:required]]
    leader = next(join for join in joins if join["player_id"] == leader_id)
    voice_provider.updates.clear()

    response = client.post(
        "/api/rooms/ROOM1/command",
        json={
            "session_token": leader["session_token"],
            "request_id": "select-voice-sync",
            "command": {"type": "select_team", "team": team},
        },
    )

    assert response.status_code == 200
    assert response.json()["snapshot"]["voice_state"]["can_publish_audio"] is False
    updates = {
        item["player_id"]: item["can_publish_audio"]
        for item in voice_provider.updates
        if item["room_id"] == "ROOM1"
    }
    assert updates == {join["player_id"]: False for join in joins}
