# Changelog

本文件记录 Avalon Online 的重要版本变化。后续公网试玩或部署前，请把玩家可感知变化、部署变化和规则变化写到这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本号采用 `v0.x.y` 原型期规则。

## Unreleased

### Added

- 新增项目 README，说明本地启动、测试、公网部署、环境变量和协作约定。
- 新增架构文档，说明 `server.py`、`avalon_engine.py`、`static/` 的职责边界。
- 新增 Render 部署文档，解释 GitHub 托管代码、Render 运行服务的关系。
- 新增版本管理约定，统一后续提交、tag 和发布记录方式。
- 新增 `.gitignore`，忽略 Python 缓存、虚拟环境、系统文件和本地环境变量。

### Changed

- 将原始 README 从一句话说明扩展为项目入口文档。

### Removed

- 从 Git 追踪中移除本地系统文件和 Python 字节码缓存。

## Historical Notes

### v17.2

- 修复身份发牌 overlay 中飞牌残留遮挡角色信息的问题。
- 身份牌内容区域改为可滚动。
- 底部只保留一个“我已确认”按钮。
- 出征/任务队伍标记改为绿色，避免与房主/队长金色冲突。

### v17.1

- 修复缺少全局 `.hidden` 样式导致首次打开页面时隐藏元素直接显示的问题。
