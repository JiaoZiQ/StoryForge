# StoryForge Roadmap

## Milestone 12: whole-book generation and global revision (implemented)

- Durable BookRun/BookSnapshot models, sequential and bounded dependency-aware scheduling.
- Accepted-only timeline, character/knowledge/relationship arcs, foreshadowing,
  transitions, pacing, and local plus PostgreSQL pgvector repetition candidates.
- Compressed governed BookCritic, deterministic book scoring, targeted revision plans,
  affected-chapter rechecks, bounded global rounds, shared budgets, pause/resume/cancel.
- Job/SSE/API/CLI/Web integration and offline five-chapter `demo-m12`.
- Milestone 13 is not started.

## Milestone 11: asynchronous jobs and distributed reliability (implemented and accepted)

- PostgreSQL-authoritative jobs/events/outbox/workers; Redis transports Job IDs only.
- Leases, recovery, bounded retry, DLQ, cooperative controls, and replayable SSE.
- Job API/CLI/Web Center and distributed provider rate/circuit state.
- Offline `demo-m11`; Milestone 12 is not started.

## Milestone 10：Provider 治理、成本与可靠性（已实现并独立提交）

- 统一 LLM/Embedding gateway、能力注册、受控 profile 与 task route。
- offline/strict/standard 隐私策略及外发前脱敏。
- ProviderCall、ProjectBudget、工作流用量聚合、Decimal 定价快照。
- 有界 retry/fallback、RPM/TPM/concurrency 限制、circuit breaker 与幂等键。
- Provider/Usage/Budget/Model Settings API、CLI 与 Web 页面。
- PostgreSQL + pgvector + MockLLM/MockEmbedding 的 `demo-m10`。

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

## Milestone 9：Web 前端与可视化控制中心（已完成）

- Next.js App Router、React、TypeScript strict、Tailwind 与响应式应用壳层。
- 项目、规划、章节、版本 diff、评估、冲突、accepted facts、工作流、Memory、Retrieval、Graph 与系统状态页面。
- OpenAPI 生成类型 + Zod 运行时校验、统一 API client、同源 server proxy、安全错误和请求 ID。
- TanStack Query 缓存/失效/工作流条件轮询，React Hook Form + Zod 表单和危险操作确认。
- Cytoscape 关系图及等价文本列表；图遍历限制 1/2 hops，正文按需加载，列表默认无正文。
- Vitest/RTL 单元测试、四个独立 Playwright 场景、axe 检查、Node 非 root 镜像、Compose 与 CI 门禁。
- PostgreSQL + pgvector + MockLLM + MockEmbedding `demo-m9`，无新增数据库 migration。

## 后续方向

后续里程碑再评估认证/RBAC、Neo4j、Redis、Celery、TTS、图片生成、PDF 与 ePub；这些不进入当前核心范围。
