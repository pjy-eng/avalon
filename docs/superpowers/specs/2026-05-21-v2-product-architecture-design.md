# Avalon Online v2 产品级架构设计

日期：2026-05-21  
分支目标：`codex/avalon-work` 作为 v2 重构分支

## 1. 背景与目标

当前项目已经能支撑朋友局原型：FastAPI 服务端、原生前端、WebSocket 房间同步、规则引擎、Redis 可选持久化和 LiveKit 可选语音都已有雏形。但现有实现仍然更像“可跑通原型”，主要风险是：

- 浏览器自行声明 `player_id`，只靠 localStorage 身份重连，存在冒充空间。
- `server.py` 同时承载房间、WebSocket、权限、持久化、LiveKit token 和命令路由，后续难以演化。
- 前端部分状态依赖阶段字符串和公告文案推断，UI 与规则契约容易漂移。
- 语音、在线状态、发言控制是第一阶段核心体验，但目前还没有产品级的语音权限模型和审计边界。
- 游戏运行状态可以广播，但长期复盘、事件审计、安全排查能力不足。

v2 的目标是把 Avalon Online 往成熟游戏产品方向设计：服务端权威裁定、强实时社交体验、清晰模块边界、可审计事件日志、可恢复会话、可扩展数据层和可替换语音供应商。

## 2. 已确认的设计决策

- 产品目标：按成熟游戏产品设计，而不是只满足临时朋友局。
- 设计范围：完整目标架构 + 第一阶段可落地范围。
- 身份体系：阶段式。第一阶段做安全房间会话，长期预留账号体系。
- 技术栈：本设计不绑定具体框架；先定义领域模块、协议和安全边界，实施计划阶段再选栈。
- 运维路线：目标架构按产品级云架构设计，第一阶段用轻量托管方案落地。
- 第一阶段产品重点：强实时社交体验，包括语音、发言控制、在线状态和移动端多人同步；安全底线同步纳入。
- 非玩家角色：第一阶段只支持玩家局；目标架构预留主持人和观战者。
- 规则模式：第一阶段默认朋友局宽松规则，任务票阶段所有出征玩家都可投成功/失败；该模式必须显式写入房间配置和复盘。
- 语音控制：第一阶段做服务端规则自动强控的核心能力，目标架构预留房主/主持人手动控场。
- 数据留存：第一阶段保存运行状态、安全审计和局后复盘；长期预留账号战绩和社交数据。
- 入口体验：第一阶段房间码邀请；长期预留大厅匹配和好友邀请。
- 落地路径：当前重构分支就是 v2 架构分支。旧版可试玩基线由 `main` 和 Git 历史保留，当前分支不需要保留旧实现，也不需要新建 `v2/` 文件夹与旧版并行。
- 前端范围：第一阶段沿用当前界面结构，只做必要微调以适配 v2 状态契约；完整 UI/UX 设计交给后续设计阶段。
- 语音方案：默认 LiveKit，但通过 `VoiceProvider` 抽象隔离，避免绑定单一供应商。
- 长期数据库：使用托管 Postgres，供应商不锁死；应用服务、Postgres、Redis 尽量同区域。

## 3. 总体架构

v2 采用“产品级模块化单体”作为第一阶段架构形态：一个应用服务部署，但内部按领域拆分。这样可以获得清晰边界和可测试性，同时避免第一阶段过早微服务化。

```text
Mobile Web Client
  |
  | HTTPS + WebSocket
  v
Authoritative App Service
  ├── Identity / Session
  ├── Room Lifecycle
  ├── Game Core
  ├── Command Gateway
  ├── Snapshot Projector
  ├── Realtime Gateway
  ├── Voice Control
  ├── Event Log / Replay
  └── Safety / Observability
      |
      ├── Managed Postgres
      ├── Redis or managed cache
      └── VoiceProvider: LiveKit adapter first
```

