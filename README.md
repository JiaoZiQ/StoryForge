# StoryForge

StoryForge 是一个面向长篇小说创作的 Python AI Agent 工程。当前完成到 Milestone 7：项目规划、章节生成、事实抽取、机械与 LLM 评估、一致性检测、LangGraph 修订闭环、FastAPI/CLI，以及 Docker Compose + PostgreSQL 的可重复部署路径。

默认本地演示使用 SQLite 和确定性的 `MockLLMProvider`，不需要 API Key，也不访问模型网络。项目尚未生产就绪。

## 当前能力

- 结构化项目、人物、地点、故事规则、章节规划和伏笔。
- 有未来信息边界的 ContextBuilder、WriterAgent 和 FactExtractorAgent。
- MechanicalEvaluator、CriticAgent、ConsistencyChecker 与可解释合并评分。
- LangGraph 多轮修订、最佳版本、候选事实隔离、checkpoint/resume 和审计事件。
- 版本化 REST API、分组 CLI、统一错误结构和默认不返回正文的数据边界。
- SQLite 本地开发、PostgreSQL 16 集成测试、Docker/Compose 冷启动和 CI 门禁。

## 架构

```mermaid
flowchart LR
    API["FastAPI"] --> APP["Application Services"]
    CLI["CLI"] --> APP
    APP --> FLOW["LangGraph workflow"]
    APP --> DOMAIN["Domain services"]
    FLOW --> DOMAIN
    DOMAIN --> AGENTS["Typed Agents"]
    DOMAIN --> EVAL["Mechanical / Consistency / Scoring"]
    DOMAIN --> REPO["Repositories"]
    AGENTS --> LLM["LLMProvider"]
    LLM --> MOCK["MockLLM"]
    LLM --> OPENAI["OpenAI-compatible"]
    REPO --> DB["SQLite / PostgreSQL"]
```

`api` 只适配 HTTP，`cli` 只适配参数和输出，`application` 编排公开用例，`services` 持有业务事务，`repositories` 隔离 SQLAlchemy，`workflows` 只负责状态和路由，`llm` 是模型调用的唯一出口。

## 核心工作流

```text
context → draft → candidate facts → evaluate
  → pass: accept version and promote facts atomically
  → fail: revision brief → revised version → re-extract → re-evaluate → compare
  → retry / accept / needs human review
```

未接受版本的事实由数据库状态与版本外键隔离；普通 Fact API 和后续章节上下文只读取 accepted 且在章节时间边界内的事实。

## 技术栈

- Python 3.12、Pydantic v2、SQLAlchemy 2、Alembic
- FastAPI、Uvicorn、LangGraph、SQLite checkpointer
- SQLite（默认本地）与 PostgreSQL 16（Compose/部署验证）
- uv、pytest/coverage、Ruff、strict mypy、GitHub Actions

## 本地快速启动

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --locked --all-groups
uv run alembic upgrade head
uv run storyforge demo-m6 --output human
uv run uvicorn storyforge.api.app:create_app --factory
```

macOS/Linux 命令相同。打开 `http://127.0.0.1:8000/health`、`/api/v1/ready` 或 `/docs`。默认数据库是仓库根目录的 `storyforge.db`；该文件已被 Git 忽略。

## Docker 快速启动

Docker Desktop 或 Docker Engine + Compose plugin 均可。仓库不需要 `.env` 才能使用安全的本地开发默认值；如果希望显式检查配置：

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

macOS/Linux：

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Compose 启动顺序是 `postgres healthy → migrate successful → api`。服务只绑定 `127.0.0.1`：API 为 8000，PostgreSQL 为 54329。结束时执行：

```bash
docker compose down
```

该命令保留 named volume。只有明确要删除本地 StoryForge 开发数据时才运行 `make docker-reset` 或 `docker compose down -v`。

## SQLite Mock 模式

development 默认配置是 SQLite + MockLLM。以下流程完全离线：

```powershell
uv run alembic upgrade head
uv run storyforge demo-m6 --output json
```

`demo-m6` 使用自动清理的临时 SQLite，覆盖应用服务、规划、修订工作流、版本、评估、冲突、facts 和事件查询。

## PostgreSQL 模式

Compose 默认使用 PostgreSQL 16 和仅限本机开发的凭据 `storyforge-dev-only`。它不得用于生产。手动连接本地 Compose 数据库时：

