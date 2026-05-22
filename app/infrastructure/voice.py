from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
import jwt


@dataclass(frozen=True)
class VoicePolicy:
    policy: str
    can_publish_audio: bool


class VoiceProvider(Protocol):
    def issue_join_token(
        self,
        room_id: str,
        player_id: str,
        display_name: str,
        can_publish_audio: bool,
    ) -> dict:
        ...

    def permission_update_payload(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        ...

    async def update_participant_permission(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        ...

    def participant_removal_payload(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        ...

    async def remove_participant(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        ...


class NoopVoiceProvider:
    def issue_join_token(
        self,
        room_id: str,
        player_id: str,
        display_name: str,
        can_publish_audio: bool,
    ) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}

    def permission_update_payload(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}

    async def update_participant_permission(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}

    def participant_removal_payload(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}

    async def remove_participant(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}


class LiveKitVoiceProvider:
    def __init__(self, url: str, api_key: str, api_secret: str) -> None:
        if not url or not api_key or not api_secret:
            raise ValueError("LiveKit voice provider requires url, api_key, and api_secret")
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret

    def issue_join_token(
        self,
        room_id: str,
        player_id: str,
        display_name: str,
        can_publish_audio: bool,
    ) -> dict:
        livekit_room = self._livekit_room(room_id)
        now = int(time.time())
        payload = {
            "iss": self.api_key,
            "sub": player_id,
            "name": display_name,
            "nbf": now,
            "exp": now + 60 * 60,
            "metadata": json.dumps(
                {"avalon_room": room_id, "player_id": player_id},
                ensure_ascii=False,
            ),
            "video": self._permission(livekit_room, can_publish_audio),
        }
        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return {
            "enabled": True,
            "url": self.url,
            "token": token,
            "room": livekit_room,
            "identity": player_id,
        }

    def permission_update_payload(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        livekit_room = self._livekit_room(room_id)
        permission = self._permission(livekit_room, can_publish_audio)
        permission.pop("roomJoin")
        permission.pop("room")
        return {
            "room": livekit_room,
            "identity": player_id,
            "permission": permission,
        }

    async def update_participant_permission(
        self,
        room_id: str,
        player_id: str,
        can_publish_audio: bool,
    ) -> dict:
        payload = self.permission_update_payload(
            room_id=room_id,
            player_id=player_id,
            can_publish_audio=can_publish_audio,
        )
        livekit_room = payload["room"]
        admin_token = self._room_admin_token(livekit_room)
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{self._api_base_url()}/twirp/livekit.RoomService/UpdateParticipant",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=payload,
            )
        response.raise_for_status()
        return {"enabled": True, "status": "updated"}

    def participant_removal_payload(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        return {
            "room": self._livekit_room(room_id),
            "identity": player_id,
        }

    async def remove_participant(
        self,
        room_id: str,
        player_id: str,
    ) -> dict:
        payload = self.participant_removal_payload(room_id=room_id, player_id=player_id)
        livekit_room = payload["room"]
        admin_token = self._room_admin_token(livekit_room)
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{self._api_base_url()}/twirp/livekit.RoomService/RemoveParticipant",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=payload,
            )
        response.raise_for_status()
        return {"enabled": True, "status": "removed"}

    @staticmethod
    def _livekit_room(room_id: str) -> str:
        return f"avalon-{room_id}"

    def _api_base_url(self) -> str:
        if self.url.startswith("wss://"):
            return f"https://{self.url.removeprefix('wss://').rstrip('/')}"
        if self.url.startswith("ws://"):
            return f"http://{self.url.removeprefix('ws://').rstrip('/')}"
        return self.url.rstrip("/")

    def _room_admin_token(self, livekit_room: str) -> str:
        now = int(time.time())
        payload = {
            "iss": self.api_key,
            "nbf": now,
            "exp": now + 60,
            "video": {
                "roomAdmin": True,
                "room": livekit_room,
            },
        }
        return jwt.encode(payload, self.api_secret, algorithm="HS256")

    @staticmethod
    def _permission(livekit_room: str, can_publish_audio: bool) -> dict:
        return {
            "roomJoin": True,
            "room": livekit_room,
            "canSubscribe": True,
            "canPublishData": True,
            "canPublish": can_publish_audio,
            "canPublishSources": ["microphone"] if can_publish_audio else [],
        }
