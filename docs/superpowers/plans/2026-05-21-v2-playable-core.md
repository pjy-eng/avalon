# Avalon Online v2 Playable Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current branch into a v2 playable core with authoritative server rules, secure room sessions, realtime snapshots, LiveKit-first voice control, event logs, and the existing UI shape adapted to structured state.

**Architecture:** Current branch is the v2 rewrite branch. Remove the old runtime implementation from this branch after confirming it is recoverable from `main`, then rebuild a Python/FastAPI modular monolith with focused domain, application, infrastructure, realtime, and static UI modules. The client sends intents; the server validates sessions and commands, adjudicates through Game Core, writes events, projects per-player snapshots, and broadcasts them.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite for local tests, managed Postgres in deployed environments, Redis optional for cache/session TTL, PyJWT, pytest, FastAPI TestClient, vanilla HTML/CSS/JavaScript for the first UI adapter, LiveKit through a `VoiceProvider` adapter.

---

## Implementation Scope

This plan implements the first `v2 playable core` described in [`docs/superpowers/specs/2026-05-21-v2-product-architecture-design.md`](/Users/vangogh/Monorepo/avalon/docs/superpowers/specs/2026-05-21-v2-product-architecture-design.md).

It intentionally does not implement accounts, friend lists, public matchmaking, standard Avalon ruleset, custom ruleset UI, host/spectator UI, final product UI/UX, or microservices.

## File Structure

Delete from this branch during Task 1:

- `avalon_engine.py`
- `server.py`
- `static/index.html`
- `static/main.js`
- `static/style.css`
- `tests/test_engine.py`

Keep:

- `AGENTS.md`
- `README.md`
- `CHANGELOG.md`
- `docs/`
- `render.yaml`
- `runtime.txt`
- `.gitignore`

Create:

- `server.py` - thin ASGI entrypoint exporting `app`.
- `app/__init__.py` - package marker.
- `app/main.py` - FastAPI app factory, routes, static mounting, startup wiring.
- `app/config.py` - environment settings and secret validation.
- `app/domain/__init__.py` - package marker.
- `app/domain/types.py` - enums and value objects shared by domain modules.
- `app/domain/rulesets.py` - role configuration and `friend_flexible` ruleset.
- `app/domain/game.py` - pure Avalon state machine.
- `app/application/__init__.py` - package marker.
- `app/application/events.py` - command, decision, and security event records.
- `app/application/sessions.py` - room session token issue/verify logic.
- `app/application/rooms.py` - room lifecycle service.
- `app/application/commands.py` - command validation and dispatch.
- `app/application/snapshots.py` - per-player snapshot projection.
- `app/infrastructure/__init__.py` - package marker.
- `app/infrastructure/db.py` - SQLAlchemy engine/session and schema models.
- `app/infrastructure/repositories.py` - persistence operations for rooms, games, participants, events, replay snapshots.
- `app/infrastructure/redis_store.py` - optional Redis-backed TTL helpers with in-memory fallback.
- `app/infrastructure/voice.py` - `VoiceProvider`, `NoopVoiceProvider`, `LiveKitVoiceProvider`.
- `app/realtime/__init__.py` - package marker.
- `app/realtime/manager.py` - WebSocket connection registry and per-player broadcast.
- `app/api/__init__.py` - package marker.
- `app/api/http.py` - HTTP routes for health, static shell, room create, LiveKit token.
- `app/api/ws.py` - WebSocket endpoint and message loop.
- `static/index.html` - existing-style v2 shell.
- `static/main.js` - v2 client intent/snapshot adapter.
- `static/style.css` - minimal styles preserving current page shape.
- `tests/conftest.py` - app/test fixtures.
- `tests/domain/test_game_core.py`
- `tests/application/test_sessions.py`
- `tests/application/test_command_gateway.py`
- `tests/application/test_snapshots.py`
- `tests/application/test_events_replay.py`
- `tests/infrastructure/test_voice_provider.py`
- `tests/api/test_health_and_rooms.py`
- `tests/api/test_ws_flow.py`

Modify:

- `requirements.txt` - add SQLAlchemy, Alembic, httpx, pytest-asyncio, python-dotenv.
- `render.yaml` - keep `uvicorn server:app`, add required environment notes only if Render syntax supports them cleanly.
- `README.md` - update v2 local startup and environment variables.
- `docs/ARCHITECTURE.md` - replace old architecture with v2 module map.
- `docs/DEPLOYMENT.md` - update Postgres/Redis/LiveKit deployment expectations.
- `CHANGELOG.md` - add Unreleased v2 architecture rewrite entry.

---

### Task 1: Clean-Slate Scaffold and Health Check

**Files:**
- Delete: `avalon_engine.py`
- Delete: `server.py`
- Delete: `static/index.html`
- Delete: `static/main.js`
- Delete: `static/style.css`
- Delete: `tests/test_engine.py`
- Create: `server.py`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/config.py`
- Create: `app/api/__init__.py`
- Create: `app/api/http.py`
- Create: `static/index.html`
- Create: `static/main.js`
- Create: `static/style.css`
- Modify: `requirements.txt`
- Test: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Confirm branch and recoverable baseline**

Run:

```bash
git status --short --branch
git log --oneline -5
git branch --show-current
```

Expected:

```text
## codex/avalon-work
codex/avalon-work
```

Confirm `main` exists locally:

```bash
git show --stat --oneline main -- README.md
```

Expected: `main` resolves to a commit. If `main` does not resolve, run `git fetch origin main:main` before deleting old files.

- [ ] **Step 2: Write the failing health test**

Create `tests/api/test_health_and_rooms.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_config_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "avalon-online-v2",
        "database": "not_configured",
        "redis": "not_configured",
        "voice": "not_configured",
    }
```

- [ ] **Step 3: Run the failing health test**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_health_returns_config_status -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Remove old implementation files**

Run:

```bash
git rm avalon_engine.py server.py static/index.html static/main.js static/style.css tests/test_engine.py
```

Expected: git stages deletion of the old runtime implementation. Do not remove `AGENTS.md`, `docs/`, `README.md`, `CHANGELOG.md`, `render.yaml`, or `runtime.txt`.

- [ ] **Step 5: Add dependencies**

Update `requirements.txt` to:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pytest==8.3.4
pytest-asyncio==0.25.2
httpx==0.28.1
PyJWT==2.10.1
redis==5.2.1
SQLAlchemy==2.0.36
alembic==1.14.0
python-dotenv==1.0.1
```

- [ ] **Step 6: Add minimal app package**

Create `app/__init__.py`:

```python
"""Avalon Online v2 application package."""
```

Create `app/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str = "avalon-online-v2"
    database_url: str | None = None
    redis_url: str | None = None
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    session_secret: str = "dev-only-session-secret"

    @property
    def database_status(self) -> str:
        return "configured" if self.database_url else "not_configured"

    @property
    def redis_status(self) -> str:
        return "configured" if self.redis_url else "not_configured"

    @property
    def voice_status(self) -> str:
        if self.livekit_url and self.livekit_api_key and self.livekit_api_secret:
            return "configured"
        return "not_configured"


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        redis_url=os.getenv("REDIS_URL"),
        livekit_url=os.getenv("LIVEKIT_URL"),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY"),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET"),
        session_secret=os.getenv("SESSION_SECRET", "dev-only-session-secret"),
    )
```

Create `app/api/__init__.py`:

```python
"""HTTP and WebSocket API modules."""
```

Create `app/api/http.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import Settings

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str | bool]:
    settings: Settings = request.app.state.settings
    return {
        "ok": True,
        "service": settings.service_name,
        "database": settings.database_status,
        "redis": settings.redis_status,
        "voice": settings.voice_status,
    }


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    with open("static/index.html", "r", encoding="utf-8") as file:
        return file.read()
```

