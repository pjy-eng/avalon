import pytest

from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService
from app.domain.types import CommandError, Phase, Role, RulesetName


def make_gateway() -> CommandGateway:
    sessions = RoomSessionService(secret="test-secret")
    rooms = RoomService(session_service=sessions)
    return CommandGateway(room_service=rooms, session_service=sessions)


def join_and_start(gateway: CommandGateway, room_id: str = "ROOM1", count: int = 5):
    joins = [gateway.handle_join(room_id=room_id, nickname=f"玩家{i}") for i in range(1, count + 1)]
    gateway.handle_command(
        room_id=room_id,
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-game",
    )
    return joins


def current_game(gateway: CommandGateway, room_id: str = "ROOM1"):
    room = gateway.room_service.get_room(room_id)
    assert room.game is not None
    return room.game


def test_join_room_issues_session_token():
    gateway = make_gateway()

    result = gateway.handle_join(room_id="ROOM1", nickname="阿澈")

    assert result.player_id.startswith("p_")
    assert result.session_token
    assert result.snapshot["room"]["room_id"] == "ROOM1"


def test_start_game_requires_host_session():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    with pytest.raises(CommandError, match="只有房主可以开局"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=guest.session_token,
            command={"type": "start_game"},
            request_id="r1",
        )


def test_start_game_creates_friend_flexible_game_after_five_players():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    assert result.snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value
    assert result.snapshot["room"]["ruleset"] == RulesetName.FRIEND_FLEXIBLE.value


def test_start_game_returns_private_per_player_snapshot_without_secret_tables():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-private",
    )

    assert result.snapshot["you"]["player_id"] == joins[0].player_id
    assert "private_panel" in result.snapshot
    assert "roles" not in result.snapshot
    assert "team_votes" not in result.snapshot
    assert "mission_votes" not in result.snapshot


def test_join_after_game_started_is_rejected_without_changing_participants():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )
    before_snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)

    with pytest.raises(CommandError, match="游戏开始后不能加入房间"):
        gateway.handle_join(room_id="ROOM1", nickname="玩家6")

    after_snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)
    assert after_snapshot["room"]["status"] == "game"
    assert after_snapshot["room"]["player_count"] == 5
    assert after_snapshot["participants"] == before_snapshot["participants"]


def test_non_host_cannot_reuse_seen_request_id_to_bypass_start_game_host_check():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    with pytest.raises(CommandError, match="只有房主可以开局"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[1].session_token,
            command={"type": "start_game"},
            request_id="start-1",
        )


def test_ready_command_marks_participant_ready_in_lobby_snapshot():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )

    participants = {participant["player_id"]: participant for participant in result.snapshot["participants"]}
    assert result.snapshot["room"]["status"] == "lobby"
    assert result.snapshot["phase_summary"]["phase"] == Phase.LOBBY.value
    assert participants[host.player_id]["ready"] is False
    assert participants[guest.player_id]["ready"] is True


def test_reset_requires_host_and_returns_room_to_lobby_with_participants_retained():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]

    for index, join in enumerate(joins):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "ready", "ready": True},
            request_id=f"ready-{index}",
        )
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="start-1",
    )

    with pytest.raises(CommandError, match="只有房主可以重置房间"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[1].session_token,
            command={"type": "reset"},
            request_id="reset-guest",
        )

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "reset"},
        request_id="reset-host",
    )

    assert result.snapshot["room"]["status"] == "lobby"
    assert result.snapshot["phase_summary"]["phase"] == Phase.LOBBY.value
    assert [participant["player_id"] for participant in result.snapshot["participants"]] == [
        join.player_id for join in joins
    ]
    assert result.snapshot["room"]["host_id"] == joins[0].player_id
    assert all(participant["ready"] is False for participant in result.snapshot["participants"])


def test_reusing_request_id_for_different_host_command_does_not_execute_reset():
    gateway = make_gateway()
    joins = [gateway.handle_join(room_id="ROOM1", nickname=f"玩家{i}") for i in range(1, 6)]
    gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "start_game"},
        request_id="x",
    )

    with pytest.raises(CommandError, match="重复请求编号对应不同操作"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[0].session_token,
            command={"type": "reset"},
            request_id="x",
        )

    snapshot = gateway.room_service.snapshot("ROOM1", viewer_id=joins[0].player_id)
    assert snapshot["room"]["status"] == "game"
    assert snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value


def test_repeating_same_request_id_and_command_returns_snapshot_without_new_event():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")
    first_result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )
    event_count = len(gateway.room_service.get_room("ROOM1").events)

    second_result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "ready", "ready": True},
        request_id="ready-1",
    )

    assert len(gateway.room_service.get_room("ROOM1").events) == event_count
    assert second_result.events == []
    participants = {participant["player_id"]: participant for participant in second_result.snapshot["participants"]}
    assert first_result.events[0].event_type == "participant_ready_changed"
    assert participants[host.player_id]["ready"] is False
    assert participants[guest.player_id]["ready"] is True


def test_select_team_command_moves_to_team_vote_and_records_event():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    leader_join = next(join for join in joins if join.player_id == game.leader_id)
    team = game.player_order[: game.required_team_size]

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=leader_join.session_token,
        command={"type": "select_team", "team": team},
        request_id="select-team-1",
    )

    assert result.snapshot["phase_summary"]["phase"] == Phase.TEAM_VOTE.value
    assert result.snapshot["phase_summary"]["current_team"] == team
    assert result.events[0].event_type == "team_selected"
    assert result.events[0].payload["team"] == team


