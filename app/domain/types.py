from __future__ import annotations

from enum import StrEnum


class CommandError(ValueError):
    """Raised when a player intent is invalid for the current game state."""


class Role(StrEnum):
    MERLIN = "梅林"
    PERCIVAL = "派西维尔"
    LOYAL = "忠臣"
    MORGANA = "莫甘娜"
    ASSASSIN = "刺客"
    MORDRED = "莫德雷德"
    OBERON = "奥伯伦"


class Phase(StrEnum):
    LOBBY = "LOBBY"
    TEAM_PROPOSAL = "TEAM_PROPOSAL"
    TEAM_VOTE = "TEAM_VOTE"
    MISSION_VOTE = "MISSION_VOTE"
    MISSION_RESULT_DISCUSSION = "MISSION_RESULT_DISCUSSION"
    ASSASSINATION = "ASSASSINATION"
    GAME_OVER = "GAME_OVER"


class RulesetName(StrEnum):
    FRIEND_FLEXIBLE = "friend_flexible"
    STANDARD_AVALON = "standard_avalon"


GOOD_ROLES = {Role.MERLIN, Role.PERCIVAL, Role.LOYAL}
EVIL_ROLES = {Role.MORGANA, Role.ASSASSIN, Role.MORDRED, Role.OBERON}
