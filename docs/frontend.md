# Milestone 9 Web 控制中心

## 页面与职责

- Dashboard 与 Projects：健康状态、最近项目、筛选、分页、创建和项目聚合概览。
- Plan 与 Chapters：规划生成/受保护替换、章节 metadata 列表、按需正文、outline 和上下文。
- Workflow：运行历史、节点事件、条件轮询、合法 resume/cancel；不伪装 WebSocket 实时推送。
- Versions/Evaluations/Conflicts/Facts：服务端 diff、评分来源、冲突生命周期和 accepted-only 长期事实。
- Memory/Retrieval/Graph：索引状态、四路候选/降级原因、来源解释、1/2-hop Cytoscape 图和等价文本视图。
- System：仅展示 health/readiness 的安全字段，不展示环境变量、连接 URL、密钥或 checkpoint。

## 前后端契约

`scripts/export_openapi.py` 从应用工厂生成稳定 `docs/openapi.json`；`openapi-typescript` 生成请求/响应类型。统一 client 使用 `openapi-fetch` 序列化路径和查询参数，成功响应再经过 Zod runtime schema。服务端返回未知形状时前端产生安全的 `invalid_api_response`，不盲信 JSON。

浏览器请求固定发往同源 `/backend`。Next.js Route Handler 读取仅服务端可见的 `STORYFORGE_INTERNAL_API_URL`，对上游路径逐段编码，转发 query、Accept、Content-Type、Authorization 和 request ID；cookie 与任意 host 不转发。503、504 和异常信息被统一为无 traceback 的公共结构。

## 查询策略

TanStack Query key 以 resource、project/chapter/run ID 和 filter 组成。创建/规划/工作流/冲突/reindex mutation 只失效相关 key。工作流 `pending`、`running`、`paused` 时每 3 秒轮询；终态停止。正文和版本正文不预取，避免列表响应或缓存无意持有长篇内容。

## 可访问性与响应式

应用壳层在窄屏使用可关闭导航；表格具备横向滚动，图谱提供键盘可访问的实体/关系按钮列表。Loading 使用 `role=status`，错误使用 `role=alert`，确认框支持初始焦点与 Escape。Playwright 用 axe 检查 serious/critical 违规。

## 限制

M9 是本地/受信网络单用户控制面。没有认证、授权、CSRF 会话、多人编辑、乐观锁 UI、WebSocket、Celery/Redis 或对象存储。同步工作流期间浏览器连接必须保持，生产化需要后续明确里程碑。

## M10 provider governance UI

Global navigation includes Providers. Project navigation includes Usage & Cost,
Budget and Model Settings; workflow detail shows calls, tokens, estimated cost,
fallbacks and rate-limit counts. Usage exposes time/task/model filters and textual
breakdowns by task, model, workflow and day. Estimated and billed values remain
separate; unknown pricing renders as `Unknown`, never zero. Budget spend is read
only and only limits can be submitted. No form accepts provider keys, endpoints or
arbitrary model names. See [ui-workflows.md](ui-workflows.md).
