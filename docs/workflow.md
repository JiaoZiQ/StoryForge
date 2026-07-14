# StoryForge 工作流

## M6 应用入口与执行语义

REST API 和分组 CLI 都只调用 `storyforge.application` 中的用例服务；HTTP route 和 CLI parser 不直接访问 ORM、拼接 Prompt 或调用 provider。每个请求/命令创建短生命周期数据库 session，LLM provider、Agent 和领域 Service 由 `DomainServiceFactory` 显式装配。FastAPI lifespan 只负责创建/释放 engine，不在 import 时连接数据库，也不自动执行 migration。

工作流 API 当前保持同步语义：启动请求会运行到完成、人工复核或显式暂停后返回 `201`；resume 返回 `200`。尚未引入 worker 时不返回虚假的 `202 Accepted`。同一章节已有 pending/running/paused WorkflowRun 时再次启动返回 409；活跃工作流期间也禁止替换规划，避免删除正在引用的章节和版本。

公共查询遵守下列数据边界：

- 章节和版本列表默认只返回 metadata；正文需显式 `include_content=true`。
- Fact API 在 repository 层固定 `status=accepted`，`candidate`、`rejected` 和 `superseded` 不能通过查询参数绕过。
- Context API 继续按当前章节过滤 accepted 历史事实、摘要和伏笔，不读取未来章节数据。
- WorkflowEvent 只暴露节点、状态、ID、attempt 和 duration，不暴露 checkpoint、正文或 Prompt。

请求状态冲突、不可恢复、取消和资源不存在均先转换为项目内部异常，再由统一 HTTP handler 映射；route 不包含分支业务规则。

## M5 LangGraph 自动修订闭环

```text
initialize_workflow → load_context → generate_draft → extract_facts
→ evaluate_draft → decide_after_evaluation
  ├─ pass → accept_version
  ├─ retry → build_revision_brief → revise_draft → extract_revision_facts
  │          → evaluate_revision → compare_versions → decide_after_comparison
  │             ├─ accept → accept_version
  │             ├─ retry → reject_revision → build_revision_brief
  │             └─ limit/stop → mark_needs_human_review
  └─ limit → mark_needs_human_review
```

LangGraph 节点只编排现有 ContextBuilder、Writer/FactExtractor/Critic/Revision Agent、EvaluationService、RevisionBriefBuilder、AcceptanceEvaluator 和 ChapterVersionService。状态是 TypedDict，只保存项目/章节/版本/评估 ID、小型评估/brief/comparison 字典、attempt、route 和时间戳。

### 路由与最佳版本

- 初次 Evaluation 只有 `passed=true` 且无 blocking reasons 才接受。
- 未通过且 `revision_attempt < max_revision_attempts` 才进入 RevisionBrief。
- AcceptanceEvaluator 比较总分、Consistency、Outline、critical/high conflict、问题集合与 brief 完成情况。
- 新 critical 永不接受；低于最小改善阈值视为无明显改善。
- WorkflowRun.best_version_id 按 critical 数、阻断数、最终分、Consistency、Outline 和 high 数排序；最后一次失败不会覆盖最佳版本。
- 达到上限时显示最佳正文为 needs_review，但不提升任何候选事实。

### 候选事实与接受事务

每个版本重新抽取事实，保存为 `candidate` 并关联 ChapterVersion/WorkflowRun。M4 Evaluation 可以读取“当前版本 candidate + 更早章节 accepted”，但 ContextBuilder 只读取 accepted。

`accept_version` 在一个事务内完成：选中版本 accepted、旧 accepted 版本/事实 superseded、其他候选版本/事实 rejected、人物/伏笔更新、Chapter/WorkflowRun 指针和状态更新。事务失败会整体回滚。`reject_revision` 和 `mark_needs_human_review` 均保留正文/评估历史，但不会写正式事实。

### Checkpoint、恢复与幂等

SQLite checkpointer 使用 WorkflowRun.thread_id。`pause_after` 在主要节点成功并写 checkpoint 后暂停；`resume` 以 `graph.invoke(None, thread_id)` 从下一节点继续。完成、失败和取消状态不能恢复。

持久化节点的数据库幂等键：

