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
