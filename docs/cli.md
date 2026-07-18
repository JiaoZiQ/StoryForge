# CLI

`storyforge` 与 REST API 复用同一 Application Service、Repository 和领域 Service。每个命令都支持 `--output human|json`；JSON 模式的标准输出只有一个可由 JSON parser 读取的文档。

## 分组命令

```text
storyforge project create|list|show
storyforge plan generate|show
storyforge chapter list|show|context|generate|evaluate|versions|diff
storyforge evaluation list|show
storyforge conflict list|resolve
storyforge fact list
storyforge workflow run|status|resume|cancel|events
storyforge demo m6
```

示例：

```powershell
uv run storyforge project create --database .\storyforge.db --title "雾岬" --genre "悬疑" --premise "档案员追查失踪记录。" --chapters 3 --words 300 --output json
uv run storyforge plan generate --database .\storyforge.db --project-id 1
uv run storyforge workflow run --database .\storyforge.db --project-id 1 --chapter-number 1 --scenario improve
uv run storyforge chapter versions --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge chapter diff --database .\storyforge.db --project-id 1 --chapter-number 1 --version-id 2 --old-version-id 1
uv run storyforge evaluation list --database .\storyforge.db --project-id 1 --chapter-number 1
uv run storyforge conflict list --database .\storyforge.db --project-id 1
uv run storyforge fact list --database .\storyforge.db --project-id 1 --output json
uv run storyforge workflow events --database .\storyforge.db --workflow-run-id 1
```

正文默认不显示；`chapter show --include-content` 是显式查看入口。Fact 命令只显示 accepted 数据。workflow run 是同步命令，返回时已经完成、需要人工复核或在指定节点暂停。

## 演示和兼容命令

```powershell
uv run storyforge demo-m6 --reset --output human
uv run storyforge demo m6 --reset --output json
```

M3–M5 的扁平命令仍保留兼容，包括 `create-project`、`generate-chapter`、`evaluate-chapter`、`run-workflow`、`resume-workflow`、`show-versions` 和 `demo-m3|m4|m5`。

## 退出码

- `0`：成功。
- `2`：命令行输入错误或旧命令的兼容状态错误。
- `3`：资源不存在。
- `4`：领域状态或并发冲突。
- `5`：provider/配置失败。
- `6`：数据库失败。
- `1`：已脱敏的其他内部错误。

CLI 不打印 traceback、Prompt、完整 provider 错误或密钥。演示固定使用 MockLLM、临时 SQLite 且不访问网络。

普通分组命令读取与 API 相同的 `STORYFORGE_LLM_PROVIDER`、model、base URL、timeout、retry 和 key 环境配置；未设置时默认 Mock。数据库仍使用命令显式给出的本地 `--database` 路径。`demo m6`/`demo-m6` 无论外部 provider 配置如何都固定使用离线 Mock。

## Milestone 7 部署命令

```powershell
uv run storyforge-wait-for-db
uv run storyforge-migrate
uv run storyforge-api
docker compose exec api storyforge demo-m7 --output human
docker compose exec api storyforge demo-m7 --output json
```

`demo-m7` 与临时 SQLite 的 `demo-m6` 不同：它要求当前 `STORYFORGE_DATABASE_URL` 是已迁移到 head 的 PostgreSQL，强制 Mock 模式，并创建唯一项目。JSON 输出是单一标准文档，包含 backend、revision、workflow/版本/评估/冲突/fact 计数，以及候选、未来和重复计数。

## Milestone 8 记忆与检索命令

```powershell
storyforge memory status --project-id 1 --output json
storyforge memory list --project-id 1 --output json
storyforge memory show --project-id 1 --memory-id 1 --output json
storyforge memory reindex --project-id 1 --chapter-version-id 2 --output json
storyforge retrieval search --project-id 1 --query "Mara brass key" --current-chapter 2 --output json
storyforge graph entities --project-id 1 --output json
storyforge graph relations --project-id 1 --current-chapter 2 --output json
storyforge graph neighbors --project-id 1 --entity-id 1 --current-chapter 2 --max-hops 2 --output json
storyforge demo-m8 --output json
```

完整 `demo-m8` 必须在已迁移的 PostgreSQL/pgvector 上运行，并要求 MockLLM、MockEmbedding 和无 API Key。SQLite 可以运行普通命令，但 vector 路由会明确降级；JSON 仍是单一标准文档。memory 列表默认不返回完整内容，任何 CLI 输出都不返回 embedding 数组。

## Milestone 10 governance commands

```powershell
storyforge provider list --output json
storyforge provider health --output json
storyforge usage summary --project-id 1 --output json
storyforge usage calls --workflow-run-id 1 --output json
storyforge budget show --project-id 1 --output json
storyforge budget set --project-id 1 --soft-limit 1 --hard-limit 2 --yes --output json
storyforge model-profile show --project-id 1 --output json
storyforge model-profile set --project-id 1 --profile balanced --yes --output json
storyforge privacy-policy set --project-id 1 --policy strict --yes --output json
storyforge demo-m10 --output json
```

Mutating commands require `--yes`; all JSON output is a single parseable document.
`provider smoke-test --provider openai-compatible` additionally requires
`STORYFORGE_ENABLE_REAL_PROVIDER_TESTS=true`, uses a fixed tiny request, and is
never part of default tests or demos.
