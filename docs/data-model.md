# 数据模型

## M12 whole-book tables

- `book_runs`: one active run per project, top Job link, chapter/job maps, progress,
  periodic summaries, budgets, checkpoint node, and safe terminal/error state.
- `book_snapshots`: immutable number, chapter-version JSON map, stable hash, aggregate
  counts, and accepted/superseded lifecycle; it stores no manuscript body.
- `timeline_events`, `character_arc_points`, `character_knowledge`, and
  `relationship_history`: snapshot-scoped accepted evidence with version links.
- `chapter_transition_evaluations`, `book_evaluations`, `book_revision_plans`, and
  `book_revision_tasks`: versioned global scoring and bounded rework history.

Analysis rows cascade from their snapshot. Facts and memory must be `accepted` and match a
version frozen in the snapshot. Candidate, rejected, superseded, and future records are
excluded by data-layer queries. Migration `3f86e80e0e51` upgrades M11 data and keeps one
Alembic head.

## M11 queue data

`jobs` stores safe operation metadata and leases; `job_events` stores ordered progress;
`outbox_messages` records enqueue intent; `worker_records` stores safe heartbeats.
Unique keys and the active-chapter index prevent duplicates. Head: `b61d3f7a2c10`.

主键沿用 Milestone 1 的自增整数。SQLite 是默认开发数据库；PostgreSQL 使用同一 SQLAlchemy metadata。

## M6 变化

- `projects.status` 增加 `created`，API 新建项目以此状态开始；新增非空 `additional_requirements`，旧数据回填空字符串。
- `evaluations` 增加 `mechanical_metrics` 与 `critic_dimensions` JSON，详情 API 可审计机械指标和 Critic 各维度理由，旧记录回填空对象。
- `consistency_conflicts` 增加可空 `resolution_note`。非 open 状态记录 `resolved_at`；重新打开清空处理时间。
- 没有为 API 复制 Chapter、Version、Evaluation、Conflict、Fact 或 Workflow 模型；HTTP/CLI DTO 只是现有持久化模型的受限投影。
- 列表响应不持久化分页数据；repository 在数据库中执行 count 和 limit/offset。

公共 Fact 投影只允许 `accepted`。`candidate`、`rejected` 与 `superseded` 仍保存在同一表供工作流内部审计，但普通 API/CLI 无权按状态读取。`valid_at_chapter=N` 还要求来源 chapter `< N`，防止当前或未来章节事实泄漏。

## M5 变化

### `chapters` 与 `chapter_versions`

`chapters` 是逻辑章节，保留当前可展示正文以兼容 M1–M4，并新增 `current_version_id`、`accepted_version_id` 指针。工作流状态为：

```text
planned → workflow_running → drafting → evaluating → revising
                                            ├→ accepted
                                            ├→ needs_review
                                            └→ workflow_failed
```

`chapter_versions` 是不可变正文历史；同章 `(chapter_id, version)` 唯一。新增：

- `status`：`draft | evaluated | revision | accepted | rejected | superseded | needs_review`。
- `source`、`parent_version_id`、`workflow_run_id`。
- `word_count`、`provider`、`model`、`prompt_versions`。
- candidate 人物/伏笔更新、`idempotency_key`、`accepted_at`。

新生成和每轮修订都创建新行。接受版本 2 后，版本 1 保留；旧 accepted 才标为 superseded，未接受的竞争版本标为 rejected。Evaluation 和 Conflict 均绑定 `chapter_version_id`。

### `facts`

选择在现有 Fact 上增加版本隔离，而不是复制 CandidateFact 表：

- `chapter_version_id` 非空，`workflow_run_id` 可空。
- `status`：`candidate | accepted | rejected | superseded`。
- `normalized_hash` 由保守 FactNormalizer 生成。
- `(chapter_version_id, normalized_hash)` 唯一，约束恢复重放不重复。

FactRepository 的长期上下文查询强制 `status=accepted`。接受新版本时，其 candidate Fact 与人物/伏笔更新在同一事务提升；旧 accepted Fact superseded，其他 candidate rejected。人工复核不会提升任何候选事实。

