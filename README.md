# StoryForge

> Milestone 12 extends the accepted single-chapter workflow into a durable whole-book
> run. It remains an engineering prototype: it does not claim publication-quality
> autonomous writing, has no authentication, and does not export PDF, DOCX, or ePub.

## Milestone 12 whole-book workflow

`BookRun` is a PostgreSQL-authoritative top-level Job. The default `sequential` mode
accepts chapters in order; `dependency_aware` only permits bounded preparation work in
parallel because later prose depends on earlier accepted facts. Each chapter still uses
the M5 chapter workflow, immutable `ChapterVersion` history, governed providers, the M8
memory/graph index, and the M11 Job/Outbox/lease/SSE reliability boundary.

After every configured chapter interval and at completion, StoryForge checks the global
timeline, character state/knowledge/relationship arcs, foreshadowing, adjacent-chapter
transitions, pacing, and repeated scenes. PostgreSQL uses pgvector cosine distance for
semantic repetition candidates; a high similarity is evidence for review, not an
automatic verdict. The full-book critic receives compressed summaries and rule results,
never the unconditional manuscript.

An immutable `BookSnapshot` stores only a stable chapter-to-version map and content hash.
Critical global conflicts, a weak ending, a broken key character arc, or insufficient
important-foreshadowing payoff block automatic acceptance. A bounded revision plan
selects only priority chapters, preserves old accepted versions, marks affected later
chapters for recheck, and stops at the configured global-round or budget limit.

Book runs can be watched, paused, resumed, or cancelled through API, CLI, or the Web
Book workspace. PostgreSQL is authoritative; Redis messages contain only safe Job IDs.
Resume reuses completed chapter jobs, provider idempotency records, evaluations, facts,
memory, snapshots, and costs.

```powershell
# Local offline smoke (SQLite fallback; Mock providers only)
uv sync --locked --all-groups
uv run alembic upgrade head
uv run storyforge demo-m12 --output human

# PostgreSQL + Redis distributed demo
docker compose --env-file .env.example up --build -d --scale dispatcher=2 --scale worker=2
docker compose --env-file .env.example exec api storyforge demo-m12 --output human

# Public CLI surface
uv run storyforge book run --project-id 1 --wait
uv run storyforge book status --book-run-id 1 --output json
uv run storyforge book watch --book-run-id 1
uv run storyforge book snapshots --project-id 1
uv run storyforge book timeline --snapshot-id 1
uv run storyforge book characters --snapshot-id 1
uv run storyforge book foreshadowing --snapshot-id 1
uv run storyforge book pacing --snapshot-id 1
uv run storyforge book revision-plan --snapshot-id 1
```

Book budgets cap estimated cost, total tokens, provider calls, per-chapter work, global
review, and global revision. Mock mode requires no API key and never calls the network.
See [book runs](docs/book-runs.md), [book evaluation](docs/book-evaluation.md), and
[book revision](docs/book-revision.md) for exact state, scoring, and recovery rules.

> Milestone 11 adds durable asynchronous jobs, a PostgreSQL transactional outbox,
> Redis/Dramatiq workers, replayable SSE progress, leases, and dead-letter handling.
> Mock execution remains offline; Milestone 12 has not started.

## Milestone 11 asynchronous execution

`POST /api/v1/jobs` returns `202` with a stable Job ID. PostgreSQL owns Job,
JobEvent, OutboxMessage, and WorkerRecord state; Redis transports only Job IDs.
Progress is replayed at `/api/v1/jobs/{id}/events` or followed with SSE at
`/api/v1/jobs/{id}/events/stream`. The Web Job Center falls back to polling.

```powershell
docker compose up --build --detach --wait
docker compose exec -T api storyforge demo-m11
storyforge job list
storyforge worker-status
```

Compose runs internal Redis, a dispatcher, and two non-root workers. Pause/cancel
are cooperative at workflow node boundaries; retry is bounded and exhausted jobs
enter the dead-letter state. Workers register before their first Job, keep idle
heartbeats, and become `offline` after the configured stale threshold.
MockLLM/MockEmbedding require no API key.

Short reads and explicit development/debug compatibility endpoints remain
synchronous. Production long actions use durable 202 Job endpoints. Delivery is
at least once and business side effects are idempotent; StoryForge does not claim
exactly-once. Redis carries Job IDs, Pub/Sub wake-ups, distributed rate limits, and
circuit state, while PostgreSQL remains the final source of truth. Redis flush is
recoverable from queued Jobs and published outbox intent. There is currently no
authentication or cross-project scheduling fairness guarantee, and Kafka is not
used. Operational details: [async jobs](docs/async-jobs.md),
[queue](docs/queue.md), and [SSE](docs/sse.md).

## Milestone 10 provider governance

