# LLM 抽象与结构化输出

## 边界

`storyforge.llm` 是 StoryForge 所有模型调用的唯一出口。调用方只传递显式、最小的 `PromptRequest` 和一个 Pydantic v2 response model；provider 只返回已验证的 `LLMResponse[T]`。该层不包含小说规划、写作、评估或工作流规则。

```text
PromptRegistry
  -> PromptRequest(name, version, messages)
  -> LLMProvider.generate(request, ResponseModel)
  -> LLMResponse(validated output, provider/model, prompt version, attempts, usage)
```

## PromptRegistry

每个 `PromptTemplate` 由名称、版本和一组带角色的消息模板组成。注册后的 `(name, version)` 不可覆盖；registry 可以显式选择默认版本，也可以按精确版本渲染。渲染会拒绝缺失变量、未使用变量和复杂属性访问，避免 prompt 输入静默偏移。

```python
from storyforge.llm import PromptMessageTemplate, PromptRegistry, PromptTemplate

registry = PromptRegistry()
registry.register(
    PromptTemplate(
        name="example.summary",
        version="1.0.0",
        messages=(
            PromptMessageTemplate(role="system", template="Return structured data."),
            PromptMessageTemplate(role="user", template="Summarize: {text}"),
        ),
    )
)
request = registry.render("example.summary", variables={"text": "..."})
```

渲染得到的 `PromptRequest.prompt` 会原样进入 `LLMResponse.prompt`，供后续持久化实际使用的 prompt 版本。具体业务 prompt 将与对应 Agent 一起在后续里程碑添加，本阶段不提前创建小说 Agent prompt。

## MockLLMProvider

Mock provider 不创建 HTTP client、不读取密钥，也不访问网络。调用方按 response model 注册字典或 Pydantic 实例；注册时会深拷贝数据，后续外部修改不会改变结果。每次调用都会重新通过目标 model 验证，因此不会绕过结构化输出契约。

`MockFailure` 可按调用顺序注入以下故障：

- `TIMEOUT`
- `INVALID_JSON`
- `SCHEMA_VALIDATION`
- `CALL_FAILURE`

故障序列耗尽后恢复为已注册的确定性响应，便于测试调用方自己的恢复策略。

## OpenAICompatibleProvider

Provider 使用 OpenAI Python SDK 的 `chat.completions.parse(..., response_format=ResponseModel)`。SDK 会为 Pydantic model 生成 strict JSON schema，返回内容仍会通过 response model 验证。SDK 内建重试固定关闭，避免与项目策略叠加。

配置在 `OpenAICompatibleProvider.from_env()` 调用时读取：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 无 | 必填；内部使用 `SecretStr`，禁止记录 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | HTTP(S) endpoint；禁止用户信息、query 和 fragment |
| `OPENAI_MODEL` | 无 | 必填；必须支持 strict structured output |
| `LLM_TIMEOUT_SECONDS` | `30` | 单次 SDK 请求超时 |
| `LLM_MAX_RETRIES` | `2` | timeout、连接、429 和可重试 HTTP 状态的额外尝试数 |
| `LLM_REPAIR_RETRIES` | `1` | 无效 JSON、schema 或长度截断的额外修复尝试数 |
| `LLM_RETRY_BASE_DELAY_SECONDS` | `0.5` | 指数退避基数 |

传输重试等待时间为 `base_delay * 2^retry_index`。401/403 不重试；显式 refusal/content filter 不修复；无效 JSON、schema 和截断输出只使用独立、有限的修复预算。测试可注入 sleeper，因此不使用真实 `sleep`。

## 内部异常

外部 SDK、HTTP 和 Pydantic 异常不会跨越 provider 边界。公开异常均继承 `LLMError`：

- `LLMConfigurationError`
- `LLMTimeoutError`
- `LLMAuthenticationError`
- `LLMRateLimitError`
- `LLMServiceError`
- `LLMInvalidResponseError`
- `LLMRefusalError`
- `PromptRegistryError`

调用异常只包含安全摘要、尝试次数和可选状态码，不附带请求头、密钥、prompt 正文或 provider 响应正文。

## 测试策略

自动化测试默认完全离线：Mock provider 测试确定性和故障注入；OpenAI-compatible 测试使用真实 SDK，但把 `httpx.MockTransport` 注入 SDK client。测试覆盖成功、环境配置、strict schema、timeout、指数退避、连接/HTTP/429 重试、无效 JSON、schema 失败、refusal、密钥缺失和日志脱敏。

运行本阶段演示：

```powershell
uv run python scripts/milestone2_demo.py
```
