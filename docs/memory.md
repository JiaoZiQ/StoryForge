# Milestone 8 Memory Index

## 可见性边界

只有 `ChapterVersion.status=accepted` 可以建立公开索引。每个 `MemoryChunk` 同时受 project、status、来源章节、`valid_from_chapter`、`valid_to_chapter` 和版本状态约束。普通检索固定排除 `candidate`、`rejected`、`superseded`、`deleted` 以及当前/未来章节来源。

接受新版本时，旧 accepted 版本的 chunk、版本来源实体和关系在同一接受事务中变为 `superseded`。被拒绝版本不会进入 ContextBuilder。该边界由 repository 查询条件和数据库状态共同实现，不依赖调用方约定。

## 切分与 embedding

`MemoryChunker` 按标题、段落、句子和硬长度顺序切分，中英文共用轻量字符/token 估算；chunk index、内容哈希和 overlap 都是确定性的，并限制单来源最大 chunk 数。索引内容包括正文、摘要、accepted facts、人物、地点、active rules 和已设置伏笔。

EmbeddingProvider 独立于 LLMProvider。MockEmbedding 使用 SHA-256 feature hashing 生成归一化 64 维向量，不调用网络、不读取 API Key；OpenAI-compatible provider 有独立模型、base URL、密钥、batch、timeout 和 retry 配置。数据库维度固定为 64，配置不匹配会立即失败。

## 生命周期与事务

`MemoryIndexRecord` 状态为 `pending → indexing → completed|failed`。接受事务只创建 pending 记录；provider 在事务外调用；最终 chunk/graph/upsert 在短事务内完成。provider 失败不会回滚已接受正文，记录只保存脱敏错误并可重试。

重复 reindex 在 completed 且非 force 时直接返回；force 也通过唯一键和 upsert 更新既有记录，不重复创建 chunk、entity 或 relation。API 的生产模式不允许 force。

## PostgreSQL 与 SQLite

PostgreSQL migration 创建 `vector` extension、`vector(64)` 列和 `vector_cosine_ops` HNSW。VectorRetriever 使用 PostgreSQL cosine distance 运算。SQLite 只保存兼容 JSON，VectorRetriever 明确报告不可用，由 HybridRetriever 降级到其余路由。