Every LLM and embedding request now passes through one governed boundary:

```text
typed task -> registered model route -> privacy/redaction -> budget reservation
-> rate limit + circuit -> bounded retry/fallback -> provider
-> token/pricing snapshot -> content-free ProviderCall audit
```

- Profiles are predefined (`offline`, `economy`, `balanced`, `quality`); clients
  cannot submit arbitrary model names, endpoints, or credentials.
- Privacy is explicit: `offline` blocks external egress, `strict` minimizes and
  redacts external input, and `standard` sends only task-required context.
- Costs use `Decimal`, immutable versioned pricing snapshots, and distinct
  estimated/billed fields. Unknown pricing is blocked unless explicitly allowed.
- Project hard budgets reserve before a call; workflow call/token/cost ceilings
  are also enforced. Budget or privacy failures never fall back to another model.
- Audits contain identifiers, hashes, token counts, status, latency, and pricing
  provenance—never prompt text, chapter bodies, keys, base URLs, or embeddings.

Safe inspection commands:

```powershell
uv run storyforge provider list --output json
uv run storyforge provider health --output json
uv run storyforge usage summary --project-id 1 --output json
uv run storyforge usage calls --project-id 1 --output json
uv run storyforge budget show --project-id 1 --output json
uv run storyforge budget set --project-id 1 --soft-limit 1 --hard-limit 2 --yes --output json
uv run storyforge model-profile set --project-id 1 --profile balanced --yes --output json
uv run storyforge privacy-policy set --project-id 1 --policy strict --yes --output json
docker compose exec api storyforge demo-m10 --output json
```

`demo-m10` requires PostgreSQL + pgvector but uses MockLLM/MockEmbedding, no API
key, and no provider network. It demonstrates success accounting, retry after 429,
timeout fallback, circuit opening, budget preflight blocking, and durable duplicate
suppression. The Web UI exposes Providers plus project Usage & Cost, Budget, and
Model Settings pages; workflow detail includes aggregate calls/tokens/cost.

An optional real smoke test sends only a tiny fixed JSON probe, never story data:

```powershell
$env:STORYFORGE_LLM_PROVIDER="openai-compatible"
$env:STORYFORGE_ENABLE_REAL_PROVIDER_TESTS="true"
uv run storyforge provider smoke-test --provider openai-compatible --output json
```

Configure the key and endpoint only through local ignored environment settings.
The smoke test may incur provider cost and remains disabled by default. See
[provider configuration](docs/providers.md), [routing](docs/model-routing.md),
[cost management](docs/cost-management.md), [reliability](docs/reliability.md),
and [privacy](docs/privacy.md).

StoryForge 是一个面向长篇小说创作的 AI Agent 工程。当前实现到 Milestone 11：
在规划、生成、评估、修订、长期记忆与 Provider 治理之上，增加持久化异步任务、
事务 outbox、Redis/Dramatiq worker、租约恢复和进度事件。

默认本地演示使用 SQLite 和确定性的 `MockLLMProvider`，不需要 API Key，也不访问模型网络。项目尚未生产就绪。

## 当前能力

- 结构化项目、人物、地点、故事规则、章节规划和伏笔。
- 有未来信息边界的 ContextBuilder、WriterAgent 和 FactExtractorAgent。
- MechanicalEvaluator、CriticAgent、ConsistencyChecker 与可解释合并评分。
- LangGraph 多轮修订、最佳版本、候选事实隔离、checkpoint/resume 和审计事件。
- 版本化 REST API、分组 CLI、统一错误结构和默认不返回正文的数据边界。
- accepted ChapterVersion 的确定性切分、Mock/OpenAI-compatible embedding 抽象和可重试索引状态。
- Keyword、pgvector、Fact、Graph 四路检索，weighted RRF 去重融合、确定性重排和来源解释。
- ContextBuilder 将过去且 accepted 的 hybrid hits 放在可选预算末尾；项目、当前大纲和 active rules 永不被检索结果挤掉。
- SQLite 降级开发、PostgreSQL 16 + pgvector 集成测试、Docker/Compose 冷启动和 CI 门禁。
- Next.js App Router + TypeScript strict Web UI，覆盖项目、规划、章节、工作流、版本、评估、冲突、事实、Memory、Retrieval、Graph 与系统状态。
- PostgreSQL 权威 Job/JobEvent/OutboxMessage/WorkerRecord、Redis 传输、双 worker、
  有界 retry/DLQ、协作式 pause/cancel 和 SSE/轮询 Job Center。
- 前端通过同源 server proxy 调用 FastAPI；OpenAPI 生成 TypeScript 类型，Zod 在运行时校验响应，浏览器不读取 provider key 或数据库凭据。

## 架构

