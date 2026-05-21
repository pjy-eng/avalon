from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


PayloadFactory = Callable[[str], dict[str, Any]]


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, set[WebSocket]]] = {}

    def connect(self, room_id: str, player_id: str, websocket: WebSocket) -> None:
        room_connections = self._rooms.setdefault(room_id, {})
        player_connections = room_connections.setdefault(player_id, set())
        player_connections.add(websocket)

    def disconnect(self, room_id: str, player_id: str, websocket: WebSocket | None = None) -> None:
        room_connections = self._rooms.get(room_id)
        if room_connections is None:
            return
        if websocket is None:
            room_connections.pop(player_id, None)
        else:
            player_connections = room_connections.get(player_id)
            if player_connections is not None:
                player_connections.discard(websocket)
                if not player_connections:
                    room_connections.pop(player_id, None)
        if not room_connections:
            self._rooms.pop(room_id, None)

    async def disconnect_player(
        self,
        room_id: str,
        player_id: str,
        payload: dict[str, Any] | None = None,
        code: int = 1000,
    ) -> None:
        room_connections = self._rooms.get(room_id)
        if room_connections is None:
            return
        websockets = list(room_connections.pop(player_id, set()))
        if not room_connections:
            self._rooms.pop(room_id, None)

        for websocket in websockets:
            try:
                if payload is not None:
                    await websocket.send_json(payload)
                await websocket.close(code=code)
            except (RuntimeError, WebSocketDisconnect):
                continue

    def online_counts(self, room_id: str) -> dict[str, int]:
        return {
            player_id: len(player_connections)
            for player_id, player_connections in self._rooms.get(room_id, {}).items()
        }

    async def send_to_player(self, room_id: str, player_id: str, payload: dict[str, Any]) -> None:
        websockets = list(self._rooms.get(room_id, {}).get(player_id, set()))
        for websocket in websockets:
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                self.disconnect(room_id, player_id, websocket)

    async def broadcast_room(
        self,
        room_id: str,
        payload: dict[str, Any] | None = None,
        payload_factory: PayloadFactory | None = None,
    ) -> None:
        room_connections = [
            (player_id, list(player_connections))
            for player_id, player_connections in self._rooms.get(room_id, {}).items()
        ]
        for player_id, websockets in room_connections:
            player_payload = payload_factory(player_id) if payload_factory is not None else payload
            if player_payload is None:
                continue
            for websocket in websockets:
                try:
                    await websocket.send_json(player_payload)
                except (RuntimeError, WebSocketDisconnect):
                    self.disconnect(room_id, player_id, websocket)
