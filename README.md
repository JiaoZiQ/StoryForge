# StoryForge

StoryForge 计划成为一个面向长篇小说创作的多 Agent 系统，通过“规划、写作、事实抽取、一致性检查、评估、修订、记忆更新”的闭环逐章生成内容。

> 当前状态：Milestone 2（LLM 抽象与结构化输出）已完成。现在提供版本化 PromptRegistry、确定性 MockLLMProvider，以及带超时、指数退避重试、结构化校验和脱敏日志的 OpenAI-compatible provider；具体小说 Agent、工作流、业务 API 与 CLI 尚未实现。

## 架构概览

项目采用模块化单体和 `src` 布局。HTTP、用例编排、领域数据、持久化、LLM、Agent 与工作流保持单向依赖，详细边界见 [架构文档](docs/architecture.md)，关系表与约束见 [数据模型文档](docs/data-model.md)，模型调用边界见 [LLM 文档](docs/llm.md)。

```mermaid
flowchart LR
    Client["API / CLI"] --> Services["Application services"]
    Services --> Agents["Agents"]
    Services --> Workflows["LangGraph workflows"]
    Agents --> LLM["LLM provider interface"]
    Workflows --> Repositories["Repository interfaces"]
    Repositories --> Database["SQLite / PostgreSQL"]
```

这些组件是第一版目标架构，不代表当前里程碑已经实现全部功能。

## 工作流目标

```text
规划 → 写作 → 事实抽取 → 一致性检查 → 质量评估
    → 修订 → 再评估 → 接受或人工复核 → 更新长期记忆
```

工作流和 checkpoint 将在 Milestone 3–5 分步实现。

## 快速启动

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn storyforge.api.app:app --reload
```

服务启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

示例响应：

```json
{"status":"ok","service":"storyforge","version":"0.1.0"}
```

## 数据库配置

默认配置为 `sqlite:///./storyforge.db`，无需安装数据库服务。Alembic 和运行时代码都会动态读取 `DATABASE_URL`。

```powershell
# SQLite（默认）
uv run alembic upgrade head

# PostgreSQL + Psycopg 3（示例占位符，请从安全环境注入真实凭据）
$env:DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/storyforge"
uv run alembic upgrade head
```

repository 的写操作只执行 `flush`，事务的 commit/rollback 由调用方统一控制。SQLite 连接会自动启用外键约束，从而与 PostgreSQL 一样执行级联删除。

## Mock 与真实模型

默认开发和全部自动化测试使用 `MockLLMProvider`，不访问网络，也不需要 API Key。下面的演示会渲染一个具名、带版本的 prompt，并让 Mock provider 针对 Pydantic response model 返回确定性结果：

```powershell
uv run python scripts/milestone2_demo.py
```

OpenAI-compatible provider 从运行时环境读取配置；不要把真实密钥写入仓库或 `.env.example`：

```powershell
$env:OPENAI_API_KEY="<secret>"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="<structured-output-capable-model>"
```

可选可靠性配置为 `LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`、`LLM_REPAIR_RETRIES` 和 `LLM_RETRY_BASE_DELAY_SECONDS`。Provider 禁用 SDK 内建重试，由项目统一执行有限次数的指数退避；结构化输出通过 Pydantic v2 校验，格式或 schema 错误只进行有限次数修复重试。所有公开失败均转换成 `storyforge.llm` 内部异常，日志只记录 provider、model、prompt 名称/版本、尝试次数和安全状态，不记录 key、prompt 正文或响应正文。

Prompt 不应直接散落在业务模块中。使用 `PromptRegistry` 注册不可变的名称/版本，再把渲染出的 `PromptRequest` 交给 provider；`LLMResponse.prompt` 会记录实际解析出的 prompt 名称和版本。完整接口与错误策略见 [LLM 文档](docs/llm.md)。

## API 与 CLI

当前只实现 `GET /health`。项目、章节和评估 API 将在 Milestone 6 暴露；`storyforge` CLI 与 `storyforge demo` 也将在该里程碑实现。

## 开发与测试

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

默认测试使用内存 SQLite、MockLLMProvider 和 `httpx.MockTransport` 离线运行，不需要数据库服务、Docker 或 API Key。测试覆盖数据层、迁移、prompt 版本、确定性 mock、结构化输出、超时、重试、无效 JSON/schema、密钥缺失和日志脱敏。

## Docker

Dockerfile、Docker Compose 和可选 PostgreSQL 配置计划在 Milestone 7 添加。当前版本不假设本机安装 Docker。

## 当前限制

- 数据层和通用 LLM 边界已实现，但尚无业务 application service 或项目/章节 API。
- 没有具体小说 Agent、记忆检索、自动评估或 LangGraph 工作流。
- 没有业务 API、CLI 或 Docker 部署配置。
- PostgreSQL 驱动与 URL 已配置，但默认测试不连接真实 PostgreSQL 服务。
- 真实 OpenAI-compatible endpoint 需要自行提供支持 strict structured output 的模型与凭据；自动化测试不会连接真实模型服务。

## Roadmap

完整阶段计划见 [ROADMAP.md](ROADMAP.md)。下一阶段是 Milestone 3：规划与单章生成；需在明确指示后开始。

## License

[MIT](LICENSE)
