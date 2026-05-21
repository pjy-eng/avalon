from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, StringConstraints

from app.api.ws import notify_room_after_command
from app.application.rooms import Participant, RoomService
from app.application.sessions import RoomSessionService, SessionError
from app.config import Settings
from app.domain.types import CommandError
from app.infrastructure.voice import VoiceProvider
from app.paths import STATIC_DIR

router = APIRouter()

StrippedNonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RequestId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
MISSING_PARTICIPANT_MESSAGE = "当前会话不属于该房间玩家。"


class JoinRoomRequest(BaseModel):
    nickname: StrippedNonEmpty


class RoomCommandRequest(BaseModel):
    session_token: StrippedNonEmpty
    request_id: RequestId
    command: dict[str, Any]


class VoiceTokenRequest(BaseModel):
    session_token: StrippedNonEmpty


@router.get("/health")
async def health(request: Request) -> dict[str, str | bool]:
    settings: Settings = request.app.state.settings
    return {
        "ok": True,
        "service": settings.service_name,
        "database": settings.database_status,
        "redis": settings.redis_status,
        "voice": settings.voice_status,
    }


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.post("/api/rooms/{room_id}/join")
async def join_room(room_id: str, payload: JoinRoomRequest, request: Request) -> dict[str, Any]:
    try:
        result = request.app.state.command_gateway.handle_join(room_id=room_id, nickname=payload.nickname)
    except CommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "room_id": result.room_id,
        "player_id": result.player_id,
        "session_token": result.session_token,
        "snapshot": result.snapshot,
    }


@router.post("/api/rooms/{room_id}/command")
async def room_command(room_id: str, payload: RoomCommandRequest, request: Request) -> dict[str, Any]:
    try:
        result = request.app.state.command_gateway.handle_command(
            room_id=room_id,
            session_token=payload.session_token,
            request_id=payload.request_id,
            command=payload.command,
        )
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except CommandError as exc:
        if str(exc) == MISSING_PARTICIPANT_MESSAGE:
            status_code = 401
        elif "只有房主" in str(exc):
            status_code = 403
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    await notify_room_after_command(
        connection_manager=request.app.state.connection_manager,
        command_gateway=request.app.state.command_gateway,
        room_service=request.app.state.room_service,
        room_id=room_id,
        result=result,
        voice_provider=request.app.state.voice_provider,
    )
    return {
        "snapshot": result.snapshot,
        "events": [asdict(event) for event in result.events],
    }


@router.post("/api/rooms/{room_id}/voice-token")
async def voice_token(room_id: str, payload: VoiceTokenRequest, request: Request) -> dict[str, Any]:
    session_service: RoomSessionService = request.app.state.session_service
    room_service: RoomService = request.app.state.room_service
    voice_provider: VoiceProvider = request.app.state.voice_provider
    try:
        claims = session_service.verify(payload.session_token, expected_room_id=room_id)
        room = room_service.get_room(room_id)
        participant = room_service.get_participant(room, claims.player_id)
        if participant.token_version != claims.token_version:
            raise SessionError("房间会话已失效，请重新加入房间。")
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except CommandError as exc:
        status_code = 401 if str(exc) == MISSING_PARTICIPANT_MESSAGE else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    can_publish_audio = True
    if room.game is not None:
        can_publish_audio = room.game.phase.value not in {"TEAM_VOTE", "MISSION_VOTE"}

    return voice_provider.issue_join_token(
        room_id=room.room_id,
        player_id=participant.player_id,
        display_name=_display_name(participant),
        can_publish_audio=can_publish_audio,
    )


def _display_name(participant: Participant) -> str:
    return f"{participant.seat}号-{participant.nickname}"
