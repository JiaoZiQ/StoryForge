# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 的结构；版本策略将在首次功能发布前确定。

## [Unreleased]

### Added

- 初始化 Python 3.12 `src` 布局与模块目录。
- 添加最小 FastAPI `/health` 端点及自动化测试。
- 配置 pytest、coverage、Ruff 与 mypy 质量门禁。
- 添加架构、进度、路线图与仓库工程约定文档。
- 添加 10 个 SQLAlchemy 2 领域模型及项目/章节级联关系。
- 添加对应的 Pydantic v2 create/update/read schema。
- 添加默认 SQLite、可选 PostgreSQL/Psycopg 3 的数据库与 session 配置。
- 添加类型化 repository 层及调用方拥有的事务边界。
- 添加首个 Alembic 迁移和 upgrade/check/downgrade 集成测试。
- 添加 CRUD、约束、级联删除和事务回滚测试。
- 添加统一的结构化 `LLMProvider` 协议、项目内部 LLM 异常与响应元数据。
- 添加确定性、零网络的 `MockLLMProvider`，支持按 Pydantic model 配置响应及注入超时、格式、schema 和调用失败。
- 添加环境驱动的 `OpenAICompatibleProvider`，支持 strict structured output、超时、指数退避、有限修复重试和脱敏日志。
- 添加具名、版本化 `PromptRegistry`，并在每次 LLM 响应中保留实际 prompt 名称与版本。
- 添加真实 OpenAI SDK + mock HTTP transport 的离线集成测试和 Milestone 2 演示脚本。
- 保留 Alembic 进程内运行前已存在的应用 logger，避免迁移配置静默禁用后续日志。
