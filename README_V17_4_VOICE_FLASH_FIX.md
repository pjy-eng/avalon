# Avalon v17.4 Voice Flash Fix

基于 v17.3。

修复点：

1. 关闭“本地音量检测 speaking_state -> 座位卡片闪烁”的 UI 联动。
   - 多人手机外放时，远端声音会被本机麦克风拾取，导致多个玩家同时被判定为 speaking。
   - 现在座位高亮只根据游戏流程里的 active_speaker / 仅开麦座位显示。

2. speaking_state 不再触发全房间 broadcast_state。
   - 避免有人说话时频繁推送 state，造成所有座位重新渲染。

3. .seat-card.speaking 从循环呼吸动画改成静态高亮。
   - 保留当前发言人的视觉提示，但不再屏闪。

4. 保留 v17.3 的 Redis reconnect/health 修复。

部署后检查：

- /health 应该包含 redis_healthy 字段。
- 如果 /health 只看到 redis_configured，没有 redis_healthy，说明 Render 当前跑的不是 v17.3/v17.4 的 server.py。
