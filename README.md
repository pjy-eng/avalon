# Avalon Online

一个面向朋友局的网页版阿瓦隆原型。项目目标是让不同地点的玩家用手机打开同一个公网地址，通过房间号进入同一局游戏，完成身份分发、发言控制、组队投票、任务投票、刺杀结算和复盘。

当前项目采用轻量架构：FastAPI 负责 HTTP、WebSocket、房间同步和部署入口；`avalon_engine.py` 负责阿瓦隆规则状态机；`static/` 里是原生 HTML/CSS/JavaScript 前端。

## 功能状态

- 支持 5-10 人房间。
- 支持房主、准备、踢人、重置房间。
- 支持私密身份分发、夜晚视野、终局身份公开。
- 支持组队投票、任务投票、失败提案、刺杀结算。
- 支持 WebSocket 实时同步、断线重连、文字公屏。
- 支持可选 LiveKit 语音房。
- 支持可选 Redis 房间持久化。

## 本地启动

建议先创建虚拟环境：

```bash
cd /Users/vangogh/Monorepo/avalon

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

启动开发服务：

```bash
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

如果 `8000` 已被占用，换一个端口：

```bash
uvicorn server:app --host 127.0.0.1 --port 8001 --reload
```

打开浏览器：

```text
http://127.0.0.1:8000
```

或：

```text
http://127.0.0.1:8001
```

局域网手机测试时，可以绑定到所有网卡：

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

然后用手机访问 Mac 的局域网 IP，例如：

```text
http://192.168.x.x:8000
```

## 测试

运行规则引擎单元测试：

```bash
pytest -q
```

当前测试重点覆盖 `avalon_engine.py` 的核心阶段流转和胜负规则。前端和 WebSocket 流程暂时没有自动化测试。

## 公网部署

这个项目不是纯静态站点，不能直接用 GitHub Pages 部署完整功能。GitHub 只负责托管代码，真正运行服务的是 Render 这类云平台。

仓库已经包含 `render.yaml`，Render 会执行：

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port $PORT
```

部署成功后，Render 会提供公网地址，朋友们可以用手机打开这个地址并通过同一个房间号加入游戏。

完整部署说明见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 环境变量

基础游戏流程不依赖 Redis 或 LiveKit。未配置时：

- 房间状态只保存在当前进程内，服务重启后会丢失。
- 语音按钮会提示 LiveKit 未配置，但文字和游戏流程仍可使用。

可选环境变量：

```text
REDIS_URL=redis://...
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
PORT=8000
```

## 项目文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：项目架构、模块职责、状态流。
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：GitHub + Render 公网部署流程。
- [docs/VERSIONING.md](docs/VERSIONING.md)：版本号、提交信息、发布记录约定。
- [CHANGELOG.md](CHANGELOG.md)：版本变更记录。

## 主要目录

```text
.
├── server.py              FastAPI 服务、WebSocket、房间、Redis、LiveKit token
├── avalon_engine.py       阿瓦隆规则状态机
├── static/
│   ├── index.html         页面结构
│   ├── main.js            前端状态渲染、交互、WebSocket、语音
│   └── style.css          视觉样式和响应式布局
├── tests/
│   └── test_engine.py     规则引擎测试
├── docs/                  架构、部署、版本管理文档
├── requirements.txt       Python 依赖
├── render.yaml            Render 部署配置
└── runtime.txt            Python 运行版本
```

## 协作约定

- 改游戏规则时，优先修改 `avalon_engine.py`，并补充 `tests/test_engine.py`。
- 改房间、WebSocket、断线重连、Redis、LiveKit 时，优先修改 `server.py`。
- 改页面体验时，先确认后端快照字段是否足够，再修改 `static/main.js` 和 `static/style.css`。
- 不提交 `.venv/`、`__pycache__/`、`.DS_Store`、pytest cache 等本地生成文件。
- 每次可试玩版本发布后，更新 `CHANGELOG.md`。
