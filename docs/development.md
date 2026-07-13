# 开发指南

## 前置条件

- Python 3.12
- uv
- PowerShell 示例命令

M3 的默认开发、测试与演示不需要 Docker、数据库服务、API Key 或公网。

## 安装

```powershell
uv sync --all-groups
uv run python --version
```

`uv.lock` 是依赖安装的锁定来源。不要把 `.venv` 提交到仓库。

## 数据库

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

全新迁移回归建议使用临时 SQLite 文件：

```powershell
$env:DATABASE_URL="sqlite:///./migration-check.sqlite3"
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade base
Remove-Item -LiteralPath .\migration-check.sqlite3
Remove-Item Env:DATABASE_URL
```

## 质量检查

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

单个测试文件：

```powershell
uv run pytest tests/integration/test_milestone3_workflow.py -q
```

## 离线调试

```powershell
uv run storyforge demo-m3 --database .\debug-m3.sqlite3 --reset
uv run storyforge show-context --database .\debug-m3.sqlite3 --project-id 1 --chapter-number 1
uv run storyforge show-chapter --database .\debug-m3.sqlite3 --project-id 1 --chapter-number 1
```

`MockLLMProvider` 按 Pydantic response model 注册确定性返回。三个 M3 Agent 使用不同 response model，因此一个 provider 可以稳定返回三个阶段的数据。失败测试使用 `MockFailure` 注入 timeout、无效结构或调用失败。

## 常见问题

- `Project already has a plan`：未显式允许覆盖；无正文时使用 `plan --replace-existing`。
- `Chapter already has content`：未显式允许重新生成；使用 `generate-chapter --regenerate`，旧正文会保留在 `chapter_versions`。
- `fact_extraction_failed`：正文和快照已保存，事实事务没有部分提交；可显式重新生成重试。
- `alembic check` 报新操作：模型与 head 迁移不一致，必须新增或修复迁移，不能只运行 `create_all`。

## 安全

- 不把真实密钥写入命令历史、仓库或测试。
- 本地数据库和生成正文不提交。
- 日志不输出 Prompt 正文、模型响应正文、密钥或带凭据 URL。