### `workflow_runs` 与 `workflow_events`

WorkflowRun 新增 workflow type、operation、唯一 `thread_id`、original/current/best/accepted version 指针、revision attempt/limit、node history、blocking reasons、error code、Prompt 版本和更新时间。状态集中为：

```text
pending | running | paused | completed | completed_needs_review | failed | cancelled
```

WorkflowEvent 记录 `node_started`、`node_completed`、`node_failed`、`route_selected`、`version_created`、`evaluation_created`、`revision_rejected`、`version_accepted`、`workflow_completed`，包括 attempt、duration、版本/评估 ID 和脱敏错误码，不保存正文。

### `version_comparisons` 与 `revisions`

VersionComparison 保存 old/new version、各维度分差、resolved/unresolved/new issue codes、decision、confidence 和理由；同一工作流的新版本只允许一个比较结果。Revision 关联 source/new version 与 WorkflowRun，并保存结构化 brief、Prompt 版本、比较前后分和接受状态。

### Evaluation 与 Conflict

Evaluation 新增 `chapter_version_id`、`workflow_run_id` 和唯一可空 `idempotency_key`。Conflict 新增非空 `chapter_version_id`。历史记录不会因后续修订或工作流失败而改写。

## M4 变化

### `chapters`

M4 使用状态：

```text
generated → evaluating → evaluated_passed
                       ↘ evaluated_needs_revision
                       ↘ evaluation_failed
```

`score` 保存最新完整评估的 0–10 最终分。旧 Evaluation 不因章节状态变化或新尝试失败而删除。

### `evaluations`

在旧评分字段基础上增加：

- `(chapter_id, evaluation_version)` 唯一；版本从 1 递增。
- `status`：`completed` 或 `partial_failed`。
- `mechanical_score`、`critic_score`、`consistency_score`、`overall_score`。
- `pacing_score`、`dialogue_score`、`emotional_impact_score`、`outline_adherence_score`，并保留 prose/plot/character。
- `raw_scores`、`weighted_scores`，用于审计权重前后结果。
- `evaluator_versions`、`prompt_versions`、`config_version`。
- `blocking_reasons`、`recommended_action`、`passed`。
- `provider`、`model`。

旧 M1 评分列的 0–100 数据库约束为兼容已有数据保留；M4 入口和 service 对 M4 分数使用 Pydantic 0–10 约束。

### `evaluation_issues`

一行保存一个机械或 Critic 问题：来源、稳定 code、分类、severity、描述、短 evidence、建议、扣分和小型 metadata。它与 Evaluation 级联删除，但正常业务不会覆盖或删除历史 Evaluation。

### `consistency_conflicts`

保存：Evaluation、项目、章节、冲突类型、severity、subject、双方 evidence、可选历史 fact ID、建议解决方案、置信度、规则 code、状态和时间戳。

状态只有一套：

```text
open | ignored | resolved | false_positive
```

恢复为 `open` 会清空 `resolved_at`；其他状态记录处理时间。

### `characters.knowledge`

人物知识边界使用 JSON 字符串列表，和作者侧 `secrets` 分离。规则引擎只有在 secret 未 reveal、人物不在知识列表、历史中也无获得事件时才报告知识泄漏。这是保守的一版关系表示，不是完整知识图谱。

### `story_rules.structured_metadata`

新增向后兼容 JSON 字段，用于机械匹配，例如：

```json
{
  "location": "city",
  "forbidden_predicates": ["uses_fire"],
  "allows_resurrection": false
}
```

自由文本 `statement` 仍保留；没有结构化 metadata 的规则不会被伪装成确定性机器判断。

## 既有 M3 表

- `projects`：brief、规划结果、目标与状态。
- `characters`、`locations`、`story_rules`：计划世界与人物。
- `chapters`、`chapter_versions`：M5 在既有快照表上扩展，没有创建第二套版本表。
- `facts`：subject/predicate/object、来源章节、有效区间、置信度和原文引句；M5 增加状态/版本隔离。
- `foreshadowings`：setup、预期/实际 payoff 和状态。

