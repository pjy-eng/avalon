# Avalon Online v2 Gameplay Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the v2 Avalon playable loop and minimum social controls so a 5-10 player room can finish a full game from join through assassination and role reveal.

**Architecture:** Keep the existing authoritative modular monolith. HTTP and WebSocket commands continue through `CommandGateway`, `AvalonGame` remains the rule authority, `SnapshotProjector` remains the privacy boundary, and the vanilla frontend renders only server snapshots. P0 gameplay commands land before P1 chat, voice, online state, lobby governance, and local private marks.

**Tech Stack:** Python 3.12-compatible FastAPI, Pydantic, pytest, FastAPI TestClient, vanilla HTML/CSS/JavaScript, optional LiveKit browser client loaded from CDN when voice is configured.

---

## Implementation Scope

This plan implements [`docs/superpowers/specs/2026-05-21-v2-gameplay-completion-design.md`](/Users/vangogh/Monorepo/avalon/docs/superpowers/specs/2026-05-21-v2-gameplay-completion-design.md). It assumes the current branch is `codex/avalon-work` and the current v2 architecture is already present.

The work is intentionally split into commits that keep the game playable at each checkpoint:

1. Backend P0 command contract.
2. Public timeline, result summaries, and terminal role reveal.
3. Online state and phase-based speaking policy.
4. Frontend P0 game actions.
5. P1 text chat and lobby governance.
6. P1 voice client and private marks.
7. Documentation and full verification.

## File Structure

Modify:

- `app/domain/game.py` - keep rule methods; no UI or transport logic added.
- `app/application/rooms.py` - add chat message model, chat history, and lobby governance operations.
- `app/application/commands.py` - dispatch new commands, validate payloads, append public events, and return snapshots.
- `app/application/snapshots.py` - project public timeline, mission result, role reveal, speaking policy, online state, and chat history.
- `app/realtime/manager.py` - expose online connection counts.
- `app/api/ws.py` - broadcast state when players connect or disconnect so online state is fresh.
- `app/main.py` - wire `ConnectionManager.online_counts` into `CommandGateway`.
- `static/index.html` - add LiveKit browser client script and any missing mount points.
- `static/main.js` - enable P0 action modals/buttons, chat, voice control, governance controls, and local private marks.
- `static/style.css` - style enabled action modals, online state, chat state, voice state, governance controls, and private marks.
- `docs/MISSING_GAMEPLAY_FEATURES.md` - mark implemented items after verification.
- `docs/ARCHITECTURE.md` - update command and snapshot contract details.
- `CHANGELOG.md` - add gameplay completion entry.

Modify tests:

- `tests/domain/test_game_core.py`
- `tests/application/test_command_gateway.py`
- `tests/application/test_snapshots.py`
- `tests/api/test_ws_flow.py`
- `tests/api/test_health_and_rooms.py`

No new packages are required for backend tests. The browser voice client uses a CDN script and must degrade cleanly if LiveKit is not configured or the script is unavailable.

---

### Task 1: Backend P0 Gameplay Command Tests

**Files:**
- Modify: `tests/application/test_command_gateway.py`
- Modify: `tests/domain/test_game_core.py`

- [ ] **Step 1: Confirm baseline**

Run:

```bash
git status --short --branch
pytest -q
```

Expected:

```text
## codex/avalon-work
74 passed
```

The untracked `AGENTS.md` may appear. Leave it untouched.

- [ ] **Step 2: Add command gateway helper functions**

In `tests/application/test_command_gateway.py`, add these helpers after `make_gateway()`:

```python
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
```

- [ ] **Step 3: Add failing tests for new gameplay commands**

Append these tests to `tests/application/test_command_gateway.py`:

```python
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
```

Add `Role` to the imports at the top:

```python
from app.domain.types import CommandError, Phase, Role, RulesetName
```

- [ ] **Step 4: Add domain regression tests for terminal mission outcomes**

Append to `tests/domain/test_game_core.py`:

```python
def test_evil_wins_immediately_after_third_failed_mission():
    game = make_game(5)
    for _ in range(3):
        approve_team(game)
        team = list(game.current_team)
        game.submit_mission_vote(actor_id=team[0], vote="Fail")
        for player_id in team[1:]:
            game.submit_mission_vote(actor_id=player_id, vote="Success")
        if game.score_evil < 3:
            game.continue_after_mission_result()

    assert game.phase == Phase.GAME_OVER
    assert game.winner == "evil"


def test_good_third_success_enters_assassination_without_winner():
    game = make_game(5)
    for _ in range(3):
        approve_team(game)
        for player_id in list(game.current_team):
            game.submit_mission_vote(actor_id=player_id, vote="Success")
        if game.score_good < 3:
            game.continue_after_mission_result()

    assert game.phase == Phase.ASSASSINATION
    assert game.winner is None
```

- [ ] **Step 5: Run tests and verify failure**

Run:

```bash
pytest tests/application/test_command_gateway.py tests/domain/test_game_core.py -q
```

Expected: new `CommandGateway` tests fail with `CommandError: 暂不支持该操作。` or missing `reveal_roles`. Existing domain tests should pass.

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/application/test_command_gateway.py tests/domain/test_game_core.py
git commit -m "test: cover v2 gameplay command loop"
```

Expected: commit succeeds with only test files staged.

---

### Task 2: Implement P0 Gameplay Commands and Events

**Files:**
- Modify: `app/application/commands.py`
- Modify: `app/application/rooms.py`
- Test: `tests/application/test_command_gateway.py`
- Test: `tests/domain/test_game_core.py`

- [ ] **Step 1: Add event helper methods to `CommandGateway`**

In `app/application/commands.py`, add these imports:

```python
from collections.abc import Callable
```

Change `CommandGateway.__init__` to accept an optional online provider that later tasks will use:

```python
    def __init__(
        self,
        room_service: RoomService,
        session_service: RoomSessionService,
        online_players_provider: Callable[[str], dict[str, int]] | None = None,
    ) -> None:
        self.room_service = room_service
        self.session_service = session_service
        self.online_players_provider = online_players_provider