Create `app/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.http import router as http_router
from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Avalon Online v2", version="0.1.0")
    app.state.settings = settings or load_settings()
    app.include_router(http_router)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    return app


app = create_app()
```

Create `server.py`:

```python
from app.main import app
```

- [ ] **Step 7: Add minimal static shell**

Create `static/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Avalon Online v2</title>
    <link rel="stylesheet" href="/static/style.css">
  </head>
  <body>
    <main class="app-shell">
      <section class="panel">
        <p class="eyebrow">Avalon Online v2</p>
        <h1>阿瓦隆圆桌</h1>
        <p id="statusText">正在连接服务...</p>
      </section>
    </main>
    <script src="/static/main.js"></script>
  </body>
</html>
```

Create `static/main.js`:

```javascript
const statusText = document.getElementById("statusText");

async function boot() {
  const response = await fetch("/health");
  const health = await response.json();
  statusText.textContent = health.ok ? "服务已就绪" : "服务暂不可用";
}

boot().catch(() => {
  statusText.textContent = "服务连接失败";
});
```

Create `static/style.css`:

```css
html {
  color-scheme: dark;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  min-height: 100vh;
  background: #111827;
  color: #f9fafb;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.panel {
  width: min(560px, 100%);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  padding: 24px;
  background: rgba(17, 24, 39, 0.88);
}

.eyebrow {
  margin: 0 0 8px;
  color: #93c5fd;
  font-size: 0.85rem;
  text-transform: uppercase;
}

h1 {
  margin: 0 0 12px;
  font-size: 2rem;
}
```

- [ ] **Step 8: Run health test**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_health_returns_config_status -q
```

Expected: `1 passed`.

- [ ] **Step 9: Run smoke server import**

Run:

```bash
python -c "from server import app; print(app.title)"
```

Expected:

```text
Avalon Online v2
```

- [ ] **Step 10: Commit scaffold**

Run:

```bash
git add requirements.txt server.py app static tests/api/test_health_and_rooms.py
git commit -m "chore: scaffold avalon v2 app"
```

---

### Task 2: Domain Types and Friend-Flexible Game Core

**Files:**
- Create: `app/domain/__init__.py`
- Create: `app/domain/types.py`
- Create: `app/domain/rulesets.py`
- Create: `app/domain/game.py`
- Test: `tests/domain/test_game_core.py`

- [ ] **Step 1: Write failing domain tests**

Create `tests/domain/test_game_core.py`:

```python
import pytest

from app.domain.game import AvalonGame
from app.domain.types import CommandError, Phase, Role, RulesetName


def make_game(count: int = 5, seed: int = 7) -> AvalonGame:
    players = [f"p{i}" for i in range(1, count + 1)]
    names = {pid: f"玩家{i}" for i, pid in enumerate(players, start=1)}
    return AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=seed)


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
    leader = game.leader_id
    game.select_team(actor_id=leader, team=game.player_order[:2])
    for player_id in game.player_order:
        game.submit_team_vote(actor_id=player_id, vote="Approve")

    loyal_player = game.player_order[0]
    game.roles[loyal_player] = Role.LOYAL
    game.submit_mission_vote(actor_id=loyal_player, vote="Fail")

    assert game.mission_votes[loyal_player] == "Fail"


def test_non_team_member_cannot_submit_mission_vote():
    game = make_game(5)
    leader = game.leader_id
    game.select_team(actor_id=leader, team=game.player_order[:2])
    for player_id in game.player_order:
        game.submit_team_vote(actor_id=player_id, vote="Approve")

    with pytest.raises(CommandError, match="只有出征队员可以提交任务票"):
        game.submit_mission_vote(actor_id=game.player_order[4], vote="Fail")


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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/domain/test_game_core.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain'` or missing domain symbols.

- [ ] **Step 3: Add domain types**

Create `app/domain/__init__.py`:

```python
"""Pure domain logic for Avalon Online v2."""
```

Create `app/domain/types.py`:

```python
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
```

- [ ] **Step 4: Add ruleset configuration**

Create `app/domain/rulesets.py`:

```python
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
```

- [ ] **Step 5: Add minimal Game Core**

Create `app/domain/game.py`:

```python
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
```

- [ ] **Step 6: Run domain tests**

Run:

```bash
pytest tests/domain/test_game_core.py -q
```

Expected: `5 passed`.

- [ ] **Step 7: Commit Game Core**

Run:

```bash
git add app/domain tests/domain/test_game_core.py
git commit -m "feat: add v2 game core"
```

---

### Task 3: Sessions, Room Lifecycle, and Command Gateway

**Files:**
- Create: `app/application/__init__.py`
- Create: `app/application/sessions.py`
- Create: `app/application/rooms.py`
- Create: `app/application/commands.py`
- Create: `app/application/events.py`
- Test: `tests/application/test_sessions.py`
- Test: `tests/application/test_command_gateway.py`

- [ ] **Step 1: Write session tests**

Create `tests/application/test_sessions.py`:

```python
import pytest

from app.application.sessions import RoomSessionService, SessionError


def test_room_session_round_trips_player_identity():
    service = RoomSessionService(secret="test-secret")

    token = service.issue(room_id="ROOM7", player_id="p1", token_version=1)
    claims = service.verify(token, expected_room_id="ROOM7")

    assert claims.room_id == "ROOM7"
    assert claims.player_id == "p1"
    assert claims.token_version == 1


def test_room_session_rejects_wrong_room():
    service = RoomSessionService(secret="test-secret")
    token = service.issue(room_id="ROOM7", player_id="p1", token_version=1)

    with pytest.raises(SessionError, match="房间会话不属于当前房间"):
        service.verify(token, expected_room_id="ROOM8")
```

- [ ] **Step 2: Write command gateway tests**

Create `tests/application/test_command_gateway.py`:

```python
import pytest

from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService
from app.domain.types import CommandError, Phase, RulesetName


def make_gateway() -> CommandGateway:
    sessions = RoomSessionService(secret="test-secret")
    rooms = RoomService(session_service=sessions)
    return CommandGateway(room_service=rooms, session_service=sessions)


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
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest tests/application/test_sessions.py tests/application/test_command_gateway.py -q
```

Expected: FAIL because application modules do not exist.

- [ ] **Step 4: Add application package and events**

Create `app/application/__init__.py`:

```python
"""Application services for room sessions, commands, snapshots, and events."""
```

Create `app/application/events.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AppEvent:
    event_type: str
    room_id: str
    actor_id: str | None
    payload: dict[str, Any]
    request_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
```

- [ ] **Step 5: Add session service**

Create `app/application/sessions.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt


class SessionError(ValueError):
    """Raised when a room session token cannot be trusted."""


@dataclass(frozen=True)
class RoomSessionClaims:
    room_id: str
    player_id: str
    token_version: int


class RoomSessionService:
    def __init__(self, secret: str, ttl_hours: int = 12) -> None:
        self.secret = secret
        self.ttl_hours = ttl_hours

    def issue(self, room_id: str, player_id: str, token_version: int) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": player_id,
            "room_id": room_id,
            "token_version": token_version,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=self.ttl_hours)).timestamp()),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def verify(self, token: str, expected_room_id: str) -> RoomSessionClaims:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise SessionError("房间会话无效，请重新加入房间。") from exc
        room_id = str(payload.get("room_id") or "")
        if room_id != expected_room_id:
            raise SessionError("房间会话不属于当前房间。")
        player_id = str(payload.get("sub") or "")
        token_version = int(payload.get("token_version") or 0)
        if not player_id or token_version < 1:
            raise SessionError("房间会话缺少玩家身份。")
        return RoomSessionClaims(room_id=room_id, player_id=player_id, token_version=token_version)
```

- [ ] **Step 6: Add room lifecycle service**