## M8 Memory 与 Graph

`MemoryChunk` 保存 project/source/chapter/version、chunk index、内容哈希、token/字符估算、`vector(64)` embedding、provider/model/dimensions、validity 和状态。公开查询固定为 `accepted`，且要求来源章节早于当前章节、有效期覆盖当前章节。`MemoryIndexRecord` 按版本/provider/model 唯一，记录 pending/indexing/completed/failed、attempt、计数与脱敏错误。

`GraphEntity` 保存受控 entity type、canonical/normalized name、可选来源版本、置信度和状态；`GraphRelation` 保存受控 predicate、subject/object 外键、证据哈希、来源版本、validity 和状态。查询只返回 accepted、过去有效关系，neighbors 最多 2 hops 并按关系 ID 去重防止循环爆炸。

PostgreSQL 使用 pgvector `vector(64)` 和 `vector_cosine_ops` HNSW。SQLite 使用 JSON 兼容列，仅支持 keyword/fact/graph 降级路径，不伪装执行向量相似度。

## 迁移历史

- `3d5c121d94ea`：M1 初始领域表。
- `b550a962dc62`：M3 规划/生成字段、状态和 `chapter_versions`。
- `ad6fd0f94186`：M4 Evaluation 明细、EvaluationIssue、Conflict、章节评估状态、人物知识和 StoryRule metadata。
- `69c75316dd7e`：M5 版本/候选事实/工作流审计/比较字段和表，以及新状态。
- `f2a6c8d91b04`：M6 项目输入、评估详情、冲突处理备注和 `created` 状态。
- `c7d4e1a2b9f0`：M7 为 `workflow_runs(chapter_id)` 增加跨 SQLite/PostgreSQL 的部分唯一索引，仅覆盖 `pending`、`running`、`paused`，从数据库层阻止同章节并发活跃工作流。
- `e8b4a2f7c913`：M8 启用 PostgreSQL `vector` extension，新增 memory/index/graph 表和 cosine HNSW；SQLite 使用兼容 JSON 列且不创建向量索引。

## M9 数据模型说明

M9 没有新增表、字段或 Alembic revision。Web UI 只消费 M6–M8 的公共 projection；列表默认无正文，Evaluation/Conflict 仍绑定 ChapterVersion，Fact/Memory/Graph 仍由 accepted 状态和章节有效期约束。TanStack Query 缓存不是持久化事实来源，刷新后必须从 API 重建。

所有后续 migration 都不修改旧 revision。迁移支持空 SQLite/PostgreSQL upgrade head；已有 M4/M5/M6 数据分别由后续 revision 安全升级。模型使用非原生字符串 Enum、SQLAlchemy JSON、timezone-aware DateTime、数据库外键和约束，PostgreSQL 专项测试覆盖 JSON、Enum、boolean、时间、级联、回滚、分页、排序、候选事实隔离和幂等唯一键。

## M10 governance data model

Migration `a91f4d2c7e10` adds `projects.model_profile` and
`projects.privacy_policy`; `project_budgets` stores Decimal soft/hard limits,
estimated/billed spend and reservations; `provider_calls` stores one row per
attempt with task/model/profile/policy, request and idempotency hashes, status,
token provenance, immutable pricing snapshot, cost, latency and safe error code.
`provider_idempotency_records` uniquely owns a provider request without storing
its output. `workflow_runs` gains aggregate call/token/cost/fallback/rate-limit
counters. Foreign keys retain project/workflow/version attribution, and no table
contains an API key, endpoint, prompt, chapter body, response body, or embedding.

The migration supports fresh SQLite/PostgreSQL upgrade, M9 data upgrade and
downgrade. SQLite batch operations temporarily disable FK enforcement to prevent
parent-table rebuild cascades, then restore checks. The unique head is
`a91f4d2c7e10`.
