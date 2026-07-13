# StoryForge 工程约定

本文件适用于整个仓库。若子目录今后增加更具体的 `AGENTS.md`，以离目标文件最近的规则为准。

## 交付纪律

- 严格按 `ROADMAP.md` 的里程碑顺序交付；一次任务只推进明确要求的里程碑。
- 先完成最小可运行闭环，再扩展能力；不要批量生成没有行为的空壳代码。
- 不得在未获明确指示时提前实现后续里程碑。
- 每个里程碑结束时更新 `README.md`、`CHANGELOG.md` 和 `docs/progress.md`。
- 发现检查或测试失败时应在当前范围内修复，不得只记录失败。

## 架构边界

- `api` 只负责 HTTP 协议、请求/响应模型和异常映射，不承载领域规则。
- `services` 编排用例；`repositories` 隔离持久化；`models` 保存持久化模型；`schemas` 保存跨边界数据结构。
- `agents` 只封装单一 Agent 职责；`workflows` 负责 LangGraph 状态与路由；`evaluation` 负责机械与 LLM 评估。
- `llm` 是所有模型调用的唯一出口。外部数据库、模型和其他服务必须通过清晰接口隔离。
- 不得把完整数据库对象直接写入 prompt；使用显式、最小、带类型的上下文模型。
- 所有 LLM 输出必须通过 Pydantic v2 模型验证，禁止用字符串切割解析评分或结构化结果。

## 编码与测试

- 目标运行时为 Python 3.12；关键函数必须有完整类型注解。
- 优先选择简单、可维护的实现，避免为“多 Agent”标签引入不必要框架。
- 关键业务逻辑必须有 pytest 测试；核心业务覆盖率目标不低于 80%。
- 单元测试不得访问公网、不得要求 API Key、不得用 `sleep` 模拟等待，并且必须可重复运行。
- 默认开发数据库为 SQLite；PostgreSQL 是可选生产配置。不得假设本机安装数据库或 Docker。
- 没有真实密钥时，后续 LLM 流程必须使用确定性的 `MockLLMProvider`。

## 安全与仓库卫生

- 不得提交 API Key、密码、`.env`、生成的小说正文、大型二进制或本地数据库文件。
- 日志不得包含密钥或完整敏感配置。
- 不得删除或覆盖不属于当前任务的用户文件；保留无关的工作区改动。
- 新增环境变量时同步维护 `.env.example`，只提供安全占位值。

## 必须通过的质量门禁

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

