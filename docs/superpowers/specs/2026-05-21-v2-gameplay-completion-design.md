# Avalon Online v2 Gameplay Completion Design

日期：2026-05-21  
目标分支：`codex/avalon-work`  
来源：`docs/MISSING_GAMEPLAY_FEATURES.md`

## 1. 背景与目标

当前 v2 已经完成房间加入、session token、WebSocket 鉴权、准备、开局、重置、私有身份快照和旧版圆桌 UI 壳恢复。规则核心 `AvalonGame` 已经具备选队、组队投票、任务投票、任务结果推进、刺杀和胜负判断，但这些动作尚未接入 `CommandGateway`、快照事件投影和前端真实操作入口。

本设计的目标是补齐“朋友局能完整打一局”的闭环，并把 P1 中最影响真实线上体验的文字、公屏、语音、在线状态、房主治理和私人标记接到同一套服务端状态契约上。

成功标准：

- 5-10 名玩家可以从加入房间一路完成开局、身份确认、队长选队、组队投票、任务投票、任务复盘、刺杀和终局身份公开。
- 所有规则裁定仍由服务端执行，前端只提交玩家意图。
- 公共历史能解释局面变化，但不泄漏个人组队票、秘密任务票提交者、非终局身份表或夜间可见信息。
- 文字和语音统一采用阶段自动控场，不在前端各自硬猜权限。
- P1 功能以最小成熟体验交付，不把本轮变成完整账号系统、主持人后台或最终视觉重设计。

## 2. 范围

### 本轮交付

- P0 第 1-7 项：完整一局规则闭环。
- P1 第 8-12 项：文字公屏、LiveKit 客户端接入、阶段自动控场、在线状态、基础房主治理、私人标记。
- 自动化测试覆盖规则、命令、快照隐私、WebSocket 广播和关键前端挂载点。
- 必要文档更新，尤其是 `docs/MISSING_GAMEPLAY_FEATURES.md` 完成状态和架构边界。

### 本轮不交付

- 账号系统、好友、战绩和公开大厅。
- 标准阿瓦隆规则集和自定义角色包 UI。
- 房主手动发言队列、主持人模式、观战者模式。
- 完整移动端视觉重设计。
- 多实例 Redis 恢复闭环和生产级事件持久化事务。

## 3. 已确认决策

- 规则模式继续使用 `friend_flexible`。在该模式下，所有出征队员都可以提交 `Success` 或 `Fail` 任务票。
- 任务结果复盘后的“进入下一轮”第一版由房主推进。
- 组队投票公开“队伍是否通过”和票数摘要，不公开每个人投了什么。
- 任务投票公开“成功/失败、失败票数量、比分”，不公开谁提交了失败票。
- `reveal_roles` 只在 `GAME_OVER` 阶段返回。
- 文字公屏和语音使用同一套阶段自动控场策略。

## 4. 方案比较

### 推荐方案：P0 闭环 + P1 最小成熟体验一次设计，分任务实施

这套方案先把规则动作、事件投影和前端操作接通，再接文字、语音、在线状态和治理入口。优点是实现时可以按功能逐个提交，但数据契约一次设计，避免 P0 刚做完又被 P1 推翻。缺点是 implementation plan 会比只做 P0 更长，需要清楚拆任务。

### 备选方案：只做 P0

只接选队、投票、任务、刺杀、历史和终局身份。优点是最快达成“能完整打一局”；缺点是朋友局真实体验仍然卡在灰置聊天、灰置语音和弱在线反馈，用户在手机上会觉得还不像能开局使用。

### 备选方案：先做 P1 社交体验

先把语音、聊天、在线状态和治理补齐，再回到规则闭环。优点是界面会更像产品；缺点是核心规则仍无法完成一局，不符合 `MISSING_GAMEPLAY_FEATURES.md` 的 P0 优先级。

结论：采用推荐方案。实现计划中仍应按“P0 闭环优先，P1 紧随其后”的顺序拆小步，确保每组改动都可测试。

## 5. 总体架构

继续沿用 v2 authoritative modular monolith：

```text
Client intent
  -> HTTP / WebSocket command validation
  -> CommandGateway session and idempotency validation
  -> RoomService / AvalonGame authoritative mutation
  -> AppEvent append
  -> SnapshotProjector per-player projection
  -> ConnectionManager per-player broadcast
  -> Frontend render from snapshot
```

关键原则：

