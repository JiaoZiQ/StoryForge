# ADR 0005：统一应用服务、同步 API 与公开数据边界

- 状态：Accepted
- 日期：2026-07-14
- 里程碑：Milestone 6

## 背景

M1–M5 已形成 repository、领域 Service、Agent 和 LangGraph 工作流，但 HTTP 仅有健康检查，CLI 也主要是按里程碑增加的扁平入口。M6 需要提供稳定 REST/CLI 边界，同时不能把事务、状态转换或 LLM 逻辑复制到协议层。

## 决策

### 1. REST 与 CLI 共享 Application Service

在领域 Service 之上增加薄 Application Service，负责把外部 DTO 转成现有用例调用并组合查询结果。FastAPI route 和 CLI handler 只解析协议、调用用例并渲染结果。所有数据库查询继续经过 Repository，所有模型调用继续经过 `LLMProvider`。

### 2. 应用使用显式工厂和生命周期

`create_app(Settings)` 在 lifespan 中创建 engine/session factory 并在关闭时 dispose。请求依赖从 `app.state` 获取显式资源；模块导入不会连接数据库、创建全局 session 或执行 migration。CLI 为每次命令构建同样的 DomainServiceFactory。

### 3. 工作流端点保持真实同步语义

当前没有后台 worker，工作流启动会执行到终态或显式暂停再返回 `201`，resume 返回 `200`。不使用会误导客户端的 `202`。异步排队、任务取消语义和跨进程锁属于后续部署阶段。

### 4. 统一错误和并发冲突

领域异常先归一为资源不存在、输入校验、状态/并发冲突、provider 不可用/超时和内部错误，再映射为 404、422、409、503、504、500。响应总是包含稳定 error code 与 request ID，不返回 traceback、SQL、Prompt、正文或原始 provider 错误。活跃 WorkflowRun 由数据库状态判断，并阻止同章重复启动和项目重规划。

### 5. 分页、过滤和排序下沉到 Repository

列表接口统一使用 `page/page_size` 和 `items/meta`，最大页长由 Settings 限制。过滤和排序通过受控枚举/字段白名单构造 SQL；不在 route 中加载全表后切片，也不接受客户端提供的 SQL 字段。

### 6. 正文和 Fact 默认最小暴露

章节/版本列表只返回 metadata，详情默认也省略正文，只有显式 `include_content=true` 才返回。公共 Fact API 固定只查询 accepted；候选、拒绝和 superseded 事实无法通过 status 参数访问。ContextBuilder 的未来章节过滤保持为服务层强制规则，而不是由客户端约定。

### 7. Settings 统一但不隐式加载 `.env`

运行配置使用 `STORYFORGE_*` 前缀并保留必要的 migration 兼容项。应用不会扫描或提交 `.env`。development/test 默认 Mock；production 明确禁止 Mock，OpenAI-compatible provider 缺少 key 或 model 时启动失败。真实密钥只驻留进程环境，不进入日志、响应、checkpoint 或演示输出。

### 8. M6 migration 只增加接口所需明细

Project 增加 additional requirements，Evaluation 增加 mechanical metrics 与 critic dimensions，Conflict 增加 resolution note。旧记录使用安全空值回填后移除临时 server default；不修改 M1–M5 migration，也不改变章节版本和事实隔离模型。

### 9. Project 采用受限硬删除

只有尚未规划、没有章节聚合和工作流历史的 created 项目允许删除；此时数据库级 cascade 仅清理尚无业务历史的空聚合。已有规划、正文、版本、评估或工作流的项目返回 409，不提供会破坏审计历史的通用硬删除。归档/软删除可在有明确产品语义的后续里程碑增加。

### 10. Request ID 与日志脱敏

客户端可提供最长 128 字符的 `X-Request-ID`，否则 middleware 生成 UUID；响应总是回传。访问日志只记录 method、path、status、duration 和 request ID，不记录 query value、header、cookie、请求/响应体。领域错误消息在公开前归一；工作流错误继续使用既有截断和 key/token/password/Bearer 脱敏。

### 11. OpenAPI 运行时生成，不提交快照

OpenAPI 由带显式 response model、summary、tag 和 operation ID 的 route 自动生成；测试检查 26 个 path、operation ID 唯一和 schema 可解析。当前不提交生成 JSON，避免框架补充字段造成无意义 diff；当存在外部 SDK 消费者时再引入版本化 schema 快照和 breaking-change gate。

### 12. 并发保护范围

数据库状态阻止同一章节同时存在多个 pending/running/paused 工作流，并阻止活跃工作流期间重规划。版本、Evaluation、Fact 和事件另有 M5 唯一幂等键。当前没有跨进程 advisory lock 或队列租约，因此 SQLite/单进程是已验证范围；多 worker 下的竞争控制留给带生产数据库和任务执行器的后续阶段。

### 13. 无认证服务只允许受控环境使用

M6 不增加用户、租户、认证或授权模型，也不启用宽松的 credentialed CORS。API 因此只适合本机、测试或受信内网，不能直接暴露到公网。认证授权、限流、审计主体和租户数据隔离必须在生产部署前作为单独里程碑设计，不能由反向代理口头约定替代。

## 后果

- 正向：API/CLI 行为一致、协议层可替换、OpenAPI 可审计、错误和安全边界集中、Mock 可完整离线验收。
- 代价：工作流请求目前会占用 Web/CLI 进程直至节点完成；SQLite 与单进程检查不足以承担生产高并发；已有业务历史的 Project 目前不能删除。
- 不做：认证授权、异步队列、分布式锁、Docker/Compose、前端和生产部署编排，留待后续明确里程碑。
