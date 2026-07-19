# REST API

## M11 Job API

`POST /api/v1/jobs` returns 202. SSE replays `Last-Event-ID`. Controls use the central
state machine. Backpressure returns 429 + `Retry-After`; broker failure returns 503.

Long-running creation endpoints return a real HTTP 202 and a Job/status/events URL:

```text
POST /api/v1/projects/{project_id}/plan/jobs
POST /api/v1/projects/{project_id}/chapters/{chapter_number}/generation-jobs
POST /api/v1/projects/{project_id}/chapters/{chapter_number}/evaluation-jobs
POST /api/v1/projects/{project_id}/chapters/{chapter_number}/workflow-jobs
POST /api/v1/projects/{project_id}/memory/reindex-jobs
```

`GET /api/v1/jobs` filters by status, type, project, chapter ID, and creation range.
Controls, replayable events, SSE, dead-letter retry/discard, `/workers`,
`/workers/health`, and `/queue/health` use content-free response models. Existing
synchronous endpoints remain explicit development/debug compatibility surfaces;
production UI and CLI submit durable jobs.

## 启动与约定

```powershell
$env:STORYFORGE_DATABASE_URL="sqlite:///./storyforge.db"
$env:STORYFORGE_LLM_PROVIDER="mock"
$env:DATABASE_URL=$env:STORYFORGE_DATABASE_URL
uv run alembic upgrade head
uv run uvicorn storyforge.api.app:create_app --factory --reload
```

业务前缀是 `/api/v1`。`/health` 只检查进程存活；`/api/v1/ready` 还检查数据库和 migration revision。Swagger UI 位于 `/docs`，schema 位于 `/openapi.json`。

列表统一返回：

```json
{
  "items": [],
  "meta": {"page": 1, "page_size": 20, "total_items": 0, "total_pages": 0}
}
```

页码从 1 开始，`page_size` 范围 1–100。所有 operation ID 显式指定且唯一。

## 路由

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 兼容存活检查 |
| GET | `/api/v1/health` | API 存活和环境 |
| GET | `/api/v1/ready` | 数据库/迁移就绪 |
| POST/GET | `/api/v1/projects` | 创建/筛选项目 |
| GET/PATCH/DELETE | `/api/v1/projects/{project_id}` | 查询、受限更新、删除空项目 |
| POST/GET | `/api/v1/projects/{project_id}/plan` | 生成/查询规划 |
| GET | `/api/v1/projects/{project_id}/chapters` | 分页查询章节 metadata |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}` | 章节与版本指针 |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/context` | 未来安全上下文摘要 |
| POST | `/api/v1/projects/{project_id}/chapters/{chapter_number}/generate` | 生成并抽取事实 |
| POST | `/api/v1/projects/{project_id}/chapters/{chapter_number}/evaluate` | 单次评估 |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/versions` | 版本历史 |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}` | 版本详情 |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/diff` | 有界版本 diff |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/evaluations` | 评估历史 |
| GET | `/api/v1/projects/{project_id}/chapters/{chapter_number}/evaluations/{evaluation_id}` | 分数、issue、provenance |
| GET | `/api/v1/projects/{project_id}/conflicts` | 筛选冲突 |
| GET/PATCH | `/api/v1/projects/{project_id}/conflicts/{conflict_id}` | 查询/转换冲突状态 |
| GET | `/api/v1/projects/{project_id}/facts` | 仅 accepted facts |
| GET | `/api/v1/projects/{project_id}/facts/{fact_id}` | accepted fact 详情 |
| POST | `/api/v1/projects/{project_id}/chapters/{chapter_number}/workflow` | 同步运行或暂停工作流 |
| GET | `/api/v1/workflow-runs/{workflow_run_id}` | 工作流状态 |
| POST | `/api/v1/workflow-runs/{workflow_run_id}/resume` | 恢复 paused 工作流 |
| POST | `/api/v1/workflow-runs/{workflow_run_id}/cancel` | 节点边界协作式取消 |
| GET | `/api/v1/workflow-runs/{workflow_run_id}/events` | 内容无关的审计事件 |
| GET | `/api/v1/projects/{project_id}/workflow-runs` | 项目工作流历史 |

章节和版本默认不返回正文；详情也需 `include_content=true`。diff 默认只返回统计，显式 `include_unified_diff=true` 才返回受配置长度限制的文本差异。

## 错误、安全与执行语义

