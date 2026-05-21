import pytest

from app.domain.game import AvalonGame
from app.domain.types import CommandError, Phase, Role, RulesetName


def make_game(count: int = 5, seed: int = 7) -> AvalonGame:
    players = [f"p{i}" for i in range(1, count + 1)]
    names = {pid: f"玩家{i}" for i, pid in enumerate(players, start=1)}
    return AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=seed)


def approve_team(game: AvalonGame) -> None:
    game.select_team(actor_id=game.leader_id, team=game.player_order[: game.required_team_size])
    for player_id in game.player_order:
        game.submit_team_vote(actor_id=player_id, vote="Approve")


def test_new_rejects_duplicate_player_ids():
    players = ["p1", "p2", "p3", "p4", "p4"]
    names = {pid: f"玩家{index}" for index, pid in enumerate(players, start=1)}

    with pytest.raises(CommandError, match="玩家 ID 不能重复"):
        AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=7)


def test_new_rejects_unsupported_ruleset():
    players = [f"p{i}" for i in range(1, 6)]
    names = {pid: f"玩家{i}" for i, pid in enumerate(players, start=1)}

    with pytest.raises(CommandError, match="暂不支持该规则集"):
        AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.STANDARD_AVALON, rng_seed=7)


def test_new_rejects_player_names_that_do_not_match_players():
    players = [f"p{i}" for i in range(1, 6)]
    names = {pid: f"玩家{i}" for i, pid in enumerate(players[:-1], start=1)}

    with pytest.raises(CommandError, match="玩家名称必须覆盖且只覆盖本局玩家"):
        AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=7)


def test_start_assigns_roles_and_first_leader():
    game = make_game(5)

    assert game.phase == Phase.TEAM_PROPOSAL
    assert len(game.roles) == 5
    assert game.leader_id in game.player_order
    assert game.ruleset == RulesetName.FRIEND_FLEXIBLE
    assert game.required_team_size == 2


def test_leader_selects_team_and_all_players_team_vote():
    game = make_game(5)
    leader = game.leader_id

    game.select_team(actor_id=leader, team=game.player_order[:2])

    assert game.phase == Phase.TEAM_VOTE
    for player_id in game.player_order:
        game.submit_team_vote(actor_id=player_id, vote="Approve")
    assert game.phase == Phase.MISSION_VOTE


def test_friend_flexible_all_team_members_can_submit_fail():
    game = make_game(5)
    approve_team(game)

    loyal_player = game.player_order[0]
    game.roles[loyal_player] = Role.LOYAL
    game.submit_mission_vote(actor_id=loyal_player, vote="Fail")

    assert game.mission_votes[loyal_player] == "Fail"


def test_non_team_member_cannot_submit_mission_vote():
    game = make_game(5)
    approve_team(game)

    with pytest.raises(CommandError, match="只有出征队员可以提交任务票"):
        game.submit_mission_vote(actor_id=game.player_order[4], vote="Fail")


def test_continue_after_mission_result_advances_round_and_resets_team_state():
    game = make_game(5)
    first_leader = game.leader_id
    approve_team(game)
    for player_id in game.current_team:
        game.submit_mission_vote(actor_id=player_id, vote="Success")

    assert game.phase == Phase.MISSION_RESULT_DISCUSSION
    assert game.score_good == 1

    game.continue_after_mission_result()

    assert game.phase == Phase.TEAM_PROPOSAL
    assert game.round_number == 2
    assert game.leader_id != first_leader
    assert game.required_team_size == 3
    assert game.current_team == []
    assert game.team_votes == {}
    assert game.mission_votes == {}


def test_assassin_wins_when_targeting_merlin():
    game = make_game(5)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.MORGANA,
        players[4]: Role.ASSASSIN,
    }
    game.score_good = 3
    game.phase = Phase.ASSASSINATION

    game.submit_assassination(actor_id=players[4], target_id=players[0])

    assert game.phase == Phase.GAME_OVER
    assert game.winner == "evil"
