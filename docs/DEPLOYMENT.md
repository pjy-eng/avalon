# Avalon Online v2 部署说明

Avalon Online v2 需要运行 FastAPI、WebSocket 和可选语音 token 服务，不是纯静态站点。GitHub 只托管代码，Render 负责运行 Python Web Service 并提供公网 HTTPS 地址。

## Render Web Service

仓库包含 `render.yaml`：

```yaml
services:
  - type: web
    name: avalon-online-ai-judge
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

`startCommand` 需要保持：

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

虽然 v2 应用实际在 `app/main.py`，但 `server.py` 会导出 `app.main:app`，所以 Render 入口仍然稳定。

## 首次部署

1. 把当前分支推送到 GitHub。
2. 在 Render 创建 Blueprint 或 Python Web Service。
3. 如果使用 Blueprint，让 Render 读取仓库中的 `render.yaml`。
4. 如果手动创建服务，填写：

```text
Environment: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn server:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

5. 配置生产环境变量。
6. 等待部署完成，打开 Render 提供的 `https://...onrender.com` 地址。

## 环境变量

### 必须配置

```text
SESSION_SECRET=strong-random-production-secret
```

线上必须设置稳定强随机 `SESSION_SECRET`。它用于 room session token 签名；如果每次部署变化，已有玩家 session 会失效。未配置时应用会使用 `dev-only-session-secret`，只适合本地开发。

Render 会自动提供：

```text
PORT
```

不要把 `PORT` 写死为固定值，start command 应使用 `$PORT`。

### Managed Postgres

```text
DATABASE_URL=postgresql+psycopg://...
```

建议在 Render 上创建 managed Postgres 并把连接串注入 `DATABASE_URL`。当前 v2 已有 SQLAlchemy model、RoomRepository 和 EventRepository 基础，但 CommandGateway 的生产命令流不应被描述为已经完整持久化。它是后续持久化闭环的基础设施。

### Redis

```text
REDIS_URL=redis://...
```

建议需要跨实例缓存或恢复时配置 managed Redis。当前未配置 Redis 时：

- `/health` 中 `redis` 为 `not_configured`。
- 房间运行主要依赖当前进程内状态。
- 重启、重新部署、实例休眠后，房间状态可能丢失。

Redis store 基础已准备好，但完整 Redis-backed 多实例恢复仍属于后续接入。

### LiveKit

```text
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

三者全部配置时，应用使用 `LiveKitVoiceProvider` 签发语音 token。

缺任一项时，应用使用 `NoopVoiceProvider`：

- 房间、ready/start/reset、WebSocket state 不受影响。
- voice-token 接口返回 disabled/not configured 语义。
- 前端应把语音显示为不可用或降级状态。

## 部署后验证

### 1. 健康检查

```text
https://你的服务名.onrender.com/health
```

期望返回：

```json
{
  "ok": true,
  "service": "avalon-online-v2",
  "database": "configured",
  "redis": "configured",
  "voice": "configured"
}
```

如果没有配置 Postgres、Redis 或 LiveKit，对应字段会是 `not_configured`。这不是启动失败，但要和预期一致。

### 2. 首页和加入房间

打开：

```text
https://你的服务名.onrender.com
```

用两个浏览器或两台手机加入同一个房间，确认每个玩家能拿到自己的 session 和 snapshot。

### 3. WebSocket state

加入房间后确认页面能收到实时 state：

- 新玩家加入后其他客户端列表更新。
- 玩家 ready 后状态同步。
- 房主 start 后进入游戏 snapshot。
- reset 后回到可重新开始的房间状态。

### 4. Voice token

未配置 LiveKit 时，验证 voice-token 降级为 disabled/not configured，页面不应阻塞游戏流程。

配置 LiveKit 后，验证：

- `/api/rooms/{room_id}/voice-token` 能返回 token。
- token 中 room 与 player identity 对应当前房间和玩家。
- 当前阶段的 `can_publish_audio` 与 snapshot 中的 voice state 一致。

## 本地部署模拟

```bash
source .venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

检查：

```bash
python -c "from server import app; print(app.title)"
curl http://127.0.0.1:8000/health
```

如果要让同一 Wi-Fi 下手机访问：

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

然后用手机打开 Mac 的局域网 IP。

## 常见问题

### GitHub Pages 可以部署吗？

不能完整部署。GitHub Pages 只能托管静态文件，而本项目需要 FastAPI、WebSocket、session token 和 voice-token API。

### `/health` 里 database 或 redis 是 `not_configured` 是失败吗？

不一定。它表示对应托管服务没有配置。当前第一阶段可以在未配置 Postgres/Redis 的情况下运行房间加入、ready/start/reset 和 WebSocket state，但生产试玩若希望降低重启丢房间风险，应继续接入持久化闭环。

### 语音不可用怎么办？

检查 Render 环境变量里是否同时配置：

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
```

如果没有配置，Noop 降级是预期行为，游戏主流程仍应可用。

### 手机打不开本地地址？

`127.0.0.1` 只代表当前设备自己。手机访问 Mac 本地服务需要：

1. Mac 和手机在同一局域网。
2. 服务使用 `--host 0.0.0.0` 启动。
3. 手机访问 Mac 的局域网 IP。
