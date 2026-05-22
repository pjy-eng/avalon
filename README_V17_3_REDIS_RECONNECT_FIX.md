# Avalon v17.3 Redis Reconnect Fix

基于 v17.2，针对长局测试中约 1 小时后断连、Render 日志大量出现：

`[redis] save room 123 failed: Connection closed by server.`

本版只改后端稳定性，不改游戏规则、身份机制、发牌动画、LiveKit 语音逻辑。

## 修复内容

- Redis 连接增加 `socket_keepalive`、`health_check_interval=30`、连接/读写超时。
- Redis 写入失败时自动重建连接并重试一次。
- Redis 临时不可用时进入短暂冷却，避免每次广播都刷屏报错。
- `/health` 增加 `redis_healthy` 字段，方便部署后直接检查 Redis 是否可用。
- 服务关闭时主动关闭 Redis client。

## 验证

- `python -m py_compile server.py avalon_engine.py` 通过。
- `pytest -q`：11 passed。

## 部署后重点检查

打开：

`https://你的-render-domain/health`

期望看到：

```json
{
  "ok": true,
  "redis_configured": true,
  "redis_healthy": true
}
```

如果 `redis_configured=true` 但 `redis_healthy=false`，优先检查 Render 环境变量里的 `REDIS_URL` 是否正确，尤其是协议是否为 Redis 服务商要求的 `redis://` 或 `rediss://`。