- `AvalonGame` 只负责游戏规则，不依赖 WebSocket、HTML、LiveKit 或 DOM。
- `CommandGateway` 是应用层命令入口，HTTP 和 WebSocket 共用它。
- `SnapshotProjector` 是隐私边界，新增字段必须从这里显式投影。
- 前端按钮和弹层只表达意图，不能自行裁定阶段、权限或胜负。

## 6. 快照契约

当前快照已包含：

- `room`
- `you`
- `phase_summary`
- `players`
- `private_panel`
- `my_action`
- `voice_state`
- `public_timeline`

本轮新增或稳定以下字段：

```text
phase_summary.current_team
phase_summary.team_vote_summary
phase_summary.mission_result
phase_summary.winner
my_action.type
my_action.required_team_size
my_action.can_submit_fail
voice_state.can_publish_audio
voice_state.publish_policy
speaker_state.mode
speaker_state.can_send_text
online_state.players
public_timeline
chat_history
reveal_roles
```

字段语义：

- `team_vote_summary` 只在组队投票完成后进入公开历史，包含通过/否决、赞成数、反对数。
- `mission_result` 只在任务票结算后可见，包含成功/失败、失败票数量、比分。
- `speaker_state.mode` 第一版为 `open` 或 `muted`，由阶段自动控场决定。
- `speaker_state.can_send_text` 与文字公屏输入框绑定。
- `online_state.players` 包含每位玩家是否在线和连接数，不包含 token、连接对象或 IP。
- `chat_history` 保存短期公开聊天，不保存私聊。
- `reveal_roles` 只在 `GAME_OVER` 返回全员身份和阵营，非终局不返回该字段。

## 7. P0 功能设计

### 7.1 队长选择出征队伍

实现条件已具备：`AvalonGame.select_team()` 已存在，快照能标出 `leader_id` 和 `my_action.type = select_team`。

设计：

- `CommandGateway` 新增 `select_team` 命令。
- 命令 payload 为 `{"type": "select_team", "team": ["player_id", ...]}`。
- 应用层校验 `team` 是列表、长度受控、元素是字符串。
- 领域层继续校验阶段、队长、人数、重复玩家和未知玩家。
- 成功后追加 `team_selected` 事件，广播所有玩家进入 `TEAM_VOTE`。
- 前端启用 `teamModal`，按 `required_team_size` 限制选择数量，提交后关闭弹层。

### 7.2 全员组队投票

实现条件已具备：`AvalonGame.submit_team_vote()` 已存在，重复提交和阶段错误由领域层拒绝。

设计：

- `CommandGateway` 新增 `team_vote` 命令。
- 命令 payload 为 `{"type": "team_vote", "vote": "Approve" | "Reject"}`。
- 成功提交单票时广播快照，当前玩家 `my_action` 变为 `wait`。
- 全员投完后，如果通过，进入 `MISSION_VOTE`；如果否决，进入下一队长的 `TEAM_PROPOSAL`。
- 公开历史只记录队伍名单、通过/否决、赞成数和反对数，不记录个人票。

### 7.3 出征队员提交任务票

实现条件已具备：`AvalonGame.submit_mission_vote()` 已存在，当前规则集中 `friend_flexible` 已明确所有出征队员可提交失败票。

设计：

- `CommandGateway` 新增 `mission_vote` 命令。
- 命令 payload 为 `{"type": "mission_vote", "vote": "Success" | "Fail"}`。
- 领域层继续校验只有当前队伍成员可提交、不能重复提交。
- 若未来接入 `standard_avalon`，应用层或领域层应按规则集拒绝好人提交 `Fail`。本轮不启用该规则集。
- 全队提交完成后广播 `mission_result`、比分和下一阶段。
- 公开历史记录任务成功/失败、失败票数量和当前比分，不记录提交者。

### 7.4 任务结果复盘后进入下一轮

实现条件已具备：`AvalonGame.continue_after_mission_result()` 已存在。

设计：

- `CommandGateway` 新增 `continue_after_result` 命令。
- 第一版仅房主可执行。
- 成功后追加 `mission_result_acknowledged` 或 `round_advanced` 事件。
- 领域层推进轮次、队长、队伍人数，并清空当前队伍和投票。
- 前端在 `MISSION_RESULT_DISCUSSION` 展示任务结果摘要和“进入下一轮”按钮，非房主只看到等待提示。

### 7.5 刺客刺杀梅林

实现条件已具备：`AvalonGame.submit_assassination()` 已存在，快照能给刺客 `my_action.type = assassinate`。

设计：

