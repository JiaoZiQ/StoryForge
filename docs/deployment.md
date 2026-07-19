# Deployment and cold start

## M11 services

Compose adds internal Redis, an outbox dispatcher, and two non-root workers. Migration
and Redis gate startup; queue readiness checks Redis. Expiring leases recover work.

## Supported scope

Milestone 11 在 PostgreSQL 16 + pgvector Compose 路径上增加内部 Redis、事务
outbox dispatcher、双 worker 和 Next.js Job Center。这不代表生产就绪；当前没有
认证、多租户、跨主机 LangGraph checkpoint、TLS、自动备份或高可用。

## Docker cold start

新 clone 不需要真实密钥：

```powershell
Copy-Item .env.example .env
docker compose config
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready
Invoke-RestMethod http://127.0.0.1:8000/openapi.json
Invoke-WebRequest http://127.0.0.1:3000
docker compose exec api storyforge --help
docker compose exec -T api storyforge demo-m11
docker compose exec -T api storyforge worker-status
docker compose exec api id
docker compose exec frontend id
```

macOS/Linux 使用 `cp` 和 `curl`。成功状态应为 pgvector PostgreSQL、Redis、API、
frontend、dispatcher 和两个 worker healthy，migrate exited 0；两个 `id` 都应显示
UID 10001。`SELECT extversion FROM pg_extension WHERE extname='vector'` 应返回 0.8.2。

`docker compose down` 保留 `storyforge_postgres_data`。`docker compose down -v` 仅在明确需要永久删除本地开发数据时使用。

## Local cold start

```powershell
uv sync --locked --all-groups
uv run alembic upgrade head
uv run alembic check
uv run storyforge demo-m6 --output json
uv run uvicorn storyforge.api.app:create_app --factory
Set-Location frontend
npm ci
npm run dev
```

默认使用 SQLite + MockLLM，无 Docker、API Key 或模型网络依赖。

## Startup contract

Compose 采用独立 migration service：PostgreSQL 通过 `pg_isready` 后，migrate 使用实际连接重试并执行 `alembic upgrade head`；只有退出码 0 才启动 API。API healthcheck 调用 readiness，所以 migration 不完整时不会 healthy；frontend 又等待 API healthy。重复 upgrade head 是幂等操作。

API、migration、frontend、Redis、dispatcher 和 worker 只加入 `internal: true` 的
backend network，因此 Mock provider 进程无公网出口。无凭据 Node gateway 同时连接
backend 与普通 ingress network，把 3000/8000 端口发布到 `127.0.0.1`；PostgreSQL
仅为本地诊断加入 ingress 并发布 54329。镜像构建阶段可以从 registry 安装锁定依赖，
但 `.dockerignore` 排除 `.env`、Git 历史、本地数据库、测试 artifact 和 node_modules。

## Production configuration

生产至少要设置：

```text
STORYFORGE_ENVIRONMENT=production
STORYFORGE_DATABASE_URL=postgresql+psycopg://...
STORYFORGE_LLM_PROVIDER=openai-compatible
STORYFORGE_LLM_MODEL=...
STORYFORGE_LLM_BASE_URL=...
STORYFORGE_LLM_API_KEY=...
STORYFORGE_EMBEDDING_PROVIDER=openai-compatible
STORYFORGE_EMBEDDING_MODEL=...
STORYFORGE_EMBEDDING_BASE_URL=...
STORYFORGE_EMBEDDING_API_KEY=...
STORYFORGE_MOCK_MODE=false
STORYFORGE_LOG_FORMAT=json
STORYFORGE_ALLOWED_ORIGINS=https://trusted.example
STORYFORGE_INTERNAL_API_URL=http://api:8000
```

不要使用 Compose 的开发密码。凭据应由部署平台运行时注入，不能写入镜像 layer、仓库或日志。API 应位于 TLS 反向代理和网络访问控制之后。

## Operational checks

- `/health` 只证明进程存活。
- `/api/v1/ready` 证明数据库可连接且 revision 为代码 head。
- `alembic current` 和 `alembic check` 用于发布前 schema 检查。
- 结构化日志写 stdout/stderr，不在容器文件系统持久化。
- named volume 需要部署者配置备份、恢复和容量监控。
- memory 索引为同步、可重试流程；生产需要监控 `memory_index_records.status=failed`。

## Known limitations

长任务由 Redis/Dramatiq worker 异步执行；PostgreSQL 仍是 Job 与业务状态权威。
当前没有认证/RBAC、Kubernetes、滚动发布、leader election 或 migration lock 服务。

## Milestone 10 operational controls

Compose remains offline/mock by default and sets `MODEL_PROFILE=offline`,
`PRIVACY_POLICY=offline`, finite project/workflow budgets, bounded retries,
rate/concurrency limits, and a disabled real-smoke flag. Provider health endpoints
report configuration and process-local circuit state without making a billable
network call. Queue-mode rate limits and circuits are shared across workers through
Redis; development inline mode may explicitly use process-local fallback.

Before enabling an external provider, supply a validated registry/pricing file,
server-side secret, strict/standard policy, and explicit budget. Unknown price is
blocked by default. Monitor `provider_calls`, budget reservations, failed usage,
and open circuits; estimated cost is not the provider invoice.