Create `app/application/rooms.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from app.application.events import AppEvent
from app.application.sessions import RoomSessionService
from app.domain.game import AvalonGame
from app.domain.types import CommandError, RulesetName


@dataclass
class Participant:
    player_id: str
    nickname: str
    seat: int
    token_version: int = 1
    connected: bool = True


@dataclass
class Room:
    room_id: str
    host_id: str | None = None
    ruleset: RulesetName = RulesetName.FRIEND_FLEXIBLE
    participants: dict[str, Participant] = field(default_factory=dict)
    game: AvalonGame | None = None
    events: list[AppEvent] = field(default_factory=list)

    def player_order(self) -> list[str]:
        return [pid for pid, _ in sorted(self.participants.items(), key=lambda item: item[1].seat)]

    def player_names(self) -> dict[str, str]:
        return {pid: participant.nickname for pid, participant in self.participants.items()}


@dataclass(frozen=True)
class JoinResult:
    room_id: str
    player_id: str
    session_token: str
    snapshot: dict


class RoomService:
    def __init__(self, session_service: RoomSessionService) -> None:
        self.session_service = session_service
        self.rooms: dict[str, Room] = {}

    def get_or_create_room(self, room_id: str) -> Room:
        room_key = room_id.strip().upper()
        if not room_key:
            raise CommandError("房间号不能为空。")
        if room_key not in self.rooms:
            self.rooms[room_key] = Room(room_id=room_key)
        return self.rooms[room_key]

    def join(self, room_id: str, nickname: str) -> JoinResult:
        room = self.get_or_create_room(room_id)
        if room.game:
            raise CommandError("游戏已经开始，新玩家不能中途加入。")
        if len(room.participants) >= 10:
            raise CommandError("房间已满，最多 10 人。")
        player_id = f"p_{uuid4().hex[:12]}"
        participant = Participant(
            player_id=player_id,
            nickname=(nickname or "玩家").strip()[:24] or "玩家",
            seat=len(room.participants) + 1,
        )
        room.participants[player_id] = participant
        if room.host_id is None:
            room.host_id = player_id
        room.events.append(AppEvent(event_type="participant_joined", room_id=room.room_id, actor_id=player_id, payload={"seat": participant.seat}))
        token = self.session_service.issue(room.room_id, player_id, participant.token_version)
        return JoinResult(room_id=room.room_id, player_id=player_id, session_token=token, snapshot=self.lobby_snapshot(room, player_id))

    def lobby_snapshot(self, room: Room, player_id: str) -> dict:
        return {
            "room": {"room_id": room.room_id, "ruleset": room.ruleset.value},
            "you": {"player_id": player_id, "is_host": player_id == room.host_id},
            "phase_summary": {"phase": "LOBBY"},
            "players": [
                {
                    "player_id": participant.player_id,
                    "nickname": participant.nickname,
                    "seat": participant.seat,
                    "connected": participant.connected,
                    "is_host": participant.player_id == room.host_id,
                }
                for participant in sorted(room.participants.values(), key=lambda item: item.seat)
            ],
        }
```

- [ ] **Step 7: Add command gateway**

Create `app/application/commands.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.application.rooms import JoinResult, RoomService
from app.application.sessions import RoomSessionService
from app.domain.game import AvalonGame
from app.domain.types import CommandError


@dataclass(frozen=True)
class CommandResult:
    snapshot: dict


class CommandGateway:
    def __init__(self, room_service: RoomService, session_service: RoomSessionService) -> None:
        self.room_service = room_service
        self.session_service = session_service
        self.seen_request_ids: set[tuple[str, str]] = set()

    def handle_join(self, room_id: str, nickname: str) -> JoinResult:
        return self.room_service.join(room_id=room_id, nickname=nickname)

    def handle_command(self, room_id: str, session_token: str, command: dict, request_id: str) -> CommandResult:
        claims = self.session_service.verify(session_token, expected_room_id=room_id)
        dedupe_key = (claims.player_id, request_id)
        if dedupe_key in self.seen_request_ids:
            room = self.room_service.get_or_create_room(room_id)
            return CommandResult(snapshot=self.room_service.lobby_snapshot(room, claims.player_id) if not room.game else {"duplicate": True})
        self.seen_request_ids.add(dedupe_key)

        room = self.room_service.get_or_create_room(room_id)
        command_type = command.get("type")
        if command_type == "start_game":
            if claims.player_id != room.host_id:
                raise CommandError("只有房主可以开局。")
            if len(room.participants) < 5:
                raise CommandError("阿瓦隆必须 5-10 人才能开始。")
            room.game = AvalonGame.new(
                players=room.player_order(),
                player_names=room.player_names(),
                ruleset=room.ruleset,
            )
            return CommandResult(snapshot=self._game_snapshot(room, claims.player_id))
        raise CommandError("未知命令类型。")

    def _game_snapshot(self, room, player_id: str) -> dict:
        assert room.game is not None
        return {
            "room": {"room_id": room.room_id, "ruleset": room.ruleset.value},
            "you": {"player_id": player_id, "is_host": player_id == room.host_id},
            "phase_summary": {"phase": room.game.phase.value, "leader_id": room.game.leader_id},
        }
```

- [ ] **Step 8: Run application tests**

Run:

```bash
pytest tests/application/test_sessions.py tests/application/test_command_gateway.py -q
```

Expected: `5 passed`.

- [ ] **Step 9: Commit sessions and command gateway**

Run:

```bash
git add app/application tests/application/test_sessions.py tests/application/test_command_gateway.py
git commit -m "feat: add room sessions and command gateway"
```

---

### Task 4: Snapshot Projector With Privacy Boundaries

**Files:**
- Create: `app/application/snapshots.py`
- Modify: `app/application/commands.py`
- Test: `tests/application/test_snapshots.py`

- [ ] **Step 1: Write failing snapshot tests**

Create `tests/application/test_snapshots.py`:

```python
from app.application.snapshots import SnapshotProjector
from app.domain.game import AvalonGame
from app.domain.types import Role, RulesetName


def test_snapshot_only_includes_current_player_private_role():
    players = ["p1", "p2", "p3", "p4", "p5"]
    names = {pid: f"玩家{index}" for index, pid in enumerate(players, start=1)}
    game = AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=1)
    game.roles = {
        "p1": Role.MERLIN,
        "p2": Role.PERCIVAL,
        "p3": Role.LOYAL,
        "p4": Role.MORGANA,
        "p5": Role.ASSASSIN,
    }
    projector = SnapshotProjector()

    p1_snapshot = projector.for_player(game=game, player_id="p1", host_id="p1", room_id="ROOM1")
    p2_snapshot = projector.for_player(game=game, player_id="p2", host_id="p1", room_id="ROOM1")

    assert p1_snapshot["private_panel"]["role"] == "梅林"
    assert p2_snapshot["private_panel"]["role"] == "派西维尔"
    assert p2_snapshot["private_panel"]["visible_players"] == [
        {"player_id": "p1", "display": "1号-玩家1"},
        {"player_id": "p4", "display": "4号-玩家4"},
    ]
    assert "roles" not in p1_snapshot
    assert "mission_votes" not in p1_snapshot


def test_snapshot_my_action_for_leader_team_proposal():
    players = ["p1", "p2", "p3", "p4", "p5"]
    names = {pid: f"玩家{index}" for index, pid in enumerate(players, start=1)}
    game = AvalonGame.new(players=players, player_names=names, ruleset=RulesetName.FRIEND_FLEXIBLE, rng_seed=1)
    projector = SnapshotProjector()

    leader_snapshot = projector.for_player(game=game, player_id=game.leader_id, host_id="p1", room_id="ROOM1")
    non_leader = next(pid for pid in players if pid != game.leader_id)
    non_leader_snapshot = projector.for_player(game=game, player_id=non_leader, host_id="p1", room_id="ROOM1")

    assert leader_snapshot["my_action"]["type"] == "select_team"
    assert non_leader_snapshot["my_action"]["type"] == "wait"
```

