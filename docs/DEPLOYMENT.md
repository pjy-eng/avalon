# 部署说明

本文档说明如何把 Avalon Online 部署到公网，让不同地点的朋友用手机访问同一个网页一起玩。

## 关键概念

GitHub 只保存代码，不运行这个项目。

这个项目包含 FastAPI、WebSocket 和可选 LiveKit/Redis，不是纯静态页面。因此不能只用 GitHub Pages 完整部署。需要 Render 这类云平台运行 Python 服务，并提供公网 HTTPS 地址。

推荐链路：

```text
Local repo -> GitHub -> Render Web Service -> Public URL
```

## Render 部署方式

仓库已经包含 `render.yaml`：

```yaml
services:
  - type: web
    name: avalon-online-ai-judge
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

Render 会自动：

1. 从 GitHub 拉取代码。
2. 执行 `pip install -r requirements.txt`。
3. 执行 `uvicorn server:app --host 0.0.0.0 --port $PORT`。
4. 检查 `/health`。
5. 提供公网 URL。

## 首次部署步骤

1. 把本地代码推送到 GitHub。

```bash
git status
git add .
git commit -m "docs: add project governance docs"
git push origin main
```

2. 打开 Render 控制台。

3. 连接 GitHub 账号，并授权 Render 访问这个仓库。

4. 创建服务。

推荐选择 Blueprint 或 Web Service：

- 如果使用 Blueprint，让 Render 读取仓库里的 `render.yaml`。
- 如果手动创建 Web Service，按下面参数填写。

5. 手动创建 Web Service 时的参数：

```text
Environment: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn server:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

6. 等待部署完成，打开 Render 提供的 `https://...onrender.com` 地址。

## 环境变量

### 必需变量

无。基础游戏流程可以直接运行。

### 可选：Redis 持久化

```text
REDIS_URL=redis://...
```

不配置 Redis 时：

- 房间只存在当前进程内。
- 服务重启、重新部署或休眠恢复后，房间可能丢失。

配置 Redis 后：

- 房间状态会保存到 Redis。
- 玩家断线或服务短暂重启后更容易恢复。

### 可选：LiveKit 语音

```text
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

不配置 LiveKit 时：

- 游戏规则、房间、文字公屏都能用。
- 语音按钮会提示 LiveKit 未配置。

配置 LiveKit 后：

- 玩家可以在网页内打开麦克风和扬声器。
- 后端会根据游戏阶段控制当前玩家是否允许发言。

## 部署后验证

部署完成后，依次检查：

1. 首页能打开。

```text
https://你的服务名.onrender.com
```

2. 健康检查正常。

```text
https://你的服务名.onrender.com/health
```

3. 两台设备进入同一房间。

```text
https://你的服务名.onrender.com/?room=TEST1
```

4. 测试大厅准备和开始游戏。

5. 测试组队投票、任务投票、结果复盘。

6. 如果配置了 LiveKit，测试麦克风和扬声器。

## 常见问题

### GitHub 上能打开吗？

GitHub 只能查看代码。这个项目需要 Python 服务运行，公网访问地址应该来自 Render，不是 GitHub 仓库页面。

### GitHub Pages 能部署吗？

不能完整部署。GitHub Pages 只能托管静态文件，而本项目需要后端 WebSocket 和 API。

### Render 部署后房间为什么丢了？

如果没有配置 Redis，房间只在当前进程内。服务重启、重新部署、休眠恢复后房间会丢失。要稳定保留房间，需要配置 `REDIS_URL`。

### 语音为什么不能用？

先检查 Render 环境变量里是否配置了：

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
```

如果未配置，语音不可用是正常现象，游戏流程不受影响。

### 手机打不开本地地址？

`127.0.0.1` 和 `localhost` 只代表当前设备自己。手机访问 Mac 本地服务时，需要：

1. Mac 和手机在同一局域网。
2. 本地服务使用 `--host 0.0.0.0` 启动。
3. 手机访问 Mac 的局域网 IP。

公网联机则应使用 Render 提供的 HTTPS 地址。
