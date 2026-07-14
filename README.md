# StoryForge

StoryForge 是一个面向长篇小说创作的分阶段 AI Agent 项目。当前完成到 Milestone 6：规划、生成、事实抽取、评估与 LangGraph 修订闭环已经通过统一 Application Service 暴露为 REST API 和分组 CLI。

默认演示使用 SQLite 和确定性的 `MockLLMProvider`，不需要 API Key，也不访问网络。

## 已实现范围

- SQLAlchemy 2、SQLite 默认数据库、可选 PostgreSQL URL，以及五段可顺序升级的 Alembic migration。
- Pydantic v2 结构化边界和统一 `LLMProvider`。
- `PlannerAgent`、`WriterAgent`、`FactExtractorAgent`、`CriticAgent`、`RevisionAgent`，Prompt 均由 `PromptRegistry` 管理并记录版本。
- 防未来信息泄漏的 `ContextBuilder`、章节生成和事实抽取。
- 本地 `MechanicalEvaluator`、规则驱动 `ConsistencyChecker`、统一 `EvaluationScorer` 和事务化 `EvaluationService`。
- 版本化 Evaluation、标准化 EvaluationIssue、可处理状态的 Conflict。
- LangGraph 条件路由、多轮修订、最佳版本选择、SQLite checkpoint/resume 和 WorkflowRun/WorkflowEvent 审计。
- 不可变 ChapterVersion，以及按版本隔离的 candidate/accepted/rejected/superseded Fact。
- FastAPI 应用工厂、显式依赖注入、统一错误模型、请求 ID、元数据日志、分页/过滤/排序和 OpenAPI。
- Project、Planning、Chapter、Version/Diff、Evaluation、Conflict、Fact、Workflow、Health/Ready REST API。
- 分组 CLI 与兼容的旧扁平命令，以及 M3/M4/M5/M6 离线演示。

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

## M6 REST API 与离线演示

先迁移数据库，再启动服务：

```powershell
$env:STORYFORGE_DATABASE_URL="sqlite:///./storyforge.db"
$env:STORYFORGE_ENVIRONMENT="development"
$env:STORYFORGE_LLM_PROVIDER="mock"
uv run alembic upgrade head
uv run uvicorn storyforge.api.app:create_app --factory --reload
```

- 存活检查：`GET http://127.0.0.1:8000/health`
- 就绪检查：`GET http://127.0.0.1:8000/api/v1/ready`
- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

主要路由前缀为 `/api/v1`，覆盖项目 CRUD、规划、章节生成/上下文/评估、不可变版本与 diff、评估历史、冲突处理、accepted Fact 查询和工作流 run/status/resume/cancel/events。工作流当前是同步执行：`POST .../workflow` 等待图执行或暂停后返回 `201`，没有伪装成后台任务。

列表统一返回 `items + meta`，默认 `page=1&page_size=20`，最大 100。章节和版本默认不返回正文；只有显式 `include_content=true` 才返回。Fact 公共接口只暴露 accepted 数据，candidate/rejected/superseded 均不可通过状态参数绕过。

完整离线演示：

```powershell
uv run storyforge demo-m6 --reset --output human
uv run storyforge demo m6 --reset --output json
```

演示会在自动清理的临时 SQLite 中创建项目、生成三章规划、让第一章修订一次后通过，并反查项目、章节、两个版本、diff、两次评估、冲突、accepted facts、工作流与事件；输出 Mechanical、Critic、Consistency、Final 和 Passed，并断言候选事实和未来事实可见数为 0，版本/评估/冲突/事实重复数为 0。

分组 CLI 示例：

```powershell
uv run storyforge project create --database .\storyforge.db --title "雾岬" --genre "悬疑" --premise "档案员追查失踪记录。" --chapters 3 --words 300 --output json
uv run storyforge plan generate --database .\storyforge.db --project-id 1
uv run storyforge chapter list --database .\storyforge.db --project-id 1
uv run storyforge workflow run --database .\storyforge.db --project-id 1 --chapter-number 1 --scenario improve
uv run storyforge chapter versions --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge evaluation list --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge conflict list --database .\storyforge.db --project-id 1
uv run storyforge fact list --database .\storyforge.db --project-id 1
uv run storyforge workflow events --database .\storyforge.db --workflow-run-id 1
```

每个分组子命令支持 `--output human|json`。JSON 模式的标准输出只有有效 JSON；错误通过稳定 code 和不同退出码区分输入错误、未找到、状态冲突、provider 和数据库失败。分组 CLI 默认使用 Mock，也会读取同一组 `STORYFORGE_LLM_*` 环境配置切换 OpenAI-compatible provider；数据库文件仍由命令的 `--database` 明确指定。

配置统一使用 `STORYFORGE_` 前缀，完整安全占位见 `.env.example`。默认开发模式为 Mock；生产环境显式禁止 Mock 回退，OpenAI-compatible 配置缺少 key/model 会启动失败。应用不会隐式读取或提交 `.env`。

## M5 离线演示

```powershell
uv run storyforge demo-m5 --database .\storyforge-m5-demo.sqlite3 --reset
```

演示在同一全新 SQLite 数据库中执行四条互相隔离的工作流：

