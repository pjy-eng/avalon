# 项目架构

本文档说明 Avalon Online 当前代码结构、模块职责和关键状态流。它的目标是让协作者知道“想改一个功能时应该从哪里入手”，避免 UI、后端同步和游戏规则互相拧巴。

## 总览

```text
Browser
  static/index.html
  static/main.js
  static/style.css
      |
      | HTTP + WebSocket
      v
server.py
  FastAPI app
  Room / PlayerRecord
  WebSocket message router
  Redis persistence
  LiveKit token endpoint
      |
      | Method calls
      v
avalon_engine.py
  AvalonGame
  Role / Phase / CONFIG
  rules, permissions, snapshots
```

项目采用“后端快照驱动前端”的方式。前端不应该自己推导核心游戏规则，而是根据服务端广播的 `state`、`control_signal`、`permissions` 和 `private_info` 渲染界面和按钮。

## 后端入口：server.py

`server.py` 负责运行服务和管理多人房间。

主要职责：

- 提供首页和静态资源。
- 提供 `/health` 健康检查。
- 提供 `/api/livekit-token`，为语音房签发 LiveKit token。
- 提供 `/ws/{room_id}` WebSocket，用于加入房间、接收玩家操作、广播状态。
- 管理房间、玩家、房主、准备状态、聊天记录、发言状态、断线重连。
- 可选地把房间状态保存到 Redis。

核心对象：

- `PlayerRecord`：玩家 ID、昵称、座位、在线状态。
- `Room`：房间内所有玩家、socket、游戏实例、聊天、准备状态、锁和过期时间。
- `rooms`：当前进程内的房间内存表。

关键流程：

1. 浏览器打开 WebSocket。
2. 第一条消息必须是 `join`。
3. 服务端把玩家加入房间，或恢复已有玩家连接。
4. 玩家后续操作进入 `handle_message()`。
5. 如果是游戏规则操作，服务端调用 `AvalonGame`。
6. 每次状态变更后，服务端执行 `broadcast_state()`，给每个玩家发送定制快照。

## 规则引擎：avalon_engine.py

`avalon_engine.py` 是核心游戏规则状态机。它应该尽量保持纯粹，不直接依赖 WebSocket、Redis、HTML 或浏览器环境。

主要职责：

- 定义 5-10 人角色配置和任务人数。
- 分发身份。
- 管理队长、轮次、当前队伍、比分、失败提案次数。
- 管理游戏阶段。
- 校验玩家操作是否合法。
- 结算组队投票、任务投票和终局刺杀。
- 生成公开快照、权限字段和私密身份信息。

主要枚举：

- `Role`：梅林、派西维尔、忠臣、莫甘娜、刺客、莫德雷德、奥伯伦。
- `Phase`：大厅、讨论、队长选人、组队投票、任务投票、结果复盘、刺杀、游戏结束。

主要公开方法：

- `start()`
- `select_team(leader_id, team)`
- `speaker_finished(player_id, force=False)`
- `finish_free_discussion()`
- `submit_team_vote(player_id, vote)`
- `submit_mission_vote(player_id, vote)`
- `continue_after_mission_result()`
- `submit_assassin_target(assassin_id, target_id)`
- `snapshot(for_player, players_public, host_id)`
- `to_dict()` / `from_dict()`

修改规则时，优先补充 `tests/test_engine.py`，保证规则和阶段流转有自动化验证。

## 前端：static/

前端是原生 HTML/CSS/JavaScript，没有构建步骤。

### index.html

`static/index.html` 是页面骨架，包含：

- 加入房间视图。
- 游戏圆桌视图。
- 顶部房间栏。
- 左右玩家席位。
- 中央法官公告、当前操作、文字公屏。
- 底部标记、信息、历史入口。
- 身份牌 overlay。
- 角色、信息、私人标记、历史、选队、刺杀 modal。

### main.js

`static/main.js` 是前端应用主体。

主要职责：

- 生成和保存本地玩家 ID。
- 连接 WebSocket、心跳、断线重连。
- 发送玩家操作。
- 接收服务端 `state` 快照并调用 `render()`。
- 渲染玩家席位、公告、操作区、聊天、历史、身份牌。
- 管理私人标记的 localStorage。
- 连接 LiveKit 语音房，按服务端权限控制本地麦克风。

