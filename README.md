# StoryForge

StoryForge 是一个面向长篇小说创作的分阶段 AI Agent 项目。当前完成到 Milestone 4：在 Milestone 3 的“规划 → 单章生成 → 事实抽取”基础上，新增可解释、可持久化、可离线运行的“机械文本评估 → 一致性检测 → LLM 文学评审 → 合并评分”链路。

默认演示使用 SQLite 和确定性的 `MockLLMProvider`，不需要 API Key，也不访问网络。Milestone 5 的 LangGraph 修订闭环、自动重写、RevisionAgent 和 AcceptanceEvaluator 尚未实现。

## 已实现范围

- SQLAlchemy 2、SQLite 默认数据库、可选 PostgreSQL URL，以及三段可顺序升级的 Alembic migration。
- Pydantic v2 结构化边界和统一 `LLMProvider`。
- `PlannerAgent`、`WriterAgent`、`FactExtractorAgent`、`CriticAgent`，Prompt 均由 `PromptRegistry` 管理并记录版本。
- 防未来信息泄漏的 `ContextBuilder`、章节生成和事实抽取。
- 本地 `MechanicalEvaluator`、规则驱动 `ConsistencyChecker`、统一 `EvaluationScorer` 和事务化 `EvaluationService`。
- 版本化 Evaluation、标准化 EvaluationIssue、可处理状态的 Conflict。
- M3/M4 离线 CLI 演示。完整业务 HTTP API 仍按 Roadmap 留在 Milestone 6。

架构边界见 [docs/architecture.md](docs/architecture.md)，评估规则见 [docs/evaluation.md](docs/evaluation.md)，数据表见 [docs/data-model.md](docs/data-model.md)，事务与失败策略见 [docs/workflow.md](docs/workflow.md)。

## 环境与安装

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --all-groups
uv run python --version
uv run alembic upgrade head
```

默认数据库是 `sqlite:///./storyforge.db`。可通过 `DATABASE_URL` 指向 PostgreSQL；示例只包含安全占位符：

```powershell
$env:DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/storyforge"
uv run alembic upgrade head
```

## M4 离线演示

```powershell
uv run storyforge demo-m4 --database .\storyforge-m4-demo.sqlite3 --reset
```

演示会创建三章规划，生成并评估正常第一章，再生成第二章；第二章同时包含人物属性直接矛盾和“已死亡人物重新说话”的 critical 冲突，用于验证阻断与评分封顶。输出包括：

- Mechanical、Critic、Consistency 和 Final score。
- `Passed`、Issue count、Conflict count、Critical conflict count。
- `Recommended action`。
- Evaluation、EvaluationIssue、Conflict 及评分明细的数据库确认。

`--reset` 只删除命令明确指定的 SQLite 文件。省略 `--reset` 时会在同一数据库中新建项目，因此命令可重复执行。

## 评估组成

### MechanicalEvaluator

完全本地、确定性运行，核心指标包括：字数、段落数、句子数、平均句长、句长标准差、对话比例、重复段落数、重复 n-gram 比例、禁用表达数、极短/超长段落比例。

规则覆盖正文为空、过短/过长、重复段落、重复 n-gram、句长过度统一、相似段落开头、AI 套话、禁用表达、标点滥用、对话比例异常、段落长度异常，以及标题或摘要混入正文。阈值与扣分集中在 `MechanicalEvaluationConfig`。

### ConsistencyChecker

规则引擎检查以下冲突类型：

- `character_state`、`character_knowledge`、`character_existence`
- `location`、`timeline`、`object_state`
- `story_rule`、`fact_contradiction`
- `foreshadowing`、`outline_violation`

`FactNormalizer` 只做保守归一化：空格、大小写、常见标点、数字、简单布尔表达，以及地点、持有、知识等明确 predicate alias；不声称完成语义同义词推理。

### CriticAgent

Critic 只接收当前章节所需的显式最小上下文，不接收 ORM 对象、未来章节事实、结局方向或作者秘密。输出八项 0–10 维度分、结构化问题、优势、修订优先级和通过建议，并经过 Pydantic 业务校验。

## 评分与通过条件

默认权重：Mechanical 20%、Prose 15%、Plot 15%、Character 10%、Pacing 10%、Dialogue 5%、Emotional impact 5%、Consistency 15%、Outline adherence 5%。权重必须精确合计为 1。

默认通过要求：

- 最终分不低于 7.0。
- 无 critical conflict。
- high conflict 不超过配置上限（默认 0）。
- Consistency 不低于 6.5。
- Outline adherence 不低于 6.0。
- Critic 建议通过。

Critical conflict 会将最终分封顶为 5；high conflict 会产生额外扣分。最终建议只返回 `accept`、`revise`、`human_review` 或 `reject`，本阶段不会自动重写。

## 分步 CLI

创建、规划与生成：

```powershell
uv run storyforge create-project `
  --database .\storyforge.db `
  --title "雾岬潮汐" `
  --genre "悬疑奇幻" `
  --premise "档案修复师追查随潮汐消失的灯塔。" `
  --chapters 3 `
  --words 300

uv run storyforge plan --database .\storyforge.db --project-id 1
uv run storyforge generate-chapter --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge evaluate-chapter --database .\storyforge.db --project-id 1 --chapter-number 1
```

查看评估与冲突：

```powershell
uv run storyforge show-evaluation --database .\storyforge-m4-demo.sqlite3 --project-id 1 --chapter-number 1 --latest
uv run storyforge list-conflicts --database .\storyforge-m4-demo.sqlite3 --project-id 1 --status open
uv run storyforge list-conflicts --database .\storyforge-m4-demo.sqlite3 --project-id 1 --severity high --type fact_contradiction
uv run storyforge update-conflict --database .\storyforge-m4-demo.sqlite3 --project-id 1 --conflict-id 1 --status ignored
```

重复评估会新增 `evaluation_version`，不会覆盖旧记录。只有事实抽取成功且已有正文的章节可以评估。Critic 调用失败时，Mechanical、Consistency、Issue 和 Conflict 作为 `partial_failed` 记录保留，章节进入 `evaluation_failed`，可重试。

M3 演示仍可运行：

```powershell
uv run storyforge demo-m3 --database .\storyforge-m3-demo.sqlite3 --reset
```

## 最小 HTTP 服务

当前 HTTP 范围仍只有健康检查。评估业务 API 明确延后到 Milestone 6，避免在本阶段复制 service 逻辑。

```powershell
uv run uvicorn storyforge.api.app:app --reload
```

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

## 质量门禁

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

迁移验收：

```powershell
uv run alembic upgrade head
uv run alembic check
```

## 安全与当前限制

- 不提交 `.env`、API Key、密码、本地数据库或生成小说正文。
- 普通日志只记录 ID、版本、分数和状态，不记录整章正文、Prompt、模型响应或敏感配置。
- 事实匹配是保守、结构化匹配，不是完整语义推理；人物知识边界目前是 JSON 字符串列表。
- StoryRule 的机械匹配依赖 `structured_metadata`；自由文本规则仍作为人类可读依据。
- SQLite 是默认开发路径；未引入 Neo4j、pgvector、Redis、Celery、前端或多媒体能力。
- 本阶段不包含自动修订、LangGraph、多轮循环或业务 API。

## Roadmap

[ROADMAP.md](ROADMAP.md) 是交付顺序的唯一依据。Milestone 4 已完成；Milestone 5 尚未开始。

## License

[MIT](LICENSE)
