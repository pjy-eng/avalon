from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.application.events import AppEvent, utc_now_iso
from app.application.sessions import RoomSessionService
from app.application.snapshots import SnapshotProjector
from app.domain.game import AvalonGame
from app.domain.types import CommandError, Phase, RulesetName


@dataclass
class Participant:
    player_id: str
    nickname: str
    seat: int
    is_host: bool = False
    ready: bool = False
    token_version: int = 1


@dataclass
class RequestRecord:
    command_type: str
    command_payload: dict[str, Any]


@dataclass
class ChatMessage:
    author_id: str
    author_display: str
    text: str
    request_id: str | None = None
    message_id: str = field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class Room:
    room_id: str
    ruleset: RulesetName = RulesetName.FRIEND_FLEXIBLE
    participants: list[Participant] = field(default_factory=list)
    events: list[AppEvent] = field(default_factory=list)
    chat_history: list[ChatMessage] = field(default_factory=list)
    seen_request_ids: dict[tuple[str, str, str], RequestRecord] = field(default_factory=dict)
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

    def create(self, room_id: str) -> Room:
        normalized_room_id = room_id.strip()
        if not normalized_room_id:
            raise CommandError("房间号不能为空。")
        room = self._rooms.get(normalized_room_id)
        if room is None:
            room = Room(room_id=normalized_room_id)
            self._rooms[normalized_room_id] = room
        return room

    def join(self, room_id: str, nickname: str) -> JoinResult:
        normalized_nickname = nickname.strip()
        if not normalized_nickname:
            raise CommandError("昵称不能为空。")

        room = self.create(room_id)
        if room.game is not None:
            raise CommandError("游戏开始后不能加入房间。")

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
                    "ready": participant.ready,
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

    def ready(self, room_id: str, actor_id: str, request_id: str, ready: bool = True) -> AppEvent:
        room = self.get_room(room_id)
        if room.game is not None:
            raise CommandError("游戏开始后不能修改准备状态。")
        participant = self.get_participant(room, actor_id)
        participant.ready = ready
        event = AppEvent(
            event_type="participant_ready_changed",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"player_id": actor_id, "ready": participant.ready},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def start(self, room_id: str, actor_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以开局。")
        if len(room.participants) < 5:
            raise CommandError("阿瓦隆至少 5 人才能开始。")
        if room.game is not None:
            raise CommandError("游戏已经开始。")

        players = self.player_order(room)
        player_names = self.player_names(room)
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
        return event

    def reset(self, room_id: str, actor_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以重置房间。")
        room.game = None
        for participant in room.participants:
            participant.ready = False
        event = AppEvent(
            event_type="room_reset",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"player_ids": self.player_order(room)},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def add_chat_message(self, room_id: str, actor_id: str, text: str, request_id: str | None = None) -> ChatMessage:
        room = self.get_room(room_id)
        participant = self.get_participant(room, actor_id)
        trimmed_text = text.strip()
        if not trimmed_text:
            raise CommandError("消息不能为空。")
        if len(trimmed_text) > 300:
            raise CommandError("消息不能超过 300 字。")

        message = ChatMessage(
            message_id=f"msg_{uuid4().hex[:12]}",
            author_id=actor_id,
            author_display=f"{participant.seat}号-{participant.nickname}",
            text=trimmed_text,
            request_id=request_id,
            created_at=utc_now_iso(),
        )
        room.chat_history.append(message)
        room.chat_history = room.chat_history[-100:]
        return message

    def kick_player(self, room_id: str, actor_id: str, target_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        self._require_lobby(room)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以移除玩家。")
        if actor_id == target_id:
            raise CommandError("房主不能移除自己。")
        target = self.get_participant(room, target_id)

        room.participants = [participant for participant in room.participants if participant.player_id != target_id]
        self._compact_seats(room)
        event = AppEvent(
            event_type="participant_kicked",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"player_id": target.player_id, "target_id": target.player_id, "nickname": target.nickname},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def transfer_host(self, room_id: str, actor_id: str, target_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        self._require_lobby(room)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以转让房主。")
        if actor_id == target_id:
            raise CommandError("房主不能转让给自己。")
        target = self.get_participant(room, target_id)

        for participant in room.participants:
            participant.is_host = participant.player_id == target.player_id
        event = AppEvent(
            event_type="host_transferred",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"from_player_id": actor_id, "to_player_id": target.player_id},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def leave_room(self, room_id: str, actor_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        self._require_lobby(room)
        actor = self.get_participant(room, actor_id)
        was_host = actor.is_host

        room.participants = [participant for participant in room.participants if participant.player_id != actor_id]
        if was_host and room.participants:
            room.participants[0].is_host = True
        self._compact_seats(room)
        event = AppEvent(
            event_type="participant_left",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"player_id": actor.player_id, "nickname": actor.nickname},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def snapshot(
        self,
        room_id: str,
        viewer_id: str | None = None,
        online_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        room = self.get_room(room_id)
        participants = sorted(room.participants, key=lambda item: item.seat)
        status = "lobby" if room.game is None else "game"
        phase = Phase.LOBBY if room.game is None else room.game.phase
        snapshot: dict[str, Any] = {
            "room": {
                "room_id": room.room_id,
                "ruleset": room.ruleset.value,
                "host_id": room.host_id,
                "player_count": len(participants),
                "status": status,
            },
            "participants": [
                {
                    "player_id": participant.player_id,
                    "nickname": participant.nickname,
                    "seat": participant.seat,
                    "is_host": participant.is_host,
                    "ready": participant.ready,
                }
                for participant in participants
            ],
            "you": self._you_payload(room, viewer_id),
            "voice_state": self._voice_state(phase),
            "speaker_state": self._speaker_state(phase),
            "online_state": self._online_state(participants, online_counts),
            "chat_history": self._chat_history(room),
        }
        if room.game is None:
            snapshot["phase_summary"] = {"phase": Phase.LOBBY.value}
            snapshot["public_timeline"] = self._public_timeline(room)
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
            mission_result = SnapshotProjector.latest_mission_result(room.events)
            if mission_result is not None:
                snapshot["phase_summary"]["mission_result"] = mission_result
            snapshot["public_timeline"] = SnapshotProjector.public_timeline(game, room.events)
        return snapshot

    def _new_player_id(self, room: Room) -> str:
        existing_ids = {participant.player_id for participant in room.participants}
        while True:
            player_id = f"p_{uuid4().hex[:10]}"
            if player_id not in existing_ids:
                return player_id

    @staticmethod
    def _require_lobby(room: Room) -> None:
        if room.game is not None:
            raise CommandError("游戏开始后不能执行该操作。")

    @staticmethod
    def _compact_seats(room: Room) -> None:
        for seat, participant in enumerate(sorted(room.participants, key=lambda item: item.seat), start=1):
            participant.seat = seat

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
            "ready": participant.ready,
        }

    @staticmethod
    def _voice_state(phase: Phase) -> dict[str, Any]:
        can_publish_audio = phase not in {Phase.TEAM_VOTE, Phase.MISSION_VOTE}
        return {
            "can_publish_audio": can_publish_audio,
            "publish_policy": "open" if can_publish_audio else "muted",
        }

    @staticmethod
    def _speaker_state(phase: Phase) -> dict[str, Any]:
        can_speak = phase not in {Phase.TEAM_VOTE, Phase.MISSION_VOTE}
        return {
            "mode": "open" if can_speak else "muted",
            "can_send_text": can_speak,
        }

    @staticmethod
    def _online_state(participants: list[Participant], online_counts: dict[str, int] | None) -> dict[str, Any]:
        counts = online_counts or {}
        return {
            "players": [
                {
                    "player_id": participant.player_id,
                    "online": int(counts.get(participant.player_id, 0)) > 0,
                    "connection_count": max(0, int(counts.get(participant.player_id, 0))),
                }
                for participant in participants
            ]
        }

    def _chat_history(self, room: Room) -> list[dict[str, Any]]:
        return [
            {
                "message_id": self._message_value(message, "message_id", ""),
                "author_id": self._message_value(message, "author_id", ""),
                "author_display": self._message_value(
                    message,
                    "author_display",
                    self._display_name(room, str(self._message_value(message, "author_id", ""))),
                ),
                "text": self._message_value(message, "text", ""),
                "request_id": self._message_value(message, "request_id", None),
                "created_at": self._message_value(message, "created_at", ""),
            }
            for message in room.chat_history[-50:]
        ]

    def _display_name(self, room: Room, player_id: str) -> str:
        participant = next((item for item in room.participants if item.player_id == player_id), None)
        if participant is None:
            return "未知玩家"
        return f"{participant.seat}号-{participant.nickname}"

    def _public_timeline(self, room: Room) -> list[dict[str, Any]]:
        timeline = []
        for event in room.events:
            summary = self._lobby_event_summary(room, event)
            if summary is None:
                continue
            timeline.append(
                {
                    "kind": event.event_type,
                    "summary": summary,
                    "created_at": event.created_at,
                }
            )
        return timeline

    def _lobby_event_summary(self, room: Room, event: AppEvent) -> str | None:
        payload = event.payload
        if event.event_type == "game_started":
            player_count = len(payload.get("players", [])) or len(room.participants)
            return f"游戏开始，共 {player_count} 名玩家。"
        if event.event_type == "team_selected":
            leader_id = str(payload.get("leader_id") or event.actor_id or "")
            team = self._display_list(room, payload.get("team", []))
            return f"第 {payload.get('round_number')} 轮，队长 {self._display_name(room, leader_id)} 选择队伍：{team}。"
        if event.event_type == "team_vote_resolved":
            result = "通过" if payload.get("approved") else "未通过"
            return (
                f"第 {payload.get('round_number')} 轮组队投票{result}："
                f"{payload.get('approve_count', 0)} 票同意，{payload.get('reject_count', 0)} 票反对。"
            )
        if event.event_type == "mission_resolved":
            result = "成功" if payload.get("succeeded") else "失败"
            return (
                f"第 {payload.get('round_number')} 轮任务{result}：失败票 "
                f"{payload.get('fail_count', 0)}/{payload.get('required_fail_count', 1)}，"
                f"比分 好人 {payload.get('score_good', 0)} - 邪恶 {payload.get('score_evil', 0)}。"
            )
        if event.event_type == "round_advanced":
            leader_id = str(payload.get("leader_id") or "")
            return (
                f"进入第 {payload.get('round_number')} 轮，队长 {self._display_name(room, leader_id)}，"
                f"需选择 {payload.get('required_team_size')} 人。"
            )
        if event.event_type == "assassination_resolved":
            target_id = str(payload.get("target_id") or "")
            winner = self._winner_label(payload.get("winner"))
            return f"刺杀目标 {self._display_name(room, target_id)}，{winner}阵营获胜。"
        if event.event_type == "game_over":
            winner = self._winner_label(payload.get("winner"))
            reason = "任务" if payload.get("reason") == "missions" else "刺杀"
            return f"游戏结束，{winner}阵营获胜，原因：{reason}。"
        return None

    def _display_list(self, room: Room, player_ids: Any) -> str:
        if not isinstance(player_ids, list):
            return "未知玩家"
        return "、".join(self._display_name(room, str(player_id)) for player_id in player_ids)

    @staticmethod
    def _winner_label(winner: Any) -> str:
        if winner == "good":
            return "好人"
        if winner == "evil":
            return "邪恶"
        return "未知"

    @staticmethod
    def _message_value(source: Any, key: str, default: Any) -> Any:
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)
