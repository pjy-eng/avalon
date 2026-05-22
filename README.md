# Avalon Online v2

Avalon Online v2 是一个面向朋友局的网页版阿瓦隆原型。玩家用手机访问同一个公网地址，通过房间号加入同一局；服务端负责房间会话、身份与阶段裁定、按玩家裁剪快照、WebSocket 实时同步，以及可选语音 token 签发。

当前代码采用 authoritative modular monolith：`server.py` 只保留部署入口，实际应用在 `app/` 目录中分层组织。

## 当前阶段能力

第一阶段已经接入：

- 房间加入和 per-room session token。
- 大厅 ready、start、reset 和房主治理命令。
- 完整一局游戏闭环：选队、组队投票、任务票、任务结果复盘推进、刺杀和终局身份公开。
- 每名玩家独立的 per-player snapshot。
- HTTP + WebSocket 实时状态同步，支持刷新恢复同一玩家身份和断线自动重连。
- 公开历史、文字公屏、在线状态、本地私人标记和按阶段控场。
- `NoopVoiceProvider` / LiveKit voice token 接口、前端降级接入，以及踢人/退出后的服务端语音房间移出。
- repository 与 event log 基础代码，为后续持久化接入做好准备。
- `static/` 朋友局圆桌 UI。

仍在后续接入：

- CommandGateway 到数据库 repository/event log 的生产持久化闭环。
- 更完整的自动化浏览器和多人联机验收。

## 本地启动

```bash
cd /Users/vangogh/Monorepo/avalon

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

如果 `8000` 被占用：

```bash
uvicorn server:app --host 127.0.0.1 --port 8001 --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

手机局域网测试时可以绑定所有网卡：

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

然后用手机访问 Mac 的局域网 IP。

## 测试

```bash
pytest -q
```

快速确认部署入口：

```bash
python -c "from server import app; print(app.title)"
```

期望输出：

```text
Avalon Online v2
```

## Render 部署

本项目不是纯静态站点，不能只靠 GitHub Pages 托管完整功能。Render 需要运行 Python 服务并保持 HTTP/WebSocket 后端在线。

`render.yaml` 的 start command 应保持：

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

Render 会使用：

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port $PORT
```

部署细节见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 环境变量

```text
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
SESSION_SECRET=change-me-in-production
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
PORT=8000
```

说明：

- `DATABASE_URL`：可选，Postgres repository/event log 基础设施使用；当前生产命令流尚未完整持久化接入。
- `REDIS_URL`：可选；未配置时 Redis 状态为 `not_configured`，当前房间主要保存在进程内。
- `SESSION_SECRET`：线上必须设置为稳定强随机值；未设置时使用本地开发默认值。
- `LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET`：三者都配置时启用 LiveKit token；缺任一项时使用 Noop voice provider。
- `PORT`：Render 自动提供；本地可手动指定。

## 项目结构

```text
server.py                  部署入口，导出 app.main:app
app/main.py                FastAPI app factory、依赖装配
app/domain/                AvalonGame 规则核心、规则集、类型
app/application/           sessions、rooms、commands、snapshots、events
app/infrastructure/        db、repositories、redis_store、voice
app/api/                   HTTP 与 WebSocket 路由
app/realtime/              WebSocket ConnectionManager
static/                    朋友局圆桌 UI，基于服务端 snapshot 渲染
tests/                     后端规则和服务测试
docs/                      架构、部署、版本说明
render.yaml                Render 部署配置
```

## 项目文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：v2 模块架构、数据流、隐私边界。
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：Render 部署、环境变量、部署后验证。
- [docs/VERSIONING.md](docs/VERSIONING.md)：版本号、提交信息、发布记录约定。
- [CHANGELOG.md](CHANGELOG.md)：版本变更记录。
