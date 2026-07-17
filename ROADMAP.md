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

## Milestone 4：评估与一致性（已完成）

- 可配置、确定性的 MechanicalEvaluator 与集中扣分。
- 结构化 CriticAgent、Prompt 版本和离线 Mock 场景。
- FactNormalizer、规则驱动 ConsistencyChecker 与可持久化 Conflict。
- EvaluationScorer 的权重、封顶、扣分与硬阻断条件。
- EvaluationService 的版本历史、事务边界和 `partial_failed` 策略。
- SQLite + Mock 的 `demo-m4` 及评估/冲突 CLI。

## Milestone 5：LangGraph 修订闭环（已完成）

- 强类型 StateGraph、条件路由、SQLite checkpoint、显式暂停/恢复和协作式取消。
- RevisionBriefBuilder、RevisionAgent、AcceptanceEvaluator、多轮修订和最大次数人工复核退出路径。
- 不可变 ChapterVersion、最佳版本追踪、版本比较和接受/拒绝历史。
- 候选事实按版本隔离，接受事务才提升正式事实；恢复由数据库唯一键保证幂等。
- WorkflowRun/WorkflowEvent 审计和 SQLite + Mock `demo-m5` 三场景演示。

## Milestone 6：完整 FastAPI 与 CLI（已完成）

- 完整 REST API、Application Service、依赖注入、统一异常映射、请求 ID、分页和 OpenAPI。
- 分组 CLI、`demo-m6`、API/CLI/迁移集成测试，以及 accepted Fact/版本数据隔离。

## Milestone 7：Docker 与完整文档（已完成）

- Python 3.12 多阶段非 root Dockerfile、`.dockerignore` 和锁定生产依赖。
- PostgreSQL 16、独立 migration service、health/readiness 门禁和 named volume 的 Docker Compose。
- development/test/production Settings、结构化脱敏日志、有限数据库等待和一键命令。
- PostgreSQL migration/API/workflow/demo 专项测试与 quality/postgres/docker 三段 CI。
- PostgreSQL + MockLLM `demo-m7`、冷启动、部署、安全、贡献、许可证和最终限制文档。

## Milestone 8：混合长期记忆与图谱检索（已完成）

- 独立 EmbeddingProvider、确定性 MockEmbedding 和 OpenAI-compatible embedding 适配器。
- accepted ChapterVersion 的结构化切分、`vector(64)` 存储、cosine HNSW、索引状态与幂等重建。
- PostgreSQL 关系表保存实体和受控关系；最多 2 hops，并按 accepted 状态与章节时间边界过滤。
- Keyword、Vector、Fact、Graph 四路召回，weighted RRF 融合、内容去重、规则式重排和来源解释。
- ContextBuilder 将 hybrid hits 放入第二章及后续上下文，同时强制保留项目、当前大纲和 active rules。
- FastAPI/CLI memory、retrieval、graph 接口，以及 PostgreSQL + MockLLM + MockEmbedding `demo-m8`。
- 第七个 Alembic migration `e8b4a2f7c913`，支持空库和已有 M7 数据升级。

## 后续方向

后续里程碑再评估 Neo4j、Redis、Celery、Web 前端、TTS、图片生成、PDF 与 ePub；这些不进入当前核心范围。
