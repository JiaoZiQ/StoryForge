# ADR 0004：可恢复的 LangGraph 修订工作流

- 状态：Accepted
- 日期：2026-07-14
- 里程碑：Milestone 5

## 背景

M1–M4 已有稳定的 repository、ContextBuilder、Writer/FactExtractor、EvaluationService 和结构化 LLM 边界。M5 需要在不复制这些业务逻辑的前提下增加多轮修订、checkpoint、恢复、版本选择和事实提升。

## 决策

### 1. 使用 LangGraph 作为同步编排器

使用强类型 StateGraph 表达节点、条件边和有限循环。LangGraph 只负责状态传递、路由、checkpoint 和节点边界；领域校验、LLM 调用和事务继续属于现有 Agent/Service/Repository。这样既可利用持久化 graph state，又不会把框架扩散到 M3/M4 领域实现。

### 2. 工作流状态与数据库状态分工

checkpoint 状态只保存 ID、小型 Pydantic dump、attempt、route 和时间戳；不保存正文、ORM、session、LLM client、连接或密钥。数据库保存所有具有业务意义和审计要求的内容。WorkflowRun.thread_id 是两者的关联键，数据库是用户可查询状态的权威来源。

### 3. Chapter 是身份，ChapterVersion 是不可变正文

扩展 M3 的 chapter_versions，而不创建重复表。Chapter 保存 current/accepted 指针和兼容性的当前正文；每次生成/修订新建 ChapterVersion。Evaluation、Conflict、Revision 和 Fact 都关联具体版本。旧版本不删除，接受新版本不会抹去历史。

### 4. 候选事实采用现有 Fact 状态扩展

选择“Fact 增加 status/version/workflow/hash”而不是 CandidateFact 表。优点是结构化事实只维护一套 schema 和查询接口；代价是所有长期上下文查询必须强制 accepted 过滤。该过滤位于 FactRepository，数据库另有非空 version FK 和 `(chapter_version_id, normalized_hash)` 唯一约束。

接受事务提升选中版本 candidate，supersede 旧 accepted，reject 其他 candidate，并同时应用人物/伏笔更新。人工复核不提升事实。该策略避免未接受文本污染后续章节。

### 5. SQLite checkpoint 与恢复

开发/测试使用独立 SQLite checkpointer 文件，避免 checkpoint 内部表进入领域 Alembic metadata。主要节点后可 `interrupt_after`；恢复调用同一 thread_id 的 `invoke(None)`。只有 paused 可恢复，completed/failed/cancelled 均不可恢复。生产高并发 checkpoint 后端不在本里程碑。

### 6. 副作用节点使用数据库幂等键

版本使用 workflow/node/attempt key；Evaluation 使用 workflow/evaluate-node/attempt key；Fact 使用版本+归一化哈希；WorkflowEvent 使用 run/node/event/attempt；VersionComparison 使用 run/new-version。幂等首先由唯一约束保证，service 在外部调用前后均查询并复用已落库结果。不能只依靠内存状态。

### 7. AcceptanceEvaluator 规则优先

版本接受是会改变正式正文和长期事实的高影响决策，因此以确定性规则比较 Final、Consistency、Outline、critical/high、blocking reasons 和问题集合。LLM 文学评审仍是 Evaluation 的一个输入，但不能绕过 critical 和硬门禁。最低改善阈值避免因浮点小变化接受无意义修订。

### 8. 最大重试与人工复核

默认最多 2 次修订，可配置 0–10。未通过且仍有次数时重试；达到上限、比较要求停止或 recommended action 为人工处理时进入 `completed_needs_review`。此状态保留最佳正文供人查看，但所有未接受事实保持 rejected。

### 9. 最佳版本选择

按“更少 critical → 更少 blocking → 更高 final → 更高 consistency → 更高 outline → 更少 high”比较。新版本变差时 reject 新版本并从最佳版本重新构建下一轮 brief；达到上限也显示最佳而不是最后版本。

### 10. 暂不引入异步任务队列

M5 的目标是验证正确、可恢复的单章闭环。Celery/Redis 会引入 worker 生命周期、消息幂等和部署面，无法替代当前数据库幂等设计。本阶段同步执行并支持节点边界取消；多进程调度、并发和超时治理留到明确的后续里程碑。

## 后果

- 正向：节点职责窄、可单测；恢复无重复；所有版本/评估/事实/事件可追溯；MockLLM 离线完整运行。
- 代价：SQLite checkpointer 仅适合本地与低并发；Chapter 仍保留兼容正文镜像；FactRepository 必须始终应用状态过滤。
- 不做：Neo4j、pgvector、多章节并行、异步 worker、复杂人工审批 UI、完整业务 API。
