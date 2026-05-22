# v17.5 麦克风状态 UI 与按玩家说话高亮修复

## 修复目标

v17.4 已经避免了“一个人说话导致所有座位一起闪”的问题，但座位卡片上缺少单独麦克风状态，玩家无法直观看出谁开麦、谁被禁麦、谁正在说话。

v17.5 补充了座位级麦克风状态显示，并把 speaking 状态改为按 playerId 匹配后再更新对应座位。

## 修改内容

### 1. 每个玩家座位显示麦克风状态

- 麦克风开启且当前流程允许说话：显示普通麦克风图标。
- 麦克风开启但当前流程禁麦：显示静音图标。
- 麦克风关闭或未加入语音：显示静音图标。
- 玩家离线：隐藏该玩家的麦克风状态，避免误判。

### 2. 只高亮正在说话的玩家

- 前端不再用全局 speaking 布尔值控制所有座位。
- 服务端接收 `speaking_state` 后，只记录对应 `player_id` 到 `speaking_ids`。
- 服务端广播轻量 `voice_activity` 消息，只包含 `speaking_ids` 与 `mic_enabled_ids`。
- 前端收到 `voice_activity` 后，只更新对应玩家座位的 `speaking` class 和麦克风 icon，不触发整列座位重绘。

### 3. 增加玩家麦克风开启状态

- 新增 `mic_state` 消息。
- 玩家打开/关闭麦克风时，前端向服务端同步 `mic_enabled`。
- 服务端在玩家 public state 中追加 `mic_enabled`。
- 玩家断线、被踢、房间重置、长时间离线清理时，会同步清除 `mic_enabled_ids` 与 `speaking_ids`。

### 4. 保留游戏流程禁麦规则

座位麦克风 UI 会结合当前 `mic_status` 判断：

- `UNMUTE_ALL`：全员允许说话。
- `MUTE_ALL`：全员禁麦。
- `MUTE_ALL_EXCEPT_Player_N`：仅对应座位允许说话。

因此玩家即使点了开麦，只要当前游戏流程不允许他说话，座位上也会显示静音状态。

## 修改文件

- `server.py`
  - 新增 `mic_enabled_ids`
  - 新增 `mic_state` 处理
  - 新增 `broadcast_voice_activity`
  - `speaking_state` 改为轻量广播，避免整房间重绘

- `static/main.js`
  - 新增座位麦克风状态渲染
  - 新增 `syncVoiceActivity`
  - 新增 `getPlayerVoiceStatus`
  - 新增 `sendMicState`
  - speaking 高亮改为按玩家匹配

- `static/style.css`
  - 新增 `mic-on`、`mic-speaking`、`mic-muted`、`mic-off` 样式
  - 新增单个座位说话高亮动画

## 测试步骤

### 基础健康检查

```bash
curl https://avalon-friends.onrender.com/health
```

期望结果：

```json
{
  "ok": true,
  "livekit_configured": true,
  "redis_configured": true,
  "redis_healthy": true
}
```

### 麦克风 UI 测试

1. 打开两个浏览器或两个设备，进入同一房间。
2. A 玩家点击右上角语音按钮。
3. A 的座位卡片应显示麦克风图标。
4. B 玩家未开麦时，B 的座位卡片应显示静音图标。
5. A 说话时，只允许 A 的座位高亮或闪动。
6. B 不说话时，B 的座位不能跟着闪。
7. A 停止说话后，A 的座位高亮应自动消失。
8. A 关闭麦克风后，A 的座位应切回静音状态。

### 游戏流程禁麦测试

1. 开始游戏并进入轮流发言阶段。
2. 当前发言人的座位应显示可开麦状态。
3. 非当前发言人即使打开语音，也应显示禁麦/静音状态。
4. 当前发言人说话时，只高亮当前发言人的座位。

### 回归测试

```bash
pytest -q
```

本地结果：

```text
11 passed
```

## 预期效果

v17.5 后，座位麦克风状态可以直接区分：

- 谁开了麦克风
- 谁被当前游戏流程禁麦
- 谁没有开麦
- 谁正在说话
- 谁已经离线

同时，正在说话的高亮只会作用在对应玩家座位，不会再出现所有座位一起闪动的问题。
