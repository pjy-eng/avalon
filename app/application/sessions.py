from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt


class SessionError(ValueError):
    """Raised when a room session token cannot be trusted."""


@dataclass(frozen=True)
class RoomSessionClaims:
    room_id: str
    player_id: str
    token_version: int


class RoomSessionService:
    def __init__(self, secret: str, ttl_hours: int = 12) -> None:
        self.secret = secret
        self.ttl_hours = ttl_hours

    def issue(self, room_id: str, player_id: str, token_version: int) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": player_id,
            "room_id": room_id,
            "token_version": token_version,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=self.ttl_hours)).timestamp()),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def verify(self, token: str, expected_room_id: str) -> RoomSessionClaims:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise SessionError("房间会话无效，请重新加入房间。") from exc
        room_id = str(payload.get("room_id") or "")
        if room_id != expected_room_id:
            raise SessionError("房间会话不属于当前房间。")
        player_id = str(payload.get("sub") or "")
        token_version = int(payload.get("token_version") or 0)
        if not player_id or token_version < 1:
            raise SessionError("房间会话缺少玩家身份。")
        return RoomSessionClaims(room_id=room_id, player_id=player_id, token_version=token_version)
