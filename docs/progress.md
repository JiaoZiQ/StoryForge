# 开发进度

## Milestone 0–3

状态：已完成并独立验收。

已交付 Python 3.12 工程与门禁、领域模型与数据库、统一 LLM 抽象，以及规划/单章生成/事实抽取的离线闭环。M3 最终验收为 103 项测试通过、覆盖率 95.71%。

## Milestone 4：章节评估与一致性检测

状态：已完成并通过最终干净环境验收。

已完成：

- 可配置、确定性的 MechanicalEvaluator 和集中扣分。
- 保守 FactNormalizer 与十组 ConsistencyChecker 规则。
- 结构化 CriticAgent、八维评分、Prompt 版本和五种 Mock 场景。
- EvaluationScorer 的原始分/权重分、冲突封顶/扣分和硬通过门禁。
- EvaluationService 的版本历史、状态转换、事务回滚和 Critic `partial_failed` 策略。
- EvaluationIssue、Conflict、人物知识和 StoryRule metadata 持久化。
- 新 Alembic migration `ad6fd0f94186`，支持空库与已有 M3 数据。
- `evaluate-chapter`、`show-evaluation`、`list-conflicts`、`update-conflict` 和离线 `demo-m4`。
- 未来事实/作者秘密隔离与正文/敏感信息日志检查。
- 161 项测试全部通过；当前总覆盖率 95.64%。

## Milestone 5：LangGraph 自动修订闭环

状态：已完成实现并通过全量测试。

已完成：

- 强类型 LangGraph StateGraph、条件路由、最大修订次数和最佳版本追踪。
- 规则式 RevisionBriefBuilder、结构化 RevisionAgent 和规则优先 AcceptanceEvaluator。
- Chapter/ChapterVersion 指针与不可变版本历史；Evaluation/Conflict 绑定具体版本。
- Fact candidate/accepted/rejected/superseded 状态、版本哈希唯一键和接受事务。
- SQLite checkpoint、六个主要暂停/恢复点、completed/cancelled 恢复保护和节点幂等。
- WorkflowRun 扩展、WorkflowEvent 审计和 VersionComparison 持久化。
- 第四个 Alembic migration `69c75316dd7e`，覆盖空库与已有 M4 数据升级/降级。
- 工作流 run/resume/cancel/status/history、版本/比较 CLI 和离线 `demo-m5`。
- 一次通过、修订后通过、达到最大次数、先保留最佳、候选事实隔离、恢复无重复和无网络测试。

2026-07-14 实现验收结果：

- Python 3.12.12；Ruff 和 strict mypy 通过。
- pytest 189 项全部通过，总覆盖率 92.42%。
- `demo-m5`：Scenario A v1 一次通过，8.46；Scenario B 的 critical 人物状态冲突使初始分封顶 5.0，修订后升至 8.46 并接受 v2；Scenario C 两轮仍为 5.97，保留 v1 并进入 `completed_needs_review`。
- checkpoint 在 `evaluate_draft` 后恢复：记录从 1 个版本/评估/事实正常增长到 2 个版本/评估/事实，重复数均为 0。
- 数据库反查 accepted facts 可进入下一章上下文，rejected facts 为 0 条可检索；未来事实、checkpoint 正文和密钥命中均为 0。

## Milestone 6：应用接口层与工程化交付

状态：已完成实现并通过干净环境验收。

已完成：

- FastAPI 应用工厂和 lifespan、显式 Settings/依赖注入、无 import-time 数据库连接。
- Project、Planning、Chapter/Context/Generate、Version/Diff、Evaluation、Conflict、accepted Fact、Workflow/Event 和 Health/Ready API。
- 统一分页、过滤、排序、请求 ID、请求体限制、稳定错误结构与 HTTP 状态映射。
- 章节/版本正文默认隐藏、Fact 状态数据隔离、未来上下文隔离和元数据日志。
- 与 API 共用 Application Service 的分组 CLI；保留 M3–M5 已发布的扁平命令。
- `Settings.from_env()` 的 `STORYFORGE_*` 配置约定、生产 Mock 禁用和 OpenAI-compatible 必填校验。
- 第五个 Alembic migration `f2a6c8d91b04`，增加 Project requirements、Evaluation 机械/文学明细和 Conflict resolution note。
- 离线 `demo-m6`：项目、规划、修订后接受、版本 diff、评估历史、冲突、accepted facts、工作流事件和重复记录审计。
- REST/CLI/settings/migration 集成测试，覆盖并发工作流、resume/cancel、冲突转换、公开事实边界、OpenAPI operation ID 和旧数据升级。

2026-07-14 最终验收结果：

- `uv sync --reinstall --all-groups` 从 lock 重装 73 个包并重建 StoryForge wheel；Python 3.12.12。
- Ruff format 检查 122 个文件、Ruff lint、strict mypy（83 个源文件）和 `git diff --check` 全部通过。
- pytest 202 项全部通过，总覆盖率 90.76%，高于 80% 门槛。
- 全新 SQLite 从 base 升级到 `f2a6c8d91b04 (head)`；`alembic check` 无待生成操作。
- OpenAPI 成功生成 26 个 path、31 个 operation 和 54 个 schema，operation ID 全部唯一。
- `demo-m6`：三章规划；第一章修订后接受 v2，Mechanical 8.5、Critic 8.2、Consistency 8.0、Final 8.16 并通过；2 个版本、34 个事件、1 条 accepted Fact；candidate/future 可见数和版本/评估/冲突/事实重复数均为 0。