客户端只发送玩家意图，例如加入房间、准备、投票、选人、发言完毕、请求开麦。客户端不声明“我有权限”，也不参与规则裁定。所有权限、阶段、身份、语音、投票和胜负都由服务端决定。

## 4. 当前分支重写策略

`codex/avalon-work` 是 v2 重构分支。进入实现计划后，可以清空旧业务实现并重建新应用结构，不需要在当前分支保留旧 `server.py`、`avalon_engine.py`、`static/` 的运行路径。

实施前必须满足：

- 确认当前分支和 git 状态。
- 确认旧版可从 `main` 或远端历史恢复。
- 明确删除清单和保留清单。
- 不默认删除仍有价值的治理文档、设计文档、部署说明和 `AGENTS.md`。
- 尽快恢复 v2 可运行骨架，避免长时间处于不可启动状态。

删除旧实现与重建 v2 骨架应作为清晰提交边界，而不是混在零散改动里。

## 5. 核心模块边界

### Identity / Session

职责：

- 创建游客身份。
- 签发房间会话 token。
- 支持安全重连。
- 维护 token 版本、过期、撤销和绑定关系。
- 预留未来账号绑定。

原则：

- 房间码用于定位房间，不等于身份凭据。
- `player_id` 不能由浏览器单方面声明为可信事实。
- 重连必须依赖服务端签发的 room session token。

### Room Lifecycle

职责：

- 创建房间。
- 生成和校验房间码、邀请 token 或房间口令。
- 管理入座、昵称、准备、房主、重置、过期。
- 预留 `participant_type = player | host | spectator`，第一阶段只开放 `player`。

### Game Core

职责：

- 阿瓦隆规则状态机。
- 角色配置、身份分发、夜晚视野。
- 阶段流转、队长、发言顺序、队伍选择。
- 组队票、任务票、刺杀、胜负。
- 规则模式：第一阶段默认 `friend_flexible`。
- 输出权限、阶段摘要、语音策略和可复盘事件。

Game Core 不依赖 WebSocket、Redis、LiveKit、HTML 或浏览器环境。

### Command Gateway

职责：

- 接收客户端命令。
- 校验会话 token、房间、玩家类型、阶段、权限。
- 执行限流和幂等检查。
- 将合法命令传入领域模块。
- 将拒绝、越权和异常写入审计事件。

### Snapshot Projector

职责：

- 把内部状态投影成每个玩家各自可见的结构化快照。
- 严格隔离身份、夜晚视野、私密任务票和个人操作提示。
- 输出旧 UI 适配层可消费的稳定字段。

建议快照结构包括：

```text
phase_summary
my_action
voice_state
private_panel
public_timeline
players
room
errors
```

公告文案只用于氛围和提示，不作为前端判断逻辑来源。

### Realtime Gateway

职责：

- WebSocket 连接管理。
- 心跳、断线、重连、连接替换。
- 命令转发给 Command Gateway。
- 按玩家发送专属快照。
- 推送在线状态、发言状态、错误提示和房间事件。

### Voice Control

职责：

- 根据 Game Core 输出的 `voice_policy` 控制谁能发言。
- 通过 `VoiceProvider` 签发语音 token、更新发布权限、静音或移除参与者。
- 接收语音状态回传，并进入快照和审计日志。

第一阶段默认实现 `LiveKitVoiceProvider`。架构保留 `VoiceProvider` 接口，未来可以替换 Agora、Daily、自托管 WebRTC/SFU 或其他服务。

### Event Log / Replay

职责：

- 记录玩家命令、服务端裁定、安全事件和关键状态变化。
- 生成局后复盘投影。
- 支撑争议排查、bug 定位和未来管理后台。

事件日志不是聊天记录，也不是简单状态 dump；它需要表达“谁在什么时候请求了什么，服务端如何裁定，为什么状态变成这样”。

### Safety / Observability

职责：

- 限流、幂等、防越权。
- 结构化错误、健康检查、配置检查。
- 安全事件审计。
- 预留错误追踪和运营后台。

