# StoryForge

StoryForge 是一个面向长篇小说创作的分阶段 AI Agent 项目。当前完成到 Milestone 3：可以在完全离线、无 API Key 的环境中，用确定性的 `MockLLMProvider` 跑通“创建项目 → 规划 → 构建上下文 → 生成单章 → 提取并持久化事实”的最小闭环。

尚未实现 Milestone 4 及之后的评估、一致性评分、自动修订、LangGraph 循环、完整业务 API、生产 CLI、Docker 与扩展基础设施。

## 已实现范围

- SQLAlchemy 2 模型、SQLite 默认数据库、可选 PostgreSQL URL、Alembic 迁移。
- Pydantic v2 严格结构化边界和统一 `LLMProvider`。
- `PlannerAgent`、`WriterAgent`、`FactExtractorAgent`，每个 Prompt 均有独立 system/user 名称与显式版本。
- `PlanningService`、防未来信息泄漏且有字符预算的 `ContextBuilder`、`ChapterGenerationService`。
- 章节正文、摘要、事实、人物状态、伏笔状态和完整章节版本快照持久化。
- M3 最小 CLI 和可重复执行的 `demo-m3`。完整 CLI 仍属于 Milestone 6。

架构边界见 [docs/architecture.md](docs/architecture.md)，表结构见 [docs/data-model.md](docs/data-model.md)，事务与失败策略见 [docs/workflow.md](docs/workflow.md)。

## 环境与安装

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --all-groups
uv run python --version
uv run alembic upgrade head
```

默认数据库是 `sqlite:///./storyforge.db`。可通过 `DATABASE_URL` 指向 PostgreSQL；示例只使用安全占位符：

```powershell
$env:DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/storyforge"
uv run alembic upgrade head
```

## M3 离线演示

以下命令不会读取 API Key，也不会访问网络：

```powershell
uv run storyforge demo-m3 --database .\storyforge-m3-demo.sqlite3 --reset
```

输出包含数据库路径、项目状态、规划章节数、上下文预算、章节状态、事实数、版本快照数和 Mock 调用次数。演示数据库可这样清理：

```powershell
Remove-Item -LiteralPath .\storyforge-m3-demo.sqlite3
```

`--reset` 只删除参数明确指定的 SQLite 文件。省略 `--reset` 时，同一数据库中会创建新的项目，因此命令可重复运行。

## 分步 CLI

```powershell
uv run storyforge create-project `
  --database .\storyforge.db `
  --title "雾岬潮汐" `
  --genre "悬疑奇幻" `
  --premise "档案修复师追查随潮汐消失的灯塔。" `
  --chapters 3 `
  --words 1800

uv run storyforge plan --database .\storyforge.db --project-id 1
uv run storyforge show-context --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge generate-chapter --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge show-chapter --database .\storyforge.db --project-id 1 --chapter-number 1
```

已有计划默认拒绝覆盖；只有尚无正文时可显式传 `plan --replace-existing`。已有正文默认拒绝重新生成；显式传 `generate-chapter --regenerate` 后会增加版本号并保留完整旧正文快照。

## 最小 HTTP 服务

当前 HTTP 范围仍只有健康检查；项目和章节业务 API 留在 Milestone 6。

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
uv run alembic downgrade base
```

测试使用 SQLite、`MockLLMProvider` 和 mock transport，禁止公网访问、不要求 Docker 或 API Key，也不使用 `sleep` 模拟等待。更多开发说明见 [docs/development.md](docs/development.md)。

## 安全说明

- 不提交 `.env`、API Key、密码、本地数据库或生成的小说正文。
- Prompt 只接收显式、最小、带类型的上下文，不直接接收完整 ORM 对象。
- Writer 上下文不包含未来章节摘要、未来来源事实、结局方向或角色秘密。
- LLM 输出必须经过 Pydantic v2 验证，不使用字符串切割解析结构化数据。

## Roadmap 与限制

[ROADMAP.md](ROADMAP.md) 是交付顺序的唯一依据。下一阶段是 Milestone 4，但本次交付没有实现其中任何功能。Neo4j、pgvector、Redis、Celery、Web 前端、PDF/ePub、TTS 和图片生成也不在当前范围。

## License

[MIT](LICENSE)
