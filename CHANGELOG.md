# Changelog

## Unreleased — Milestone 10

### Added

- Central provider registry/router and governed LLM/embedding calls.
- Privacy policies, high-confidence redaction, content-free ProviderCall audit,
  Decimal usage pricing, project budgets, and workflow ceilings.
- Bounded retries, explicit fallback, process-local rate limits/circuit breaker,
  and durable idempotency claims.
- Governance API/CLI/Web pages and PostgreSQL offline `demo-m10`.
- Alembic revision `a91f4d2c7e10` for project settings, budgets, provider calls,
  idempotency records, and workflow aggregates.

### Fixed

- M10 SQLite batch migration now preserves foreign-key children and safely
  restores legacy chapter content during downgrade.
- Usage API now converts between explicit response models instead of returning a
  Pydantic cross-model validation error.
- Embedding indexing and vector queries no longer bypass privacy, budget,
  reliability, and usage auditing.
- Workflow usage aggregation now follows the persisted call's workflow identity;
  embedding budget rejections are recorded as `budget_blocked`, and workflow hard
  limits preserve the best version for human review.
- Long project navigation now scrolls within its dark sidebar, preserving WCAG AA
  contrast for the Milestone 10 governance links on short viewports.
- `demo-m10` now injects one deterministic manual clock into retry, rate-limit,
  circuit-breaker, and total-deadline handling instead of relying on wall time.
- Model routing now rejects structured-output-incompatible fallbacks and embedding
  dimension mismatches; context-length failures route without retry to a registered
  long-context fallback.
- OpenAPI JSON and generated TypeScript types now include the Milestone 10
  Provider/Usage/Budget/Profile/Privacy contract.
- PostgreSQL tests now prove concurrent hard-budget reservations and identical
  idempotency keys cannot invoke the raw provider twice; API coverage also verifies
  checkpoint resume does not duplicate provider usage or cost.

本项目遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 的结构。

## [Unreleased]

### Added

- M9：Next.js App Router + React + TypeScript strict Web 控制中心，覆盖项目、规划、章节、版本、评估、冲突、事实、工作流、Memory、Retrieval、Graph 与系统状态。
- M9：OpenAPI 自动生成 TypeScript 类型、Zod 运行时响应校验、TanStack Query 缓存/失效/条件轮询和统一安全错误结构。
- M9：同源 Next.js server proxy，固定内部 API 上游、请求大小限制、header allowlist、请求 ID 透传和 503/504 安全映射。
- M9：Cytoscape 1/2-hop 图谱、服务端版本 diff、检索来源解释、accepted-only 事实视图和按需正文加载。
- M9：Vitest/RTL 覆盖率门禁、四个独立 Playwright E2E 场景、axe 检查、Node 24 非 root 镜像、Compose frontend 服务和 CI job。
- M9：PostgreSQL + pgvector + MockLLM/MockEmbedding `demo-m9`，返回安全 Web URL 与计数摘要。
- M8：独立 EmbeddingProvider、确定性且无网络的 MockEmbedding，以及带批处理、维度校验、超时和脱敏异常的 OpenAI-compatible embedding provider。
- M8：第七个 Alembic migration `e8b4a2f7c913`，在 PostgreSQL 启用 pgvector，新增 `memory_chunks`、`memory_index_records`、`graph_entities`、`graph_relations` 和 cosine HNSW 索引。
- M8：accepted 版本的结构化切分、同步可重试索引、候选/拒绝/已替代/未来记忆隔离和重复 reindex 幂等。
- M8：Keyword、Vector、Fact、Graph 四路检索、weighted RRF、内容去重、确定性重排、来源解释及 vector 失败降级。
- M8：关系图谱 1/2 hop 查询、Memory/Graph/Hybrid REST API 与 CLI，以及 PostgreSQL + MockLLM + MockEmbedding `demo-m8`。
- M7：Python 3.12.12 slim 多阶段、锁定依赖、UID 10001 非 root 的生产式 Dockerfile 与敏感文件隔离 `.dockerignore`。
- M7：PostgreSQL 16、`pg_isready`、one-shot migration、精确 readiness 和 named volume 组成的 Docker Compose 启动链。
- M7：development/test/production Settings、安全 CORS/Mock/开发密码校验、结构化 JSON 日志和数据库有界等待入口。
- M7：第六个 Alembic migration `c7d4e1a2b9f0`，用跨 SQLite/PostgreSQL 部分唯一索引阻止同章节并发活跃工作流。
- M7：真实 PostgreSQL marker 集成测试、GitHub Actions quality/postgres/docker jobs，以及 PostgreSQL + Mock `demo-m7`。
- M7：Makefile、安全 clean、部署/冷启动文档、ADR 0006、CONTRIBUTING、SECURITY 与 CODE_OF_CONDUCT。

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
- M4：本地 `MechanicalEvaluator`，覆盖长度、重复、句式、套话、禁用表达、标点、对话与段落结构，并集中配置阈值和扣分。
- M4：保守 `FactNormalizer` 和十组规则驱动 `ConsistencyChecker`，输出可解释、带证据和置信度的冲突。
- M4：结构化 `CriticAgent`、八维文学评分、Prompt 版本记录，以及正常、死亡冲突、大纲偏离、低质量和事实冲突 Mock 场景。
- M4：`EvaluationScorer` 的可验证权重、critical 封顶、high 扣分、最低分门禁和推荐动作。
- M4：`EvaluationService` 的不可变版本历史、EvaluationIssue/Conflict 持久化、章节状态转换、原子写入和 Critic `partial_failed` 保留策略。
- M4：第三个 Alembic migration `ad6fd0f94186`，新增评分明细、冲突表、问题表、人物知识边界和结构化 StoryRule metadata。
- M4：`evaluate-chapter`、`show-evaluation`、`list-conflicts`、`update-conflict` 和可重复离线 `demo-m4`。
- M4：机械规则、归一化、一致性、Critic、评分、事务、迁移、CLI、未来信息隔离与日志脱敏测试。
- M5：LangGraph 强类型章节工作流，覆盖生成、抽取、评估、条件路由、修订、比较、接受、拒绝、人工复核和失败出口。
- M5：确定性 `RevisionBriefBuilder`、结构化 `RevisionAgent` 和规则优先 `AcceptanceEvaluator`。
- M5：扩展 `chapter_versions` 为不可变正文版本，Evaluation/Conflict/Fact 绑定具体版本，并持久化完整版本比较。
- M5：Fact 增加 `candidate`、`accepted`、`rejected`、`superseded` 状态及版本哈希唯一键，接受事务才提升正式长期事实。
- M5：SQLite LangGraph checkpointer、显式 pause/resume、节点重放幂等键、最佳版本追踪和最大修订次数。
- M5：扩展 WorkflowRun，新增 WorkflowEvent 和 VersionComparison 审计记录。
- M5：第四个 Alembic migration `69c75316dd7e`，支持空库和已有 M4 正文/事实/评估安全升级。
- M5：`run-workflow`、`resume-workflow`、`cancel-workflow`、状态/历史/版本/比较查询和离线 `demo-m5`。
- M5：一次通过、修订后通过、达到上限、六个暂停恢复点、候选事实隔离、幂等、迁移与无网络 CLI 测试。
- M6：FastAPI 应用工厂与 lifespan 基础设施，Project/Planning/Chapter/Version/Evaluation/Conflict/Fact/Workflow/Health API，统一错误与请求 ID。
- M6：数据库分页/过滤/排序、正文默认隐藏、accepted Fact 公共隔离、同步工作流 HTTP 语义和可用 OpenAPI。
- M6：`storyforge project|plan|chapter|evaluation|conflict|fact|workflow|demo` 分组 CLI、human/JSON 输出和稳定退出码。
- M6：第五个 Alembic migration `f2a6c8d91b04`，增加 created 项目状态、项目附加要求、评估指标/维度和冲突处理备注。
- M6：离线 `demo-m6` 与 REST E2E，验证修订后通过、版本/评估/事实无重复、候选/未来事实不可见和日志脱敏。

