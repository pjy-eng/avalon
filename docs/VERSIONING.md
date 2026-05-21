# 版本管理约定

本文档定义 Avalon Online 的版本、提交和发布记录规则。目标是让多人协作时能知道“当前线上是什么版本、这次改了什么、出了问题怎么回退”。

## 当前阶段

项目仍处在原型期，推荐使用 `0.x.y` 版本号。

```text
v0.MINOR.PATCH
```

示例：

```text
v0.18.0
v0.18.1
v0.19.0
```

旧提交中出现过 `v15`、`v17.1`、`v17.2` 这类版本名，可以作为历史版本理解。后续建议统一迁移到 `v0.x.y`。

## 版本号规则

### PATCH

只修 bug，不改变玩家可感知的规则或主要流程。

示例：

```text
v0.18.1
```

适用场景：

- 修复身份牌弹窗遮挡。
- 修复样式溢出。
- 修复断线提示。
- 修复 README 错字。

### MINOR

加入新能力、调整体验或改变可试玩流程，但仍属于原型期兼容迭代。

示例：

```text
v0.19.0
```

适用场景：

- 新增语音能力。
- 重做大厅 UX。
- 调整游戏阶段流程。
- 新增 Redis 持久化。

### MAJOR

原型期暂不使用 `v1.0.0`，除非满足：

- 游戏主流程稳定。
- 多人公网联机稳定。
- 部署文档完整。
- 规则和 UI 有基本测试或验收清单。
- 已经约定“这是朋友局可长期使用的正式版”。

## 提交信息

推荐使用简化 Conventional Commits：

```text
type: summary
```

常用 type：

```text
feat: 新功能
fix: 修复 bug
docs: 文档
style: 样式，不改变逻辑
refactor: 重构，不改变行为
test: 测试
chore: 工程配置、依赖、清理
deploy: 部署配置
```

示例：

```text
docs: add Render deployment guide
fix: prevent deal overlay from showing on first load
feat: add lobby ready state
test: cover mission fail threshold
chore: ignore local Python artifacts
```

## 分支建议

小改动可以直接在 `main` 上提交，但多人协作时推荐：

```text
main
feature/lobby-ux
fix/deal-overlay
docs/project-governance
```

合并前至少运行：

```bash
pytest -q
```

如果改了前端，还要手动打开本地页面验证核心流程。

## 发布流程

每次准备给朋友公网试玩前，建议执行：

1. 确认工作区干净或只包含本次改动。

```bash
git status
```

2. 运行测试。

```bash
pytest -q
```

3. 更新 `CHANGELOG.md`。

4. 提交。

```bash
git add .
git commit -m "docs: add project governance docs"
```

5. 打 tag。

```bash
git tag v0.18.0
git push origin main --tags
```

6. 在 Render 上确认部署成功。

## CHANGELOG 规则

`CHANGELOG.md` 采用倒序记录：

```markdown
## v0.18.0 - 2026-05-21

### Added
- 新增 ...

### Fixed
- 修复 ...

### Changed
- 调整 ...
```

每次发布前至少写清：

- 玩家会感知到什么变化。
- 是否影响部署。
- 是否影响规则。
- 是否需要配置新的环境变量。

## 不应进入 Git 的文件

以下文件不应提交：

```text
.venv/
__pycache__/
*.pyc
.DS_Store
.pytest_cache/
.env
.env.*
```

这些已经在 `.gitignore` 中声明。历史上已提交的缓存文件应从 Git 追踪中移除。
