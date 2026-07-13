# ADR 0002：M3 计划存储、上下文隔离与事务边界

状态：Accepted
日期：2026-07-13

## 背景

Milestone 3 需要离线跑通规划与单章生成，同时避免提前引入 LangGraph、评估循环或复杂检索基础设施。现有模型使用整数主键、关系表和少量 JSON 字段。

## 决策

1. 章节计划直接保存在 `chapters`：稳定、常查字段使用列，列表型计划细节使用经 Pydantic 验证的 `outline_metadata` JSON。M3 不新增独立 `chapter_plans` 表。
2. 新增 `chapter_versions` 保存每次生成的完整正文快照。现有 `revisions` 只记录后续修订元数据，不能满足“旧正文不可丢失”。
3. PlanningService 在 LLM 调用前后使用短事务；完整计划的所有实体在一个事务中写入。LLM 网络等待不占用数据库事务。
4. 章节正文和事实分两个持久化阶段。正文先提交并创建快照；事实抽取失败时明确标记 `fact_extraction_failed`，保留可恢复产物。
5. ContextBuilder 是独立 service。它按来源章节过滤事实、按 setup 章节过滤伏笔、拒绝未来摘要，并始终排除角色秘密与结局方向。
6. M3 使用简单的确定性字符预算和相关性过滤，不引入向量数据库或 LLM 选择器。

## 结果

- 可以验证计划事务的原子性，又不会在 LLM 调用期间长时间持有锁。
- 失败后可以检查和重用已生成正文，不会产生“正文存在但状态成功、事实只写一半”的歧义。
- 当前实现适用于 SQLite，并保持 PostgreSQL 兼容边界。
- JSON 元数据必须在 service 边界由 Pydantic 模型构造；不接受任意 dict。

## 未选择方案

- 独立 `chapter_plans` 表：M3 查询模式不需要额外 join，拆表增加迁移和仓储复杂度。
- 单个超长事务包住 Writer 与 FactExtractor：会长时间持锁，且事实失败会丢失有价值的正文。
- 将角色秘密放入通用 Writer 上下文：容易产生无意泄漏，M3 明确禁止。
- LangGraph/checkpoint：属于 Milestone 5。