```mermaid
flowchart LR
    API["FastAPI"] --> APP["Application Services"]
    WEB["Next.js Web UI"] --> PROXY["Same-origin server proxy"]
    PROXY --> API
    CLI["CLI"] --> APP
    APP --> JOB["Job Service / Outbox"]
    DISP["Dispatcher"] --> REDIS["Redis / Dramatiq"]
    REDIS --> WORKER["Worker pool"]
    WORKER --> APP
    JOB --> DB
    DISP --> DB
    APP --> FLOW["LangGraph workflow"]
    APP --> DOMAIN["Domain services"]
    FLOW --> DOMAIN
    DOMAIN --> AGENTS["Typed Agents"]
    DOMAIN --> EVAL["Mechanical / Consistency / Scoring"]
    DOMAIN --> REPO["Repositories"]
    DOMAIN --> MEMORY["Memory index / Hybrid retrieval"]
    MEMORY --> EMBED["EmbeddingProvider"]
    MEMORY --> GRAPH["Relational graph"]
    AGENTS --> LLM["LLMProvider"]
    LLM --> MOCK["MockLLM"]
    LLM --> OPENAI["OpenAI-compatible"]
    REPO --> DB["SQLite / PostgreSQL + pgvector"]
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
- SQLite（降级本地）与 PostgreSQL 16 + pgvector（完整混合检索）
- uv、pytest/coverage、Ruff、strict mypy、GitHub Actions
- Next.js 16、React 19、TypeScript strict、Tailwind CSS、TanStack Query、React Hook Form、Zod、Cytoscape.js
- Vitest、React Testing Library、Playwright 与 axe-core

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

Compose 启动顺序是 `pgvector PostgreSQL healthy → migrate successful → api healthy → frontend healthy`。M8 migration 创建 `vector` extension、`vector(64)` 列和 cosine HNSW 索引；M9 不新增 migration。服务只绑定 `127.0.0.1`：Web 为 3000、API 为 8000、PostgreSQL 为 54329。打开 `http://127.0.0.1:3000`。结束时执行：

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

Compose 默认使用 PostgreSQL 16 + pgvector 0.8.2 和仅限本机开发的凭据 `storyforge-dev-only`。它不得用于生产。手动连接本地 Compose 数据库时：

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
| `STORYFORGE_EMBEDDING_PROVIDER` | `mock` | `mock` 或 `openai-compatible`，与 LLM 独立 |
| `STORYFORGE_EMBEDDING_MODEL` | `mock-hash-embedding-v1` | embedding 模型名 |
| `STORYFORGE_EMBEDDING_BASE_URL` | OpenAI v1 URL | embedding 专用 base URL |
| `STORYFORGE_EMBEDDING_API_KEY` | 空 | embedding 专用 `SecretStr` |
| `STORYFORGE_EMBEDDING_DIMENSIONS` | `64` | 必须与当前数据库 `vector(64)` 一致 |
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

API 前缀为 `/api/v1`。主要资源包括 projects、planning、chapters/context、versions/diff、evaluations、conflicts、accepted facts、workflow runs/events，以及 M8 memory/retrieval/graph。完整路由见 [docs/api.md](docs/api.md)。

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

## demo-m8

```powershell
docker compose exec api storyforge demo-m8 --output human
docker compose exec api storyforge demo-m8 --output json
```

该演示要求 PostgreSQL 的 `vector` extension、MockLLM 和 MockEmbedding，不读取 API Key，也不访问外部模型网络。它生成并修订第一章、索引 accepted v2、运行 Keyword/Vector/Fact/Graph 四路检索、构建第二章上下文，并检查 candidate/rejected/superseded/future 隔离与 chunk/entity/relation 幂等。

常用查询：

```powershell
docker compose exec api storyforge memory status --project-id 1 --output json
docker compose exec api storyforge memory list --project-id 1 --output json
docker compose exec api storyforge retrieval search --project-id 1 --query "Mara brass key" --current-chapter 2 --output json
docker compose exec api storyforge graph entities --project-id 1 --output json
docker compose exec api storyforge graph relations --project-id 1 --current-chapter 2 --output json
```

列表和检索响应不返回 embedding 数组；memory 正文默认只返回 preview，完整内容需要显式 `include_content`。

## Web UI 与 demo-m9

本地前后端开发：

```powershell
uv run uvicorn storyforge.api.app:create_app --factory
Set-Location frontend
npm ci
npm run dev
```

浏览器只访问 `http://127.0.0.1:3000`；`/backend/*` 由 Next.js server proxy 转发到固定的 `STORYFORGE_INTERNAL_API_URL`。不要把 provider key 写入 `NEXT_PUBLIC_*`。Compose 中可用以下命令准备一个包含修订、评估、冲突、accepted memory 和图谱的演示项目：

