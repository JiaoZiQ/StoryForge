# ADR 0003：M4 规则评估、冲突持久化与版本历史

- 状态：Accepted
- 日期：2026-07-14

## 背景

章节评估既需要文学判断，也需要可重复、可解释的一致性约束。项目必须在无网络、无密钥的 SQLite 环境中演示，并为未来修订流程保留完整判断依据。

## 决策

1. 一致性检查优先使用确定性规则引擎。LLM Critic 负责文学和整体叙事判断，不代替事实、时间、状态和 outline 的机械规则。这样可以离线测试、稳定复现并给出明确 rule code。
2. Conflict 独立成表并关联 Evaluation、Project、Chapter 和可选历史 Fact。状态统一为 open/ignored/resolved/false_positive，不创建第二套冲突状态。
3. CriticAgent 失败时保留已经完成的 Mechanical 与 Consistency 结果，创建 `partial_failed` Evaluation，并保存本地 Issue/Conflict；不把局部结果冒充最终通过分。
4. Evaluation 使用每章递增版本，每次尝试新增记录，永不静默覆盖旧结果。新尝试失败不删除旧版本。
5. 最终分保存原始分与加权分。默认权重合计为 1；critical 冲突封顶且阻止通过，high 冲突扣分并受数量门禁，另设 consistency、outline 和总分下限。
6. 人物知识边界使用 `characters.knowledge` JSON 字符串列表，并与 `secrets` 分开。它足以支持当前结构化规则，但明确不是完整关系图。
7. 本阶段不引入 Neo4j。当前证据规模、查询和规则可由关系表、索引与显式 DTO 满足；图数据库会增加部署、迁移和测试成本，却不能替代缺失的语义标注。
8. StoryRule 保留自由文本，同时增加可选 `structured_metadata` 做可测试匹配；缺少 metadata 时不进行不可解释的“魔法判断”。
9. M4 只提供 CLI 薄适配。完整评估 REST API 与统一异常映射按 Roadmap 留到 M6。

## 后果

- 离线 Mock 与本地规则可以完整验收。
- 冲突和评分可追溯到具体版本、Prompt 和规则配置。
- 需要显式维护结构化事实、知识列表和 StoryRule metadata。
- 对自由文本隐含矛盾、复杂同义词、空间移动耗时和跨叙事视角的推理能力有限。
- M5 可以消费 recommended_action 和 blocking_reasons，但 M4 不自动执行修订。
