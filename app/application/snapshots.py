from __future__ import annotations

from typing import Any

from app.domain.game import AvalonGame
from app.domain.types import EVIL_ROLES, GOOD_ROLES, Phase, Role


class SnapshotProjector:
    @classmethod
    def for_player(cls, game: AvalonGame, player_id: str, host_id: str | None, room_id: str) -> dict[str, Any]:
        return {
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
            "phase_summary": {
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
            },
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
            "public_timeline": [],
        }

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
        can_publish_audio = phase in {
            Phase.TEAM_PROPOSAL,
            Phase.MISSION_RESULT_DISCUSSION,
            Phase.ASSASSINATION,
            Phase.GAME_OVER,
        }
        return {
            "can_publish_audio": can_publish_audio,
            "publish_policy": "open" if can_publish_audio else "muted",
        }

    @staticmethod
    def _display(game: AvalonGame, player_id: str) -> str:
        seat_number = game.player_order.index(player_id) + 1
        return f"{seat_number}号-{game.player_names[player_id]}"

    @staticmethod
    def _side(role: Role) -> str:
        if role in GOOD_ROLES:
            return "good"
        return "evil"