- Scenario A：正常草稿一次评估通过，接受版本 1，不进入修订。
- Scenario B：初稿不通过，生成 RevisionBrief 和版本 2；重新抽取、评估、比较后接受版本 2，版本 1 保留为 rejected 历史。
- Scenario C：两轮修订均无明显改善，达到上限后进入 `completed_needs_review`，保留最佳版本且不提升候选事实。
- Checkpoint recovery：在 `evaluate_draft` 后暂停，再由相同 `thread_id` 恢复；确认版本、评估和事实均无重复。

工作流节点与主路由：

```mermaid
flowchart LR
    I["initialize"] --> C["load_context"] --> G["generate_draft"] --> F["extract_facts"] --> E["evaluate_draft"] --> D{"passed?"}
    D -->|yes| A["accept_version"]
    D -->|retry available| B["build_revision_brief"] --> R["revise_draft"] --> RF["extract_revision_facts"] --> RE["evaluate_revision"] --> V["compare_versions"]
    V -->|accept| A
    V -->|retry| X["reject_revision"] --> B
    D -->|limit| H["needs_human_review"]
    V -->|limit / stop| H
```

自动接受不只看总分：必须通过 M4 的 consistency、outline、critical/high conflict 和 Critic 门禁；版本比较还检查新严重问题、修订任务完成情况和最小改善阈值。默认最多修订 2 次。新版本更差时继续保留当前最佳版本。

正文版本永不覆盖：`Chapter` 保存逻辑章节和 current/accepted 指针，`ChapterVersion` 保存每次生成或修订。每次 Evaluation/Conflict 都关联具体版本。抽取结果先保存为 candidate Fact；只有 `accept_version` 的事务会提升选中版本的事实，并使旧 accepted 事实 superseded。rejected/needs-review 版本的事实不会进入 `ContextBuilder`。

checkpoint 位于单独 SQLite 文件，只保存 ID、路由、小型评分/brief 数据和时间，不保存 ORM session、LLM client、数据库连接、API Key 或整章正文。主要节点具有数据库唯一键保护，可安全恢复。

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

Critical conflict 会将最终分封顶为 5；high conflict 会产生额外扣分。EvaluationService 只返回 `accept`、`revise`、`human_review` 或 `reject`；M5 工作流根据这些结果和版本比较决定是否进入 RevisionAgent。

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

## 工作流 CLI

对已经规划的章节启动、暂停、恢复和查询：

```powershell
uv run storyforge run-workflow --database .\storyforge.db --project-id 1 --chapter-number 1 --scenario improve --max-revision-attempts 2
uv run storyforge run-workflow --database .\storyforge.db --project-id 1 --chapter-number 1 --scenario improve --pause-after evaluate_draft
uv run storyforge resume-workflow --database .\storyforge.db --workflow-run-id 1 --scenario improve
uv run storyforge workflow-status --database .\storyforge.db --workflow-run-id 1
uv run storyforge workflow-history --database .\storyforge.db --workflow-run-id 1
uv run storyforge show-versions --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge compare-versions --database .\storyforge.db --workflow-run-id 1
uv run storyforge cancel-workflow --database .\storyforge.db --workflow-run-id 1
```

Mock 场景为 `pass`、`improve` 和 `stagnate`。生产 provider 不包含场景分支。默认 checkpoint 文件与数据库同目录、文件名后缀为 `.checkpoints.sqlite3`；也可用 `--checkpoint` 显式指定。已完成或已取消的工作流不能 resume。

## HTTP 错误与安全边界

错误响应统一包含 `error`、`message`、`details` 和 `request_id`。资源不存在为 404，状态/并发冲突为 409，输入或领域校验为 422，provider 配置/不可用为 503，provider 超时为 504。响应不包含 traceback、原始数据库错误、Prompt、正文或密钥。

请求可传 `X-Request-ID`，否则服务生成 UUID；响应总是回传同一 header。HTTP 日志只记录 method、path、status、duration 和 request ID，不记录 header、cookie、请求体或响应体。

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
- 普通日志与 WorkflowEvent 只记录 ID、节点、版本、分数、时长和状态，不记录整章正文、Prompt、模型响应或敏感配置。
- 事实匹配是保守、结构化匹配，不是完整语义推理；人物知识边界目前是 JSON 字符串列表。
- StoryRule 的机械匹配依赖 `structured_metadata`；自由文本规则仍作为人类可读依据。
- SQLite 是默认开发路径；未引入 Neo4j、pgvector、Redis、Celery、前端或多媒体能力。
- 当前工作流为同步单进程执行；未引入异步队列、多章节并行、复杂人工审批 UI 或跨进程 worker 调度。
- SQLite checkpointer 适合本地/单进程演示；生产级高并发 checkpoint 后端留待后续阶段。
- 当前没有认证、授权或租户隔离，不应把服务直接暴露到公网；也未实现分布式锁。
- M6 不包含 Docker/Compose、异步任务队列或部署编排；这些属于后续里程碑。

## Roadmap

[ROADMAP.md](ROADMAP.md) 是交付顺序的唯一依据。Milestone 6 已完成；未开始 Milestone 7。

## License

[MIT](LICENSE)
