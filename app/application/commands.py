from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.events import AppEvent
from app.application.rooms import JoinResult, RequestRecord, RoomService
from app.application.sessions import RoomSessionService
from app.domain.types import CommandError


@dataclass(frozen=True)
class CommandResult:
    snapshot: dict[str, Any]
    events: list[AppEvent] = field(default_factory=list)


class CommandGateway:
    def __init__(self, room_service: RoomService, session_service: RoomSessionService) -> None:
        self.room_service = room_service
        self.session_service = session_service

    def handle_join(self, room_id: str, nickname: str) -> JoinResult:
        return self.room_service.join(room_id=room_id, nickname=nickname)

    def handle_command(
        self,
        room_id: str,
        session_token: str,
        command: dict[str, Any],
        request_id: str,
    ) -> CommandResult:
        claims = self.session_service.verify(session_token, expected_room_id=room_id)
        room = self.room_service.get_room(room_id)
        participant = self.room_service.get_participant(room, claims.player_id)
        if participant.token_version != claims.token_version:
            raise CommandError("房间会话已失效，请重新加入房间。")

        command_type = str(command.get("type") or "")
        dedupe_key = (room.room_id, participant.player_id, request_id)
        existing_request = room.seen_request_ids.get(dedupe_key)
        if existing_request is not None:
            if existing_request.command_type != command_type or existing_request.command_payload != command:
                raise CommandError("重复请求编号对应不同操作。")
            return CommandResult(snapshot=self.room_service.snapshot(room.room_id, viewer_id=participant.player_id))

        if command_type == "start_game":
            result = self._handle_start_game(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "ready":
            result = self._handle_ready(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "reset":
            result = self._handle_reset(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        else:
            raise CommandError("暂不支持该操作。")

        room.seen_request_ids[dedupe_key] = RequestRecord(command_type=command_type, command_payload=dict(command))
        return result

    def _handle_start_game(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.start(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(
            snapshot=self.room_service.snapshot(room_id, viewer_id=actor_id),
            events=[event],
        )

    def _handle_ready(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        ready = bool(command.get("ready", True))
        event = self.room_service.ready(room_id=room_id, actor_id=actor_id, ready=ready, request_id=request_id)
        return CommandResult(
            snapshot=self.room_service.snapshot(room_id, viewer_id=actor_id),
            events=[event],
        )

    def _handle_reset(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.reset(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(
            snapshot=self.room_service.snapshot(room_id, viewer_id=actor_id),
            events=[event],
        )
