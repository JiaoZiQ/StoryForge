# ADR 0007：pgvector 混合长期记忆与关系图谱

状态：Accepted

## 背景

M8 需要在不泄漏未接受版本和未来章节的前提下，把已接受章节转为可检索长期记忆；同时必须支持无密钥、无模型网络的确定性演示，并保持 SQLite 开发路径。

## 决策

1. 使用独立 EmbeddingProvider，而不是复用 LLMProvider。测试默认 SHA-256 feature hashing Mock；生产适配 OpenAI-compatible embedding。
2. PostgreSQL 使用 pgvector `vector(64)`、cosine distance 和 HNSW `vector_cosine_ops`。固定维度使 schema 和 provider 形状可启动时验证。
3. MemoryChunk 使用版本、状态和章节有效期做数据层隔离。只索引 accepted ChapterVersion；新 accepted 版本在接受事务中 supersede 旧 memory。
4. 接受事务与 embedding 调用分成两阶段：事务内创建 pending，事务外调用 provider，短事务写入索引。embedding 失败保留已接受正文并记录 retryable failed。
5. 四路召回使用 weighted RRF；稳定哈希/规范事实去重；规则式 Reranker 优先。LLM reranker 不进入本里程碑。
6. 图谱使用现有 PostgreSQL 关系表和受控 predicate，最多查询 2 hops。M8 不引入 Neo4j，避免增加第二个一致性和部署边界。
7. ContextBuilder 保留项目、当前大纲和 active rules，hybrid memory 最后进入预算。vector 不可用时明确降级，不能静默伪装成功。
8. SQLite 不执行向量相似度；它只用于 keyword/fact/graph 降级、单元测试和本地开发。

## 后果

优点是部署仍只有一个主数据库，所有结果可解释、可审计、可离线测试，并能用数据库约束保持幂等与隔离。代价是固定 64 维需要未来 migration 才能更换，关系图不适合复杂图算法，同步 embedding 也不适合高吞吐生产环境。Elasticsearch、Neo4j、异步索引、LLM reranker 和复杂语义实体消歧留给后续明确里程碑。
