# StoryForge 工作流

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

## 不属于 M4

M4 不执行重写、不循环调用 Critic、不做 AcceptanceEvaluator，也不建立 LangGraph checkpoint。`recommended_action` 是数据，不是自动动作。
