# REST API

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

工作流目前是同步执行：启动返回 201，只有在完成、进入人工复核或显式暂停后才返回；resume 返回 200。没有后台队列，因此不返回 202。

## M7 容器运行

`storyforge-api` 从 Settings 读取 host、port、log level 与 text/JSON 格式，并用 Uvicorn factory 启动。`/health` 不访问数据库或 LLM；`/api/v1/ready` 执行数据库 ping 并要求 migration revision 等于 `c7d4e1a2b9f0`，过期 schema 返回统一 503 `database_not_ready`。

Compose 只向 `127.0.0.1:8000` 发布 API。当前没有认证或授权，不能将端口直接暴露公网。生产部署还需外部 TLS、反向代理、访问控制、密钥管理、限流和备份策略。