- ChapterVersion：`workflow:{run}:generate_draft:0` 或 `workflow:{run}:revise_draft:{attempt}`。
- Evaluation：`workflow:{run}:{evaluate_node}:{attempt}`。
- Fact：`(chapter_version_id, normalized_hash)`。
- WorkflowEvent：`(workflow_run_id, node, event_type, attempt)`。
- VersionComparison：`(workflow_run_id, new_version_id)`。

恢复测试覆盖 generate、extract、evaluate、revision、comparison 决策后暂停；均验证不重复版本、Evaluation 或 Fact。checkpoint 单独存储，不包含正文、session、client、连接或密钥。

### 失败、取消和审计

节点进入/完成/失败和路由均写 WorkflowEvent，错误文本限制长度并脱敏 API Key、token、password、Authorization/Bearer。异常使 WorkflowRun failed；已有 accepted 内容保持不变，未接受章节进入 workflow_failed。cancel 是节点边界协作式取消，不中断正在执行的 provider 请求。

## M3 生成前置链路

```text
create project → plan → build bounded context → generate chapter → extract facts
```

只有正文存在且事实抽取成功的章节可以进入 M4。`fact_extraction_failed` 默认拒绝评估，避免在缺少当前章事实时给出虚假的完整一致性结论。

## M4 评估链路

1. 读取项目、章节和当前章 outline，验证状态与正文。
2. 只加载当前章事实、有效历史事实、人物公开状态/知识边界、活跃规则、当前可见伏笔和更早章节摘要。
3. 短事务将章节标记为 `evaluating`。
4. 在事务外运行 MechanicalEvaluator。
5. 在事务外运行 ConsistencyChecker。
6. 构造最小 CriticContext，在事务外调用 CriticAgent。
7. EvaluationScorer 合并原始分、权重分、冲突扣分和阻断条件。
8. 单一事务新增 Evaluation、EvaluationIssue、Conflict，并更新章节分数与最终状态。

## 状态转换

```text
generated ───────────────→ evaluating
evaluated_passed ────────→ evaluating
evaluated_needs_revision → evaluating
evaluation_failed ───────→ evaluating

evaluating → evaluated_passed
evaluating → evaluated_needs_revision
evaluating → evaluation_failed
```

`planned`、`generating`、`extracting_facts`、`fact_extraction_failed` 或已在 `evaluating` 的章节不能开始新评估。

## 失败与事务策略

| 失败阶段 | 新 Evaluation | 本地结果 | 章节状态 | 历史记录 |
|---|---|---|---|---|
| Mechanical | 不创建 | 无可靠完整结果 | `evaluation_failed` | 保留 |
| Consistency | 不创建 | 无可靠完整结果 | `evaluation_failed` | 保留 |
| Critic/provider/schema | 创建 `partial_failed` | Mechanical、Consistency、Issue、Conflict 保留 | `evaluation_failed` | 保留 |
| 完整结果写入 | 整体回滚 | 不产生半条完整评估 | `evaluation_failed` | 保留 |
| 成功 | 创建 `completed` 新版本 | 全部保存 | passed/needs_revision | 保留 |

Provider 原始错误统一在 Agent 边界转换；对外只暴露项目内部异常。日志只包含项目/章节/评估 ID、版本、分数和状态。

## 未来信息隔离

- 历史 Fact 查询要求来源章节 `< 当前章节`，同时要求 `valid_from_chapter <= 当前章节` 且未过期。
- 更晚章节创建的 Fact 即使错误地写了较早有效期，也不会进入当前评估。
- 只加载 setup chapter 不晚于当前章的伏笔。
- CriticContext 不包含人物 secrets、项目 ending direction 或未来摘要。
- ConsistencyChecker 自身仍保留 future-fact 规则，便于检测错误调用者直接传入的非法证据。

## M4 与 M5 的职责分界

M4 EvaluationService 仍只计算/持久化一次评估和 `recommended_action`；它不知道 LangGraph 或重试循环。M5 负责消费结果、创建新版本、重新抽取/评估、成对比较和路由，节点不复制 M4 规则。

不属于 M5/M6：跨章节并行、异步任务队列、复杂人工审批 UI、全书级审稿、Neo4j/pgvector/Redis/Celery。
