from app.application.snapshots import SnapshotProjector
from app.domain.game import AvalonGame
from app.domain.types import Phase, Role, RulesetName


def make_game(count: int = 5) -> AvalonGame:
    players = [f"p{i}" for i in range(1, count + 1)]
    names = {pid: f"玩家{i}" for i, pid in enumerate(players, start=1)}
    return AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=7)


def visible_ids(snapshot: dict) -> set[str]:
    return {player["player_id"] for player in snapshot["private_panel"]["visible_players"]}


def test_snapshot_only_exposes_current_player_role_and_no_vote_or_role_tables():
    game = make_game(5)
    player_id = game.player_order[0]

    snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")

    assert snapshot["private_panel"]["role"] == game.roles[player_id].value
    assert "roles" not in snapshot
    assert "team_votes" not in snapshot
    assert "mission_votes" not in snapshot
    for other_id in game.player_order[1:]:
        assert game.roles[other_id].value not in str(snapshot)


def test_percival_sees_merlin_and_morgana_players_without_distinguishing_them():
    game = make_game(5)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.MORGANA,
        players[4]: Role.ASSASSIN,
    }

    snapshot = SnapshotProjector.for_player(game=game, player_id=players[1], host_id=None, room_id="ROOM1")

    assert visible_ids(snapshot) == {players[0], players[3]}
    assert {player["display"] for player in snapshot["private_panel"]["visible_players"]} == {
        "1号-玩家1",
        "4号-玩家4",
    }
    assert all("role" not in player for player in snapshot["private_panel"]["visible_players"])


def test_merlin_does_not_see_mordred():
    game = make_game(8)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.LOYAL,
        players[4]: Role.LOYAL,
        players[5]: Role.MORGANA,
        players[6]: Role.ASSASSIN,
        players[7]: Role.MORDRED,
    }

    snapshot = SnapshotProjector.for_player(game=game, player_id=players[0], host_id=None, room_id="ROOM1")

    assert visible_ids(snapshot) == {players[5], players[6]}


def test_evil_players_see_each_other_except_oberon_is_hidden_both_ways():
    game = make_game(10)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.LOYAL,
        players[4]: Role.LOYAL,
        players[5]: Role.LOYAL,
        players[6]: Role.MORGANA,
        players[7]: Role.ASSASSIN,
        players[8]: Role.MORDRED,
        players[9]: Role.OBERON,
    }

    morgana_snapshot = SnapshotProjector.for_player(game=game, player_id=players[6], host_id=None, room_id="ROOM1")
    oberon_snapshot = SnapshotProjector.for_player(game=game, player_id=players[9], host_id=None, room_id="ROOM1")

    assert visible_ids(morgana_snapshot) == {players[7], players[8]}
    assert visible_ids(oberon_snapshot) == set()


def test_leader_can_select_team_during_team_proposal_and_others_wait():
    game = make_game(5)
    leader_snapshot = SnapshotProjector.for_player(game=game, player_id=game.leader_id, host_id=None, room_id="ROOM1")
    non_leader = next(player_id for player_id in game.player_order if player_id != game.leader_id)
    non_leader_snapshot = SnapshotProjector.for_player(game=game, player_id=non_leader, host_id=None, room_id="ROOM1")

    assert leader_snapshot["my_action"]["type"] == "select_team"
    assert non_leader_snapshot["my_action"]["type"] == "wait"


def test_team_vote_action_only_for_players_who_have_not_voted():
    game = make_game(5)
    game.select_team(actor_id=game.leader_id, team=game.player_order[: game.required_team_size])
    game.submit_team_vote(actor_id=game.player_order[0], vote="Approve")

    voted_snapshot = SnapshotProjector.for_player(game=game, player_id=game.player_order[0], host_id=None, room_id="ROOM1")
    pending_snapshot = SnapshotProjector.for_player(game=game, player_id=game.player_order[1], host_id=None, room_id="ROOM1")

    assert voted_snapshot["my_action"]["type"] == "wait"
    assert pending_snapshot["my_action"]["type"] == "team_vote"


def test_mission_vote_action_only_for_current_team_members_who_have_not_voted():
    game = make_game(5)
    game.select_team(actor_id=game.leader_id, team=game.player_order[: game.required_team_size])
    for player_id in game.player_order:
        game.submit_team_vote(actor_id=player_id, vote="Approve")
    game.submit_mission_vote(actor_id=game.current_team[0], vote="Success")

    voted_snapshot = SnapshotProjector.for_player(game=game, player_id=game.current_team[0], host_id=None, room_id="ROOM1")
    pending_snapshot = SnapshotProjector.for_player(game=game, player_id=game.current_team[1], host_id=None, room_id="ROOM1")
    off_team_snapshot = SnapshotProjector.for_player(game=game, player_id=game.player_order[-1], host_id=None, room_id="ROOM1")

    assert voted_snapshot["my_action"]["type"] == "wait"
    assert pending_snapshot["my_action"] == {"type": "mission_vote", "can_submit_fail": True}
    assert off_team_snapshot["my_action"]["type"] == "wait"


def test_assassin_can_assassinate_during_assassination_phase():
    game = make_game(5)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.MORGANA,
        players[4]: Role.ASSASSIN,
    }
    game.phase = Phase.ASSASSINATION

    assassin_snapshot = SnapshotProjector.for_player(game=game, player_id=players[4], host_id=None, room_id="ROOM1")
    loyal_snapshot = SnapshotProjector.for_player(game=game, player_id=players[2], host_id=None, room_id="ROOM1")

    assert assassin_snapshot["my_action"]["type"] == "assassinate"
    assert loyal_snapshot["my_action"]["type"] == "wait"