```powershell
$env:DATABASE_URL="postgresql+psycopg://storyforge:storyforge-dev-only@127.0.0.1:54329/storyforge_dev"
uv run alembic current
```

生产必须显式配置 PostgreSQL URL、非 Mock provider、真实模型和密钥，并设置 `STORYFORGE_MOCK_MODE=false`。密码中的特殊字符必须进行 URL percent-encoding。

## 环境变量

| 变量 | development 默认 | 说明 |
|---|---:|---|
| `STORYFORGE_ENVIRONMENT` | `development` | `development`、`test`、`production` |
| `STORYFORGE_DATABASE_URL` | `sqlite:///./storyforge.db` | 应用数据库；test/production 必须显式提供 |
| `STORYFORGE_LLM_PROVIDER` | `mock` | `mock` 或 `openai-compatible` |
| `STORYFORGE_LLM_MODEL` | `mock-storyforge-v1` | Provider 模型名 |
| `STORYFORGE_LLM_BASE_URL` | OpenAI v1 URL | OpenAI-compatible base URL |
| `STORYFORGE_LLM_API_KEY` | 空 | `SecretStr`，不得提交或记录 |
| `STORYFORGE_MOCK_MODE` | `true` | production 必须为 false |
| `STORYFORGE_AUTO_MIGRATE` | `false` | 本地入口可选；Compose 使用独立 migrate 服务 |
| `STORYFORGE_API_HOST` | `127.0.0.1` | 容器内为 `0.0.0.0` |
| `STORYFORGE_API_PORT` | `8000` | Uvicorn 端口 |
| `STORYFORGE_LOG_LEVEL` | `INFO` | 标准日志级别 |
| `STORYFORGE_LOG_FORMAT` | `text` | `text` 或 `json` |
| `STORYFORGE_ALLOWED_ORIGINS` | 空 | 逗号分隔 CORS origin |
| `STORYFORGE_CORS_ALLOW_CREDENTIALS` | `false` | 为 true 时禁止 `*` origin |
| `STORYFORGE_REQUEST_BODY_LIMIT` | `1048576` | 最大请求体字节数 |
| `STORYFORGE_MAX_REVISION_ATTEMPTS` | `3` | 修订上限 |
| `STORYFORGE_CHECKPOINT_PATH` | 自动 | SQLite checkpoint 文件 |
| `STORYFORGE_DATABASE_WAIT_ATTEMPTS` | `30` | 有界数据库连接重试次数 |
| `STORYFORGE_DATABASE_WAIT_INTERVAL_SECONDS` | `1` | 重试间隔 |

完整安全示例见 [.env.example](.env.example)。StoryForge 不会隐式加载 `.env`；Compose 仅用它做变量插值。

## Migration

应用启动不会默认修改 schema。显式运行：

```powershell
$env:DATABASE_URL=$env:STORYFORGE_DATABASE_URL
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Compose 的 one-shot `migrate` 服务等待真实数据库连接后执行 `upgrade head`；失败时 `api` 不会通过依赖门禁启动。readiness 还会检查数据库 revision 等于代码声明的 head。

## API

API 前缀为 `/api/v1`。主要资源包括 projects、planning、chapters/context、versions/diff、evaluations、conflicts、accepted facts、workflow runs/events。完整路由见 [docs/api.md](docs/api.md)。

- `/health`：仅进程存活，不调用数据库或 LLM。
- `/api/v1/ready`：检查数据库和精确 migration head。
- 错误统一包含 `error`、`message`、`details`、`request_id`。
- 章节和版本列表默认不含正文；正文必须显式 `include_content=true`。

## Swagger

API 启动后访问：

- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## CLI

```powershell
uv run storyforge --help
uv run storyforge project list --database .\storyforge.db --output json
uv run storyforge chapter list --database .\storyforge.db --project-id 1
uv run storyforge workflow events --database .\storyforge.db --workflow-run-id 1
```

分组 CLI 与 REST API 复用 Application Service。`--output json` 只向 stdout 输出一个标准 JSON 文档；错误使用稳定退出码和 stderr JSON。详见 [docs/cli.md](docs/cli.md)。

## demo-m6

```powershell
uv run storyforge demo-m6 --output human
uv run storyforge demo m6 --output json
```

使用临时 SQLite + MockLLM；适合无 Docker 的本地功能验证。

## demo-m7

```powershell
docker compose exec api storyforge demo-m7 --output human
docker compose exec api storyforge demo-m7 --output json
```

使用当前配置的 PostgreSQL + MockLLM，不创建临时 SQLite。每次创建唯一项目并验证 accepted version、修订、评估、冲突、accepted facts、候选/未来事实不可见和全部重复计数为 0。重复运行安全。

## 测试

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic check
git diff --check
```

