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