错误模型固定为 `error`、`message`、`details`、`request_id`。映射：404 不存在，409 状态/并发冲突，413 请求体过大，422 输入/领域校验，503 provider/配置不可用，504 provider 超时，500 已脱敏内部错误。

请求和响应可通过 `X-Request-ID` 关联。普通日志不记录请求体、响应体、Prompt、正文、header、cookie、密钥或数据库凭据。Fact 查询固定 accepted；`status=candidate` 会返回 422。Context 查询只读取当前章之前可见的 accepted 事实。

旧 workflow 端点仍可在开发/调试中同步执行并返回 201；生产入口使用
`workflow-jobs` 的 202 异步语义。两者不会静默互换。

## M7 容器运行

`storyforge-api` 从 Settings 读取 host、port、log level 与 text/JSON 格式，并用 Uvicorn factory 启动。`/health` 不访问数据库、LLM 或 embedding provider；`/api/v1/ready` 执行数据库 ping 并要求 migration revision 等于 `e8b4a2f7c913`，过期 schema 返回统一 503 `database_not_ready`。

Compose 只向 `127.0.0.1:8000` 发布 API。当前没有认证或授权，不能将端口直接暴露公网。生产部署还需外部 TLS、反向代理、访问控制、密钥管理、限流和备份策略。

## M8 Memory、Retrieval 与 Graph

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/v1/projects/{project_id}/retrieval/search` | 四路混合检索；返回分路计数、degraded reason、来源解释，不返回向量 |
| GET | `/api/v1/projects/{project_id}/memory` | accepted、过去有效 memory 分页列表；默认仅 preview |
| GET | `/api/v1/projects/{project_id}/memory/{memory_id}` | memory 详情；正文需 `include_content=true` |
| GET | `/api/v1/projects/{project_id}/memory/status` | 索引状态、attempt 和计数 |
| POST | `/api/v1/projects/{project_id}/memory/reindex` | 幂等重建 accepted 版本索引 |
| GET | `/api/v1/projects/{project_id}/graph/entities` | accepted 实体列表 |
| GET | `/api/v1/projects/{project_id}/graph/entities/{entity_id}` | 实体详情 |
| GET | `/api/v1/projects/{project_id}/graph/relations` | 按章节边界过滤关系 |
| GET | `/api/v1/projects/{project_id}/graph/neighbors` | 最多 2 hops 的去循环邻居查询 |

`debug=true` 默认禁用；生产强制 reindex 被拒绝。所有路由只适配参数并调用 Application Service。普通响应不包含 embedding 数组、完整 prompt 或默认正文。

## M9 Web proxy 与契约生成

`scripts/export_openapi.py` 从 `create_app()` 导出 `docs/openapi.json`，frontend 的 `openapi-typescript` 生成严格路径/请求/响应类型；CI 重新生成并要求 Git diff 为空。浏览器不直接持有 API origin，只访问同源 `/backend`。Next.js server proxy 使用固定、仅服务端可见的上游，保留 query 与 request ID，限制 header 和 1 MiB body，不转发 cookie 或任意 host。

Web client 对成功响应继续执行 Zod 校验；404、409、413、422、503、504 和 500 统一映射为可展示的安全错误。内部 URL、traceback、Prompt、正文、embedding 和凭据不进入错误详情。

## M10 governance routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/providers` | Secret-free capability registry |
| GET | `/api/v1/providers/health` | Configuration/circuit status; no probe call |
| GET | `/api/v1/projects/{project_id}/usage` | Filtered aggregate usage |
| GET | `/api/v1/projects/{project_id}/usage/calls` | Content-free attempt history |
| GET | `/api/v1/workflow-runs/{workflow_run_id}/usage` | Workflow aggregate usage |
| GET/PUT | `/api/v1/projects/{project_id}/budget` | Read or replace limits only |
| GET | `/api/v1/system/model-profiles` | Allowed profiles |
| GET | `/api/v1/projects/{project_id}/model-settings` | Current profile/policy |
| PATCH | `/api/v1/projects/{project_id}/model-profile` | Select predefined profile |
| PATCH | `/api/v1/projects/{project_id}/privacy-policy` | Select enforced policy |

Usage can filter task/provider/model/status/time. Decimal values serialize as
strings. Clients cannot write spend, arbitrary model names, keys, endpoints, or
pricing. Active workflows block profile/privacy changes with 409. Budget/privacy/
idempotency conflicts use the shared safe error envelope.
