from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import Role, RulesetName


@dataclass(frozen=True)
class Ruleset:
    name: RulesetName
    mission_fail_policy: str


FRIEND_FLEXIBLE = Ruleset(
    name=RulesetName.FRIEND_FLEXIBLE,
    mission_fail_policy="all_team_members",
)


RULESETS = {
    RulesetName.FRIEND_FLEXIBLE: FRIEND_FLEXIBLE,
}


CONFIG = {
    5: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN],
        "mission_sizes": [2, 3, 2, 3, 3],
    },
    6: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN],
        "mission_sizes": [2, 3, 4, 3, 4],
    },
    7: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN, Role.OBERON],
        "mission_sizes": [2, 3, 3, 4, 4],
    },
    8: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.LOYAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN, Role.MORDRED],
        "mission_sizes": [3, 4, 4, 5, 5],
    },
    9: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.LOYAL, Role.LOYAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN, Role.MORDRED],
        "mission_sizes": [3, 4, 4, 5, 5],
    },
    10: {
        "roles": [Role.MERLIN, Role.PERCIVAL, Role.LOYAL, Role.LOYAL, Role.LOYAL, Role.LOYAL, Role.MORGANA, Role.ASSASSIN, Role.MORDRED, Role.OBERON],
        "mission_sizes": [3, 4, 4, 5, 5],
    },
}
