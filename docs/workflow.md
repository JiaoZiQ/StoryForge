# Milestone 3 工作流

## 规划

1. 读取最小项目 brief，并验证尚无正文。
2. 短事务将项目标记为 `planning`。
3. `PlannerAgent` 在事务外调用 LLM，返回 `NovelPlan`。
4. 校验章节总数、连续编号、唯一人物/地点、引用与伏笔范围。
5. 单一事务保存项目规划字段、人物、地点、规则、全部章节计划和伏笔，并标记 `planned`。

失败不会产生半套计划。已有计划默认拒绝覆盖；只有没有正文且显式 `replace_existing=True` 时，旧计划的删除与新计划写入才在同一事务发生。

## 上下文

ContextBuilder 的必选内容是项目方向和当前章计划；当前章计划不会因预算被裁掉。可选内容按以下优先级加入：

1. 活跃世界规则
2. 当前章参与人物
3. 当前章相关且由更早章节产生的事实
4. 已经 setup 的开放伏笔
5. 最近已生成章节摘要
6. 当前章地点详情

预算元数据记录候选、纳入、遗漏数量和类别。即使预算小于必选内容，也保留当前章计划并明确 `mandatory_outline_exceeded_budget=true`。

防泄漏规则：

- 不查询当前章或未来章产生的事实。
- 不加入未来章节摘要或未来伏笔 setup。
- 不加入项目结局方向。
- 不加入角色 `secrets`；`author_secrets` 在 M3 始终为空。

## 章节生成

```text
planned → generating → extracting_facts → generated
                    ↘ failed
                                      ↘ fact_extraction_failed
```

1. 验证项目与章节状态；已有正文必须显式 `regenerate=True`。
2. 构建上下文并调用 WriterAgent。
3. 在独立事务中保存正文、摘要、生成元数据和完整 `ChapterVersion` 快照。
4. 调用 FactExtractorAgent；机械过滤低置信度、重复、引句不存在、来源章节不符的记录。
5. 在一个事务中写入事实、人物状态与伏笔状态，并将章节标记为 `generated`。

最后一章生成完成后，项目状态为 `completed`；否则保持 `generating`。

## 失败策略

| 失败阶段 | 持久化结果 | 状态 | 是否可重试 |
|---|---|---|---|
| Planner 调用/校验 | 不保存部分计划 | project `failed` | 是 |
| 计划写入 | 整体回滚 | project `failed` | 是 |
| Writer 调用 | 不写正文 | chapter/project `failed` | 是 |
| 正文写入 | 整体回滚 | chapter/project `failed` | 是 |
| FactExtractor 调用 | 保留正文与快照，不写新事实 | `fact_extraction_failed` / project `failed` | 是 |
| 事实事务 | 事实与状态更新整体回滚，正文保留 | `fact_extraction_failed` / project `failed` | 是 |

M3 不实现自动重试循环、评分、自动修订或 LangGraph checkpoint。
