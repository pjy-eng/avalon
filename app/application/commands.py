from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.application.events import AppEvent
from app.application.rooms import JoinResult, RequestRecord, Room, RoomService
from app.application.sessions import RoomSessionService, SessionError
from app.application.snapshots import SnapshotProjector
from app.domain.game import AvalonGame
from app.domain.types import CommandError, Phase


@dataclass(frozen=True)
class CommandResult:
    snapshot: dict[str, Any]
    events: list[AppEvent] = field(default_factory=list)


class CommandGateway:
    def __init__(
        self,
        room_service: RoomService,
        session_service: RoomSessionService,
        online_players_provider: Callable[[str], Mapping[str, int]] | None = None,
    ) -> None:
        self.room_service = room_service
        self.session_service = session_service
        self.online_players_provider = online_players_provider

    def handle_join(self, room_id: str, nickname: str) -> JoinResult:
        return self.room_service.join(room_id=room_id, nickname=nickname)

    def handle_resume(self, room_id: str, session_token: str) -> JoinResult:
        claims = self.session_service.verify(session_token, expected_room_id=room_id)
        room = self.room_service.get_room(room_id)
        participant = self.room_service.get_participant(room, claims.player_id)
        if participant.token_version != claims.token_version:
            raise SessionError("房间会话已失效，请重新加入房间。")
        return JoinResult(
            room_id=room.room_id,
            player_id=participant.player_id,
            session_token=session_token,
            snapshot=self._snapshot_for_actor(room.room_id, participant.player_id),
        )

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
            return CommandResult(snapshot=self._snapshot_for_actor(room.room_id, participant.player_id))

        if command_type == "start_game":
            result = self._handle_start_game(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "ready":
            result = self._handle_ready(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "reset":
            result = self._handle_reset(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "send_chat":
            result = self._handle_send_chat(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "kick_player":
            result = self._handle_kick_player(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "transfer_host":
            result = self._handle_transfer_host(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "leave_room":
            result = self._handle_leave_room(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "select_team":
            result = self._handle_select_team(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "team_vote":
            result = self._handle_team_vote(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "mission_vote":
            result = self._handle_mission_vote(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        elif command_type == "continue_after_result":
            result = self._handle_continue_after_result(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
            )
        elif command_type == "assassinate":
            result = self._handle_assassinate(
                room_id=room.room_id,
                actor_id=participant.player_id,
                request_id=request_id,
                command=command,
            )
        else:
            raise CommandError("暂不支持该操作。")

        room.seen_request_ids[dedupe_key] = RequestRecord(command_type=command_type, command_payload=dict(command))
        return result

    def _handle_start_game(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.start(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(
            snapshot=self._snapshot_for_actor(room_id, actor_id),
            events=[event],
        )

    def _handle_ready(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        ready = bool(command.get("ready", True))
        event = self.room_service.ready(room_id=room_id, actor_id=actor_id, ready=ready, request_id=request_id)
        return CommandResult(
            snapshot=self._snapshot_for_actor(room_id, actor_id),
            events=[event],
        )

    def _handle_reset(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.reset(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(
            snapshot=self._snapshot_for_actor(room_id, actor_id),
            events=[event],
        )

    def _handle_send_chat(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        if not self._can_send_text(room_id):
            raise CommandError("当前阶段禁止发言。")
        text = self._string_payload(command, "text")
        message = self.room_service.add_chat_message(
            room_id=room_id,
            actor_id=actor_id,
            text=text,
            request_id=request_id,
        )
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="chat_message_sent",
            payload={"message_id": message.message_id},
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_kick_player(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        target_id = self._string_payload(command, "target_id")
        event = self.room_service.kick_player(
            room_id=room_id,
            actor_id=actor_id,
            target_id=target_id,
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_transfer_host(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        target_id = self._string_payload(command, "target_id")
        event = self.room_service.transfer_host(
            room_id=room_id,
            actor_id=actor_id,
            target_id=target_id,
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_leave_room(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.leave_room(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(
            snapshot=self.room_service.snapshot(room_id, viewer_id=None, online_counts=self._online_counts(room_id)),
            events=[event],
        )

    def _handle_select_team(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        room = self.room_service.get_room(room_id)
        game = self._require_game(room)
        team = self._string_list_payload(command, "team")

        game.select_team(actor_id=actor_id, team=team)
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="team_selected",
            payload={
                "round_number": game.round_number,
                "leader_id": actor_id,
                "team": team,
                "required_team_size": game.required_team_size,
            },
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_team_vote(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        room = self.room_service.get_room(room_id)
        game = self._require_game(room)
        vote = self._string_payload(command, "vote")
        round_number = game.round_number
        team = game.current_team[:]
        votes_after = {**game.team_votes, actor_id: vote}

        game.submit_team_vote(actor_id=actor_id, vote=vote)

        events: list[AppEvent] = []
        if len(votes_after) == len(game.player_order):
            approve_count = sum(1 for value in votes_after.values() if value == "Approve")
            reject_count = len(votes_after) - approve_count
            events.append(
                self._append_event(
                    room_id=room_id,
                    actor_id=None,
                    event_type="team_vote_resolved",
                    payload={
                        "round_number": round_number,
                        "team": team,
                        "approved": approve_count > len(game.player_order) / 2,
                        "approve_count": approve_count,
                        "reject_count": reject_count,
                    },
                    request_id=request_id,
                )
            )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=events)

    def _handle_mission_vote(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        room = self.room_service.get_room(room_id)
        game = self._require_game(room)
        vote = self._string_payload(command, "vote")
        round_number = game.round_number
        team = game.current_team[:]
        votes_after = {**game.mission_votes, actor_id: vote}
        required_fail_count = 2 if len(game.player_order) >= 7 and round_number == 4 else 1

        game.submit_mission_vote(actor_id=actor_id, vote=vote)

        events: list[AppEvent] = []
        if len(votes_after) == len(team):
            fail_count = sum(1 for value in votes_after.values() if value == "Fail")
            succeeded = fail_count < required_fail_count
            events.append(
                self._append_event(
                    room_id=room_id,
                    actor_id=None,
                    event_type="mission_resolved",
                    payload={
                        "round_number": round_number,
                        "team": team,
                        "succeeded": succeeded,
                        "fail_count": fail_count,
                        "required_fail_count": required_fail_count,
                        "score_good": game.score_good,
                        "score_evil": game.score_evil,
                    },
                    request_id=request_id,
                )
            )
            if game.winner == "evil":
                events.append(
                    self._append_event(
                        room_id=room_id,
                        actor_id=None,
                        event_type="game_over",
                        payload={
                            "winner": game.winner,
                            "reason": "missions",
                        },
                        request_id=request_id,
                    )
                )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=events)

    def _handle_continue_after_result(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        room = self.room_service.get_room(room_id)
        game = self._require_game(room)
        if actor_id != room.host_id:
            raise CommandError("只有房主可以推进下一轮。")

        game.continue_after_mission_result()
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="round_advanced",
            payload={
                "round_number": game.round_number,
                "leader_id": game.leader_id,
                "required_team_size": game.required_team_size,
            },
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_assassinate(
        self,
        room_id: str,
        actor_id: str,
        request_id: str,
        command: dict[str, Any],
    ) -> CommandResult:
        room = self.room_service.get_room(room_id)
        game = self._require_game(room)
        target_id = self._string_payload(command, "target_id")

        game.submit_assassination(actor_id=actor_id, target_id=target_id)
        assassination_event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="assassination_resolved",
            payload={
                "target_id": target_id,
                "winner": game.winner,
            },
            request_id=request_id,
        )
        game_over_event = self._append_event(
            room_id=room_id,
            actor_id=None,
            event_type="game_over",
            payload={
                "winner": game.winner,
                "reason": "assassination",
            },
            request_id=request_id,
        )
        return CommandResult(
            snapshot=self._snapshot_for_actor(room_id, actor_id),
            events=[assassination_event, game_over_event],
        )

    def _snapshot_for_actor(self, room_id: str, actor_id: str) -> dict[str, Any]:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            return self.room_service.snapshot(room_id, viewer_id=actor_id, online_counts=self._online_counts(room_id))
        return SnapshotProjector.for_player(
            game=room.game,
            player_id=actor_id,
            host_id=room.host_id,
            room_id=room.room_id,
            events=room.events,
            chat_history=room.chat_history,
            online_counts=self._online_counts(room_id),
        )

    def _append_event(
        self,
        room_id: str,
        actor_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> AppEvent:
        room = self.room_service.get_room(room_id)
        event = AppEvent(
            event_type=event_type,
            room_id=room.room_id,
            actor_id=actor_id,
            payload=payload,
            request_id=request_id,
        )
        room.events.append(event)
        return event

    @staticmethod
    def _require_game(room: Room) -> AvalonGame:
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        return room.game

    def _can_send_text(self, room_id: str) -> bool:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            return True
        return room.game.phase not in {Phase.TEAM_VOTE, Phase.MISSION_VOTE}

    @staticmethod
    def _string_list_payload(command: dict[str, Any], key: str) -> list[str]:
        value = command.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise CommandError(f"{key} 必须是字符串列表。")
        return value[:]

    @staticmethod
    def _string_payload(command: dict[str, Any], key: str) -> str:
        value = command.get(key)
        if not isinstance(value, str):
            raise CommandError(f"{key} 必须是字符串。")
        return value

    def _online_counts(self, room_id: str) -> dict[str, int]:
        if self.online_players_provider is None:
            return {}
        return dict(self.online_players_provider(room_id))
