# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 的结构。

## [Unreleased]

### Added

- M0：Python 3.12 `src` 工程、FastAPI 健康检查、pytest/coverage/Ruff/mypy 门禁。
- M1：十个基础 SQLAlchemy 2 领域模型、Pydantic v2 schema、repository、SQLite/PostgreSQL 配置与首个 Alembic 迁移。
- M2：统一结构化 LLM provider、确定性 Mock、OpenAI-compatible provider、脱敏错误策略与版本化 PromptRegistry。
- M3：`PlannerAgent`、`WriterAgent`、`FactExtractorAgent` 及六个独立、显式版本的 system/user Prompt。
- M3：`PlanningService`，支持结构校验、引用校验、原子持久化与受保护的计划替换。
- M3：独立 `ContextBuilder`，支持防未来信息泄漏、来源章节过滤、秘密隔离、相关事实筛选和可审计字符预算。
- M3：`ChapterGenerationService`，持久化正文、摘要、事实、人物状态、伏笔状态、生成元数据与完整版本快照。
- M3：事实提取失败时保留正文并进入 `fact_extraction_failed` 可恢复状态。
- M3：第二个独立 Alembic 迁移 `b550a962dc62`，包含 M3 字段、状态和 `chapter_versions` 表。
- M3：`create-project`、`plan`、`show-context`、`generate-chapter`、`show-chapter` 与可重复的 `demo-m3` 离线 CLI。
- M3：成功、无效规划、上下文预算、未来信息隔离、重复生成保护、版本保留、失败状态、迁移与 CLI 测试。

### Changed

- 项目状态增加 `planned`、`generating`、`failed`；章节状态增加生成与事实提取阶段状态，同时保留此前状态供后续里程碑使用。
- README、架构、数据模型、开发、工作流与进度文档同步到 Milestone 3。

### Fixed

- Writer 上下文不再暴露结局方向、角色秘密、未来章节摘要或由未来章节产生的事实。
- FactExtractor 的 setup 更新会复用同一章节已有的计划伏笔，避免重复记录。