- `CommandGateway` 新增 `assassinate` 命令。
- 命令 payload 为 `{"type": "assassinate", "target_id": "player_id"}`。
- 领域层校验阶段、刺客身份和目标存在。
- 提交后进入 `GAME_OVER`，广播胜利方和 `reveal_roles`。
- 前端启用 `assassinModal`，刺客选择目标后提交；其他玩家只看等待刺客。

### 7.6 公开历史和任务结果事件

实现条件已具备：`Room.events` 和 `AppEvent` 已存在，快照已有 `public_timeline` 预留空字段。

设计：

- 每个成功命令追加一个结构化公开事件。
- `SnapshotProjector` 把 `room.events` 投影为 `public_timeline`。
- 事件摘要由服务端生成或由前端基于稳定 `kind` 字段渲染。第一版建议服务端返回 `summary`，前端只显示。
- 公开事件类型包括：`game_started`、`team_selected`、`team_vote_resolved`、`mission_resolved`、`round_advanced`、`assassination_resolved`、`game_over`。
- 隐私测试必须覆盖：非终局快照不含全员角色表；任务历史不含投票提交者；组队历史不含个人票。

### 7.7 终局身份公开

实现条件已具备：领域层持有完整 `roles`，当前快照投影边界可以按阶段裁剪。

设计：

- `SnapshotProjector` 在 `GAME_OVER` 返回 `reveal_roles`。
- `reveal_roles` 每项包含 `player_id`、`display`、`role`、`side`。
- 非 `GAME_OVER` 阶段不返回 `reveal_roles` 字段。
- 前端在终局当前操作区、信息弹层或历史弹层展示身份公开结果。

## 8. P1 功能设计

### 8.1 文字公屏

实现条件具备：WebSocket、HTTP command 和房间内存状态已存在。

设计：

- `Room` 新增短期 `chat_history`。
- `CommandGateway` 新增 `send_chat` 命令。
- 命令 payload 为 `{"type": "send_chat", "text": "..."}`。
- 服务端裁剪空白、限制长度，第一版建议单条最多 300 字，房间最多保留最近 100 条。
- 是否允许发言由 `speaker_state.can_send_text` 决定。
- 成功后广播所有玩家快照或轻量 chat event。为了保持当前架构简单，第一版可直接广播快照。

### 8.2 语音客户端接入

实现条件部分具备：后端已有 `/voice-token` 和 `VoiceProvider`，前端尚未引入 LiveKit client。

设计：

- 前端点击语音按钮时调用 `/api/rooms/{room_id}/voice-token`。
- 若返回 `enabled: false`，显示“语音未配置”降级状态，不阻断游戏。
- 若返回 LiveKit token，加载 LiveKit client 并加入房间。
- 麦克风发布权限跟随 `voice_state.can_publish_audio`。
- 第一版如果没有服务端主动调用 LiveKit 管理 API 更新已入会权限，前端必须在每次快照更新时根据 `voice_state` 启停本地麦克风发布。
- 扬声器按钮只控制本地订阅音频静音，不改变服务端权限。

### 8.3 阶段自动控场和在线状态

已确认采用阶段自动控场。

策略：

```text
LOBBY                         open
TEAM_PROPOSAL                 open
TEAM_VOTE                     muted
MISSION_VOTE                  muted
MISSION_RESULT_DISCUSSION     open
ASSASSINATION                 open
GAME_OVER                     open
```

含义：

- `open`：允许发送文字，允许发布麦克风。
- `muted`：禁止发送文字，停止或禁止发布麦克风，但仍可听语音和接收系统消息。

在线状态：

- `ConnectionManager` 暴露房间内当前在线玩家集合。
- `SnapshotProjector` 或应用层 snapshot 包装逻辑注入 `online_state`。
- 前端座位卡展示在线/离线状态，断线玩家保留席位。
- 同一玩家多连接时仍视为在线，连接数可用于调试但不需要重点展示。

### 8.4 房主治理操作

实现条件部分具备：房主、席位、session token version 已存在。

第一版范围：

- 大厅阶段踢人。
- 大厅阶段转移房主。
- 玩家主动退出大厅。
- 断线重连继续使用现有 session token，游戏开始后不允许新玩家加入。

设计：

- `kick_player` 仅房主可执行，第一版只允许 `LOBBY`。
- `transfer_host` 仅房主可执行，目标必须是当前房间玩家。
- `leave_room` 第一版只允许 `LOBBY`，离开后重新排座或保留空座需要实现计划阶段根据代码复杂度决定；推荐大厅离开后压缩座位，游戏中断线只标离线不移除。
- 被踢或退出时提高该 participant 的 `token_version` 或移除 participant，使旧 token 失效。

### 8.5 私人标记

实现条件具备：前端已有标记入口，第一版无需服务端同步。

