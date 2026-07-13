# StoryForge Roadmap

所有里程碑按顺序、独立验收。完成一个阶段不自动开始下一阶段。

## Milestone 0：仓库初始化（已完成）

- Python 3.12 `src` 布局和 Git 仓库
- pytest、Ruff、mypy 配置
- 最小 FastAPI `/health` 入口
- 基础测试和架构文档

## Milestone 1：领域模型与数据库（已完成）

- SQLAlchemy 2 模型与 Pydantic v2 schema
- repository 层、默认 SQLite、可选 PostgreSQL 配置
- Alembic 初始化迁移与 CRUD 测试

## Milestone 2：LLM 抽象（已完成）

- 统一的结构化 LLM provider 接口
- 确定性的 MockLLMProvider
- 带超时、重试和脱敏日志的 OpenAI-compatible provider

## Milestone 3：规划与单章生成

- PlannerAgent、WriterAgent、FactExtractorAgent
- 独立 ContextBuilder 与防未来信息泄漏检索
- 第一条端到端章节生成路径

## Milestone 4：评估与一致性

- MechanicalEvaluator 与结构化 LLMCritic
- ConsistencyAgent 和冲突模型
- 可配置评分权重及测试

## Milestone 5：LangGraph 修订闭环

- 状态、条件路由、checkpoint 和失败恢复
- RevisionAgent 与 AcceptanceEvaluator
- 最大修订次数及人工复核退出路径

## Milestone 6：FastAPI 与 CLI

- 完整 REST API、统一异常处理与 OpenAPI 文档
- `storyforge` CLI 和离线 `storyforge demo`
- API/CLI 集成测试

## Milestone 7：Docker 与完整文档

- Dockerfile、Docker Compose 与 PostgreSQL 服务
- 完整使用、架构、数据模型、工作流、评估和演示文档

## 后续方向

第一版完成后再评估 Neo4j、Redis、Celery、Web 前端、TTS、图片生成、PDF 和 ePub；这些能力不进入第一版核心范围。
