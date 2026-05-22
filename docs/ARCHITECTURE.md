# Avalon Online v2 架构

本文档描述 Avalon Online v2 当前的 authoritative modular monolith 架构。目标是让后续协作者知道规则、房间会话、实时同步、快照裁剪和部署入口分别在哪里，避免把游戏裁定散落到前端或临时 API 里。

## 总览

```text
Browser
  static/index.html
  static/main.js
  static/style.css
      |
      | HTTP / WebSocket
      v
app/api
  http.py
  ws.py
      |
      | Client intent
      v
app/application/commands.py
  CommandGateway
      |
      v
app/application/rooms.py + app/domain/game.py
  RoomService / AvalonGame
      |
      v
app/application/snapshots.py
  SnapshotProjector
      |
      | per-player state
      v
Client render
```

`server.py` 只导出 `app.main:app`，保持 Render start command 与旧入口兼容。真正的 FastAPI app 创建和依赖装配在 `app/main.py`。

## 核心数据流

1. Client intent 从浏览器发出，可以是 HTTP command，也可以是 WebSocket command。
2. `app/api/http.py` 或 `app/api/ws.py` 校验请求形态，把命令交给 `CommandGateway`。
3. `CommandGateway` 校验 room session、request id 幂等信息和 actor 身份。
4. `RoomService` 维护房间、参与者、房主、ready/start/reset 等应用状态。
5. `AvalonGame` 作为 domain core 裁定身份、阶段、队伍、投票、任务和胜负规则。
6. `SnapshotProjector` 把 authoritative state 投影成指定玩家可见的 per-player snapshot。
7. API 返回当前 actor snapshot，WebSocket 通过 `ConnectionManager` 广播各自裁剪后的 state。

当前 `CommandGateway` 已接入 join、ready、start、reset、select_team、team_vote、mission_vote、continue_after_result、assassinate、send_chat 和大厅治理命令。HTTP 与 WebSocket 仍共享同一路径，避免两套规则裁定。

## 模块地图

```text
server.py
  Re-export app.main:app for uvicorn and Render.

app/main.py
  FastAPI app factory.
  Mount static files.
  Wire Settings, RoomSessionService, RoomService, CommandGateway,
  ConnectionManager, and voice provider.

app/config.py
  Read DATABASE_URL, REDIS_URL, SESSION_SECRET,
  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET.

app/domain/
  game.py       AvalonGame authoritative rule state.
  rulesets.py   Player counts, roles, mission sizes.
  types.py      Role, Phase, ruleset, command errors.

app/application/
  sessions.py   Signed room session tokens.
  rooms.py      Room lifecycle, participants, host, ready/start/reset.
  commands.py   CommandGateway and command result projection.
  snapshots.py  Per-player SnapshotProjector.
  events.py     App event model.

app/infrastructure/
  db.py            SQLAlchemy models and engine helpers.
  repositories.py  RoomRepository and EventRepository foundation.
  redis_store.py   Redis client/store foundation.
  voice.py         Noop and LiveKit voice token providers.

app/api/
  http.py       /health, /, room join, room command, voice-token.
  ws.py         Room WebSocket command and state channel.

app/realtime/
  manager.py    WebSocket connection registration and per-room broadcast.

static/
  First-phase browser UI for structured snapshots.
```

## Authoritative State

服务端是权威状态源。前端只能表达玩家意图和渲染快照，不应该自行裁定：

- 谁是队长。
- 当前阶段能否发言、选队、投票或刺杀。
- 某票是否有效。
- 任务是否成功。
- 哪些身份或投票对某个玩家可见。

这些规则应保留在 `app/domain/game.py`、`app/application/rooms.py` 和 `SnapshotProjector` 中。

## 隐私边界

`AvalonGame` 可以保留完整 roles、team votes、mission votes、current team 和胜负状态。它是后端内存中的 authoritative model，不直接暴露给浏览器。

`SnapshotProjector.for_player(...)` 是隐私裁剪边界：

- 每个玩家只收到自己的 `private_panel.role` 和按角色规则可见的玩家。
- 公共玩家列表只包含展示名、座位顺序、leader 等公共信息。
- `my_action` 只描述当前玩家自己的下一步动作。
- 投票和任务历史继续在 projector 层区分 public result、private vote、hidden vote。

新增 gameplay completion 字段包括 `public_timeline`、`mission_result`、`reveal_roles`、`speaker_state`、`online_state` 和 `chat_history`。其中 `reveal_roles` 仅在 `GAME_OVER` 返回；`TEAM_VOTE` 与 `MISSION_VOTE` 阶段统一禁言禁麦。

如果 UI 需要新增展示字段，优先在 snapshot contract 中显式建模，不要在前端用字符串或 DOM 状态硬猜。

## HTTP 和 WebSocket

当前 HTTP 入口：

- `GET /`：返回 `static/index.html`。
- `GET /health`：返回 service、database、redis、voice 状态。
- `POST /api/rooms/{room_id}/join`：加入房间并签发 session token。
- `POST /api/rooms/{room_id}/command`：提交 ready/start/reset、完整游戏动作、聊天和大厅治理命令。
- `POST /api/rooms/{room_id}/voice-token`：按当前 voice provider 返回 token 或 disabled 状态。

当前 WebSocket 入口：

- `/ws/{room_id}`：建立实时通道，接收带 session 的客户端命令，广播 per-player state。

WebSocket 和 HTTP 应共享 `CommandGateway`，避免两套规则路径。

## 配置和基础设施

`Settings` 读取：

```text
DATABASE_URL
REDIS_URL
SESSION_SECRET
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
```

当前基础设施状态：

- Postgres repository/event log 代码已存在，适合后续接入生产命令流持久化。
- Redis store 基础代码已存在，适合后续做房间状态缓存或恢复。
- LiveKit 三个变量完整时使用 `LiveKitVoiceProvider`；否则使用 `NoopVoiceProvider`。
- `SESSION_SECRET` 未配置时会使用开发默认值，线上必须显式设置。

## Deferred Items

这些内容不要在产品说明或部署说明里写成已完成：

- CommandGateway 到 repository/event log 的生产级事务持久化。
- Redis-backed 多实例房间恢复闭环。
- 多人浏览器端到端自动化验收。
- 更完整的语音权限审计、异常恢复和跨实例在线状态恢复。

## 修改建议

- 改规则：优先修改 `app/domain/`，并补充测试。
- 改房间、session、命令：优先修改 `app/application/`，保持 HTTP/WS 共用路径。
- 改快照或 UI 状态：先改 `SnapshotProjector` contract，再改 `static/` 渲染。
- 改部署或环境变量：同步更新 `README.md`、`docs/DEPLOYMENT.md` 和 `/health` 预期。
