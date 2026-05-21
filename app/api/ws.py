from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService, SessionError
from app.domain.types import CommandError
from app.realtime import ConnectionManager

router = APIRouter()

HELLO_SESSION_TOKEN_ERROR = "第一条消息必须包含 session_token。"
REQUEST_ID_REQUIRED_ERROR = "request_id 不能为空。"
REQUEST_ID_TYPE_ERROR = "request_id 必须是字符串。"
REQUEST_ID_TOO_LONG_ERROR = "request_id 长度不能超过 128。"


@router.websocket("/ws/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()

    player_id: str | None = None
    connected_room_id: str | None = None
    connected = False
    manager: ConnectionManager = websocket.app.state.connection_manager
    command_gateway: CommandGateway = websocket.app.state.command_gateway
    room_service: RoomService = websocket.app.state.room_service
    session_service: RoomSessionService = websocket.app.state.session_service

    try:
        hello_message = await websocket.receive_json()
        session_token = _hello_session_token(hello_message)
        if not session_token:
            await _send_error_and_close(websocket, HELLO_SESSION_TOKEN_ERROR)
            return

        try:
            claims = session_service.verify(session_token, expected_room_id=room_id)
            room = room_service.get_room(room_id)
            participant = room_service.get_participant(room, claims.player_id)
            if participant.token_version != claims.token_version:
                raise SessionError("房间会话已失效，请重新加入房间。")
        except (SessionError, CommandError) as exc:
            await _send_error_and_close(websocket, str(exc))
            return

        player_id = participant.player_id
        connected_room_id = room.room_id
        manager.connect(room.room_id, player_id, websocket)
        connected = True
        await manager.send_to_player(
            room.room_id,
            player_id,
            {"type": "state", "snapshot": command_gateway._snapshot_for_actor(room.room_id, player_id)},
        )

        while True:
            message = await websocket.receive_json()
            await _handle_message(
                websocket=websocket,
                room_id=room.room_id,
                session_token=session_token,
                message=message,
                command_gateway=command_gateway,
                connection_manager=manager,
            )
    except WebSocketDisconnect:
        return
    finally:
        if connected and connected_room_id is not None and player_id is not None:
            manager.disconnect(connected_room_id, player_id, websocket)


async def _handle_message(
    websocket: WebSocket,
    room_id: str,
    session_token: str,
    message: Any,
    command_gateway: CommandGateway,
    connection_manager: ConnectionManager,
) -> None:
    if not isinstance(message, dict):
        await websocket.send_json({"type": "error", "message": "消息格式无效。"})
        return

    message_type = message.get("type")
    if message_type == "ping":
        await websocket.send_json({"type": "pong"})
        return

    if message_type != "command":
        await websocket.send_json({"type": "error", "message": "未知消息类型。"})
        return

    request_id, request_id_error = _command_request_id(message)
    if request_id_error is not None:
        await websocket.send_json({"type": "error", "message": request_id_error})
        return

    command = message.get("command")
    if not isinstance(command, dict):
        await websocket.send_json({"type": "error", "message": "command 必须是对象。"})
        return

    try:
        command_gateway.handle_command(
            room_id=room_id,
            session_token=session_token,
            request_id=request_id,
            command=command,
        )
    except (SessionError, CommandError) as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        return

    await connection_manager.broadcast_room(
        room_id,
        payload_factory=lambda player_id: {
            "type": "state",
            "snapshot": command_gateway._snapshot_for_actor(room_id, player_id),
        },
    )


def _hello_session_token(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    if message.get("type") != "hello":
        return None
    session_token = str(message.get("session_token") or "").strip()
    return session_token or None


def _command_request_id(message: dict[str, Any]) -> tuple[str | None, str | None]:
    request_id = message.get("request_id")
    if not isinstance(request_id, str):
        return None, REQUEST_ID_TYPE_ERROR

    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        return None, REQUEST_ID_REQUIRED_ERROR
    if len(normalized_request_id) > 128:
        return None, REQUEST_ID_TOO_LONG_ERROR
    return normalized_request_id, None


async def _send_error_and_close(websocket: WebSocket, message: str) -> None:
    await websocket.send_json({"type": "error", "message": message})
    await websocket.close()