```

Add these private helpers inside `CommandGateway`:

```python
    def _append_event(
        self,
        room_id: str,
        actor_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        request_id: str | None,
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
    def _string_list_payload(command: dict[str, Any], key: str, message: str) -> list[str]:
        value = command.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise CommandError(message)
        return [item.strip() for item in value]

    @staticmethod
    def _string_payload(command: dict[str, Any], key: str, message: str) -> str:
        value = command.get(key)
        if not isinstance(value, str) or not value.strip():
            raise CommandError(message)
        return value.strip()

    def _online_counts(self, room_id: str) -> dict[str, int]:
        if self.online_players_provider is None:
            return {}
        return self.online_players_provider(room_id)
```

- [ ] **Step 2: Extend command dispatch**

Replace the `if command_type == ...` block in `handle_command()` with:

```python
        if command_type == "start_game":
            result = self._handle_start_game(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "ready":
            result = self._handle_ready(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "reset":
            result = self._handle_reset(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "select_team":
            result = self._handle_select_team(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "team_vote":
            result = self._handle_team_vote(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "mission_vote":
            result = self._handle_mission_vote(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "continue_after_result":
            result = self._handle_continue_after_result(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
        elif command_type == "assassinate":
            result = self._handle_assassinate(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        else:
            raise CommandError("暂不支持该操作。")
```

- [ ] **Step 3: Implement P0 command handlers**

Add these methods to `CommandGateway` before `_snapshot_for_actor`:

```python
    def _handle_select_team(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        team = self._string_list_payload(command, "team", "team 必须是玩家 ID 列表。")
        room.game.select_team(actor_id=actor_id, team=team)
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="team_selected",
            payload={
                "round_number": room.game.round_number,
                "leader_id": actor_id,
                "team": team,
                "required_team_size": room.game.required_team_size,
            },
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_team_vote(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        vote = self._string_payload(command, "vote", "vote 必须是 Approve 或 Reject。")
        votes_after = {**room.game.team_votes, actor_id: vote}
        team_before = room.game.current_team[:]
        round_number = room.game.round_number
        room.game.submit_team_vote(actor_id=actor_id, vote=vote)
        events: list[AppEvent] = []
        if len(votes_after) == len(room.game.player_order):
            approve_count = sum(1 for value in votes_after.values() if value == "Approve")
            reject_count = len(room.game.player_order) - approve_count
            approved = approve_count > len(room.game.player_order) / 2
            events.append(
                self._append_event(
                    room_id=room_id,
                    actor_id=None,
                    event_type="team_vote_resolved",
                    payload={
                        "round_number": round_number,
                        "team": team_before,
                        "approved": approved,
                        "approve_count": approve_count,
                        "reject_count": reject_count,
                    },
                    request_id=request_id,
                )
            )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=events)

    def _handle_mission_vote(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        vote = self._string_payload(command, "vote", "vote 必须是 Success 或 Fail。")
        team_before = room.game.current_team[:]
        votes_after = {**room.game.mission_votes, actor_id: vote}
        round_number = room.game.round_number
        room.game.submit_mission_vote(actor_id=actor_id, vote=vote)
        events: list[AppEvent] = []
        if len(votes_after) == len(team_before):
            fail_count = sum(1 for value in votes_after.values() if value == "Fail")
            threshold = 2 if len(room.game.player_order) >= 7 and round_number == 4 else 1
            succeeded = fail_count < threshold
            events.append(
                self._append_event(
                    room_id=room_id,
                    actor_id=None,
                    event_type="mission_resolved",
                    payload={
                        "round_number": round_number,
                        "team": team_before,
                        "succeeded": succeeded,
                        "fail_count": fail_count,
                        "required_fail_count": threshold,
                        "score_good": room.game.score_good,
                        "score_evil": room.game.score_evil,
                    },
                    request_id=request_id,
                )
            )
            if room.game.phase.value == "GAME_OVER":
                events.append(
                    self._append_event(
                        room_id=room_id,
                        actor_id=None,
                        event_type="game_over",
                        payload={"winner": room.game.winner, "reason": "missions"},
                        request_id=request_id,
                    )
                )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=events)

    def _handle_continue_after_result(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        if actor_id != room.host_id:
            raise CommandError("只有房主可以推进下一轮。")
        room.game.continue_after_mission_result()
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="round_advanced",
            payload={
                "round_number": room.game.round_number,
                "leader_id": room.game.leader_id,
                "required_team_size": room.game.required_team_size,
            },
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_assassinate(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            raise CommandError("游戏尚未开始。")
        target_id = self._string_payload(command, "target_id", "target_id 必须是玩家 ID。")
        room.game.submit_assassination(actor_id=actor_id, target_id=target_id)
        events = [
            self._append_event(
                room_id=room_id,
                actor_id=actor_id,
                event_type="assassination_resolved",
                payload={
                    "target_id": target_id,
                    "winner": room.game.winner,
                    "hit_merlin": room.game.winner == "evil",
                },
                request_id=request_id,
            ),
            self._append_event(
                room_id=room_id,
                actor_id=None,
                event_type="game_over",
                payload={"winner": room.game.winner, "reason": "assassination"},
                request_id=request_id,
            ),
        ]
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=events)
```

- [ ] **Step 4: Pass event context into snapshots**

Replace `_snapshot_for_actor()` with:

```python
    def _snapshot_for_actor(self, room_id: str, actor_id: str) -> dict[str, Any]:
        room = self.room_service.get_room(room_id)
        online_counts = self._online_counts(room.room_id)
        if room.game is None:
            return self.room_service.snapshot(
                room_id,
                viewer_id=actor_id,
                online_counts=online_counts,
            )
        return SnapshotProjector.for_player(
            game=room.game,
            player_id=actor_id,
            host_id=room.host_id,
            room_id=room.room_id,
            events=room.events,
            chat_history=getattr(room, "chat_history", []),
            online_counts=online_counts,
        )
```

This introduces parameters that Task 3 will implement in `SnapshotProjector` and `RoomService.snapshot()`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
pytest tests/application/test_command_gateway.py tests/domain/test_game_core.py -q
```

Expected: failures now move from unsupported commands to snapshot keyword arguments or missing `reveal_roles`. Continue to Task 3 before committing if the command handlers call snapshot parameters that do not exist yet.

---

### Task 3: Snapshot Timeline, Role Reveal, Speaking Policy, and Chat Contract

**Files:**
- Modify: `app/application/snapshots.py`
- Modify: `app/application/rooms.py`
- Modify: `tests/application/test_snapshots.py`
- Test: `tests/application/test_snapshots.py`
- Test: `tests/application/test_command_gateway.py`

- [ ] **Step 1: Add failing snapshot tests**

Append to `tests/application/test_snapshots.py`:

```python
from app.application.events import AppEvent


def test_public_timeline_projects_resolved_events_without_private_votes():
    game = make_game(5)
    players = game.player_order
    events = [
        AppEvent(
            event_type="team_selected",
            room_id="ROOM1",
            actor_id=players[0],
            payload={"round_number": 1, "leader_id": players[0], "team": players[:2], "required_team_size": 2},
        ),
        AppEvent(
            event_type="team_vote_resolved",
            room_id="ROOM1",
            actor_id=None,
            payload={"round_number": 1, "team": players[:2], "approved": True, "approve_count": 4, "reject_count": 1},
        ),
        AppEvent(
            event_type="mission_resolved",
            room_id="ROOM1",
            actor_id=None,
            payload={
                "round_number": 1,
                "team": players[:2],
                "succeeded": False,
                "fail_count": 1,
                "required_fail_count": 1,
                "score_good": 0,
                "score_evil": 1,
            },
        ),
    ]

    snapshot = SnapshotProjector.for_player(
        game=game,
        player_id=players[0],
        host_id=players[0],
        room_id="ROOM1",
        events=events,
    )

    summaries = [item["summary"] for item in snapshot["public_timeline"]]
    assert any("选择队伍" in summary for summary in summaries)
    assert any("赞成 4" in summary for summary in summaries)
    assert any("失败票 1" in summary for summary in summaries)
    assert "team_votes" not in str(snapshot)
    assert "mission_votes" not in str(snapshot)


def test_reveal_roles_only_appears_at_game_over():
    game = make_game(5)
    player_id = game.player_order[0]

    before = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    assert "reveal_roles" not in before

    game.phase = Phase.GAME_OVER
    game.winner = "good"
    after = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")

    assert "reveal_roles" in after
    assert {item["player_id"] for item in after["reveal_roles"]} == set(game.player_order)
    assert all("role" in item and "side" in item for item in after["reveal_roles"])


def test_speaker_state_mutes_vote_phases_and_opens_discussion_phases():
    game = make_game(5)
    player_id = game.player_order[0]

    game.phase = Phase.TEAM_VOTE
    muted = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    assert muted["speaker_state"] == {"mode": "muted", "can_send_text": False}
    assert muted["voice_state"]["can_publish_audio"] is False

    game.phase = Phase.MISSION_RESULT_DISCUSSION
    open_snapshot = SnapshotProjector.for_player(game=game, player_id=player_id, host_id=None, room_id="ROOM1")
    assert open_snapshot["speaker_state"] == {"mode": "open", "can_send_text": True}
    assert open_snapshot["voice_state"]["can_publish_audio"] is True


def test_online_state_marks_connected_players_without_exposing_connection_details():
    game = make_game(5)
    players = game.player_order

    snapshot = SnapshotProjector.for_player(
        game=game,
        player_id=players[0],
        host_id=None,
        room_id="ROOM1",
        online_counts={players[0]: 2, players[2]: 1},
    )

    online = {item["player_id"]: item for item in snapshot["online_state"]["players"]}
    assert online[players[0]] == {"player_id": players[0], "online": True, "connection_count": 2}
    assert online[players[1]] == {"player_id": players[1], "online": False, "connection_count": 0}
    assert "websocket" not in str(snapshot).lower()
```

- [ ] **Step 2: Update `SnapshotProjector.for_player` signature and base payload**

In `app/application/snapshots.py`, change the import block to include:

```python
from app.application.events import AppEvent
```

Change the `for_player` signature to:

```python
    def for_player(
        cls,
        game: AvalonGame,
        player_id: str,
        host_id: str | None,
        room_id: str,
        events: list[AppEvent] | None = None,
        chat_history: list[Any] | None = None,
        online_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
```

In the returned dict, replace `"voice_state": cls._voice_state(game.phase), "public_timeline": []` with:

```python
            "voice_state": cls._voice_state(game.phase),
            "speaker_state": cls._speaker_state(game.phase),
            "online_state": cls._online_state(game, online_counts or {}),
            "public_timeline": cls._public_timeline(game, events or []),
            "chat_history": cls._chat_history(game, chat_history or []),
```

After creating the payload, add terminal role reveal before returning. The simplest implementation is to assign the dict to `snapshot` first:

```python
        snapshot = {
            ...
        }
        if game.phase == Phase.GAME_OVER:
            snapshot["reveal_roles"] = cls._reveal_roles(game)
        return snapshot
```

- [ ] **Step 3: Add snapshot helper methods**

Add these methods to `SnapshotProjector`:

```python
    @classmethod
    def _public_timeline(cls, game: AvalonGame, events: list[AppEvent]) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for event in events:
            item = cls._timeline_item(game, event)
            if item is not None:
                timeline.append(item)
        return timeline

    @classmethod
    def _timeline_item(cls, game: AvalonGame, event: AppEvent) -> dict[str, Any] | None:
        payload = event.payload
        event_type = event.event_type
        if event_type == "game_started":
            return {
                "kind": event_type,
                "summary": f"游戏开始，规则 {payload.get('ruleset', game.ruleset.value)}。",
                "created_at": event.created_at,
            }
        if event_type == "team_selected":
            team = "、".join(cls._display(game, player_id) for player_id in payload.get("team", []))
            leader_id = payload.get("leader_id")
            return {
                "kind": event_type,
                "summary": f"第 {payload.get('round_number')} 轮，{cls._display(game, leader_id)} 选择队伍：{team}。",
                "created_at": event.created_at,
            }
        if event_type == "team_vote_resolved":
            result = "通过" if payload.get("approved") else "否决"
            return {
                "kind": event_type,
                "summary": (
                    f"第 {payload.get('round_number')} 轮组队{result}："
                    f"赞成 {payload.get('approve_count')}，反对 {payload.get('reject_count')}。"
                ),
                "created_at": event.created_at,
            }
        if event_type == "mission_resolved":
            result = "成功" if payload.get("succeeded") else "失败"
            return {
                "kind": event_type,
                "summary": (
                    f"第 {payload.get('round_number')} 轮任务{result}：失败票 {payload.get('fail_count')}，"
                    f"比分 正义 {payload.get('score_good')} : 邪恶 {payload.get('score_evil')}。"
                ),
                "created_at": event.created_at,
            }
        if event_type == "round_advanced":
            return {
                "kind": event_type,
                "summary": f"进入第 {payload.get('round_number')} 轮，队长是 {cls._display(game, payload.get('leader_id'))}。",
                "created_at": event.created_at,
            }
        if event_type == "assassination_resolved":
            target = cls._display(game, payload.get("target_id"))
            if payload.get("hit_merlin"):
                summary = f"刺客选择 {target}，命中梅林，邪恶方获胜。"
            else:
                summary = f"刺客选择 {target}，未命中梅林，正义方获胜。"
            return {"kind": event_type, "summary": summary, "created_at": event.created_at}
        if event_type == "game_over":
            winner = "正义方" if payload.get("winner") == "good" else "邪恶方"
            return {"kind": event_type, "summary": f"游戏结束，{winner}获胜。", "created_at": event.created_at}
        return None

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
    def _online_state(cls, game: AvalonGame, online_counts: dict[str, int]) -> dict[str, Any]:
        return {
            "players": [
                {
                    "player_id": player_id,
                    "online": online_counts.get(player_id, 0) > 0,
                    "connection_count": online_counts.get(player_id, 0),
                }
                for player_id in game.player_order
            ]
        }

    @classmethod
    def _chat_history(cls, game: AvalonGame, chat_history: list[Any]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for message in chat_history[-100:]:
            author_id = getattr(message, "author_id", None)
            messages.append(
                {
                    "message_id": getattr(message, "message_id", ""),
                    "author_id": author_id,
                    "author_display": cls._display(game, author_id) if author_id in game.player_order else "系统",
                    "text": getattr(message, "text", ""),
                    "created_at": getattr(message, "created_at", ""),
                }
            )
        return messages
```

Update `_display` so it tolerates missing IDs used by event safety:

```python
    @staticmethod
    def _display(game: AvalonGame, player_id: str | None) -> str:
        if player_id not in game.player_order:
            return "未知玩家"
        seat_number = game.player_order.index(player_id) + 1
        return f"{seat_number}号-{game.player_names[player_id]}"
```

- [ ] **Step 4: Implement unified speaking policy**

Replace `_voice_state()` with:

```python
    @classmethod
    def _voice_state(cls, phase: Phase) -> dict[str, Any]:
        speaker_state = cls._speaker_state(phase)
        return {
            "can_publish_audio": speaker_state["mode"] == "open",
            "publish_policy": speaker_state["mode"],
        }

    @staticmethod
    def _speaker_state(phase: Phase) -> dict[str, Any]:
        muted_phases = {Phase.TEAM_VOTE, Phase.MISSION_VOTE}
        mode = "muted" if phase in muted_phases else "open"
        return {
            "mode": mode,
            "can_send_text": mode == "open",
        }
```

- [ ] **Step 5: Extend lobby snapshots in `RoomService`**

In `app/application/rooms.py`, add this dataclass near `RequestRecord`:

```python
@dataclass
class ChatMessage:
    message_id: str
    author_id: str
    text: str
    created_at: str
```

Add to `Room`:

```python
    chat_history: list[ChatMessage] = field(default_factory=list)
```

Change `RoomService.snapshot()` signature:

```python
    def snapshot(
        self,
        room_id: str,
        viewer_id: str | None = None,
        online_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
```

Before returning `snapshot`, add lobby-compatible fields:

```python
        counts = online_counts or {}
        snapshot["voice_state"] = {"can_publish_audio": True, "publish_policy": "open"}
        snapshot["speaker_state"] = {"mode": "open", "can_send_text": True}
        snapshot["online_state"] = {
            "players": [
                {
                    "player_id": participant.player_id,
                    "online": counts.get(participant.player_id, 0) > 0,
                    "connection_count": counts.get(participant.player_id, 0),
                }
                for participant in participants
            ]
        }
        snapshot["chat_history"] = [
            {
                "message_id": message.message_id,
                "author_id": message.author_id,
                "author_display": self._display_name(room, message.author_id),
                "text": message.text,
                "created_at": message.created_at,
            }
            for message in room.chat_history[-100:]
        ]
        snapshot["public_timeline"] = []
```

Add helper:

```python
    def _display_name(self, room: Room, player_id: str) -> str:
        participant = next((item for item in room.participants if item.player_id == player_id), None)
        if participant is None:
            return "系统"
        return f"{participant.seat}号-{participant.nickname}"
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/application/test_snapshots.py tests/application/test_command_gateway.py tests/domain/test_game_core.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 7: Commit P0 backend contract**

```bash
git add app/application/commands.py app/application/rooms.py app/application/snapshots.py tests/application/test_command_gateway.py tests/application/test_snapshots.py tests/domain/test_game_core.py
git commit -m "feat: complete backend gameplay command loop"
```

---

### Task 4: WebSocket Online State Broadcast

**Files:**
- Modify: `app/realtime/manager.py`
- Modify: `app/api/ws.py`
- Modify: `app/main.py`
- Modify: `tests/api/test_ws_flow.py`

- [ ] **Step 1: Add failing online-state WebSocket test**

Append to `tests/api/test_ws_flow.py`:

```python
def test_ws_broadcasts_online_state_when_players_connect_and_disconnect():
    client = make_client()
    joins = join_players(client, count=5)

    with client.websocket_connect("/ws/ROOM1") as host_ws:
        host_initial = hello(host_ws, joins[0]["session_token"])
        assert host_initial["snapshot"]["online_state"]["players"][0]["online"] is True

        with client.websocket_connect("/ws/ROOM1") as guest_ws:
            guest_initial = hello(guest_ws, joins[1]["session_token"])
            host_after_guest_connect = host_ws.receive_json()

        host_after_guest_disconnect = host_ws.receive_json()

    assert guest_initial["type"] == "state"
    connected = {
        item["player_id"]: item["online"]
        for item in host_after_guest_connect["snapshot"]["online_state"]["players"]
    }
    disconnected = {
        item["player_id"]: item["online"]
        for item in host_after_guest_disconnect["snapshot"]["online_state"]["players"]
    }
    assert connected[joins[0]["player_id"]] is True
    assert connected[joins[1]["player_id"]] is True
    assert disconnected[joins[0]["player_id"]] is True
    assert disconnected[joins[1]["player_id"]] is False
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/api/test_ws_flow.py::test_ws_broadcasts_online_state_when_players_connect_and_disconnect -q
```

Expected: FAIL because existing connections do not receive online-state broadcasts.

- [ ] **Step 3: Add online counts to `ConnectionManager`**

In `app/realtime/manager.py`, add:

```python
    def online_counts(self, room_id: str) -> dict[str, int]:
        return {
            player_id: len(player_connections)
            for player_id, player_connections in self._rooms.get(room_id, {}).items()
        }
```

- [ ] **Step 4: Wire online provider in `app/main.py`**

Replace manager and gateway setup with:

```python
    connection_manager = ConnectionManager()
    app.state.connection_manager = connection_manager
    app.state.command_gateway = CommandGateway(
        room_service,
        session_service,
        online_players_provider=connection_manager.online_counts,
    )
```

- [ ] **Step 5: Broadcast state on connect and disconnect**

In `app/api/ws.py`, after `manager.connect(...)`, replace the single-player send with:

```python
        await manager.broadcast_room(
            room.room_id,
            payload_factory=lambda target_player_id: {
                "type": "state",
                "snapshot": command_gateway._snapshot_for_actor(room.room_id, target_player_id),
            },
        )
```

In the `finally` block, after `manager.disconnect(...)`, add:

```python
            await manager.broadcast_room(
                connected_room_id,
                payload_factory=lambda target_player_id: {
                    "type": "state",
                    "snapshot": command_gateway._snapshot_for_actor(connected_room_id, target_player_id),
                },
            )
```

- [ ] **Step 6: Run WebSocket tests**

Run:

```bash
pytest tests/api/test_ws_flow.py -q
```

Expected: all WebSocket tests pass. If an existing test receives an extra online-state broadcast, update the test to drain the expected state message and assert `payload["type"] == "state"`.

- [ ] **Step 7: Commit online state**

```bash
git add app/realtime/manager.py app/api/ws.py app/main.py tests/api/test_ws_flow.py
git commit -m "feat: broadcast online state"
```

---

### Task 5: Frontend P0 Gameplay Actions

**Files:**
- Modify: `static/main.js`
- Modify: `static/style.css`
- Modify: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Add static contract test for enabled gameplay actions**

In `tests/api/test_health_and_rooms.py`, add:

```python
def test_frontend_contains_enabled_gameplay_action_handlers():
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    for required in [
        "openTeamModal",
        "submitSelectedTeam",
        "sendCommand({type: \"team_vote\", vote: \"Approve\"})",
        "sendCommand({type: \"mission_vote\", vote: \"Success\"})",
        "sendCommand({type: \"continue_after_result\"})",
        "openAssassinModal",
        "submitAssassination",
    ]:
        assert required in main_js

    assert "选择出征队伍（待接入）" not in main_js
    assert "任务成功（待接入）" not in main_js
```

- [ ] **Step 2: Run failing static test**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_frontend_contains_enabled_gameplay_action_handlers -q
```

Expected: FAIL because the handlers do not exist and old disabled labels still exist.

- [ ] **Step 3: Add frontend state for team selection and assassination**

In `static/main.js`, extend `appState`:

```javascript
  selectedTeam: new Set(),
  pendingAssassinationTarget: "",
```

If keeping `appState` serializable is preferred, use arrays:

```javascript
  selectedTeam: [],
  pendingAssassinationTarget: "",
```

Use the array form for easier modal re-rendering.

- [ ] **Step 4: Replace disabled P0 buttons in `renderActions()`**

In `TEAM_PROPOSAL`, replace the disabled button with:

```javascript
        button("选择出征队伍", "btn btn-gold", openTeamModal),
```

In `TEAM_VOTE`, replace disabled vote buttons with:

```javascript
      row.append(
        button("赞成", "btn btn-good", () => sendCommand({type: "team_vote", vote: "Approve"})),
        button("反对", "btn btn-bad", () => sendCommand({type: "team_vote", vote: "Reject"})),
      );
```

In `MISSION_VOTE`, replace disabled mission buttons with:

```javascript
      row.append(
        button("任务成功", "btn btn-good", () => sendCommand({type: "mission_vote", vote: "Success"})),
        button("任务失败", "btn btn-bad", () => sendCommand({type: "mission_vote", vote: "Fail"})),
      );
```

In `MISSION_RESULT_DISCUSSION`, replace the disabled continue button with host-aware behavior:

```javascript
    const canContinue = Boolean(snapshot.you?.is_host);
    elements.actionArea.append(paragraph("任务结果已结算，复盘后由房主推进下一轮。"));
    if (canContinue) {
      elements.actionArea.append(button("进入下一轮", "btn btn-gold", () => sendCommand({type: "continue_after_result"})));
    } else {
      elements.actionArea.append(paragraph("等待房主进入下一轮。"));
    }
```

In `ASSASSINATION`, replace disabled button with:

```javascript
        button("选择刺杀目标", "btn btn-danger armed", openAssassinModal),
```

In `GAME_OVER`, replace the paragraph text with:

```javascript
    elements.actionArea.append(paragraph(`游戏结束：${winnerLabel(snapshot.phase_summary?.winner)} 获胜。`));
    appendRevealRoles(snapshot);
```

- [ ] **Step 5: Add team selection modal functions**

Add these functions before `openRoleModal()`:

```javascript
function openTeamModal() {
  const snapshot = appState.snapshot;
  const players = normalizePlayers(snapshot);
  const required = Number(snapshot?.phase_summary?.required_team_size || 0);
  appState.selectedTeam = currentTeam(snapshot).slice(0, required);
  if (appState.selectedTeam.length === 0) {
    appState.selectedTeam = [];
  }
  renderTeamModal(players, required);
  openModal(elements.teamModal);
}

function renderTeamModal(players, required) {
  elements.teamModalBody.replaceChildren();
  const count = document.createElement("p");
  count.className = "modal-sub strong";
  count.textContent = `已选择 ${appState.selectedTeam.length}/${required}`;
  elements.teamModalBody.append(count);

  const grid = document.createElement("div");
  grid.className = "picker-grid";
  players.forEach((player) => {
    const selected = appState.selectedTeam.includes(player.player_id);
    const item = button(player.display, selected ? "picker-option selected" : "picker-option", () => {
      toggleTeamMember(player.player_id, required);
      renderTeamModal(players, required);
    });
    grid.append(item);
  });
  elements.teamModalBody.append(grid);

  const actions = document.createElement("div");
  actions.className = "button-row";
  const submit = button("提交队伍", "btn btn-gold", submitSelectedTeam);
  submit.disabled = appState.selectedTeam.length !== required;
  actions.append(submit, button("取消", "btn btn-secondary", closeModals));
  elements.teamModalBody.append(actions);
}

function toggleTeamMember(playerId, required) {
  if (appState.selectedTeam.includes(playerId)) {
    appState.selectedTeam = appState.selectedTeam.filter((id) => id !== playerId);
    return;
  }
  if (appState.selectedTeam.length >= required) {
    showTopError(`本轮只能选择 ${required} 名玩家。`);
    return;
  }
  appState.selectedTeam = [...appState.selectedTeam, playerId];
}

function submitSelectedTeam() {
  const required = Number(appState.snapshot?.phase_summary?.required_team_size || 0);
  if (appState.selectedTeam.length !== required) {
    showTopError(`请选择 ${required} 名出征队员。`);
    return;
  }
  closeModals();
  sendCommand({type: "select_team", team: appState.selectedTeam});
}
```

- [ ] **Step 6: Add assassination modal functions**

Add after team modal functions:

```javascript
function openAssassinModal() {
  const players = normalizePlayers(appState.snapshot);
  appState.pendingAssassinationTarget = "";
  elements.assassinModalBody.replaceChildren();
  const grid = document.createElement("div");
  grid.className = "picker-grid";
  players.forEach((player) => {
    const item = button(player.display, "picker-option", () => {
      appState.pendingAssassinationTarget = player.player_id;
      [...grid.children].forEach((child) => child.classList.remove("selected"));
      item.classList.add("selected");
    });
    grid.append(item);
  });
  const actions = document.createElement("div");
  actions.className = "button-row";
  actions.append(button("确认刺杀", "btn btn-danger armed", submitAssassination), button("取消", "btn btn-secondary", closeModals));
  elements.assassinModalBody.append(grid, actions);
  openModal(elements.assassinModal);
}

function submitAssassination() {
  if (!appState.pendingAssassinationTarget) {
    showTopError("请选择刺杀目标。");
    return;
  }
  const targetId = appState.pendingAssassinationTarget;
  closeModals();
  sendCommand({type: "assassinate", target_id: targetId});
}
```

- [ ] **Step 7: Add terminal role reveal renderer**

Add before `appendHostReset()`:

```javascript
function appendRevealRoles(snapshot) {
  const roles = snapshot.reveal_roles || [];
  if (roles.length === 0) return;
  const box = document.createElement("div");
  box.className = "reveal-list";
  roles.forEach((item) => {
    const row = document.createElement("div");
    row.className = `reveal-row ${item.side === "evil" ? "evil" : "good"}`;
    row.textContent = `${item.display}：${item.role}`;
    box.append(row);
  });
  elements.actionArea.append(box);
}
```

In `openInfoModal()`, after appending the info table, add:

```javascript
  if (Array.isArray(snapshot.reveal_roles) && snapshot.reveal_roles.length > 0) {
    const title = document.createElement("h3");
    title.className = "modal-section-title";
    title.textContent = "终局身份";
    const list = document.createElement("div");
    list.className = "reveal-list";
    snapshot.reveal_roles.forEach((item) => {
      const row = document.createElement("div");
      row.className = `reveal-row ${item.side === "evil" ? "evil" : "good"}`;
      row.textContent = `${item.display}：${item.role}`;
      list.append(row);
    });
    elements.infoModalBody.append(title, list);
  }
```

- [ ] **Step 8: Add CSS for pickers and reveal list**

Add to `static/style.css`:

```css
.picker-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

.picker-option {
  min-height: 44px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.07);
  color: var(--foreground);
  font-weight: 700;
}

.picker-option.selected {
  border-color: rgba(200,169,74,.8);
  background: rgba(200,169,74,.22);
  color: var(--gold);
}

.reveal-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.reveal-row {
  padding: 9px 10px;
  border-radius: 8px;
  background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.12);
}

.reveal-row.good {
  color: var(--good);
}

.reveal-row.evil {
  color: var(--evil);
}

.modal-section-title {
  margin: 18px 0 8px;
  font-size: 15px;
}
```

- [ ] **Step 9: Run static and backend tests**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_frontend_contains_enabled_gameplay_action_handlers tests/application/test_command_gateway.py -q
```

Expected: tests pass.

- [ ] **Step 10: Commit frontend P0 actions**

```bash
git add static/main.js static/style.css tests/api/test_health_and_rooms.py
git commit -m "feat: enable core gameplay actions"
```

---

### Task 6: P1 Chat and Lobby Governance

**Files:**
- Modify: `app/application/rooms.py`
- Modify: `app/application/commands.py`
- Modify: `static/main.js`
- Modify: `static/style.css`
- Modify: `tests/application/test_command_gateway.py`
- Modify: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Add failing chat and governance tests**

Append to `tests/application/test_command_gateway.py`:

```python
def test_send_chat_stores_trimmed_message_when_speaking_is_open():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=host.session_token,
        command={"type": "send_chat", "text": "  大家准备一下  "},
        request_id="chat-1",
    )

    assert result.snapshot["chat_history"][-1]["text"] == "大家准备一下"
    assert result.snapshot["chat_history"][-1]["author_id"] == host.player_id
    assert result.events[0].event_type == "chat_message_sent"


def test_send_chat_is_rejected_during_secret_vote_phase():
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

    with pytest.raises(CommandError, match="当前阶段禁止发言"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=joins[0].session_token,
            command={"type": "send_chat", "text": "投我赞成"},
            request_id="chat-muted",
        )


def test_host_can_kick_lobby_player_and_old_token_stops_working():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=host.session_token,
        command={"type": "kick_player", "target_id": guest.player_id},
        request_id="kick-1",
    )

    assert guest.player_id not in [participant["player_id"] for participant in result.snapshot["participants"]]
    with pytest.raises(CommandError, match="当前会话不属于该房间玩家"):
        gateway.handle_command(
            room_id="ROOM1",
            session_token=guest.session_token,
            command={"type": "ready", "ready": True},
            request_id="ready-after-kick",
        )


def test_host_can_transfer_host_in_lobby():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=host.session_token,
        command={"type": "transfer_host", "target_id": guest.player_id},
        request_id="transfer-1",
    )

    assert result.snapshot["room"]["host_id"] == guest.player_id
    participants = {item["player_id"]: item for item in result.snapshot["participants"]}
    assert participants[host.player_id]["is_host"] is False
    assert participants[guest.player_id]["is_host"] is True


def test_player_can_leave_lobby_and_seats_are_compacted():
    gateway = make_gateway()
    host = gateway.handle_join(room_id="ROOM1", nickname="房主")
    guest = gateway.handle_join(room_id="ROOM1", nickname="玩家2")
    third = gateway.handle_join(room_id="ROOM1", nickname="玩家3")

    result = gateway.handle_command(
        room_id="ROOM1",
        session_token=guest.session_token,
        command={"type": "leave_room"},
        request_id="leave-1",
    )

    participants = result.snapshot["participants"]
    assert [item["player_id"] for item in participants] == [host.player_id, third.player_id]
    assert [item["seat"] for item in participants] == [1, 2]
```

- [ ] **Step 2: Implement room service chat and governance**

In `app/application/rooms.py`, add imports:

```python
from app.application.events import utc_now_iso
```

Add methods to `RoomService`:

```python
    def add_chat_message(self, room_id: str, actor_id: str, text: str) -> ChatMessage:
        room = self.get_room(room_id)
        self.get_participant(room, actor_id)
        normalized = text.strip()
        if not normalized:
            raise CommandError("消息不能为空。")
        if len(normalized) > 300:
            raise CommandError("消息不能超过 300 字。")
        message = ChatMessage(
            message_id=f"msg_{uuid4().hex[:12]}",
            author_id=actor_id,
            text=normalized,
            created_at=utc_now_iso(),
        )
        room.chat_history.append(message)
        room.chat_history = room.chat_history[-100:]
        return message

    def kick_player(self, room_id: str, actor_id: str, target_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        if room.game is not None:
            raise CommandError("游戏开始后不能踢人。")
        if actor_id != room.host_id:
            raise CommandError("只有房主可以踢人。")
        if actor_id == target_id:
            raise CommandError("房主不能踢自己，请先转移房主。")
        target = self.get_participant(room, target_id)
        room.participants.remove(target)
        self._compact_seats(room)
        event = AppEvent(
            event_type="participant_kicked",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"target_id": target_id},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def transfer_host(self, room_id: str, actor_id: str, target_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        if room.game is not None:
            raise CommandError("游戏开始后不能转移房主。")
        if actor_id != room.host_id:
            raise CommandError("只有房主可以转移房主。")
        target = self.get_participant(room, target_id)
        for participant in room.participants:
            participant.is_host = participant.player_id == target.player_id
        event = AppEvent(
            event_type="host_transferred",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"target_id": target_id},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def leave_room(self, room_id: str, actor_id: str, request_id: str) -> AppEvent:
        room = self.get_room(room_id)
        if room.game is not None:
            raise CommandError("游戏开始后不能退出房间，只会显示为离线。")
        participant = self.get_participant(room, actor_id)
        was_host = participant.is_host
        room.participants.remove(participant)
        if was_host and room.participants:
            room.participants[0].is_host = True
        self._compact_seats(room)
        event = AppEvent(
            event_type="participant_left",
            room_id=room.room_id,
            actor_id=actor_id,
            payload={"player_id": actor_id},
            request_id=request_id,
        )
        room.events.append(event)
        return event

    def _compact_seats(self, room: Room) -> None:
        for index, participant in enumerate(sorted(room.participants, key=lambda item: item.seat), start=1):
            participant.seat = index
```

- [ ] **Step 3: Add command handlers**

In `CommandGateway.handle_command()`, add dispatch entries before the final `else`:

```python
        elif command_type == "send_chat":
            result = self._handle_send_chat(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "kick_player":
            result = self._handle_kick_player(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "transfer_host":
            result = self._handle_transfer_host(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id, command=command)
        elif command_type == "leave_room":
            result = self._handle_leave_room(room_id=room.room_id, actor_id=participant.player_id, request_id=request_id)
```

Add handlers:

```python
    def _can_send_text(self, room_id: str) -> bool:
        room = self.room_service.get_room(room_id)
        if room.game is None:
            return True
        return room.game.phase.value not in {"TEAM_VOTE", "MISSION_VOTE"}

    def _handle_send_chat(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        if not self._can_send_text(room_id):
            raise CommandError("当前阶段禁止发言。")
        text = self._string_payload(command, "text", "text 必须是非空字符串。")
        message = self.room_service.add_chat_message(room_id=room_id, actor_id=actor_id, text=text)
        event = self._append_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="chat_message_sent",
            payload={"message_id": message.message_id},
            request_id=request_id,
        )
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_kick_player(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        target_id = self._string_payload(command, "target_id", "target_id 必须是玩家 ID。")
        event = self.room_service.kick_player(room_id=room_id, actor_id=actor_id, target_id=target_id, request_id=request_id)
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_transfer_host(self, room_id: str, actor_id: str, request_id: str, command: dict[str, Any]) -> CommandResult:
        target_id = self._string_payload(command, "target_id", "target_id 必须是玩家 ID。")
        event = self.room_service.transfer_host(room_id=room_id, actor_id=actor_id, target_id=target_id, request_id=request_id)
        return CommandResult(snapshot=self._snapshot_for_actor(room_id, actor_id), events=[event])

    def _handle_leave_room(self, room_id: str, actor_id: str, request_id: str) -> CommandResult:
        event = self.room_service.leave_room(room_id=room_id, actor_id=actor_id, request_id=request_id)
        return CommandResult(snapshot=self.room_service.snapshot(room_id, viewer_id=None, online_counts=self._online_counts(room_id)), events=[event])
```

- [ ] **Step 4: Enable chat frontend**

In `static/main.js`, remove chat disable calls from `disableUnsupportedChrome()`:

```javascript
  // Leave chat controls managed by renderChatControls().
```

Add to `bindEvents()`:

```javascript
  elements.sendChatBtn?.addEventListener("click", sendChatMessage);
  elements.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") sendChatMessage();
  });
```

Remove the old listeners that call `showTopError(missingFeatureHints.chat)`.

Add functions:

```javascript
function renderChatControls(snapshot) {
  const canSend = Boolean(snapshot?.speaker_state?.can_send_text);
  if (elements.chatInput) {
    elements.chatInput.disabled = !canSend;
    elements.chatInput.placeholder = canSend ? "输入消息…" : "当前阶段禁言";
  }
  if (elements.sendChatBtn) elements.sendChatBtn.disabled = !canSend;
  if (elements.chatStatusText) elements.chatStatusText.textContent = canSend ? "可发言" : "禁言";
}

function sendChatMessage() {
  const text = (elements.chatInput?.value || "").trim();
  if (!text) return;
  sendCommand({type: "send_chat", text});
  if (elements.chatInput) elements.chatInput.value = "";
}
```

Call `renderChatControls(snapshot)` inside `renderSnapshot()` after `renderChat()`.

Update `renderChat()`:

```javascript
function renderChat() {
  elements.chatMessages.replaceChildren();
  const snapshotMessages = appState.snapshot?.chat_history || [];
  const localMessages = appState.messages.slice(-20);
  const messages = snapshotMessages.length > 0
    ? snapshotMessages.map((message) => ({
        author: message.author_display || displayName(message.author_id),
        text: message.text,
        error: false,
      }))
    : localMessages;
  if (messages.length === 0) {
    elements.chatMessages.append(chatLine("系统", "暂无公屏消息。", true));
    return;
  }
  messages.slice(-100).forEach((message) => {
    elements.chatMessages.append(chatLine(message.author, message.text, message.error));
  });
}
```

- [ ] **Step 5: Add governance controls to info modal**

In `openInfoModal()`, after the info table, add:

```javascript
  appendGovernanceControls(snapshot, players);
```

Add functions:

```javascript
function appendGovernanceControls(snapshot, players) {
  if (!snapshot.you?.is_host || phase(snapshot) !== "LOBBY") return;
  const title = document.createElement("h3");
  title.className = "modal-section-title";
  title.textContent = "房主管理";
  const list = document.createElement("div");
  list.className = "governance-list";
  players.forEach((player) => {
    if (player.player_id === snapshot.you.player_id) return;
    const row = document.createElement("div");
    row.className = "governance-row";
    const name = document.createElement("span");
    name.textContent = player.display;
    const actions = document.createElement("div");
    actions.className = "governance-actions";
    actions.append(
      button("转交", "mini-btn", () => sendCommand({type: "transfer_host", target_id: player.player_id})),
      button("踢出", "mini-btn danger", () => sendCommand({type: "kick_player", target_id: player.player_id})),
    );
    row.append(name, actions);
    list.append(row);
  });
  elements.infoModalBody.append(title, list);
}
```

In `renderLobbyActions()`, add an exit button for non-host players:

```javascript
  if (!you.is_host) {
    elements.actionArea.append(button("退出房间", "btn btn-secondary", () => sendCommand({type: "leave_room"})));
  }
```

- [ ] **Step 6: Add CSS for chat and governance**

Add:

```css
.governance-list {
  display: grid;
  gap: 8px;
}

.governance-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  background: rgba(255,255,255,.06);
}

.governance-actions {
  display: flex;
  gap: 6px;
}

.mini-btn {
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 7px;
  background: rgba(255,255,255,.08);
  color: var(--foreground);
  padding: 6px 8px;
}

.mini-btn.danger {
  color: var(--evil);
  border-color: rgba(189,73,73,.35);
}
```

- [ ] **Step 7: Add frontend static contract test**

In `tests/api/test_health_and_rooms.py`, add:

```python
def test_frontend_contains_chat_and_governance_handlers():
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    for required in [
        "sendChatMessage",
        "renderChatControls",
        "appendGovernanceControls",
        "transfer_host",
        "kick_player",
        "leave_room",
    ]:
        assert required in main_js
```

- [ ] **Step 8: Run targeted tests**

Run:

```bash
pytest tests/application/test_command_gateway.py tests/api/test_health_and_rooms.py -q
```

Expected: tests pass.

- [ ] **Step 9: Commit chat and governance**

```bash
git add app/application/rooms.py app/application/commands.py static/main.js static/style.css tests/application/test_command_gateway.py tests/api/test_health_and_rooms.py
git commit -m "feat: add chat and lobby governance"
```

---

### Task 7: Voice Client and Private Marks

**Files:**
- Modify: `static/index.html`
- Modify: `static/main.js`
- Modify: `static/style.css`
- Modify: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Add static contract test**

In `tests/api/test_health_and_rooms.py`, add:

```python
def test_frontend_contains_voice_and_private_mark_handlers():
    index_html = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    main_js = (REPO_ROOT / "static" / "main.js").read_text(encoding="utf-8")

    assert "livekit-client.umd.min.js" in index_html
    for required in [
        "toggleVoice",
        "syncVoicePublishing",
        "toggleSpeaker",
        "openTagsModal",
        "setPrivateMark",
        "privateMarkKey",
    ]:
        assert required in main_js
```

- [ ] **Step 2: Add LiveKit script to `static/index.html`**

Before `<script src="/static/main.js"></script>`, add:

```html
  <script src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js"></script>
```

- [ ] **Step 3: Add voice state and event handlers**

In `static/main.js`, extend `appState`:

```javascript
  voiceRoom: null,
  voiceConnected: false,
  speakerMuted: false,
```

In `bindEvents()`, add:

```javascript
  elements.voiceBtn?.addEventListener("click", toggleVoice);
  elements.listenBtn?.addEventListener("click", toggleSpeaker);
  elements.openTagsBtn?.addEventListener("click", openTagsModal);
```

Remove voice and tags disable calls from `disableUnsupportedChrome()`.

- [ ] **Step 4: Implement voice functions**

Add:

```javascript
async function toggleVoice() {
  if (appState.voiceConnected) {
    disconnectVoice();
    return;
  }
  await connectVoice();
}

async function connectVoice() {
  if (!appState.sessionToken || !appState.roomId) {
    showTopError("请先加入房间。");
    return;
  }
  const LiveKit = window.LivekitClient || window.LiveKitClient;
  if (!LiveKit?.Room) {
    showTopError("语音客户端加载失败，仍可继续文字和游戏流程。");
    return;
  }
  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(appState.roomId)}/voice-token`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_token: appState.sessionToken}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "语音连接失败。");
    if (!payload.enabled) {
      showTopError("语音未配置，当前可继续使用文字和游戏流程。");
      updateVoiceButtons();
      return;
    }
    const room = new LiveKit.Room();
    room.on("trackSubscribed", (track) => {
      const element = track.attach();
      element.dataset.livekitAudio = "remote";
      element.muted = appState.speakerMuted;
      document.body.append(element);
    });
    room.on("trackUnsubscribed", (track) => {
      track.detach().forEach((element) => element.remove());
    });
    await room.connect(payload.url, payload.token);
    appState.voiceRoom = room;
    appState.voiceConnected = true;
    await syncVoicePublishing();
    updateVoiceButtons();
  } catch (error) {
    showTopError(error.message || "语音连接失败。");
  }
}

function disconnectVoice() {
  if (appState.voiceRoom) {
    try { appState.voiceRoom.disconnect(); } catch (_) {}
  }
  document.querySelectorAll("[data-livekit-audio='remote']").forEach((element) => element.remove());
  appState.voiceRoom = null;
  appState.voiceConnected = false;
  updateVoiceButtons();
}

async function syncVoicePublishing() {
  if (!appState.voiceRoom || !appState.voiceConnected) return;
  const canPublish = Boolean(appState.snapshot?.voice_state?.can_publish_audio);
  try {
    await appState.voiceRoom.localParticipant.setMicrophoneEnabled(canPublish);
  } catch (_) {
    if (canPublish) showTopError("无法开启麦克风，请检查浏览器权限。");
  }
  updateVoiceButtons();
}

function toggleSpeaker() {
  appState.speakerMuted = !appState.speakerMuted;
  document.querySelectorAll("[data-livekit-audio='remote']").forEach((element) => {
    element.muted = appState.speakerMuted;
  });
  updateVoiceButtons();
}

function updateVoiceButtons() {
  const canPublish = Boolean(appState.snapshot?.voice_state?.can_publish_audio);
  if (elements.voiceBtn) {
    elements.voiceBtn.classList.toggle("voice-on", appState.voiceConnected && canPublish);
    elements.voiceBtn.title = canPublish ? "语音" : "当前阶段禁麦";
    elements.voiceBtn.querySelector(".ctrl-label").textContent = appState.voiceConnected ? (canPublish ? "开麦" : "禁麦") : "语音";
  }
  if (elements.listenBtn) {
    elements.listenBtn.classList.toggle("muted", appState.speakerMuted);
    elements.listenBtn.querySelector(".ctrl-label").textContent = appState.speakerMuted ? "静音" : "扬声器";
  }
}
```

Call `syncVoicePublishing()` and `updateVoiceButtons()` inside `renderSnapshot()` after `renderChatControls(snapshot)`. The call to `syncVoicePublishing()` is async; use:

```javascript
  syncVoicePublishing();
  updateVoiceButtons();
```

- [ ] **Step 5: Implement private marks**

Replace `openTagsBtn` disabled behavior with `openTagsModal`.

Add:

```javascript
const markOptions = [
  {value: "trusted", label: "可信"},
  {value: "suspect", label: "可疑"},
  {value: "watch", label: "观察"},
  {value: "", label: "清除"},
];

function privateMarkKey(playerId) {
  return `avalon_mark:${appState.roomId}:${appState.playerId}:${playerId}`;
}

function privateMarkFor(playerId) {
  return localStorage.getItem(privateMarkKey(playerId)) || "";
}

function setPrivateMark(playerId, value) {
  if (value) {
    localStorage.setItem(privateMarkKey(playerId), value);
  } else {
    localStorage.removeItem(privateMarkKey(playerId));
  }
  renderSnapshot(appState.snapshot);
  openTagsModal();
}

function openTagsModal() {
  const players = normalizePlayers(appState.snapshot);
  elements.tagsModalBody.replaceChildren();
  players.forEach((player) => {
    const row = document.createElement("div");
    row.className = "mark-row";
    const name = document.createElement("span");
    name.textContent = player.display;
    const actions = document.createElement("div");
    actions.className = "mark-actions";
    markOptions.forEach((option) => {
      const item = button(option.label, privateMarkFor(player.player_id) === option.value ? "mini-btn selected" : "mini-btn", () => {
        setPrivateMark(player.player_id, option.value);
      });
      actions.append(item);
    });
    row.append(name, actions);
    elements.tagsModalBody.append(row);
  });
  openModal(elements.tagsModal);
}

function markLabel(value) {
  const option = markOptions.find((item) => item.value === value);
  return option?.label || "";
}
```

In `playerTags(player, snapshot)`, add:

```javascript
  const mark = privateMarkFor(player.player_id);
  if (mark) tags.push({kind: `mark-${mark}`, label: markLabel(mark)});
```

- [ ] **Step 6: Add CSS for voice and marks**

Add:

```css
.ctrl-btn.muted {
  opacity: .72;
}

.mark-row {
  display: grid;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255,255,255,.08);
}

.mark-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-btn.selected {
  border-color: rgba(200,169,74,.8);
  color: var(--gold);
  background: rgba(200,169,74,.18);
}

.tag.mark-trusted { background: rgba(73, 189, 132, .18); color: var(--good); }
.tag.mark-suspect { background: rgba(189, 73, 73, .18); color: var(--evil); }
.tag.mark-watch { background: rgba(200,169,74,.18); color: var(--gold); }
```

- [ ] **Step 7: Run static tests**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_frontend_contains_voice_and_private_mark_handlers -q
```

Expected: PASS.

- [ ] **Step 8: Commit voice and marks**

```bash
git add static/index.html static/main.js static/style.css tests/api/test_health_and_rooms.py
git commit -m "feat: add voice client and private marks"
```

---

### Task 8: Documentation and Verification

**Files:**
- Modify: `docs/MISSING_GAMEPLAY_FEATURES.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update missing gameplay doc**

Edit `docs/MISSING_GAMEPLAY_FEATURES.md` so the top section says P0/P1 are implemented in v2, and move the old P0/P1 checklist under a short “历史缺失清单” section. The first paragraphs should read:

```markdown
# v2 Gameplay Completion Status

本文档最初记录旧版 UI 已表达、但 v2 架构尚未完整接入的功能。当前 `codex/avalon-work` 已补齐完整一局闭环和第一版朋友局线上体验。

## 当前已实现

- 队长选择出征队伍：`select_team` 命令、队伍选择弹层、服务端队长/人数/成员校验。
- 全员组队投票：`team_vote` 命令、通过/否决结算、公开票数摘要且不泄漏个人票。
- 出征队员提交任务票：`mission_vote` 命令、队员权限校验、失败票数量和比分公开。
- 任务结果复盘后进入下一轮：房主执行 `continue_after_result`。
- 刺客刺杀梅林：`assassinate` 命令、终局胜负和身份公开。
- 公开历史：`public_timeline` 投影开局、选队、组队结果、任务结果、轮次推进和刺杀结果。
- 终局身份公开：`GAME_OVER` 才返回 `reveal_roles`。
- 文字公屏：`send_chat` 命令，按阶段自动控场。
- 语音客户端：LiveKit 配置存在时可连接，未配置时降级。
- 在线状态：WebSocket 连接/断开广播 `online_state`。
- 房主治理：大厅踢人、转交房主、玩家退出。
- 私人标记：本地 `localStorage` 标记。
```

- [ ] **Step 2: Update architecture doc**

In `docs/ARCHITECTURE.md`, replace the deferred sentence:

```markdown
当前 `CommandGateway` 已接入 join、ready、start、reset。完整游戏动作如 select team、team vote、mission vote、assassination 的前端发送和 gateway 命令接入仍是后续任务。
```

with:

```markdown
当前 `CommandGateway` 已接入 join、ready、start、reset、select_team、team_vote、mission_vote、continue_after_result、assassinate、send_chat 和大厅治理命令。HTTP 与 WebSocket 仍共享同一路径，避免两套规则裁定。
```

Add to the snapshot section:

```markdown
新增 gameplay completion 字段包括 `public_timeline`、`mission_result`、`reveal_roles`、`speaker_state`、`online_state` 和 `chat_history`。其中 `reveal_roles` 仅在 `GAME_OVER` 返回；`TEAM_VOTE` 与 `MISSION_VOTE` 阶段统一禁言禁麦。
```

- [ ] **Step 3: Update changelog**

Add under the current Unreleased section in `CHANGELOG.md`:

```markdown
- 完整接入 v2 游戏闭环：选队、组队投票、任务票、任务复盘推进、刺杀和终局身份公开。
- 新增公开历史、阶段自动控场、文字公屏、在线状态、基础房主治理、LiveKit 前端降级接入和本地私人标记。
```

- [ ] **Step 4: Run full automated verification**

Run:

```bash
pytest -q
python -c "from server import app; print(app.title)"
```

Expected:

```text
... all tests passed ...
Avalon Online v2
```

- [ ] **Step 5: Run local server**

Run:

```bash
uvicorn server:app --host 127.0.0.1 --port 8001
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8001
```

Keep this server running for manual verification, or use port `8000` if `8001` is occupied.

- [ ] **Step 6: Manual browser verification**

Open `http://127.0.0.1:8001/?room=123` in the in-app browser and verify:

1. Join as 5 players in separate browser sessions or tabs with independent sessions.
2. Host starts the game.
3. Identity overlay appears and can be dismissed.
4. Current leader opens team modal, selects exactly required players, submits.
5. All players submit team votes.
6. If rejected, leader rotates and returns to team proposal.
7. If approved, expedition members submit mission votes.
8. Mission result shows failure count and score.
9. Host advances to next round.
10. After three good successes, assassin can open target modal and submit assassination.
11. Game over displays winner and all roles.
12. `TEAM_VOTE` and `MISSION_VOTE` disable chat and mic publishing.
13. LiveKit unconfigured state shows a graceful voice error and does not block gameplay.
14. Host can kick and transfer host in lobby.
15. Private marks persist after reopening the marks modal.

- [ ] **Step 7: Commit docs**

```bash
git add docs/MISSING_GAMEPLAY_FEATURES.md docs/ARCHITECTURE.md CHANGELOG.md
git commit -m "docs: update gameplay completion status"
```

- [ ] **Step 8: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected:

```text
## codex/avalon-work
```

Only user-owned untracked files such as `AGENTS.md` may remain.

---

## Self-Review Checklist

- Spec coverage:
  - P0 commands are covered in Tasks 1-5.
  - `public_timeline`, `mission_result`, `reveal_roles`, `speaker_state`, `online_state`, and `chat_history` are covered in Tasks 3-4 and 6.
  - Chat, voice, online, governance, and private marks are covered in Tasks 6-7.
  - Documentation and verification are covered in Task 8.
- Privacy:
  - Personal team votes and mission vote submitters are never projected.
  - Full roles only appear through `reveal_roles` at `GAME_OVER`.
  - Online state exposes player IDs and counts only, not sockets or network data.
- Execution order:
  - Backend command tests fail before implementation.
  - Snapshot support lands before frontend depends on new fields.
  - WebSocket online state lands before UI displays online state.
  - P1 features follow after P0 game actions.
