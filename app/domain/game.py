from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.domain.rulesets import CONFIG
from app.domain.types import CommandError, EVIL_ROLES, Phase, Role, RulesetName


@dataclass
class AvalonGame:
    player_order: list[str]
    player_names: dict[str, str]
    ruleset: RulesetName
    roles: dict[str, Role]
    phase: Phase
    round_number: int
    leader_index: int
    current_team: list[str] = field(default_factory=list)
    required_team_size: int = 0
    team_votes: dict[str, str] = field(default_factory=dict)
    mission_votes: dict[str, str] = field(default_factory=dict)
    score_good: int = 0
    score_evil: int = 0
    winner: str | None = None

    @classmethod
    def new(
        cls,
        players: list[str],
        player_names: dict[str, str],
        ruleset: RulesetName,
        rng_seed: int | None = None,
    ) -> "AvalonGame":
        if len(players) not in CONFIG:
            raise CommandError("阿瓦隆必须 5-10 人才能开始。")
        rng = random.Random(rng_seed)
        roles = CONFIG[len(players)]["roles"][:]
        rng.shuffle(roles)
        leader_index = rng.randrange(len(players))
        return cls(
            player_order=players[:],
            player_names=player_names.copy(),
            ruleset=ruleset,
            roles={pid: roles[index] for index, pid in enumerate(players)},
            phase=Phase.TEAM_PROPOSAL,
            round_number=1,
            leader_index=leader_index,
            required_team_size=CONFIG[len(players)]["mission_sizes"][0],
        )

    @property
    def leader_id(self) -> str:
        return self.player_order[self.leader_index % len(self.player_order)]

    def select_team(self, actor_id: str, team: list[str]) -> None:
        self._require_phase(Phase.TEAM_PROPOSAL)
        if actor_id != self.leader_id:
            raise CommandError("只有当前队长可以选择队伍。")
        if len(team) != self.required_team_size:
            raise CommandError(f"本轮必须选择 {self.required_team_size} 名玩家。")
        if len(set(team)) != len(team):
            raise CommandError("队伍中不能出现重复玩家。")
        if any(pid not in self.player_order for pid in team):
            raise CommandError("队伍包含不存在的玩家。")
        self.current_team = team[:]
        self.team_votes = {}
        self.phase = Phase.TEAM_VOTE

    def submit_team_vote(self, actor_id: str, vote: str) -> None:
        self._require_phase(Phase.TEAM_VOTE)
        if actor_id not in self.player_order:
            raise CommandError("未知玩家不能投票。")
        if vote not in {"Approve", "Reject"}:
            raise CommandError("组队票只能是 Approve 或 Reject。")
        if actor_id in self.team_votes:
            raise CommandError("你已经提交过组队票。")
        self.team_votes[actor_id] = vote
        if len(self.team_votes) == len(self.player_order):
            approvals = sum(1 for value in self.team_votes.values() if value == "Approve")
            if approvals > len(self.player_order) / 2:
                self.phase = Phase.MISSION_VOTE
                self.mission_votes = {}
            else:
                self.phase = Phase.TEAM_PROPOSAL
                self.current_team = []
                self.team_votes = {}
                self.leader_index = (self.leader_index + 1) % len(self.player_order)

    def submit_mission_vote(self, actor_id: str, vote: str) -> None:
        self._require_phase(Phase.MISSION_VOTE)
        if actor_id not in self.current_team:
            raise CommandError("只有出征队员可以提交任务票。")
        if vote not in {"Success", "Fail"}:
            raise CommandError("任务票只能是 Success 或 Fail。")
        if actor_id in self.mission_votes:
            raise CommandError("你已经提交过任务票。")
        self.mission_votes[actor_id] = vote
        if len(self.mission_votes) == len(self.current_team):
            fail_count = sum(1 for value in self.mission_votes.values() if value == "Fail")
            threshold = 2 if len(self.player_order) >= 7 and self.round_number == 4 else 1
            if fail_count >= threshold:
                self.score_evil += 1
            else:
                self.score_good += 1
            if self.score_evil >= 3:
                self.winner = "evil"
                self.phase = Phase.GAME_OVER
            elif self.score_good >= 3:
                self.phase = Phase.ASSASSINATION
            else:
                self.phase = Phase.MISSION_RESULT_DISCUSSION

    def submit_assassination(self, actor_id: str, target_id: str) -> None:
        self._require_phase(Phase.ASSASSINATION)
        if self.roles.get(actor_id) != Role.ASSASSIN:
            raise CommandError("只有刺客可以提交刺杀目标。")
        if target_id not in self.player_order:
            raise CommandError("刺杀目标不是本局玩家。")
        self.winner = "evil" if self.roles.get(target_id) == Role.MERLIN else "good"
        self.phase = Phase.GAME_OVER

    def role_visible_to_merlin(self) -> list[str]:
        return [pid for pid, role in self.roles.items() if role in EVIL_ROLES and role != Role.MORDRED]

    def _require_phase(self, phase: Phase) -> None:
        if self.phase != phase:
            raise CommandError(f"当前阶段是 {self.phase.value}，不能执行该操作。")