## 6. 数据流

玩家动作的标准流程：

```text
Client intent
  -> Command Gateway validates session / room / phase / permission / rate limit / idempotency
  -> Game Core adjudicates
  -> Event Log stores command and decision
  -> Snapshot Projector creates per-player snapshots
  -> Realtime Gateway broadcasts authorized snapshots
  -> Voice Control syncs voice permission if needed
```

客户端永远不直接改变服务端状态。即使前端按钮被人为启用，服务端仍会拒绝非法动作并记录审计事件。

## 7. 安全模型

不可信边界：

- 浏览器代码。
- URL 参数。
- localStorage。
- WebSocket 消息。
- 客户端声明的 `player_id`、权限、阶段、麦克风状态。

可信裁定边界：

- 应用服务。
- 托管 Postgres。
- Redis 中由服务端写入的短期状态。
- LiveKit 管理 API，且只通过服务端调用。

第一阶段安全底线：

- 房间会话 token，避免只靠 localStorage `player_id` 冒充重连。
- 服务端权威权限，前端按钮只影响体验。
- 私密快照隔离，玩家只收到自己可见的数据。
- 限流和幂等，防连点、脚本刷消息、重复投票造成状态错乱。
- 审计事件，记录越权请求、token 失效、重复投票、限流、房主踢人、重置、语音权限变化。
- 密钥卫生，数据库、Redis、LiveKit 密钥只在服务端；前端只拿短期 token。

## 8. 游戏规则与语音控场

第一阶段默认规则模式：`friend_flexible`。

规则含义：

- 组队票：全员可以赞成或反对。
- 任务票：所有出征队员都可以投成功或失败。
- 服务端仍然防止非队员投任务票、重复投票、错误阶段投票和越权刺杀。
- 规则模式写入房间配置、事件日志和局后复盘。

未来预留：

- `standard_avalon`：好人任务票只能成功，邪恶阵营可成功或失败。
- `custom`：房主可选角色包、发言流程、任务票规则。

语音控场：

- Game Core 输出 `voice_policy`。
- `voice_policy` 可能是全员可说、全员禁言、仅当前发言人、仅队长、仅刺客等。
- VoiceProvider 根据 `voice_policy` 同步真实语音权限。
- 前端按钮状态与真实发布权限保持一致。
- 第一阶段不做手动控场 UI，但数据模型预留 `override_policy` 和审计原因。

## 9. 数据模型与部署位置

长期数据使用托管 Postgres，供应商不锁死。候选包括 Render Postgres、Supabase、Neon、Fly Managed Postgres 等。第一阶段选择时优先考虑：

- 与应用服务同区域。
- 自动备份。
- 环境变量连接。
- 密钥不进入前端。
- 尽量通过平台私有网络连接数据库。

Postgres 保存：

- `rooms`：房间元数据、房间码、规则模式、创建时间、状态。
- `participants`：玩家席位、昵称、参与者类型、会话绑定。
- `games`：对局状态、开始/结束时间、胜负、规则模式。
- `game_events`：命令、裁定、安全事件和状态变化。
- `replay_snapshots`：局后复盘投影。

Redis 或托管缓存保存短期实时状态：

- 在线连接、心跳、断线 TTL。
- 会话 token 版本、撤销状态或短期黑名单。
- 限流计数。
- 幂等 key。
- 当前快照缓存。

LiveKit 只作为实时媒体服务，不作为游戏状态真相来源。

## 10. 前端范围

第一阶段沿用当前界面形态，根据现有项目架构微调：

- 保留房间加入与圆桌席位。
- 保留身份牌 overlay。
- 保留当前操作区。
- 保留聊天、历史、语音入口。

第一阶段必须调整的是状态驱动方式：

- 从结构化快照读取阶段、行动、身份、语音和历史。
- 按 `my_action` 渲染当前玩家主动作。
- 按 `voice_state` 展示麦克风和发言状态。
- 按 `private_panel` 展示身份和夜晚视野。
- 按 `public_timeline` 展示公开历史和局后复盘。

