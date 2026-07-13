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

明确未实现：

- Milestone 5：LangGraph、RevisionAgent、AcceptanceEvaluator、自动重写和多轮修订。
- Milestone 6：完整评估 REST API 和生产级统一 CLI/API 异常映射。
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
- 网络阻断、未来事实、作者秘密和日志正文隔离由集成测试验证。Milestone 5 未开始。
