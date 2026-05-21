from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.application.events import AppEvent
from app.application.sessions import RoomSessionService
from app.domain.game import AvalonGame
from app.domain.types import CommandError, Phase, RulesetName


@dataclass
class Participant:
    player_id: str
    nickname: str
    seat: int
    is_host: bool = False
    token_version: int = 1


@dataclass
class Room:
    room_id: str
    ruleset: RulesetName = RulesetName.FRIEND_FLEXIBLE
    participants: list[Participant] = field(default_factory=list)
    events: list[AppEvent] = field(default_factory=list)
    seen_request_ids: set[str] = field(default_factory=set)
    game: AvalonGame | None = None

    @property
    def host_id(self) -> str | None:
        host = next((participant for participant in self.participants if participant.is_host), None)
        return host.player_id if host else None


@dataclass(frozen=True)
class JoinResult:
    room_id: str
    player_id: str
    session_token: str
    snapshot: dict[str, Any]


class RoomService:
    def __init__(self, session_service: RoomSessionService) -> None:
        self.session_service = session_service
        self._rooms: dict[str, Room] = {}

    def join(self, room_id: str, nickname: str) -> JoinResult:
        normalized_room_id = room_id.strip()
        normalized_nickname = nickname.strip()
        if not normalized_room_id:
            raise CommandError("房间号不能为空。")
        if not normalized_nickname:
            raise CommandError("昵称不能为空。")

        room = self._rooms.setdefault(normalized_room_id, Room(room_id=normalized_room_id))
        player_id = self._new_player_id(room)
        participant = Participant(
            player_id=player_id,
            nickname=normalized_nickname,
            seat=len(room.participants) + 1,
            is_host=not room.participants,
        )
        room.participants.append(participant)
        room.events.append(
            AppEvent(
                event_type="participant_joined",
                room_id=room.room_id,
                actor_id=participant.player_id,
                payload={
                    "player_id": participant.player_id,
                    "nickname": participant.nickname,
                    "seat": participant.seat,
                    "is_host": participant.is_host,
                },
            )
        )
        token = self.session_service.issue(
            room_id=room.room_id,
            player_id=participant.player_id,
            token_version=participant.token_version,
        )
        return JoinResult(
            room_id=room.room_id,
            player_id=participant.player_id,
            session_token=token,
            snapshot=self.snapshot(room.room_id, viewer_id=participant.player_id),
        )

    def get_room(self, room_id: str) -> Room:
        try:
            return self._rooms[room_id]
        except KeyError as exc:
            raise CommandError("房间不存在，请重新加入。") from exc

    def get_participant(self, room: Room, player_id: str) -> Participant:
        participant = next((item for item in room.participants if item.player_id == player_id), None)
        if participant is None:
            raise CommandError("当前会话不属于该房间玩家。")
        return participant

    def player_order(self, room: Room) -> list[str]:
        return [participant.player_id for participant in sorted(room.participants, key=lambda item: item.seat)]

    def player_names(self, room: Room) -> dict[str, str]:
        return {participant.player_id: participant.nickname for participant in sorted(room.participants, key=lambda item: item.seat)}

    def snapshot(self, room_id: str, viewer_id: str | None = None) -> dict[str, Any]:
        room = self.get_room(room_id)
        participants = sorted(room.participants, key=lambda item: item.seat)
        snapshot: dict[str, Any] = {
            "room": {
                "room_id": room.room_id,
                "ruleset": room.ruleset.value,
                "host_id": room.host_id,
                "player_count": len(participants),
            },
            "participants": [
                {
                    "player_id": participant.player_id,
                    "nickname": participant.nickname,
                    "seat": participant.seat,
                    "is_host": participant.is_host,
                }
                for participant in participants
            ],
            "you": self._you_payload(room, viewer_id),
        }
        if room.game is None:
            snapshot["phase_summary"] = {"phase": Phase.LOBBY.value}
        else:
            game = room.game
            snapshot["phase_summary"] = {
                "phase": game.phase.value,
                "round_number": game.round_number,
                "leader_id": game.leader_id,
                "required_team_size": game.required_team_size,
                "current_team": game.current_team[:],
                "score_good": game.score_good,
                "score_evil": game.score_evil,
                "winner": game.winner,
            }
        return snapshot

    def _new_player_id(self, room: Room) -> str:
        existing_ids = {participant.player_id for participant in room.participants}
        while True:
            player_id = f"p_{uuid4().hex[:10]}"
            if player_id not in existing_ids:
                return player_id

    def _you_payload(self, room: Room, viewer_id: str | None) -> dict[str, Any] | None:
        if viewer_id is None:
            return None
        participant = next((item for item in room.participants if item.player_id == viewer_id), None)
        if participant is None:
            return None
        return {
            "player_id": participant.player_id,
            "nickname": participant.nickname,
            "seat": participant.seat,
            "is_host": participant.is_host,
        }