- [ ] **Step 2: Run snapshot tests to verify failure**

Run:

```bash
pytest tests/application/test_snapshots.py -q
```

Expected: FAIL because `SnapshotProjector` does not exist.

- [ ] **Step 3: Implement SnapshotProjector**

Create `app/application/snapshots.py`:

```python
from __future__ import annotations

from app.domain.game import AvalonGame
from app.domain.types import EVIL_ROLES, Phase, Role


class SnapshotProjector:
    def for_player(self, game: AvalonGame, player_id: str, host_id: str | None, room_id: str) -> dict:
        return {
            "room": {"room_id": room_id, "ruleset": game.ruleset.value},
            "you": {"player_id": player_id, "is_host": player_id == host_id},
            "phase_summary": {
                "phase": game.phase.value,
                "round": game.round_number,
                "leader_id": game.leader_id,
                "required_team_size": game.required_team_size,
                "current_team": game.current_team,
                "score": {"good": game.score_good, "evil": game.score_evil},
                "winner": game.winner,
            },
            "my_action": self._my_action(game, player_id),
            "voice_state": self._voice_state(game, player_id),
            "private_panel": self._private_panel(game, player_id),
            "public_timeline": [],
            "players": [
                {"player_id": pid, "display": self._display(game, pid), "is_leader": pid == game.leader_id}
                for pid in game.player_order
            ],
        }

    def _my_action(self, game: AvalonGame, player_id: str) -> dict:
        if game.phase == Phase.TEAM_PROPOSAL and player_id == game.leader_id:
            return {"type": "select_team", "required_team_size": game.required_team_size}
        if game.phase == Phase.TEAM_VOTE and player_id not in game.team_votes:
            return {"type": "team_vote"}
        if game.phase == Phase.MISSION_VOTE and player_id in game.current_team and player_id not in game.mission_votes:
            return {"type": "mission_vote", "can_submit_fail": True}
        if game.phase == Phase.ASSASSINATION and game.roles.get(player_id) == Role.ASSASSIN:
            return {"type": "assassinate"}
        return {"type": "wait"}

    def _voice_state(self, game: AvalonGame, player_id: str) -> dict:
        can_publish = game.phase in {Phase.TEAM_PROPOSAL, Phase.MISSION_RESULT_DISCUSSION, Phase.ASSASSINATION, Phase.GAME_OVER}
        return {"can_publish_audio": can_publish, "policy": "open" if can_publish else "muted"}

    def _private_panel(self, game: AvalonGame, player_id: str) -> dict:
        role = game.roles[player_id]
        visible_players: list[dict[str, str]] = []
        if role == Role.MERLIN:
            visible_players = [
                {"player_id": pid, "display": self._display(game, pid)}
                for pid, other_role in game.roles.items()
                if other_role in EVIL_ROLES and other_role != Role.MORDRED
            ]
        elif role == Role.PERCIVAL:
            visible_players = [
                {"player_id": pid, "display": self._display(game, pid)}
                for pid, other_role in sorted(game.roles.items(), key=lambda item: game.player_order.index(item[0]))
                if other_role in {Role.MERLIN, Role.MORGANA}
            ]
        elif role in EVIL_ROLES and role != Role.OBERON:
            visible_players = [
                {"player_id": pid, "display": self._display(game, pid)}
                for pid, other_role in sorted(game.roles.items(), key=lambda item: game.player_order.index(item[0]))
                if pid != player_id and other_role in EVIL_ROLES and other_role != Role.OBERON
            ]
        return {
            "role": role.value,
            "side": "good" if role not in EVIL_ROLES else "evil",
            "visible_players": visible_players,
        }

    def _display(self, game: AvalonGame, player_id: str) -> str:
        seat = game.player_order.index(player_id) + 1
        return f"{seat}号-{game.player_names[player_id]}"
```

- [ ] **Step 4: Use projector in command gateway**

Modify `app/application/commands.py`:

```python
from app.application.snapshots import SnapshotProjector
```

Update `CommandGateway.__init__`:

```python
    def __init__(self, room_service: RoomService, session_service: RoomSessionService) -> None:
        self.room_service = room_service
        self.session_service = session_service
        self.projector = SnapshotProjector()
        self.seen_request_ids: set[tuple[str, str]] = set()
```

Replace `_game_snapshot` with:

```python
    def _game_snapshot(self, room, player_id: str) -> dict:
        assert room.game is not None
        return self.projector.for_player(game=room.game, player_id=player_id, host_id=room.host_id, room_id=room.room_id)
```

- [ ] **Step 5: Run snapshot and command tests**

Run:

```bash
pytest tests/application/test_snapshots.py tests/application/test_command_gateway.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit snapshots**

Run:

```bash
git add app/application/snapshots.py app/application/commands.py tests/application/test_snapshots.py
git commit -m "feat: add per-player snapshot projection"
```

---

### Task 5: Persistence, Event Log, and Replay Projection

**Files:**
- Create: `app/infrastructure/__init__.py`
- Create: `app/infrastructure/db.py`
- Create: `app/infrastructure/repositories.py`
- Modify: `app/application/events.py`
- Test: `tests/application/test_events_replay.py`

- [ ] **Step 1: Write failing persistence tests**

Create `tests/application/test_events_replay.py`:

```python
from app.application.events import AppEvent
from app.infrastructure.db import create_schema, make_engine, session_scope
from app.infrastructure.repositories import EventRepository


def test_event_repository_persists_command_decision_and_security_events():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)

    with session_scope(engine) as session:
        repo = EventRepository(session)
        repo.append(AppEvent(event_type="command.join_room", room_id="ROOM1", actor_id="p1", request_id="r1", payload={"nickname": "阿澈"}))
        repo.append(AppEvent(event_type="decision.accepted", room_id="ROOM1", actor_id="p1", request_id="r1", payload={"phase": "LOBBY"}))
        repo.append(AppEvent(event_type="security.rate_limited", room_id="ROOM1", actor_id="p1", request_id="r2", payload={"command": "chat"}))
        session.flush()

    with session_scope(engine) as session:
        repo = EventRepository(session)
        events = repo.list_room_events("ROOM1")

    assert [event.event_type for event in events] == [
        "command.join_room",
        "decision.accepted",
        "security.rate_limited",
    ]
    assert events[0].payload == {"nickname": "阿澈"}
```

- [ ] **Step 2: Run persistence test to verify failure**

Run:

```bash
pytest tests/application/test_events_replay.py -q
```

Expected: FAIL because infrastructure modules do not exist.

- [ ] **Step 3: Add SQLAlchemy schema**

Create `app/infrastructure/__init__.py`:

```python
"""Infrastructure adapters for persistence, cache, and voice providers."""
```

Create `app/infrastructure/db.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import JSON, DateTime, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "game_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(64))
    inserted_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


def make_engine(database_url: str):
    return create_engine(database_url, future=True)


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Add EventRepository**

Create `app/infrastructure/repositories.py`:

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import AppEvent
from app.infrastructure.db import EventRecord


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AppEvent) -> None:
        self.session.add(
            EventRecord(
                event_id=event.event_id,
                event_type=event.event_type,
                room_id=event.room_id,
                actor_id=event.actor_id,
                request_id=event.request_id,
                payload=event.payload,
                created_at=event.created_at,
            )
        )

    def list_room_events(self, room_id: str) -> list[AppEvent]:
        records = self.session.scalars(
            select(EventRecord).where(EventRecord.room_id == room_id).order_by(EventRecord.inserted_at, EventRecord.event_id)
        ).all()
        return [
            AppEvent(
                event_id=record.event_id,
                event_type=record.event_type,
                room_id=record.room_id,
                actor_id=record.actor_id,
                request_id=record.request_id,
                payload=record.payload,
                created_at=record.created_at,
            )
            for record in records
        ]
