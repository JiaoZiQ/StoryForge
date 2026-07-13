# StoryForge Roadmap

所有里程碑按顺序独立验收；完成一个阶段不会自动开始下一阶段。

## Milestone 0：仓库初始化（已完成）

- Python 3.12 `src` 布局、Git 仓库与工程工具。
- pytest、coverage、Ruff、strict mypy。
- 最小 FastAPI `/health` 与基础文档。

## Milestone 1：领域模型与数据库（已完成）

- SQLAlchemy 2 模型与 Pydantic v2 schema。
- repository、SQLite 默认配置、可选 PostgreSQL URL。
- Alembic 初始迁移、CRUD、约束、级联和事务测试。

## Milestone 2：LLM 抽象（已完成）

- 统一结构化 `LLMProvider` 与项目内部异常。
- 确定性 `MockLLMProvider`。
- 具备超时、重试、结构化校验和脱敏日志的 OpenAI-compatible provider。
- 具名、版本化 `PromptRegistry`。

## Milestone 3：规划与单章生成（已完成）

- `PlannerAgent`、`WriterAgent`、`FactExtractorAgent`。
- `PlanningService`、独立 `ContextBuilder`、`ChapterGenerationService`。
- 防未来信息泄漏、字符预算、事实相关性筛选和秘密隔离。
- 计划、正文、摘要、事实、人物状态、伏笔与完整版本快照持久化。
- 可重复执行的 SQLite + Mock 离线演示与 M3 最小 CLI。

## Milestone 4：评估与一致性（未开始）

- MechanicalEvaluator 与结构化 LLMCritic。
- ConsistencyAgent、冲突模型与可配置评分权重。

## Milestone 5：LangGraph 修订闭环（未开始）

- 状态、条件路由、checkpoint 和失败恢复。
- RevisionAgent、AcceptanceEvaluator、最大修订次数与人工复核退出路径。

## Milestone 6：完整 FastAPI 与 CLI（未开始）

- 完整 REST API、统一异常映射和 OpenAPI。
- 生产级 CLI、完整 demo 与 API/CLI 集成测试。

## Milestone 7：Docker 与完整文档（未开始）

- Dockerfile、Docker Compose、PostgreSQL 服务。
- 完整使用、部署和演示文档。

## 后续方向

第一版完成后再评估 Neo4j、pgvector、Redis、Celery、Web 前端、TTS、图片生成、PDF 与 ePub；这些不进入当前核心范围。