明确未实现：

- Milestone 7：部署、认证授权、异步 worker 和生产可观测性。
- 异步任务队列、多章节并行、复杂人工审批前端和全书级审稿。
- Neo4j、pgvector、Redis、Celery、前端、PDF/ePub、TTS 和图片生成。

M4 验收命令：

```powershell
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run storyforge demo-m4 --database .\storyforge-m4-demo.sqlite3 --reset
```

2026-07-14 最终验收结果：

- `uv sync --reinstall --all-groups` 解析 52 个包，卸载并重装 51 个包，项目 wheel 重新构建成功。
- Python 3.12.12；Ruff format 检查 81 个文件、Ruff lint、strict mypy（53 个源文件）全部通过。
- pytest 收集 161 项并全部通过，总覆盖率 95.72%。
- 全新 SQLite 从 base 顺序执行三个 migration 到 `ad6fd0f94186 (head)`；`alembic check` 无待生成操作；downgrade base 后再次 upgrade head 成功。
- `demo-m4` 在无 `OPENAI_API_KEY` 的环境成功：正常章 Mechanical 9.5、Critic 8.2、Consistency 10.0、Final 8.66、通过并建议 accept；冲突章 Mechanical 10.0、Critic 6.2、Consistency 4.0、Final 5.0、不通过并建议 human_review。
- 冲突章保存 1 个 high 事实矛盾和 1 个 critical 死亡人物行动；critical 使最终分严格封顶为 5.0。
- 数据库反查：2 条 completed Evaluation、3 条 EvaluationIssue、2 条 Conflict，原始分、权重分、evaluator version、prompt version 均存在，provider 均为 mock。
- README 的创建/规划/生成/评估、评估历史、冲突过滤/状态更新、M3/M4 demo 和真实 Uvicorn `/health` 命令均执行成功。
- 网络阻断、未来事实、作者秘密和日志正文隔离由集成测试验证。该段为 M4 历史验收记录。

## Milestone 7：Docker、PostgreSQL 与工程交付

状态：实现完成，最终门禁与冷启动实测通过。

- Python 3.12.12 slim 多阶段镜像，锁定 uv 依赖，UID/GID 10001 非 root，默认 exec-form `storyforge-api`。
- Compose 使用 PostgreSQL 16 named volume、`pg_isready`、one-shot migrate 和 readiness health gate；重复迁移与 API 重启保留数据。
- Settings 区分 development/test/production，生产拒绝 SQLite、Mock、开发密码和 credentialed wildcard CORS。
- 新 migration `c7d4e1a2b9f0` 用部分唯一索引保证同章节仅一个活跃工作流；readiness 要求精确 head。
- PostgreSQL 专项测试覆盖 migration、Alembic check、JSON/Enum/timezone/boolean、事务回滚、级联、分页排序、Fact 隔离、工作流/API/demo 幂等。
- GitHub Actions 分为 quality、postgres-tests、docker-build，全部使用 MockLLM 和锁文件，不需要真实 API Key。
- `demo-m7` 使用当前 PostgreSQL 创建唯一项目、修订一次并验证 accepted facts、未来边界和四类重复计数。
- Docker/Compose、部署、贡献、安全、行为准则、MIT License 和新电脑冷启动文档已补齐。
- 最终全量运行收集 228 项（含真实 PostgreSQL marker），228 passed；分支覆盖率 90.01%，Ruff、strict mypy、Alembic check、Docker build 和 Compose 冷启动均通过。

## Milestone 8：混合长期记忆与图谱检索

状态：实现完成，独立 pgvector 冷启动验收通过。

- 新增 EmbeddingProvider 抽象、确定性 MockEmbedding、OpenAI-compatible embedding 适配器和独立配置/密钥边界。
- 新 migration `e8b4a2f7c913` 启用 pgvector 0.8.2，新增 `vector(64)` memory、索引审计、图实体/关系表与 cosine HNSW。
- accepted ChapterVersion 自动创建同步索引；embedding 失败不回滚已接受正文，而是保存 failed 状态并允许重试。
- MemoryChunk、GraphEntity 和 GraphRelation 均按状态、项目、章节有效期与版本过滤；重复 reindex 使用唯一约束和 upsert 保持幂等。
- Keyword、Vector、Fact、Graph 四路召回通过 weighted RRF 融合、内容哈希/规范文本去重和确定性重排，并保留 matched sources 与解释。
- ContextBuilder 将 hybrid memory 放在可选预算末尾，项目、当前大纲和 active rules 始终保留；vector 不可用时明确降级为 keyword + fact + graph。
- REST API 和 CLI 提供 memory status/list/show/reindex、retrieval search、graph entities/relations/neighbors；默认不返回正文或 embedding 数组。
- `demo-m8` 使用 PostgreSQL + MockLLM + MockEmbedding，第一章修订后接受 v2，索引并检索到第二章上下文，验证四种不可见状态和三类重复数均为 0。
