# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 的结构。

## [Unreleased]

### Added

- M0：Python 3.12 `src` 工程、FastAPI 健康检查、pytest/coverage/Ruff/mypy 门禁。
- M1：十个基础 SQLAlchemy 2 领域模型、Pydantic v2 schema、repository、SQLite/PostgreSQL 配置与首个 Alembic 迁移。
- M2：统一结构化 LLM provider、确定性 Mock、OpenAI-compatible provider、脱敏错误策略与版本化 PromptRegistry。
- M3：`PlannerAgent`、`WriterAgent`、`FactExtractorAgent` 及六个独立、显式版本的 system/user Prompt。
- M3：`PlanningService`，支持结构校验、引用校验、原子持久化与受保护的计划替换。
- M3：独立 `ContextBuilder`，支持防未来信息泄漏、来源章节过滤、秘密隔离、相关事实筛选和可审计字符预算。
- M3：`ChapterGenerationService`，持久化正文、摘要、事实、人物状态、伏笔状态、生成元数据与完整版本快照。
- M3：事实提取失败时保留正文并进入 `fact_extraction_failed` 可恢复状态。
- M3：第二个独立 Alembic 迁移 `b550a962dc62`，包含 M3 字段、状态和 `chapter_versions` 表。
- M3：`create-project`、`plan`、`show-context`、`generate-chapter`、`show-chapter` 与可重复的 `demo-m3` 离线 CLI。
- M3：成功、无效规划、上下文预算、未来信息隔离、重复生成保护、版本保留、失败状态、迁移与 CLI 测试。
- M4：本地 `MechanicalEvaluator`，覆盖长度、重复、句式、套话、禁用表达、标点、对话与段落结构，并集中配置阈值和扣分。
- M4：保守 `FactNormalizer` 和十组规则驱动 `ConsistencyChecker`，输出可解释、带证据和置信度的冲突。
- M4：结构化 `CriticAgent`、八维文学评分、Prompt 版本记录，以及正常、死亡冲突、大纲偏离、低质量和事实冲突 Mock 场景。
- M4：`EvaluationScorer` 的可验证权重、critical 封顶、high 扣分、最低分门禁和推荐动作。
- M4：`EvaluationService` 的不可变版本历史、EvaluationIssue/Conflict 持久化、章节状态转换、原子写入和 Critic `partial_failed` 保留策略。
- M4：第三个 Alembic migration `ad6fd0f94186`，新增评分明细、冲突表、问题表、人物知识边界和结构化 StoryRule metadata。
- M4：`evaluate-chapter`、`show-evaluation`、`list-conflicts`、`update-conflict` 和可重复离线 `demo-m4`。
- M4：机械规则、归一化、一致性、Critic、评分、事务、迁移、CLI、未来信息隔离与日志脱敏测试。

### Changed

- 项目状态增加 `planned`、`generating`、`failed`；章节状态增加生成与事实提取阶段状态，同时保留此前状态供后续里程碑使用。
- README、架构、数据模型、开发、工作流与进度文档同步到 Milestone 3。
- README、架构、数据模型、评估、开发、工作流、ADR 与进度文档同步到 Milestone 4。
- 章节状态增加 `evaluated_passed`、`evaluated_needs_revision` 和 `evaluation_failed`；旧状态保留兼容。

### Fixed

- Writer 上下文不再暴露结局方向、角色秘密、未来章节摘要或由未来章节产生的事实。
- FactExtractor 的 setup 更新会复用同一章节已有的计划伏笔，避免重复记录。
- 本章首次回收伏笔不再因持久化状态已经更新而误判为重复回收。
- Evaluation 迁移会为已有 M3 评估按章节和 ID 回填稳定版本号。
- `demo-m4` 同时构造 high 事实矛盾和 critical 死亡人物行动，实际展示 critical 冲突阻断及最终分 5.0 封顶。
