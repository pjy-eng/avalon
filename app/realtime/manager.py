from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


PayloadFactory = Callable[[str], dict[str, Any]]


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    def connect(self, room_id: str, player_id: str, websocket: WebSocket) -> None:
        room_connections = self._rooms.setdefault(room_id, {})
        room_connections[player_id] = websocket

    def disconnect(self, room_id: str, player_id: str) -> None:
        room_connections = self._rooms.get(room_id)
        if room_connections is None:
            return
        room_connections.pop(player_id, None)
        if not room_connections:
            self._rooms.pop(room_id, None)

    async def send_to_player(self, room_id: str, player_id: str, payload: dict[str, Any]) -> None:
        websocket = self._rooms.get(room_id, {}).get(player_id)
        if websocket is None:
            return
        await websocket.send_json(payload)

    async def broadcast_room(
        self,
        room_id: str,
        payload: dict[str, Any] | None = None,
        payload_factory: PayloadFactory | None = None,
    ) -> None:
        room_connections = list(self._rooms.get(room_id, {}).items())
        for player_id, websocket in room_connections:
            player_payload = payload_factory(player_id) if payload_factory is not None else payload
            if player_payload is None:
                continue
            try:
                await websocket.send_json(player_payload)
            except (RuntimeError, WebSocketDisconnect):
                self.disconnect(room_id, player_id)