```powershell
docker compose exec api storyforge demo-m9 --frontend-url http://localhost:3000 --output json
```

输出的 `frontend_url` 可直接打开。命令只返回标识符和计数，不返回正文、Prompt、embedding 或凭据；要求 PostgreSQL + pgvector、MockLLM、MockEmbedding，且运行时 Compose 网络禁止访问公网。更多说明见 [frontend/README.md](frontend/README.md)。

## 测试

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic check
git diff --check
Set-Location frontend
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

pytest 默认运行 SQLite/单元测试并跳过未配置的 `postgres` marker；coverage 门槛为 80%。

## PostgreSQL 测试

必须使用名称以 `_test` 结尾的独立数据库。测试启动会拒绝其他数据库名，并会清空该测试数据库。

```powershell
docker run -d --name storyforge-postgres-test -e POSTGRES_USER=storyforge -e POSTGRES_PASSWORD=storyforge-test-only -e POSTGRES_DB=storyforge_test -p 127.0.0.1:54330:5432 pgvector/pgvector:0.8.2-pg16-bookworm
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
docker build -f frontend/Dockerfile -t storyforge-web:test .
docker run --rm storyforge:test storyforge --help
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready
docker compose exec api alembic check
docker compose exec api storyforge demo-m9 --frontend-url http://localhost:3000 --output json
docker compose exec api id
docker compose exec frontend id
docker compose down
```

macOS/Linux 使用 `curl` 替代 `Invoke-RestMethod`。

## 一键命令

Makefile 还提供 `frontend-install`、`frontend-lint`、`frontend-test`、`frontend-build` 和 `frontend-e2e`。Windows 没有 make 时直接使用上文对应的 `uv`、`npm` 与 Docker 命令。

`make clean` 只删除仓库内的工具缓存、coverage 和构建产物，不删除 `.env`、数据库或 Docker volume。

## 项目目录

```text
src/storyforge/{agents,api,application,cli,consistency,embeddings,evaluation,graph,
                llm,memory,models,prompts,repositories,retrieval,revision,services,workflows}
alembic/versions/      schema history
tests/{unit,integration}
frontend/               Next.js App Router Web UI、Vitest 与 Playwright
docs/                  architecture, workflows, API, CLI, deployment, ADRs
Dockerfile             locked Python multi-stage runtime image
frontend/Dockerfile    locked Node multi-stage non-root runtime image
docker-compose.yml     PostgreSQL → migration → API → frontend
```

## 数据模型

Project 拥有 Character、Location、StoryRule、Chapter、Fact、MemoryChunk、GraphEntity 和 WorkflowRun。Chapter 是逻辑身份，ChapterVersion 保存不可变正文；Evaluation/Conflict/Fact/MemoryChunk 绑定具体版本。WorkflowRun/WorkflowEvent/VersionComparison 提供恢复和审计。详见 [docs/data-model.md](docs/data-model.md)、[docs/memory.md](docs/memory.md)、[docs/retrieval.md](docs/retrieval.md) 和 [docs/graph.md](docs/graph.md)。

## 当前限制

- API 无认证、授权、速率限制或多租户隔离，不得直接暴露公网。
- 长任务通过 PostgreSQL 任务/事件/事务 outbox 和 Redis-backed Dramatiq worker
  执行；短查询仍保持同步。
- LangGraph checkpoint 仍使用 SQLite 文件；Compose 通过单机 named volume 在 API
  与 worker 间共享。任务状态、租约和事件以 PostgreSQL 为权威，但该文件方案不支持
  跨主机高可用或并发写扩展。
- PostgreSQL 已通过迁移与集成测试，但没有完成生产容量、备份恢复或高可用验证。
- 图谱当前保存在 PostgreSQL 关系表中，查询最多 2 hops；没有 Neo4j 或完整语义实体消歧。
- MockEmbedding 是确定性测试向量，不代表生产语义质量；数据库维度当前固定为 64。
- Web UI 是可信本地/单用户控制面，没有认证、RBAC 或多人协作；Job Center 使用
  SSE，并在断连时退化为轮询。
- 未实现 Elasticsearch、LLM reranker、PDF/ePub/TTS/图片和全书级评审。

## 安全警告

不要提交 `.env`、API Key、数据库密码、生成正文或本地数据库。生产日志支持 JSON，应用访问日志只记录 request ID、方法、路径、状态和耗时，并对常见密钥/连接 URL 脱敏。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## Roadmap

[ROADMAP.md](ROADMAP.md) 是交付顺序的唯一依据。Milestone 11 已完成独立验收；
Milestone 12 尚未开始。

## Contributing

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。所有变更必须通过 Ruff、strict mypy、pytest/coverage 和适用的 migration/PostgreSQL 检查。

## License

项目采用 [MIT License](LICENSE)。