```

- [ ] **Step 5: Run persistence tests**

Run:

```bash
pytest tests/application/test_events_replay.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit persistence**

Run:

```bash
git add app/infrastructure app/application/events.py tests/application/test_events_replay.py
git commit -m "feat: add event persistence"
```

---

### Task 6: Durable Room/Game Repository and Redis TTL Store

**Files:**
- Modify: `app/infrastructure/db.py`
- Modify: `app/infrastructure/repositories.py`
- Create: `app/infrastructure/redis_store.py`
- Test: `tests/infrastructure/test_repositories_and_redis.py`

- [ ] **Step 1: Write failing repository and Redis fallback tests**

Create `tests/infrastructure/test_repositories_and_redis.py`:

```python
from app.infrastructure.db import create_schema, make_engine, session_scope
from app.infrastructure.redis_store import InMemoryTTLStore
from app.infrastructure.repositories import RoomRepository


def test_room_repository_persists_room_participants_and_game_state():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_schema(engine)

    with session_scope(engine) as session:
        repo = RoomRepository(session)
        repo.upsert_room(room_id="ROOM1", ruleset="friend_flexible", status="IN_GAME")
        repo.upsert_participant(room_id="ROOM1", player_id="p1", nickname="阿澈", seat=1, participant_type="player", token_version=1)
        repo.upsert_game(room_id="ROOM1", phase="TEAM_PROPOSAL", state={"leader_id": "p1"})
        session.flush()

    with session_scope(engine) as session:
        repo = RoomRepository(session)
        room = repo.get_room_bundle("ROOM1")

    assert room["room"]["room_id"] == "ROOM1"
    assert room["room"]["ruleset"] == "friend_flexible"
    assert room["participants"][0]["player_id"] == "p1"
    assert room["game"]["state"] == {"leader_id": "p1"}


def test_in_memory_ttl_store_supports_idempotency_keys():
    store = InMemoryTTLStore()

    assert store.set_once("idem:p1:r1", "1", ttl_seconds=60) is True
    assert store.set_once("idem:p1:r1", "1", ttl_seconds=60) is False
    assert store.get("idem:p1:r1") == "1"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/infrastructure/test_repositories_and_redis.py -q
```

Expected: FAIL because `RoomRepository` and `InMemoryTTLStore` do not exist.

- [ ] **Step 3: Extend database schema**

Add these models to `app/infrastructure/db.py` below `EventRecord`:

```python
class RoomRecord(Base):
    __tablename__ = "rooms"

    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ruleset: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ParticipantRecord(Base):
    __tablename__ = "participants"

    participant_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    player_id: Mapped[str] = mapped_column(String(120), index=True)
    nickname: Mapped[str] = mapped_column(String(80))
    seat: Mapped[int]
    participant_type: Mapped[str] = mapped_column(String(32))
    token_version: Mapped[int]


class GameRecord(Base):
    __tablename__ = "games"

    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phase: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

If `Mapped[int]` requires an explicit import in the local SQLAlchemy version, keep the annotation as shown; SQLAlchemy 2 infers integer columns from `Mapped[int]`.

- [ ] **Step 4: Add RoomRepository**

Append to `app/infrastructure/repositories.py`:

```python
from app.infrastructure.db import GameRecord, ParticipantRecord, RoomRecord
```

Add this class:

```python
class RoomRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_room(self, room_id: str, ruleset: str, status: str) -> None:
        record = self.session.get(RoomRecord, room_id)
        if record is None:
            self.session.add(RoomRecord(room_id=room_id, ruleset=ruleset, status=status))
            return
        record.ruleset = ruleset
        record.status = status

    def upsert_participant(
        self,
        room_id: str,
        player_id: str,
        nickname: str,
        seat: int,
        participant_type: str,
        token_version: int,
    ) -> None:
        participant_id = f"{room_id}:{player_id}"
        record = self.session.get(ParticipantRecord, participant_id)
        if record is None:
            self.session.add(
                ParticipantRecord(
                    participant_id=participant_id,
                    room_id=room_id,
                    player_id=player_id,
                    nickname=nickname,
                    seat=seat,
                    participant_type=participant_type,
                    token_version=token_version,
                )
            )
            return
        record.nickname = nickname
        record.seat = seat
        record.participant_type = participant_type
        record.token_version = token_version

    def upsert_game(self, room_id: str, phase: str, state: dict) -> None:
        record = self.session.get(GameRecord, room_id)
        if record is None:
            self.session.add(GameRecord(room_id=room_id, phase=phase, state=state))
            return
        record.phase = phase
        record.state = state

    def get_room_bundle(self, room_id: str) -> dict:
        room = self.session.get(RoomRecord, room_id)
        participants = self.session.scalars(
            select(ParticipantRecord).where(ParticipantRecord.room_id == room_id).order_by(ParticipantRecord.seat)
        ).all()
        game = self.session.get(GameRecord, room_id)
        return {
            "room": None if room is None else {"room_id": room.room_id, "ruleset": room.ruleset, "status": room.status},
            "participants": [
                {
                    "player_id": participant.player_id,
                    "nickname": participant.nickname,
                    "seat": participant.seat,
                    "participant_type": participant.participant_type,
                    "token_version": participant.token_version,
                }
                for participant in participants
            ],
            "game": None if game is None else {"phase": game.phase, "state": game.state},
        }
```

- [ ] **Step 5: Add Redis TTL abstraction with in-memory fallback**

Create `app/infrastructure/redis_store.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Entry:
    value: str
    expires_at: float


class InMemoryTTLStore:
    def __init__(self) -> None:
        self._values: dict[str, _Entry] = {}

    def set_once(self, key: str, value: str, ttl_seconds: int) -> bool:
        self._purge_expired()
        if key in self._values:
            return False
        self._values[key] = _Entry(value=value, expires_at=time.time() + ttl_seconds)
        return True

    def get(self, key: str) -> str | None:
        self._purge_expired()
        entry = self._values.get(key)
        return None if entry is None else entry.value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, entry in self._values.items() if entry.expires_at <= now]
        for key in expired:
            self._values.pop(key, None)
```

- [ ] **Step 6: Run repository tests**

Run:

```bash
pytest tests/infrastructure/test_repositories_and_redis.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit durable repository**

Run:

```bash
git add app/infrastructure/db.py app/infrastructure/repositories.py app/infrastructure/redis_store.py tests/infrastructure/test_repositories_and_redis.py
git commit -m "feat: add durable room repository"
```

---

### Task 7: VoiceProvider and LiveKit-First Adapter

**Files:**
- Create: `app/infrastructure/voice.py`
- Test: `tests/infrastructure/test_voice_provider.py`

- [ ] **Step 1: Write failing voice provider tests**

Create `tests/infrastructure/test_voice_provider.py`:

```python
import jwt

from app.infrastructure.voice import LiveKitVoiceProvider, NoopVoiceProvider, VoicePolicy


def test_noop_voice_provider_returns_disabled_token():
    provider = NoopVoiceProvider()

    token = provider.issue_join_token(room_id="ROOM1", player_id="p1", display_name="1号-阿澈", can_publish_audio=False)

    assert token == {"enabled": False, "reason": "voice_not_configured"}


def test_livekit_token_contains_microphone_publish_grant():
    provider = LiveKitVoiceProvider(url="wss://livekit.example", api_key="key", api_secret="secret")

    result = provider.issue_join_token(room_id="ROOM1", player_id="p1", display_name="1号-阿澈", can_publish_audio=True)
    payload = jwt.decode(result["token"], "secret", algorithms=["HS256"])

    assert result["enabled"] is True
    assert result["url"] == "wss://livekit.example"
    assert payload["iss"] == "key"
    assert payload["sub"] == "p1"
    assert payload["video"]["room"] == "avalon-ROOM1"
    assert payload["video"]["canPublish"] is True
    assert payload["video"]["canPublishSources"] == ["microphone"]


def test_voice_policy_maps_to_publish_permission():
    policy = VoicePolicy(policy="muted", can_publish_audio=False)

    assert policy.can_publish_audio is False


def test_livekit_permission_update_payload_disables_audio_publish():
    provider = LiveKitVoiceProvider(url="wss://livekit.example", api_key="key", api_secret="secret")

    payload = provider.permission_update_payload(room_id="ROOM1", player_id="p1", can_publish_audio=False)

    assert payload == {
        "room": "avalon-ROOM1",
        "identity": "p1",
        "permission": {
            "canPublish": False,
            "canSubscribe": True,
            "canPublishData": True,
            "canPublishSources": [],
        },
    }
```