pytest 默认运行 SQLite/单元测试并跳过未配置的 `postgres` marker；coverage 门槛为 80%。

## PostgreSQL 测试

必须使用名称以 `_test` 结尾的独立数据库。测试启动会拒绝其他数据库名，并会清空该测试数据库。

```powershell
docker run -d --name storyforge-postgres-test -e POSTGRES_USER=storyforge -e POSTGRES_PASSWORD=storyforge-test-only -e POSTGRES_DB=storyforge_test -p 127.0.0.1:54330:5432 postgres:16-bookworm
$env:STORYFORGE_POSTGRES_TEST_URL="postgresql+psycopg://storyforge:storyforge-test-only@127.0.0.1:54330/storyforge_test"
$env:DATABASE_URL=$env:STORYFORGE_POSTGRES_TEST_URL
$env:STORYFORGE_DATABASE_URL=$env:STORYFORGE_POSTGRES_TEST_URL
uv run pytest -m postgres --no-cov
docker rm -f storyforge-postgres-test
```

macOS/Linux 将 `$env:NAME="value"` 改为 `export NAME="value"`。

## Docker 测试

```powershell
docker compose config
docker build -t storyforge:test .
docker run --rm storyforge:test storyforge --help
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready
docker compose exec api alembic check
docker compose exec api storyforge demo-m7 --output json
docker compose exec api id
docker compose down
```

macOS/Linux 使用 `curl` 替代 `Invoke-RestMethod`。

## 一键命令

Makefile 提供 `setup`、`lint`、`typecheck`、`test`、`test-postgres`、`migrate`、`api`、`demo`、`docker-build`、`docker-up`、`docker-test`、`clean` 和显式危险操作 `docker-reset`。Windows 没有 make 时直接使用上文对应的 `uv`/Docker 命令。

`make clean` 只删除仓库内的工具缓存、coverage 和构建产物，不删除 `.env`、数据库或 Docker volume。

## 项目目录

```text
src/storyforge/{agents,api,application,cli,consistency,evaluation,llm,models,
                prompts,repositories,revision,services,workflows}
alembic/versions/      schema history
tests/{unit,integration}
docs/                  architecture, workflows, API, CLI, deployment, ADRs
Dockerfile             locked multi-stage runtime image
docker-compose.yml     PostgreSQL → migration → API
```

## 数据模型

Project 拥有 Character、Location、StoryRule、Chapter、Fact 和 WorkflowRun。Chapter 是逻辑身份，ChapterVersion 保存不可变正文；Evaluation/Conflict/Fact 绑定具体版本。WorkflowRun/WorkflowEvent/VersionComparison 提供恢复和审计。详见 [docs/data-model.md](docs/data-model.md)。

## 当前限制

- API 无认证、授权、速率限制或多租户隔离，不得直接暴露公网。
- 工作流仍是同步单进程调用；没有 Redis、Celery 或分布式 worker。
- checkpoint 使用 SQLite 文件，适合当前单实例演示，不适合多副本共享。
- PostgreSQL 已通过迁移与集成测试，但没有完成生产容量、备份恢复或高可用验证。
- 未实现 Neo4j、pgvector 语义检索、前端、PDF/ePub/TTS/图片和全书级评审。

## 安全警告

不要提交 `.env`、API Key、数据库密码、生成正文或本地数据库。生产日志支持 JSON，应用访问日志只记录 request ID、方法、路径、状态和耗时，并对常见密钥/连接 URL 脱敏。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## Roadmap

[ROADMAP.md](ROADMAP.md) 是交付顺序的唯一依据。Milestone 7 已完成；本次没有开始后续里程碑。

## Contributing

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。所有变更必须通过 Ruff、strict mypy、pytest/coverage 和适用的 migration/PostgreSQL 检查。

## License

项目采用 [MIT License](LICENSE)。
