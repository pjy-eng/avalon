from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.events import AppEvent
from app.application.rooms import JoinResult, RoomService
from app.application.sessions import RoomSessionService
from app.domain.game import AvalonGame
from app.domain.types import CommandError, RulesetName


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

        if request_id in room.seen_request_ids:
            return CommandResult(snapshot=self.room_service.snapshot(room.room_id, viewer_id=participant.player_id))

        command_type = str(command.get("type") or "")
        if command_type == "start_game":
            result = self._handle_start_game(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        else:
            raise CommandError("暂不支持该操作。")

        room.seen_request_ids.add(request_id)
        return result

    def _handle_start_game(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以开局。")
        if len(room.participants) < 5:
            raise CommandError("阿瓦隆至少 5 人才能开始。")
        if room.game is not None:
            raise CommandError("游戏已经开始。")

        players = self.room_service.player_order(room)
        player_names = self.room_service.player_names(room)
        game = AvalonGame.new(
            players=players,
            player_names=player_names,
            ruleset=RulesetName.FRIEND_FLEXIBLE,
        )
        room.game = game
        room.ruleset = game.ruleset
        event = AppEvent(
            event_type="game_started",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"ruleset": game.ruleset.value, "players": players},
            request_id=request_id,
        )
        room.events.append(event)
        return CommandResult(
            snapshot=self.room_service.snapshot(room.room_id, viewer_id=actor_id),
            events=[event],
        )