这轮不做完整视觉系统、不重做移动端交互范式、不交付最终产品 UI。后续 UI/UX 设计应基于 v2 快照契约展开。

## 11. 第一阶段交付范围

第一阶段交付 `v2 playable core`：

- 新应用骨架。
- Game Core、规则模式、阶段机、权限、快照契约。
- 房间码、游客身份、房间会话 token、安全重连。
- Realtime Gateway：WebSocket 命令、心跳、限流、幂等、专属广播。
- VoiceProvider：LiveKit-first token 签发和阶段自动控麦。
- 托管 Postgres 数据模型和 Redis 短期状态设计。
- 事件日志和局后复盘投影。
- 沿用旧 UI 的 v2 适配层。
- 健康检查、配置检查和基础结构化日志。

第一阶段不交付：

- 完整账号系统。
- 好友、战绩、公开大厅、快速匹配。
- 主持人和观战者真实 UI。
- 完整 UI/UX 重设计。
- 微服务化、容器编排、复杂灰度发布。
- 标准规则和自定义规则编辑器的完整产品化。

## 12. 测试与验收

自动化测试：

- Game Core 单元测试：5-10 人配置、身份视野、阶段流转、宽松任务票、胜负、刺杀。
- Command 测试：越权、重复投票、错误阶段、断线重连、限流、幂等。
- Snapshot 测试：不同玩家看到的信息不同，私密字段不泄露。
- Realtime 集成测试：多连接进房、广播、重连、掉线、房主重置。
- VoiceProvider 测试：LiveKit adapter 可 mock，验证 `voice_policy` 到权限调用。
- Persistence 测试：房间、对局、事件日志和复盘投影能保存和恢复。

手动验收：

- 5-10 人进入同一房间。
- 准备、开局、身份查看。
- 队长选人、组队投票、任务投票。
- 任务结果复盘、刺杀、终局身份公开。
- 语音连接、阶段控麦、发言状态。
- 刷新、断线、重连、弱网提示。
- 越权请求被拒绝且进入审计。
- 服务重启后能恢复必要房间和对局状态。

## 13. 后续阶段

第二阶段：产品 UI/UX 升级  
基于 v2 快照契约，由设计师重做移动端体验、品牌视觉、复盘体验和关键操作流。

第三阶段：账号与社交  
账号绑定、好友、房间历史、战绩、邀请。

第四阶段：大厅、匹配、主持和观战  
公开房间、快速匹配、主持人、观战者、管理工具。

第五阶段：规模化运维  
拆分实时网关、队列、监控、灰度发布、风控后台。

## 14. 设计风险与应对

- 风险：重写分支短期不可运行。  
  应对：实现计划先恢复最小可运行骨架，再逐步补模块。

- 风险：安全模型过重拖慢第一阶段。  
  应对：第一阶段只落地会话 token、服务端权限、快照隔离、限流幂等、审计和密钥卫生。

- 风险：语音权限与游戏阶段不同步。  
  应对：Game Core 输出 `voice_policy`，VoiceProvider 只执行策略，不自行推断规则。

- 风险：前端沿用旧 UI 导致继续硬猜阶段。  
  应对：旧 UI 只作为展示壳，必须消费结构化快照。

- 风险：托管服务供应商锁定。  
  应对：Postgres、Redis 和 VoiceProvider 都通过配置和 adapter 隔离；第一阶段用托管方案，目标架构不绑定供应商。

## 15. 参考资料

- LiveKit Authentication: https://docs.livekit.io/frontends/build/authentication/
- LiveKit Participant management: https://docs.livekit.io/intro/basics/rooms-participants-tracks/participants/
- Render Postgres: https://render.com/docs/postgresql
- Supabase Database: https://supabase.com/docs/guides/database/overview
- Neon Postgres: https://neon.com/docs/introduction
- Fly Managed Postgres: https://fly.io/docs/mpg/