- [ ] **Step 2: Run voice tests to verify failure**

Run:

```bash
pytest tests/infrastructure/test_voice_provider.py -q
```

Expected: FAIL because `app.infrastructure.voice` does not exist.

- [ ] **Step 3: Implement voice providers**

Create `app/infrastructure/voice.py`:

```python
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import jwt


@dataclass(frozen=True)
class VoicePolicy:
    policy: str
    can_publish_audio: bool


class VoiceProvider(Protocol):
    def issue_join_token(self, room_id: str, player_id: str, display_name: str, can_publish_audio: bool) -> dict:
        raise NotImplementedError

    def permission_update_payload(self, room_id: str, player_id: str, can_publish_audio: bool) -> dict:
        raise NotImplementedError


class NoopVoiceProvider:
    def issue_join_token(self, room_id: str, player_id: str, display_name: str, can_publish_audio: bool) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}

    def permission_update_payload(self, room_id: str, player_id: str, can_publish_audio: bool) -> dict:
        return {"enabled": False, "reason": "voice_not_configured"}


class LiveKitVoiceProvider:
    def __init__(self, url: str, api_key: str, api_secret: str) -> None:
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret

    def issue_join_token(self, room_id: str, player_id: str, display_name: str, can_publish_audio: bool) -> dict:
        now = int(time.time())
        livekit_room = f"avalon-{room_id}"
        payload = {
            "iss": self.api_key,
            "sub": player_id,
            "name": display_name,
            "nbf": now - 5,
            "exp": now + 60 * 60,
            "metadata": json.dumps({"avalon_room": room_id, "player_id": player_id}, ensure_ascii=False),
            "video": {
                "room": livekit_room,
                "roomJoin": True,
                "canPublish": can_publish_audio,
                "canSubscribe": True,
                "canPublishData": True,
                "canPublishSources": ["microphone"] if can_publish_audio else [],
            },
        }
        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return {"enabled": True, "url": self.url, "token": token, "room": livekit_room, "identity": player_id}

    def permission_update_payload(self, room_id: str, player_id: str, can_publish_audio: bool) -> dict:
        return {
            "room": f"avalon-{room_id}",
            "identity": player_id,
            "permission": {
                "canPublish": can_publish_audio,
                "canSubscribe": True,
                "canPublishData": True,
                "canPublishSources": ["microphone"] if can_publish_audio else [],
            },
        }
```

- [ ] **Step 4: Run voice tests**

Run:

```bash
pytest tests/infrastructure/test_voice_provider.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit voice provider**

Run:

```bash
git add app/infrastructure/voice.py tests/infrastructure/test_voice_provider.py
git commit -m "feat: add voice provider abstraction"
```

---

### Task 8: HTTP Routes for Rooms and LiveKit Token

**Files:**
- Modify: `app/main.py`
- Modify: `app/api/http.py`
- Modify: `app/config.py`
- Test: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Extend HTTP tests**

Append to `tests/api/test_health_and_rooms.py`:

```python

def test_create_room_join_returns_session_token():
    client = TestClient(create_app())

    response = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"})

    assert response.status_code == 200
    data = response.json()
    assert data["room_id"] == "ROOM1"
    assert data["player_id"].startswith("p_")
    assert data["session_token"]
    assert data["snapshot"]["room"]["room_id"] == "ROOM1"


def test_livekit_token_returns_disabled_when_voice_not_configured():
    client = TestClient(create_app())
    join = client.post("/api/rooms/ROOM1/join", json={"nickname": "阿澈"}).json()

    response = client.post(
        "/api/rooms/ROOM1/voice-token",
        json={"session_token": join["session_token"]},
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "reason": "voice_not_configured"}
```

- [ ] **Step 2: Run HTTP tests to verify failure**

Run:

```bash
pytest tests/api/test_health_and_rooms.py -q
```

Expected: existing health test passes and new route tests fail with `404`.

- [ ] **Step 3: Wire services into app state**

Modify `app/main.py`:

```python
from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService
from app.infrastructure.voice import LiveKitVoiceProvider, NoopVoiceProvider
```

Update `create_app` before `include_router`:

```python
    session_service = RoomSessionService(secret=app.state.settings.session_secret)
    room_service = RoomService(session_service=session_service)
    app.state.session_service = session_service
    app.state.room_service = room_service
    app.state.command_gateway = CommandGateway(room_service=room_service, session_service=session_service)
    if app.state.settings.voice_status == "configured":
        app.state.voice_provider = LiveKitVoiceProvider(
            url=app.state.settings.livekit_url or "",
            api_key=app.state.settings.livekit_api_key or "",
            api_secret=app.state.settings.livekit_api_secret or "",
        )
    else:
        app.state.voice_provider = NoopVoiceProvider()
```

- [ ] **Step 4: Add HTTP room routes**

Modify `app/api/http.py` imports:

```python
from pydantic import BaseModel, Field

from app.application.sessions import SessionError
from app.domain.types import CommandError
```

Add request models and routes:

```python
class JoinRoomRequest(BaseModel):
    nickname: str = Field(default="玩家", min_length=1, max_length=24)


class VoiceTokenRequest(BaseModel):
    session_token: str = Field(min_length=1)


@router.post("/api/rooms/{room_id}/join")
async def join_room(room_id: str, body: JoinRoomRequest, request: Request) -> dict:
    try:
        result = request.app.state.command_gateway.handle_join(room_id=room_id, nickname=body.nickname)
    except CommandError as exc:
        return {"error": str(exc)}
    return {
        "room_id": result.room_id,
        "player_id": result.player_id,
        "session_token": result.session_token,
        "snapshot": result.snapshot,
    }


@router.post("/api/rooms/{room_id}/voice-token")
async def voice_token(room_id: str, body: VoiceTokenRequest, request: Request) -> dict:
    try:
        claims = request.app.state.session_service.verify(body.session_token, expected_room_id=room_id)
    except SessionError as exc:
        return {"enabled": False, "reason": str(exc)}
    room = request.app.state.room_service.get_or_create_room(room_id)
    participant = room.participants[claims.player_id]
    display_name = f"{participant.seat}号-{participant.nickname}"
    can_publish_audio = True
    if room.game:
        from app.application.snapshots import SnapshotProjector

        snapshot = SnapshotProjector().for_player(room.game, claims.player_id, room.host_id, room.room_id)
        can_publish_audio = bool(snapshot["voice_state"]["can_publish_audio"])
    return request.app.state.voice_provider.issue_join_token(
        room_id=room.room_id,
        player_id=claims.player_id,
        display_name=display_name,
        can_publish_audio=can_publish_audio,
    )
```

- [ ] **Step 5: Run HTTP tests**

Run:

```bash
pytest tests/api/test_health_and_rooms.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit HTTP routes**

Run:

```bash
git add app/main.py app/api/http.py app/config.py tests/api/test_health_and_rooms.py
git commit -m "feat: add v2 room http routes"
```