设计：

- 使用 `localStorage` 按 `room_id + player_id + target_player_id` 保存私人标记。
- 标记只对当前浏览器可见，不进入服务端快照。
- 支持 3-4 个快速状态，例如“可信”、“可疑”、“重点观察”、“清除”。
- 座位卡展示自己的标记，不影响游戏规则。

## 9. 前端 UX 原则

本轮不重做整体视觉，但关键操作必须像真正能玩：

- 当前阶段主动作只出现在“当前操作”区域。
- 玩家无法操作时显示原因，而不是只有灰按钮。
- 队长选队弹层要显示已选人数和目标人数。
- 投票/任务票提交后按钮立刻消失或变为等待状态，避免误以为没有提交。
- 任务结果复盘要明确显示本轮结果、失败票数量、当前比分和下一步。
- 终局要明确显示胜利方和全员身份。
- 移动端按钮不能过小，弹层内容不能被底部导航遮挡。

## 10. 错误处理

- 未知命令返回“暂不支持该操作。”
- payload 类型错误返回具体字段错误，例如“team 必须是玩家 ID 列表。”
- 越权命令由服务端拒绝，例如非队长选队、非队员投任务票、非刺客刺杀。
- 重复 request id 沿用现有幂等逻辑。
- 重复投票由领域层拒绝，前端显示服务端错误并重新渲染快照。
- LiveKit 未配置时语音按钮展示降级，不阻断文字和规则流程。
- WebSocket 断开时保留当前快照，并提示刷新或重新进入。

## 11. 测试计划

后端测试：

- `tests/domain/test_game_core.py`：补足完整五轮、任务三成三败、刺杀胜负、任务失败票阈值。
- `tests/application/test_command_gateway.py`：覆盖五个新规则命令、payload 校验、越权、重复提交、房主推进、非终局身份不泄漏。
- `tests/application/test_snapshots.py`：覆盖 `public_timeline`、`reveal_roles`、`speaker_state`、`online_state` 和 `chat_history` 裁剪。
- `tests/api/test_ws_flow.py`：覆盖 WebSocket 下选队、投票、任务、刺杀后按玩家广播。
- `tests/api/test_health_and_rooms.py`：覆盖静态挂载点和 voice token 降级。

前端验证：

- 至少本地手动跑一局 5 人路径。
- 验证浏览器当前房间页能完成选队、投票、任务、继续、刺杀和终局公开。
- 验证 `TEAM_VOTE` 和 `MISSION_VOTE` 阶段文字输入与麦克风不可用。
- 验证 LiveKit 未配置时不影响完整规则闭环。

文档验证：

- 更新 `docs/MISSING_GAMEPLAY_FEATURES.md`，把已完成项从缺失清单移出或标注完成。
- 如快照契约变化明显，更新 `docs/ARCHITECTURE.md`。

## 12. 实施顺序建议

1. P0 命令网关和领域事件：接 `select_team`、`team_vote`、`mission_vote`、`continue_after_result`、`assassinate`。
2. P0 快照投影：补 `public_timeline`、`mission_result`、`reveal_roles`。
3. P0 前端操作：启用队伍选择、组队投票、任务票、继续下一轮、刺杀弹层。
4. P0 验收：用 HTTP/WebSocket 测试和手动本地房间完成一局。
5. P1 文字和阶段控场：补 `speaker_state`、`chat_history`、`send_chat`。
6. P1 在线状态：从连接管理注入 `online_state` 并渲染座位状态。
7. P1 语音客户端：接 `/voice-token` 和 LiveKit 降级状态。
8. P1 房主治理和私人标记：补大厅治理命令、本地标记 UI。
9. 文档收尾：更新缺失清单、架构说明和 changelog。

## 13. 实现条件检查

已具备：

- 领域模型已有完整核心规则方法。
- 快照已经有 `my_action`、`voice_state`、`public_timeline` 预留空字段。
- HTTP 和 WebSocket 已共用 `CommandGateway`。
- 前端已保留 P0/P1 入口，只是当前灰置。
- 测试结构已覆盖 domain、application、api、infrastructure。

需要实现但无需额外决策：

- 命令 payload 校验。
- 公开事件投影。
- 终局身份公开裁剪。
- 前端弹层交互。
- 阶段自动控场。
- 短期聊天记录。
- 在线状态注入。
- LiveKit 客户端降级与接入。
- 大厅房主治理。
- 本地私人标记。

当前没有需要用户继续提供的信息或外部服务配置才能开始实现。LiveKit 未配置时必须保持可降级。
