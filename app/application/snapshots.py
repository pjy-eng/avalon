from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.application.events import AppEvent
from app.domain.game import AvalonGame
from app.domain.types import EVIL_ROLES, GOOD_ROLES, Phase, Role


class SnapshotProjector:
    @classmethod
    def for_player(
        cls,
        game: AvalonGame,
        player_id: str,
        host_id: str | None,
        room_id: str,
        events: Sequence[AppEvent] | None = None,
        chat_history: Sequence[Any] | None = None,
        online_counts: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        phase_summary = {
            "phase": game.phase.value,
            "round_number": game.round_number,
            "round": game.round_number,
            "leader_id": game.leader_id,
            "required_team_size": game.required_team_size,
            "current_team": game.current_team[:],
            "score_good": game.score_good,
            "score_evil": game.score_evil,
            "score": {
                "good": game.score_good,
                "evil": game.score_evil,
            },
            "winner": game.winner,
        }
        mission_result = cls.latest_mission_result(events)
        if mission_result is not None:
            phase_summary["mission_result"] = mission_result

        snapshot = {
            "room": {
                "room_id": room_id,
                "ruleset": game.ruleset.value,
                "host_id": host_id,
                "player_count": len(game.player_order),
                "status": "game",
            },
            "you": {
                "player_id": player_id,
                "is_host": player_id == host_id,
                "nickname": game.player_names[player_id],
                "seat": game.player_order.index(player_id) + 1,
            },
            "phase_summary": phase_summary,
            "players": [
                {
                    "player_id": candidate_id,
                    "display": cls._display(game, candidate_id),
                    "seat": game.player_order.index(candidate_id) + 1,
                    "nickname": game.player_names[candidate_id],
                    "is_host": candidate_id == host_id,
                    "is_leader": candidate_id == game.leader_id,
                }
                for candidate_id in game.player_order
            ],
            "private_panel": cls._private_panel(game, player_id),
            "my_action": cls._my_action(game, player_id),
            "voice_state": cls._voice_state(game.phase),
            "speaker_state": cls._speaker_state(game.phase),
            "online_state": cls._online_state(game, online_counts),
            "chat_history": cls._chat_history(game, chat_history),
            "public_timeline": cls.public_timeline(game, events),
        }
        if game.phase == Phase.GAME_OVER:
            snapshot["reveal_roles"] = cls._reveal_roles(game)
        return snapshot

    @classmethod
    def _private_panel(cls, game: AvalonGame, player_id: str) -> dict[str, Any]:
        role = game.roles[player_id]
        return {
            "role": role.value,
            "side": cls._side(role),
            "visible_players": [
                {
                    "player_id": visible_id,
                    "display": cls._display(game, visible_id),
                }
                for visible_id in cls._visible_player_ids(game, player_id)
            ],
        }

    @classmethod
    def _visible_player_ids(cls, game: AvalonGame, player_id: str) -> list[str]:
        role = game.roles[player_id]
        if role == Role.MERLIN:
            return [
                candidate_id
                for candidate_id in game.player_order
                if game.roles[candidate_id] in EVIL_ROLES and game.roles[candidate_id] != Role.MORDRED
            ]
        if role == Role.PERCIVAL:
            return [
                candidate_id
                for candidate_id in game.player_order
                if game.roles[candidate_id] in {Role.MERLIN, Role.MORGANA}
            ]
        if role in EVIL_ROLES and role != Role.OBERON:
            return [
                candidate_id
                for candidate_id in game.player_order
                if candidate_id != player_id
                and game.roles[candidate_id] in EVIL_ROLES
                and game.roles[candidate_id] != Role.OBERON
            ]
        return []

    @staticmethod
    def _my_action(game: AvalonGame, player_id: str) -> dict[str, Any]:
        if game.phase == Phase.TEAM_PROPOSAL and player_id == game.leader_id:
            return {"type": "select_team"}
        if game.phase == Phase.TEAM_VOTE and player_id not in game.team_votes:
            return {"type": "team_vote"}
        if game.phase == Phase.MISSION_VOTE and player_id in game.current_team and player_id not in game.mission_votes:
            return {"type": "mission_vote", "can_submit_fail": game.ruleset.value == "friend_flexible"}
        if game.phase == Phase.ASSASSINATION and game.roles[player_id] == Role.ASSASSIN:
            return {"type": "assassinate"}
        return {"type": "wait"}

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
    def _display(game: AvalonGame, player_id: str) -> str:
        if player_id not in game.player_order:
            return "未知玩家"
        name = game.player_names.get(player_id)
        if not name:
            return "未知玩家"
        seat_number = game.player_order.index(player_id) + 1
        return f"{seat_number}号-{name}"

    @staticmethod
    def _side(role: Role) -> str:
        if role in GOOD_ROLES:
            return "good"
        return "evil"

    @classmethod
    def _online_state(cls, game: AvalonGame, online_counts: Mapping[str, int] | None) -> dict[str, Any]:
        counts = online_counts or {}
        return {
            "players": [
                {
                    "player_id": player_id,
                    "online": int(counts.get(player_id, 0)) > 0,
                    "connection_count": max(0, int(counts.get(player_id, 0))),
                }
                for player_id in game.player_order
            ]
        }

    @classmethod
    def _chat_history(cls, game: AvalonGame, chat_history: Sequence[Any] | None) -> list[dict[str, Any]]:
        return [
            {
                "message_id": cls._value(message, "message_id", ""),
                "author_id": cls._value(message, "author_id", ""),
                "author_display": cls._value(message, "author_display", cls._display(game, str(cls._value(message, "author_id", "")))),
                "text": cls._value(message, "text", ""),
                "request_id": cls._value(message, "request_id", None),
                "created_at": cls._value(message, "created_at", ""),
            }
            for message in list(chat_history or [])[-50:]
        ]

    @classmethod
    def _reveal_roles(cls, game: AvalonGame) -> list[dict[str, Any]]:
        return [
            {
                "player_id": player_id,
                "display": cls._display(game, player_id),
                "role": game.roles[player_id].value,
                "side": cls._side(game.roles[player_id]),
            }
            for player_id in game.player_order
        ]

    @classmethod
    def public_timeline(cls, game: AvalonGame, events: Sequence[AppEvent] | None) -> list[dict[str, Any]]:
        timeline = []
        for event in events or []:
            summary = cls._event_summary(game, event)
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

    @classmethod
    def latest_mission_result(cls, events: Sequence[AppEvent] | None) -> dict[str, Any] | None:
        for event in reversed(events or []):
            if event.event_type != "mission_resolved":
                continue
            payload = event.payload
            return {
                "round_number": payload.get("round_number"),
                "team": list(payload.get("team", [])) if isinstance(payload.get("team"), list) else [],
                "succeeded": payload.get("succeeded"),
                "fail_count": payload.get("fail_count"),
                "required_fail_count": payload.get("required_fail_count"),
                "score_good": payload.get("score_good"),
                "score_evil": payload.get("score_evil"),
            }
        return None

    @classmethod
    def _event_summary(cls, game: AvalonGame, event: AppEvent) -> str | None:
        payload = event.payload
        if event.event_type == "game_started":
            player_count = len(payload.get("players", [])) or len(game.player_order)
            return f"游戏开始，共 {player_count} 名玩家。"
        if event.event_type == "team_selected":
            leader_id = str(payload.get("leader_id") or event.actor_id or "")
            team = cls._display_list(game, payload.get("team", []))
            return f"第 {payload.get('round_number')} 轮，队长 {cls._display(game, leader_id)} 选择队伍：{team}。"
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
                f"进入第 {payload.get('round_number')} 轮，队长 {cls._display(game, leader_id)}，"
                f"需选择 {payload.get('required_team_size')} 人。"
            )
        if event.event_type == "assassination_resolved":
            target_id = str(payload.get("target_id") or "")
            winner = cls._winner_label(payload.get("winner"))
            return f"刺杀目标 {cls._display(game, target_id)}，{winner}阵营获胜。"
        if event.event_type == "game_over":
            winner = cls._winner_label(payload.get("winner"))
            reason = "任务" if payload.get("reason") == "missions" else "刺杀"
            return f"游戏结束，{winner}阵营获胜，原因：{reason}。"
        return None

    @classmethod
    def _display_list(cls, game: AvalonGame, player_ids: Any) -> str:
        if not isinstance(player_ids, list):
            return "未知玩家"
        return "、".join(cls._display(game, str(player_id)) for player_id in player_ids)

    @staticmethod
    def _winner_label(winner: Any) -> str:
        if winner == "good":
            return "好人"
        if winner == "evil":
            return "邪恶"
        return "未知"

    @staticmethod
    def _value(source: Any, key: str, default: Any) -> Any:
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)