def test_non_leader_cannot_select_team_via_gateway():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    non_leader = next(join for join in joins if join.player_id != game.leader_id)

    with pytest.raises(CommandError, match="只有当前队长可以选择队伍"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=non_leader.session_token,
            command={"type": "select_team", "team": game.player_order[: game.required_team_size]},
            request_id="select-team-bad",
        )


def test_team_vote_command_resolves_approved_team_without_revealing_personal_votes():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    leader_join = next(join for join in joins if join.player_id == game.leader_id)
    gateway.handle_command(
        room_id="ROOM1",
        session_token=leader_join.session_token,
        command={"type": "select_team", "team": game.player_order[: game.required_team_size]},
        request_id="select-team-1",
    )

    result = None
    for index, join in enumerate(joins):
        result = gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "team_vote", "vote": "Approve"},
            request_id=f"team-vote-{index}",
        )

    assert result is not None
    assert result.snapshot["phase_summary"]["phase"] == Phase.MISSION_VOTE.value
    assert "team_votes" not in result.snapshot
    resolved_events = [event for event in result.events if event.event_type == "team_vote_resolved"]
    assert resolved_events
    assert resolved_events[0].payload["approved"] is True
    assert resolved_events[0].payload["approve_count"] == len(joins)
    assert resolved_events[0].payload["reject_count"] == 0


def test_rejected_team_vote_rotates_leader_and_returns_to_team_proposal():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    first_leader = game.leader_id
    leader_join = next(join for join in joins if join.player_id == first_leader)
    gateway.handle_command(
        room_id="ROOM1",
        session_token=leader_join.session_token,
        command={"type": "select_team", "team": game.player_order[: game.required_team_size]},
        request_id="select-team-1",
    )

    result = None
    for index, join in enumerate(joins):
        result = gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "team_vote", "vote": "Reject"},
            request_id=f"team-reject-{index}",
        )

    assert result is not None
    assert result.snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value
    assert result.snapshot["phase_summary"]["leader_id"] != first_leader
    assert result.snapshot["phase_summary"]["current_team"] == []


def test_mission_vote_command_resolves_result_and_keeps_votes_secret():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    leader_join = next(join for join in joins if join.player_id == game.leader_id)
    team = game.player_order[: game.required_team_size]
    gateway.handle_command(
        room_id="ROOM1",
        session_token=leader_join.session_token,
        command={"type": "select_team", "team": team},
        request_id="select-team-1",
    )
    for index, join in enumerate(joins):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "team_vote", "vote": "Approve"},
            request_id=f"team-vote-{index}",
        )

    result = None
    for index, player_id in enumerate(team):
        join = next(item for item in joins if item.player_id == player_id)
        result = gateway.handle_command(
            room_id="ROOM1",
            session_token=join.session_token,
            command={"type": "mission_vote", "vote": "Success"},
            request_id=f"mission-vote-{index}",
        )

    assert result is not None
    assert result.snapshot["phase_summary"]["phase"] == Phase.MISSION_RESULT_DISCUSSION.value
    assert result.snapshot["phase_summary"]["score_good"] == 1
    assert "mission_votes" not in result.snapshot
    mission_events = [event for event in result.events if event.event_type == "mission_resolved"]
    assert mission_events
    assert mission_events[0].payload["fail_count"] == 0
    assert mission_events[0].payload["succeeded"] is True


def test_continue_after_result_is_host_only_and_advances_round():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    leader_join = next(join for join in joins if join.player_id == game.leader_id)
    team = game.player_order[: game.required_team_size]
    gateway.handle_command("ROOM1", leader_join.session_token, {"type": "select_team", "team": team}, "select-team-1")
    for index, join in enumerate(joins):
        gateway.handle_command("ROOM1", join.session_token, {"type": "team_vote", "vote": "Approve"}, f"team-vote-{index}")
    for index, player_id in enumerate(team):
        join = next(item for item in joins if item.player_id == player_id)
        gateway.handle_command("ROOM1", join.session_token, {"type": "mission_vote", "vote": "Success"}, f"mission-vote-{index}")

    with pytest.raises(CommandError, match="只有房主可以推进下一轮"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[1].session_token,
            command={"type": "continue_after_result"},
            request_id="continue-guest",
        )

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=joins[0].session_token,
        command={"type": "continue_after_result"},
        request_id="continue-host",
    )

    assert result.snapshot["phase_summary"]["phase"] == Phase.TEAM_PROPOSAL.value
    assert result.snapshot["phase_summary"]["round_number"] == 2
    assert result.events[0].event_type == "round_advanced"


def test_assassinate_command_ends_game_and_reveals_roles_only_at_game_over():
    gateway = make_gateway()
    joins = join_and_start(gateway)
    game = current_game(gateway)
    players = game.player_order
    game.roles = {
        players[0]: Role.MERLIN,
        players[1]: Role.PERCIVAL,
        players[2]: Role.LOYAL,
        players[3]: Role.MORGANA,
        players[4]: Role.ASSASSIN,
    }
    game.phase = Phase.ASSASSINATION
    assassin_join = next(join for join in joins if join.player_id == players[4])
    pre_assassination_snapshot = gateway._snapshot_for_actor("ROOM1", players[4])

    assert "reveal_roles" not in pre_assassination_snapshot

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=assassin_join.session_token,
        command={"type": "assassinate", "target_id": players[0]},
        request_id="assassinate-1",
    )

    assert result.snapshot["phase_summary"]["phase"] == Phase.GAME_OVER.value
    assert result.snapshot["phase_summary"]["winner"] == "evil"
    assert "reveal_roles" in result.snapshot
    assert {item["player_id"] for item in result.snapshot["reveal_roles"]} == set(players)
    assert result.events[0].event_type == "assassination_resolved"