### Changed

- Compose 启动链扩展为 PostgreSQL → migrate → API → frontend，并使用 internal network 阻止运行时容器访问公网；M9 不新增 migration。
- README、架构、工作流、数据模型、评估、开发、部署、API、Memory/Retrieval/Graph、进度和 ADR 同步到 Milestone 9。
- ContextBuilder 现在将 accepted、过去章节的 hybrid hits 纳入写作上下文；项目、当前章节大纲和 active StoryRule 是强制预算项，memory 始终最后加入。
- Compose 与 PostgreSQL CI service 改用 `pgvector/pgvector:0.8.2-pg16-bookworm`；readiness 精确要求 M8 head `e8b4a2f7c913`。
- readiness 从“返回当前 revision”加强为“数据库 revision 必须等于代码 migration head”，过期 schema 返回统一 503。
- README、架构、数据模型、工作流、评估、开发、API、CLI、进度和发布元数据同步到 Milestone 7。

- 项目状态增加 `planned`、`generating`、`failed`；章节状态增加生成与事实提取阶段状态，同时保留此前状态供后续里程碑使用。
- README、架构、数据模型、开发、工作流与进度文档同步到 Milestone 3。
- README、架构、数据模型、评估、开发、工作流、ADR 与进度文档同步到 Milestone 4。
- 章节状态增加 `evaluated_passed`、`evaluated_needs_revision` 和 `evaluation_failed`；旧状态保留兼容。
- README、架构、数据模型、评估、开发、工作流、ADR 与进度文档同步到 Milestone 5。
- 章节状态增加 workflow/drafting/revising/accepted/needs-review/failed 阶段；旧 M1–M4 状态保持可升级兼容。
- README、API、CLI、架构、数据模型、评估、开发、工作流、ADR 与进度文档同步到 Milestone 6。

### Fixed

- 修复 M8 验收中 active StoryRule 在极小上下文预算下可能被检索结果挤出的缺陷。
- 修复 HybridRetriever 启用时小于 100 字符的 ContextBuilder 预算被下游检索 schema 拒绝的问题。
- 修复 M7→M8 migration 测试的 downgrade 代码错位，以及 HybridRetriever 新去重语义对应的过期测试断言。
- 修复测试环境 CLI 在应用显式 `--database` 参数前读取 Settings，导致安全的“test 必须显式数据库”校验误报的问题。
- 修复仅依靠应用查询阻止同章节并发工作流的竞态窗口。
- 修复 BuildKit cache mount 被构建层删除而造成 Docker build 失败的问题。

- Writer 上下文不再暴露结局方向、角色秘密、未来章节摘要或由未来章节产生的事实。
- FactExtractor 的 setup 更新会复用同一章节已有的计划伏笔，避免重复记录。
- 本章首次回收伏笔不再因持久化状态已经更新而误判为重复回收。
- Evaluation 迁移会为已有 M3 评估按章节和 ID 回填稳定版本号。
- `demo-m4` 同时构造 high 事实矛盾和 critical 死亡人物行动，实际展示 critical 冲突阻断及最终分 5.0 封顶。
- checkpoint 状态只保存声明过的可序列化字段，避免保存枚举对象、正文、数据库 session 或 LLM client。
- 达到最大修订次数时，未选中的最后版本会正确标记为 rejected，不再停留在 evaluated。
- 工作流错误脱敏先处理 Bearer 凭据，再处理通用 Authorization/API Key 字段，避免残留 token。
