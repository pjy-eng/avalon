from __future__ import annotations

import json

import jwt

from app.infrastructure.voice import LiveKitVoiceProvider, NoopVoiceProvider, VoicePolicy


TEST_SECRET = "test-secret-with-enough-length-for-hs256"


def decode_token(token: str) -> dict:
    return jwt.decode(token, TEST_SECRET, algorithms=["HS256"])


def test_noop_voice_provider_returns_disabled_token():
    provider = NoopVoiceProvider()

    token = provider.issue_join_token(
        room_id="ROOM1",
        player_id="p1",
        display_name="阿澈",
        can_publish_audio=True,
    )

    assert token == {"enabled": False, "reason": "voice_not_configured"}


def test_livekit_token_contains_microphone_publish_grant():
    provider = LiveKitVoiceProvider(
        url="wss://livekit.example",
        api_key="key",
        api_secret=TEST_SECRET,
    )

    result = provider.issue_join_token(
        room_id="ROOM1",
        player_id="p1",
        display_name="阿澈",
        can_publish_audio=True,
    )
    payload = decode_token(result["token"])

    assert result["enabled"] is True
    assert result["url"] == "wss://livekit.example"
    assert result["room"] == "avalon-ROOM1"
    assert result["identity"] == "p1"
    assert payload["iss"] == "key"
    assert payload["sub"] == "p1"
    assert payload["name"] == "阿澈"
    assert payload["video"] == {
        "roomJoin": True,
        "room": "avalon-ROOM1",
        "canSubscribe": True,
        "canPublishData": True,
        "canPublish": True,
        "canPublishSources": ["microphone"],
    }


def test_livekit_token_disables_publish_when_audio_is_not_allowed():
    provider = LiveKitVoiceProvider(
        url="wss://livekit.example",
        api_key="key",
        api_secret=TEST_SECRET,
    )

    result = provider.issue_join_token(
        room_id="ROOM1",
        player_id="p1",
        display_name="阿澈",
        can_publish_audio=False,
    )
    payload = decode_token(result["token"])

    assert payload["video"]["canPublish"] is False
    assert payload["video"]["canPublishSources"] == []


def test_voice_policy_maps_to_publish_permission():
    policy = VoicePolicy(policy="leader_only", can_publish_audio=True)
    muted = VoicePolicy(policy="muted", can_publish_audio=False)

    assert policy.policy == "leader_only"
    assert policy.can_publish_audio is True
    assert muted.policy == "muted"
    assert muted.can_publish_audio is False


def test_livekit_permission_update_payload_disables_audio_publish():
    provider = LiveKitVoiceProvider(
        url="wss://livekit.example",
        api_key="key",
        api_secret=TEST_SECRET,
    )

    payload = provider.permission_update_payload(
        room_id="ROOM1",
        player_id="p1",
        can_publish_audio=False,
    )

    assert payload == {
        "room": "avalon-ROOM1",
        "identity": "p1",
        "permission": {
            "canPublish": False,
            "canSubscribe": True,
            "canPublishData": True,
            "canPublishSources": [],
        },
    }


def test_livekit_metadata_is_json_and_name_claim_preserves_chinese_display_name():
    provider = LiveKitVoiceProvider(
        url="wss://livekit.example",
        api_key="key",
        api_secret=TEST_SECRET,
    )

    result = provider.issue_join_token(
        room_id="中文房间",
        player_id="p1",
        display_name="阿澈",
        can_publish_audio=True,
    )
    payload = decode_token(result["token"])

    assert payload["name"] == "阿澈"
    assert json.loads(payload["metadata"]) == {
        "avalon_room": "中文房间",
        "player_id": "p1",
    }


def test_livekit_token_has_expiration_after_not_before():
    provider = LiveKitVoiceProvider(
        url="wss://livekit.example",
        api_key="key",
        api_secret=TEST_SECRET,
    )

    result = provider.issue_join_token(
        room_id="ROOM1",
        player_id="p1",
        display_name="阿澈",
        can_publish_audio=True,
    )
    payload = decode_token(result["token"])

    assert isinstance(payload["nbf"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > payload["nbf"]
