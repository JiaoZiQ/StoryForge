# Deployment and cold start

## Supported scope

Milestone 7 提供可重复的单机 Docker Compose 开发/验收路径，不代表生产就绪。当前没有认证、队列、多副本共享 checkpoint、TLS、自动备份或高可用。

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
docker compose exec api storyforge --help
docker compose exec api storyforge demo-m7 --output json
docker compose exec api id
```

macOS/Linux 使用 `cp` 和 `curl`。成功状态应为 PostgreSQL healthy、migrate exited 0、API healthy；`id` 应显示 UID 10001。

`docker compose down` 保留 `storyforge_postgres_data`。`docker compose down -v` 仅在明确需要永久删除本地开发数据时使用。

## Local cold start

```powershell
uv sync --locked --all-groups
uv run alembic upgrade head
uv run alembic check
uv run storyforge demo-m6 --output json
uv run uvicorn storyforge.api.app:create_app --factory
```

默认使用 SQLite + MockLLM，无 Docker、API Key 或模型网络依赖。

## Startup contract

Compose 采用独立 migration service：PostgreSQL 通过 `pg_isready` 后，migrate 使用实际连接重试并执行 `alembic upgrade head`；只有退出码 0 才启动 API。API healthcheck 调用 readiness，所以 migration 不完整时不会 healthy。重复 upgrade head 是幂等操作。

## Production configuration

生产至少要设置：

```text
STORYFORGE_ENVIRONMENT=production
STORYFORGE_DATABASE_URL=postgresql+psycopg://...
STORYFORGE_LLM_PROVIDER=openai-compatible
STORYFORGE_LLM_MODEL=...
STORYFORGE_LLM_BASE_URL=...
STORYFORGE_LLM_API_KEY=...
STORYFORGE_MOCK_MODE=false
STORYFORGE_LOG_FORMAT=json
STORYFORGE_ALLOWED_ORIGINS=https://trusted.example
```

不要使用 Compose 的开发密码。凭据应由部署平台运行时注入，不能写入镜像 layer、仓库或日志。API 应位于 TLS 反向代理和网络访问控制之后。

## Operational checks

- `/health` 只证明进程存活。
- `/api/v1/ready` 证明数据库可连接且 revision 为代码 head。
- `alembic current` 和 `alembic check` 用于发布前 schema 检查。
- 结构化日志写 stdout/stderr，不在容器文件系统持久化。
- named volume 需要部署者配置备份、恢复和容量监控。

## Known limitations

工作流请求同步执行；SQLite checkpoint 只适合当前单实例；没有滚动发布、leader election 或 migration lock 服务；没有 Kubernetes、云厂商模板、Redis/Celery 或镜像自动发布。
