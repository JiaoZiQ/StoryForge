# 数据模型

所有主键沿用 Milestone 1 的自增整数。SQLite 是默认开发数据库；PostgreSQL 使用同一 SQLAlchemy metadata。

## M3 相关表

### `projects`

保留标题、类型、前提、目标章节数与目标字数，新增：

- `language`、`tone`、`audience`
- `logline`、`themes`
- `world_summary`、`central_conflict`、`ending_direction`、`style_guide`
- 状态：`draft → planning → planned → generating → completed`，失败进入 `failed`

`active` 与 `archived` 为此前兼容状态，M3 用例不会写入它们。

### `characters`

规划输出保存姓名、角色、描述、目标、说话风格、当前状态与作者秘密。`personality_traits` 保存结构化性格列表；旧的 `personality` 文本字段保留兼容。

### `locations` 与 `story_rules`

地点保存描述和 JSON 规则列表；世界/叙事规则保存分类、语句、来源 Prompt 版本与启用状态。

### `chapters`

- `objective`：当前章目标。
- `outline`：可读概要。
- `outline_metadata`：经 `ChapterOutlineContext` 验证的结构化计划，包括关键事件、参与人物、地点、必须事实、禁止泄漏、伏笔 setup/payoff 与结尾钩子。
- `content`、`summary`、`version`。
- `generation_metadata`：经 `GenerationMetadata` 验证的 provider、model、Prompt 版本、调用次数、耗时和时间戳。
- M3 状态：`planned → generating → extracting_facts → generated`；写作失败为 `failed`，事实失败为 `fact_extraction_failed`。

### `chapter_versions`

每次成功写出正文后立即创建不可变快照，保存章节 ID、版本号、标题、完整正文、摘要和生成元数据。`(chapter_id, version)` 唯一；重新生成不会覆盖旧正文。

### `facts`

事实关联项目与来源章节，保存 subject/predicate/object、`fact_type`、置信度、原文引句和有效章节区间。ContextBuilder 还会用来源章节号阻止未来事实泄漏。

### `foreshadowings`

保存 setup、预期 payoff、实际 payoff、描述、重要性和状态。计划生成时为 `planned`；setup 章节生成后为 `open`；提取到 payoff 后为 `resolved`。

## JSON 约束

JSON 只用于适合整体读写的小型结构：字符串列表、章节计划元数据与生成元数据。写入这些字段的数据均先经过对应 Pydantic v2 模型验证，不把任意未验证 dict 作为业务输入。

## 迁移

- `3d5c121d94ea`：M1 初始领域表。
- `b550a962dc62`：M3 字段、生成状态和 `chapter_versions`。

第二个迁移没有修改旧迁移，并支持从空库升级到 head、`alembic check` 与降级到 base。
