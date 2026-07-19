# Milestone 8 Relational Story Graph

## 模型

图谱保存在 PostgreSQL/SQLite 共用的关系表中，不引入 Neo4j。GraphEntity 使用受控类型（人物、地点、物品、秘密、事件、规则等）、保守 normalized name、可选来源版本和状态。GraphRelation 使用受控 predicate、subject/object 外键、原文证据、证据哈希、来源版本、有效期、置信度和状态。

## 抽取边界

GraphExtractor 规则优先，只从当前 accepted 版本的 accepted structured facts 建立关系。关系 evidence 必须是章节正文的真实子串；低置信度或未知 predicate 不会被伪装为确定关系。人物和地点计划数据作为 project canonical entities，可供版本关系复用。

## 查询与隔离

实体/关系列表和邻居查询固定过滤 project、accepted status 和章节有效期。neighbors 只允许 1 或 2 hops；访问过的 relation ID 去重，因此环不会造成无限遍历或重复结果。未来关系、rejected/superseded 关系和其他项目实体不可见。

当前实现适合小型、可解释的故事图谱。它没有完整语义实体消歧、复杂路径语言、图算法或 Neo4j 水平扩展能力。

## M12 relationship history

Accepted GraphRelations from versions frozen in a BookSnapshot contribute evidence-backed
character relationship history. Changes retain chapter/version and validity ranges; an
accepted replacement supersedes old graph sources. Public graph traversal remains bounded
to one or two hops.

## M9 可视化

Cytoscape 画布以受控形状区分人物、地点和其他实体，边标签来自受控 predicate。搜索、当前章节和 traversal 选择直接映射 API 参数；选择实体后才请求最多 1/2-hop 邻居。页面同时提供实体与关系列表按钮，键盘和屏幕阅读器不依赖 Canvas。前端 `validateGraphHops` 和 API schema 双重拒绝超过 2 hops。