当前 `main.js` 较大，后续可以逐步拆分：

```text
static/js/socket.js        WebSocket、心跳、重连
static/js/render-board.js  玩家席位和圆桌渲染
static/js/render-actions.js 当前操作区
static/js/modals.js        身份牌、历史、标记、选队、刺杀
static/js/voice.js         LiveKit 语音
static/js/storage.js       localStorage key 和私人标记
```

拆分前不要大规模重构。每次只在明确功能范围内拆一小块，并保持页面可运行。

### style.css

`static/style.css` 负责视觉样式、身份牌动画、modal、响应式布局。

做 UI 改动时要同步检查：

- 后端 `permissions` 是否能准确表达当前玩家可做什么。
- `control_signal` 是否能准确表达当前阶段、队长、队伍、麦克风和投票状态。
- UI 文案是否和实际规则一致。
- 移动端屏幕是否可用。

## 状态快照契约

服务端广播的 WebSocket 消息主要形态：

```json
{
  "type": "state",
  "room_id": "ROOM1",
  "you": {
    "id": "player-id",
    "name": "玩家",
    "seat": 1,
    "is_host": true
  },
  "state": {
    "current_phase": "LOBBY",
    "control_signal": {},
    "public_announcement": "",
    "players": [],
    "private_info": {},
    "permissions": {},
    "mission_result_history": [],
    "team_vote_history": [],
    "winner": null,
    "error_message": null,
    "reveal_roles": []
  },
  "chat_history": [],
  "server_time": "..."
}
```

前端最依赖的字段：

- `state.current_phase`：当前阶段，用于标题、操作分支、弹窗行为。
- `state.control_signal`：队长、队伍、比分、麦克风、投票状态、当前发言人。
- `state.permissions`：当前玩家能否开始、准备、选队、投票、提交任务、刺杀、聊天、发言。
- `state.private_info`：当前玩家私密身份和夜晚视野。
- `state.reveal_roles`：游戏结束后的身份公开。

## WebSocket 事件

浏览器发送给后端的主要事件：

```text
join
toggle_ready
start_game
select_team
speaker_finished
finish_free_discussion
team_vote
mission_vote
continue_after_result
assassin_target
chat
speaking_state
kick_player
reset_room
ping
client_pong
```

后端发送给浏览器的主要事件：

```text
state
error
kicked
server_ping
pong
```

## 数据持久化

默认本地开发不需要 Redis。此时房间只存在当前 Python 进程里，服务重启后房间会丢失。

设置 `REDIS_URL` 后，`server.py` 会保存：

- 房间 ID。
- 房主 ID。
- 玩家列表。
- 准备状态。
- `AvalonGame` 的可序列化状态。
- 聊天记录。
- `game_seq`。

不保存：

- WebSocket 连接对象。
- 实时语音对象。
- 浏览器 localStorage 中的私人标记。

## 语音架构

语音使用 LiveKit。浏览器向 `/api/livekit-token` 请求 token，后端用 `LIVEKIT_API_SECRET` 签发短期 token。

服务端不转发音频，只负责：

- 校验玩家是否已加入房间。
- 给玩家签发对应 LiveKit room 的 token。
- 在 `control_signal.personal_audio_allowed` 中告诉前端当前玩家是否可以开麦。
- 接收 `speaking_state`，用于在玩家席位上显示发言状态。

## 测试策略

当前已有测试集中在规则引擎：

```bash
pytest -q
```

后续建议按风险补测试：

- 改 `avalon_engine.py`：必须补或更新单元测试。
- 改 `server.py` 的消息处理：补 WebSocket 或房间状态测试。
- 改前端关键流程：至少手动验证大厅、开局、选队、投票、任务、终局、重连。

## 修改边界建议

- 游戏规则问题：从 `avalon_engine.py` 入手。
- 房间同步问题：从 `server.py` 的 `handle_message()`、`broadcast_state()` 入手。
- 玩家看到的按钮和状态错乱：先看 `permissions` 和 `control_signal`，再看 `static/main.js`。
- 页面拥挤、布局混乱：先梳理目标体验，再改 `static/index.html` 和 `static/style.css`。
- 语音问题：先确认 LiveKit 环境变量，再看 `static/main.js` 的语音函数和 `/api/livekit-token`。
