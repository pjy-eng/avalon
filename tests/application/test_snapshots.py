from app.application.events import AppEvent
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

    snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=player_id, room_id="ROOM1")

    assert snapshot["room"]["host_id"] == player_id
    assert snapshot["room"]["player_count"] == 5
    assert snapshot["room"]["status"] == "game"
    assert snapshot["you"]["nickname"] == game.player_names[player_id]
    assert snapshot["you"]["seat"] == 1
    assert snapshot["players"][0]["seat"] == 1
    assert snapshot["players"][0]["nickname"] == game.player_names[player_id]
    assert snapshot["players"][0]["is_host"] is True
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


def test_public_timeline_projects_resolved_events_without_private_votes():
    game = make_game(5)
    team = game.player_order[: game.required_team_size]
    events = [
        AppEvent(
            event_type="mission_resolved",
            room_id="ROOM1",
            actor_id=None,
            payload={
                "round_number": 0,
                "team": [game.player_order[-1]],
                "succeeded": False,
                "fail_count": 1,
                "required_fail_count": 1,
                "score_good": 0,
                "score_evil": 1,
            },
        ),
        AppEvent(
            event_type="team_vote_resolved",
            room_id="ROOM1",
            actor_id=None,
            payload={
                "round_number": 1,
                "team": team,
                "approved": True,
                "approve_count": 4,
                "reject_count": 1,
                "personal_votes": {game.player_order[0]: "Reject"},
            },
        ),
        AppEvent(
            event_type="mission_resolved",
            room_id="ROOM1",
            actor_id=None,
            payload={
                "round_number": 1,
                "team": team,
                "succeeded": True,
                "fail_count": 0,
                "required_fail_count": 1,
                "score_good": 1,
                "score_evil": 0,
                "votes": {team[0]: "Success", team[1]: "Success"},
            },
        ),
    ]

    snapshot = SnapshotProjector.for_player(
        game=game,
        player_id=game.player_order[0],
        host_id=None,
        room_id="ROOM1",
        events=events,
    )

    assert [item["kind"] for item in snapshot["public_timeline"]] == [
        "mission_resolved",
        "team_vote_resolved",
        "mission_resolved",
    ]
    assert "4 票同意" in snapshot["public_timeline"][1]["summary"]
    assert snapshot["phase_summary"]["mission_result"] == {
        "round_number": 1,
        "team": team,
        "succeeded": True,
        "fail_count": 0,
        "required_fail_count": 1,
        "score_good": 1,
        "score_evil": 0,
    }
    timeline_text = str(snapshot["public_timeline"])
    assert "personal_votes" not in timeline_text
    assert "votes" not in timeline_text
    assert "Reject" not in timeline_text
    assert "Success" not in timeline_text
    assert "votes" not in str(snapshot["phase_summary"]["mission_result"])


def test_reveal_roles_only_appears_at_game_over():
    game = make_game(5)
    player_id = game.player_order[0]

    live_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    game.phase = Phase.GAME_OVER
    game.winner = "good"
    game_over_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")

    assert "reveal_roles" not in live_snapshot
    assert {item["player_id"] for item in game_over_snapshot["reveal_roles"]} == set(game.player_order)
    assert all("role" in item for item in game_over_snapshot["reveal_roles"])


def test_speaker_state_mutes_vote_phases_and_opens_discussion_phases():
    game = make_game(5)
    player_id = game.player_order[0]

    game.phase = Phase.TEAM_VOTE
    team_vote_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    game.phase = Phase.MISSION_VOTE
    mission_vote_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    game.phase = Phase.MISSION_RESULT_DISCUSSION
    discussion_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")

    assert team_vote_snapshot["speaker_state"] == {"mode": "muted", "can_send_text": False}
    assert team_vote_snapshot["voice_state"]["can_publish_audio"] is False
    assert mission_vote_snapshot["speaker_state"] == {"mode": "muted", "can_send_text": False}
    assert mission_vote_snapshot["voice_state"]["publish_policy"] == "muted"
    assert discussion_snapshot["speaker_state"] == {"mode": "open", "can_send_text": True}
    assert discussion_snapshot["voice_state"]["can_publish_audio"] is True


def test_online_state_marks_connected_players_without_connection_details():
    game = make_game(5)
    counts = {game.player_order[0]: 2, game.player_order[2]: 1, "ghost": 4}

    snapshot = SnapshotProjector.for_player(
        game=game,
        player_id=game.player_order[0],
        host_id=None,
        room_id="ROOM1",
        online_counts=counts,
    )

    players = {item["player_id"]: item for item in snapshot["online_state"]["players"]}
    assert players[game.player_order[0]] == {
        "player_id": game.player_order[0],
        "online": True,
        "connection_count": 2,
    }
    assert players[game.player_order[1]] == {
        "player_id": game.player_order[1],
        "online": False,
        "connection_count": 0,
    }
    assert "ghost" not in players
    assert "connections" not in str(snapshot["online_state"])
