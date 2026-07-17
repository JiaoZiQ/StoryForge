# ADR 0008：同源 Web 控制中心与生成式 API 契约

状态：Accepted

## 背景

M9 需要在不改变 M1–M8 核心服务、数据隔离和同步工作流语义的前提下提供可视化控制面。浏览器不能获得 provider key、数据库 URL、完整 checkpoint 或默认正文，也不能把前端变成第二套业务实现。

## 决策

1. 使用 Next.js App Router + React + TypeScript strict；页面和 hooks 只调用 FastAPI，不访问 ORM、LLM SDK 或环境密钥。
2. 从 FastAPI OpenAPI 生成 TypeScript 类型，同时用手写、宽松但关键字段严格的 Zod schema 做运行时校验。生成文件必须在 CI 中检查漂移。
3. 浏览器只请求同源 `/backend`。Next.js Route Handler 从服务端环境读取固定 API origin，使用 path 编码、header allowlist、1 MiB body 上限和统一安全错误，避免公开内部拓扑和任意代理。
4. TanStack Query 管理缓存与 mutation 失效。工作流只在非终态按 3 秒轮询；没有后台队列时不声称 WebSocket 或异步执行。
5. 章节/版本正文按需获取；Fact 固定 accepted；Memory/Graph/Retrieval 继续依赖 API 的项目、版本、状态和未来章节过滤，不在 UI 复制规则。
6. Cytoscape 只做展示，查询最多 2 hops，并提供等价文本列表。服务端 diff、评分和冲突状态仍是唯一事实来源。
7. 前端使用 Node 24 多阶段、UID 10001 非 root standalone 镜像；Compose 等待 API healthy 后启动前端。API/frontend 仅连接 internal network，另用不持有凭据的非 root Node gateway 发布本机端口，保证 Mock provider 进程无公网出口。
8. M9 不新增数据库表或 migration；演示命令组合既有 M8 应用服务并返回无正文的安全 Web URL 摘要。

## 后果

优点是 API 仍是唯一业务边界，类型漂移可检测，浏览器 bundle 无密钥，控制面可离线、可容器化、可测试。代价是 OpenAPI 类型和 Zod schema 需要同步维护；同步工作流可能占用长请求；当前单用户模型不适合直接公网部署。认证/RBAC、异步作业、WebSocket、多用户协作和更复杂图交互留给后续里程碑。