---

### Task 9: WebSocket Realtime Gateway

**Files:**
- Create: `app/realtime/__init__.py`
- Create: `app/realtime/manager.py`
- Create: `app/api/ws.py`
- Modify: `app/main.py`
- Test: `tests/api/test_ws_flow.py`

- [ ] **Step 1: Write WebSocket tests**

Create `tests/api/test_ws_flow.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_ws_requires_session_token():
    client = TestClient(create_app())

    with client.websocket_connect("/ws/ROOM1") as websocket:
        websocket.send_json({"type": "hello"})
        message = websocket.receive_json()

    assert message == {"type": "error", "message": "第一条消息必须包含 session_token。"}


def test_ws_join_and_start_game_broadcasts_snapshot():
    client = TestClient(create_app())
    joins = [client.post("/api/rooms/ROOM1/join", json={"nickname": f"玩家{i}"}).json() for i in range(1, 6)]

    with client.websocket_connect("/ws/ROOM1") as websocket:
        websocket.send_json({"type": "hello", "session_token": joins[0]["session_token"]})
        hello = websocket.receive_json()
        assert hello["type"] == "state"
        assert hello["snapshot"]["room"]["room_id"] == "ROOM1"

        websocket.send_json({"type": "command", "request_id": "start-1", "command": {"type": "start_game"}})
        state = websocket.receive_json()

    assert state["type"] == "state"
    assert state["snapshot"]["phase_summary"]["phase"] == "TEAM_PROPOSAL"
```

- [ ] **Step 2: Run WebSocket tests to verify failure**

Run:

```bash
pytest tests/api/test_ws_flow.py -q
```

Expected: FAIL with `WebSocketDisconnect` or `404` because `/ws/{room_id}` does not exist.

- [ ] **Step 3: Add realtime manager**

Create `app/realtime/__init__.py`:

```python
"""Realtime WebSocket utilities."""
```

Create `app/realtime/manager.py`:

```python
from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, player_id: str, websocket: WebSocket) -> None:
        self.connections.setdefault(room_id, {})[player_id] = websocket

    def disconnect(self, room_id: str, player_id: str) -> None:
        self.connections.get(room_id, {}).pop(player_id, None)

    async def send_to_player(self, room_id: str, player_id: str, payload: dict) -> None:
        websocket = self.connections.get(room_id, {}).get(player_id)
        if websocket:
            await websocket.send_json(payload)
```

- [ ] **Step 4: Add WebSocket endpoint**

Create `app/api/ws.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.application.sessions import SessionError
from app.domain.types import CommandError

router = APIRouter()


@router.websocket("/ws/{room_id}")
async def room_ws(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    player_id: str | None = None
    try:
        first = await websocket.receive_json()
        session_token = first.get("session_token")
        if not session_token:
            await websocket.send_json({"type": "error", "message": "第一条消息必须包含 session_token。"})
            return
        try:
            claims = websocket.app.state.session_service.verify(session_token, expected_room_id=room_id)
        except SessionError as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            return
        player_id = claims.player_id
        room = websocket.app.state.room_service.get_or_create_room(room_id)
        await websocket.app.state.connection_manager.connect(room.room_id, player_id, websocket)
        snapshot = websocket.app.state.room_service.lobby_snapshot(room, player_id) if not room.game else websocket.app.state.command_gateway._game_snapshot(room, player_id)
        await websocket.send_json({"type": "state", "snapshot": snapshot})

        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if message.get("type") != "command":
                await websocket.send_json({"type": "error", "message": "未知 WebSocket 消息类型。"})
                continue
            try:
                result = websocket.app.state.command_gateway.handle_command(
                    room_id=room_id,
                    session_token=session_token,
                    command=message.get("command") or {},
                    request_id=message.get("request_id") or "",
                )
            except CommandError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue
            await websocket.send_json({"type": "state", "snapshot": result.snapshot})
    except WebSocketDisconnect:
        pass
    finally:
        if player_id:
            room_key = room_id.strip().upper()
            websocket.app.state.connection_manager.disconnect(room_key, player_id)
```

- [ ] **Step 5: Wire WebSocket router and manager**

Modify `app/main.py` imports:

```python
from app.api.ws import router as ws_router
from app.realtime.manager import ConnectionManager
```

Add before routers:

```python
    app.state.connection_manager = ConnectionManager()
```

Add after `include_router(http_router)`:

```python
    app.include_router(ws_router)
```

- [ ] **Step 6: Run WebSocket tests**

Run:

```bash
pytest tests/api/test_ws_flow.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit realtime gateway**

Run:

```bash
git add app/realtime app/api/ws.py app/main.py tests/api/test_ws_flow.py
git commit -m "feat: add v2 websocket gateway"
```

---

### Task 10: Frontend Adapter for Structured v2 Snapshots

**Files:**
- Modify: `static/index.html`
- Modify: `static/main.js`
- Modify: `static/style.css`
- Test: `tests/api/test_health_and_rooms.py`

- [ ] **Step 1: Add static shell test**

Append to `tests/api/test_health_and_rooms.py`:

```python

def test_index_contains_v2_snapshot_mount_points():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="roomInput"' in html
    assert 'id="phaseSummary"' in html
    assert 'id="playersList"' in html
    assert 'id="primaryAction"' in html
    assert 'id="privatePanel"' in html
    assert 'id="voiceState"' in html
```

- [ ] **Step 2: Run static shell test to verify failure**

Run:

```bash
pytest tests/api/test_health_and_rooms.py::test_index_contains_v2_snapshot_mount_points -q
```

Expected: FAIL because the minimal shell lacks v2 mount points.

- [ ] **Step 3: Replace static HTML with existing-shape v2 shell**

Update `static/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Avalon Online v2</title>
    <link rel="stylesheet" href="/static/style.css">
  </head>
  <body>
    <main class="layout">
      <section id="joinPanel" class="panel join-panel">
        <p class="eyebrow">Avalon Online v2</p>
        <h1>进入阿瓦隆圆桌</h1>
        <label>房间号 <input id="roomInput" value="ROOM1" maxlength="24"></label>
        <label>昵称 <input id="nameInput" value="玩家" maxlength="24"></label>
        <button id="joinButton">加入房间</button>
      </section>

      <section id="gamePanel" class="panel game-panel hidden">
        <header class="topbar">
          <div>
            <p class="eyebrow" id="roomLabel">ROOM</p>
            <h2 id="phaseSummary">等待状态</h2>
          </div>
          <div id="voiceState" class="pill">语音未连接</div>
        </header>

        <section class="board">
          <div>
            <h3>圆桌席位</h3>
            <div id="playersList" class="players-list"></div>
          </div>
          <div>
            <h3>当前操作</h3>
            <div id="primaryAction" class="action-panel">等待服务端快照</div>
          </div>
        </section>

        <section class="board">
          <div>
            <h3>身份牌</h3>
            <div id="privatePanel" class="private-panel">开局后显示你的身份</div>
          </div>
          <div>
            <h3>公开历史</h3>
            <div id="publicTimeline" class="timeline">暂无历史</div>
          </div>
        </section>
      </section>
    </main>
    <script src="/static/main.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Replace static JS with v2 join and render adapter**

Update `static/main.js`:

```javascript
let currentRoomId = "";
let currentSessionToken = "";
let ws = null;

const $ = (id) => document.getElementById(id);

$("joinButton").addEventListener("click", async () => {
  const roomId = $("roomInput").value.trim().toUpperCase();
  const nickname = $("nameInput").value.trim() || "玩家";
  const response = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nickname }),
  });
  const data = await response.json();
  currentRoomId = data.room_id;
  currentSessionToken = data.session_token;
  renderSnapshot(data.snapshot);
  $("joinPanel").classList.add("hidden");
  $("gamePanel").classList.remove("hidden");
  connectWebSocket();
});

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/ws/${encodeURIComponent(currentRoomId)}`);
  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({ type: "hello", session_token: currentSessionToken }));
  });
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") renderSnapshot(message.snapshot);
    if (message.type === "error") $("primaryAction").textContent = message.message;
  });
}

