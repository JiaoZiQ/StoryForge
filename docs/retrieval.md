# Milestone 8 Hybrid Retrieval

## 四路召回

- Keyword：在 accepted MemoryChunk 上做确定性关键词匹配。
- Vector：由 EmbeddingProvider 生成 query vector，PostgreSQL 使用 pgvector cosine distance 排序。
- Fact：直接读取 accepted 且在章节时间边界内的结构化事实。
- Graph：读取 accepted 实体关系和最多 2 hops 的可解释路径。

所有路由再次经过统一 final filter：project 必须匹配，状态必须 accepted，来源章节必须早于当前章节，有效期必须覆盖当前章节。

## 融合、去重与重排

HybridRetriever 使用可配置权重的 reciprocal rank fusion。相同 chunk 由稳定内容哈希合并；相同结构化 fact 由规范文本键合并。合并结果保留全部 `matched_sources`，explanation 记录分路命中与重排因素。

Reranker 是确定性规则：当前人物/地点、accepted fact、active rule、伏笔、可信来源、多路命中和近期章节获得加分，超长内容扣分。最终仍受 top-k 与字符预算限制，不调用 LLM reranker。

## 降级

任一路由失败都会产生稳定的 `*_unavailable` reason；只要仍有路由可用，系统继续返回安全结果。典型 SQLite 或 embedding 失败路径为 keyword + fact + graph。所有路由都失败时才返回项目内部 RetrievalError。降级不会放宽状态或未来信息过滤。

## ContextBuilder

RetrievalQueryBuilder 从当前大纲、上一章摘要和活跃伏笔生成有界查询，并排除 forbidden reveal。ContextBuilder 将去重后的 hybrid hits 放在最后一个可选预算类别；ProjectContext、当前 ChapterOutlineContext 和 active StoryRule 是强制项，即使预算不足也不会被 memory 挤掉。metadata 记录 query、hit IDs、来源构成、版本和降级原因。
