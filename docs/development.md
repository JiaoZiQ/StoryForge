# 开发指南

## 前置条件

- Python 3.12
- uv
- PowerShell 示例命令

默认开发、测试与 M5 演示不需要 Docker、外部数据库、API Key 或公网。

## 安装

```powershell
uv sync --all-groups
uv run python --version
```

`uv.lock` 是依赖安装的锁定来源。不要提交 `.venv`、工具缓存或本地数据库。

## 数据库

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

全新迁移回归：

```powershell
$env:DATABASE_URL="sqlite:///./migration-check.sqlite3"
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade base
Remove-Item -LiteralPath .\migration-check.sqlite3
Remove-Item Env:DATABASE_URL
```

测试同时覆盖空库升级、已有 M1/M3/M4 数据升级、metadata 对齐、降级到 M4、降级 base 和再次升级。新增字段或表必须创建新 migration，不能改写已交付 revision。

## 质量检查

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

覆盖率已由 `uv run pytest` 自动启用并要求至少 80%。M4 相关测试：

```powershell
uv run pytest tests/unit/test_milestone4_mechanical.py -q
uv run pytest tests/unit/test_milestone4_consistency.py -q
uv run pytest tests/unit/test_milestone4_critic.py -q
uv run pytest tests/unit/test_milestone4_scoring.py -q
uv run pytest tests/integration/test_milestone4_evaluation_service.py -q
uv run pytest tests/integration/test_milestone4_cli.py -q
```

M5 相关测试：

```powershell
uv run pytest tests/unit/test_milestone5_revision.py -q
uv run pytest tests/integration/test_milestone5_workflow.py -q
uv run pytest tests/integration/test_milestone5_migration.py -q
uv run pytest tests/integration/test_milestone5_cli.py -q
```

## 离线调试

```powershell
uv run storyforge demo-m4 --database .\debug-m4.sqlite3 --reset
uv run storyforge show-evaluation --database .\debug-m4.sqlite3 --project-id 1 --chapter-number 1 --latest
uv run storyforge list-conflicts --database .\debug-m4.sqlite3 --project-id 1 --status open
```

完整工作流调试：

```powershell
uv run storyforge demo-m5 --database .\debug-m5.sqlite3 --checkpoint .\debug-m5-checkpoints.sqlite3 --reset
uv run storyforge workflow-status --database .\debug-m5.sqlite3 --checkpoint .\debug-m5-checkpoints.sqlite3 --workflow-run-id 2
uv run storyforge workflow-history --database .\debug-m5.sqlite3 --checkpoint .\debug-m5-checkpoints.sqlite3 --workflow-run-id 2
uv run storyforge show-versions --database .\debug-m5.sqlite3 --project-id 2 --chapter-number 1
uv run storyforge compare-versions --database .\debug-m5.sqlite3 --workflow-run-id 2
```

`demo-m5` 的项目 1/2/3 分别对应一次通过、修订后通过和达到上限；项目 4 用于 checkpoint 恢复。Mock workflow 场景为 `pass`、`improve` 和 `stagnate`。

`MockLLMProvider` 按 Pydantic response model 注册确定性返回。Critic 场景可选 `normal`、`death`、`outline`、`poor` 和 `conflict`；生产 service 不包含测试场景判断。

单章分步调试：

```powershell
uv run storyforge create-project --database .\debug.db --title "Test" --genre "Mystery" --premise "A moving lighthouse." --chapters 3 --words 300
uv run storyforge plan --database .\debug.db --project-id 1
uv run storyforge generate-chapter --database .\debug.db --project-id 1 --chapter-number 1
uv run storyforge evaluate-chapter --database .\debug.db --project-id 1 --chapter-number 1
```

## 常见问题

- `Fact extraction must succeed before evaluation`：先修复/重试事实抽取，不能将缺失事实的结果冒充完整评估。
- `Chapter cannot be evaluated from status ...`：章节未生成完成、已经在评估，或状态转换非法。
- `CriticAgent failed; local evaluation results were preserved`：查询最新 Evaluation，可看到 `partial_failed` 的 Mechanical/Consistency 结果；修复 provider 后重试会新增版本。
- `alembic check` 报新操作：模型与 head 不一致，必须新增或修复 migration。
- `Only paused workflows can be resumed`：WorkflowRun 已完成、失败、取消，或没有在显式 pause 节点停下。
- `Another workflow is already active for this chapter`：先查询/恢复/取消现有 pending、running 或 paused 工作流。

## 安全检查

- 测试用 monkeypatch 阻断 `demo-m4`/`demo-m5` 网络连接并删除 API Key 环境变量。
- 日志测试确认不出现整章正文、人物 secrets 或未来事实。
- Prompt 请求可在 Mock 的 `requests` 中检查，确保只包含显式 CriticContext。
- 不把真实密钥、正文、SQLite 文件或带凭据 URL 提交到仓库。
- checkpoint 文件按字节检查不包含完整正文或 `sk-` 密钥；WorkflowEvent 响应不包含正文/Payload/Prompt。