function sendCommand(command) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: "command",
    request_id: crypto.randomUUID(),
    command,
  }));
}

function renderSnapshot(snapshot) {
  $("roomLabel").textContent = snapshot.room?.room_id || "ROOM";
  $("phaseSummary").textContent = snapshot.phase_summary?.phase || "LOBBY";
  $("voiceState").textContent = snapshot.voice_state?.can_publish_audio ? "你可以发言" : "你现在只能听";
  $("playersList").innerHTML = (snapshot.players || []).map((player) => `
    <div class="player-card">
      <strong>${escapeHtml(player.display || player.nickname || player.player_id)}</strong>
      ${player.is_leader ? "<span>队长</span>" : ""}
      ${player.is_host ? "<span>房主</span>" : ""}
    </div>
  `).join("");
  renderAction(snapshot.my_action || { type: "wait" });
  renderPrivate(snapshot.private_panel || {});
}

function renderAction(action) {
  if (action.type === "select_team") {
    $("primaryAction").innerHTML = `<button id="startPlaceholder">请选择 ${action.required_team_size} 名玩家出征</button>`;
    return;
  }
  if (action.type === "team_vote") {
    $("primaryAction").innerHTML = `<button id="approveButton">赞成</button><button id="rejectButton">反对</button>`;
    $("approveButton").addEventListener("click", () => sendCommand({ type: "team_vote", vote: "Approve" }));
    $("rejectButton").addEventListener("click", () => sendCommand({ type: "team_vote", vote: "Reject" }));
    return;
  }
  if (action.type === "mission_vote") {
    $("primaryAction").innerHTML = `<button id="successButton">任务成功</button><button id="failButton">任务失败</button>`;
    $("successButton").addEventListener("click", () => sendCommand({ type: "mission_vote", vote: "Success" }));
    $("failButton").addEventListener("click", () => sendCommand({ type: "mission_vote", vote: "Fail" }));
    return;
  }
  $("primaryAction").textContent = "等待其他玩家操作";
}

function renderPrivate(privatePanel) {
  if (!privatePanel.role) {
    $("privatePanel").textContent = "开局后显示你的身份";
    return;
  }
  const visible = (privatePanel.visible_players || []).map((player) => player.display).join("、") || "无额外视野";
  $("privatePanel").innerHTML = `<strong>${escapeHtml(privatePanel.role)}</strong><p>${escapeHtml(privatePanel.side)}</p><p>${escapeHtml(visible)}</p>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
```

- [ ] **Step 5: Replace CSS**

Update `static/style.css`:

```css
html {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  min-height: 100vh;
  background: #101827;
  color: #f8fafc;
}

button,
input {
  font: inherit;
}

button {
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  background: #38bdf8;
  color: #082f49;
  font-weight: 700;
}

input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  margin-top: 6px;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 10px;
  background: #0f172a;
  color: #f8fafc;
}

label {
  display: block;
  margin: 14px 0;
}

.layout {
  width: min(1040px, 100%);
  margin: 0 auto;
  padding: 20px;
  box-sizing: border-box;
}

.panel {
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  padding: 18px;
  background: rgba(15, 23, 42, 0.92);
}

.hidden {
  display: none;
}

.eyebrow {
  margin: 0 0 6px;
  color: #93c5fd;
  font-size: 0.78rem;
  text-transform: uppercase;
}

.topbar,
.board {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-items: start;
}

.pill,
.player-card,
.action-panel,
.private-panel,
.timeline {
  border-radius: 8px;
  padding: 12px;
  background: #172033;
}

.players-list {
  display: grid;
  gap: 8px;
}

@media (max-width: 760px) {
  .topbar,
  .board {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run static shell tests**

Run:

```bash
pytest tests/api/test_health_and_rooms.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit frontend adapter**

Run:

```bash
git add static tests/api/test_health_and_rooms.py
git commit -m "feat: add structured snapshot frontend adapter"
```

---

### Task 11: Documentation, Deployment, and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `CHANGELOG.md`
- Modify: `render.yaml`

- [ ] **Step 1: Update README v2 startup**

In `README.md`, replace old feature status and startup wording with:

```markdown
# Avalon Online v2

Avalon Online v2 is a web-based Avalon game focused on authoritative server rules, room-scoped guest sessions, realtime WebSocket snapshots, LiveKit-first voice control, event logs, and post-game replay.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

## Runtime Services

- `DATABASE_URL`: managed Postgres for long-term rooms, games, events, and replay data.
- `REDIS_URL`: optional short-term cache for online state, rate limits, session TTL, and idempotency.
- `SESSION_SECRET`: required outside local development for room session token signing.
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`: optional voice provider configuration.
```

- [ ] **Step 2: Update architecture doc**

In `docs/ARCHITECTURE.md`, replace old module map with:

```markdown
# Avalon Online v2 Architecture

The v2 architecture is an authoritative modular monolith.

```text
Client intent
  -> Command Gateway
  -> Game Core
  -> Event Log
  -> Snapshot Projector
  -> Realtime Gateway
  -> Per-player WebSocket state
```

Core modules:

- `app/domain`: pure Avalon rules and phase state.
- `app/application`: sessions, rooms, commands, snapshots, events.
- `app/infrastructure`: database, repositories, Redis/cache, voice providers.
- `app/realtime`: WebSocket connection management.
- `app/api`: HTTP and WebSocket route entrypoints.
- `static`: first-phase UI shell that consumes structured v2 snapshots.
```

- [ ] **Step 3: Update deployment doc**

In `docs/DEPLOYMENT.md`, include:

```markdown
## v2 Services

Deploy the app service with:

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

Use managed Postgres for long-term data. Keep Postgres in the same region as the app service when possible. Use Redis for short-term realtime state if available. Keep LiveKit and database secrets in server environment variables only.
```

- [ ] **Step 4: Update changelog**

Under `## Unreleased`, add:

```markdown
### Changed

- Rebuild current branch toward Avalon Online v2 modular monolith architecture.
- Add authoritative room sessions, structured snapshots, event log, and LiveKit-first voice provider plan.
```

- [ ] **Step 5: Verify Render command still imports app**

Keep `render.yaml` start command:

```yaml
startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
```

Run:

```bash
python -c "from server import app; print(app.title)"
```

Expected:

```text
Avalon Online v2
```

- [ ] **Step 6: Run full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Run local smoke server**

Run:

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

Expected: server starts and logs `Uvicorn running on http://127.0.0.1:8000`. Stop with `Ctrl+C` after checking `/health`.

- [ ] **Step 8: Commit documentation and deployment updates**

Run:

```bash
git add README.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md CHANGELOG.md render.yaml
git commit -m "docs: update v2 deployment and architecture docs"
```

---

## Self-Review Checklist

- Spec coverage:
  - Current branch clean-slate rewrite: Task 1.
  - Modular monolith skeleton: Tasks 1-3.
  - Friend-flexible Game Core: Task 2.
  - Room session token: Task 3.
  - Command validation and idempotency seed: Task 3.
  - Per-player structured snapshots: Task 4.
  - Event log and replay foundation: Task 5.
  - Durable room/game persistence and Redis TTL fallback: Task 6.
  - VoiceProvider abstraction and permission mapping: Task 7.
  - HTTP and WebSocket routes: Tasks 8-9.
  - Existing UI shape adapted to structured snapshots: Task 10.
  - Deployment and docs: Task 11.

- Deferred product work beyond this first playable core:
  - Account login, friend lists, public matchmaking, host/spectator UI, standard ruleset UI, and final product UI/UX.
