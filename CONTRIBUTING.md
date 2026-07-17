# Contributing to StoryForge

感谢你改进 StoryForge。当前项目按 `ROADMAP.md` 的里程碑顺序交付；请先在 Issue 或讨论中确认较大范围变更，避免同时引入未计划的基础设施或业务能力。

## 开发环境

需要 Python 3.12 和 uv：

```powershell
git clone https://github.com/JiaoZiQ/StoryForge.git
Set-Location StoryForge
uv sync --locked --all-groups
uv run alembic upgrade head
uv run storyforge demo-m6 --output json
```

也可按 README 使用 Docker Compose。默认 MockLLM 测试不需要 API Key 或公网。

## 分支和提交

- 从最新主分支创建短生命周期分支。
- 每个提交保持单一目的，推荐 Conventional Commits 风格，例如 `fix: enforce workflow uniqueness`。
- 不要将无关格式化、生成正文或本地环境文件混入提交。
- 不要重写仓库中已有 Alembic revision；schema 变化必须新增 migration。

## 质量门禁

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic check
git diff --check
```

修改跨数据库持久化或部署代码时，还必须按 README 运行 `pytest -m postgres --no-cov`、Docker build 和 Compose health/demo 检查。

## 工程规则

- API/CLI 是薄适配层；业务规则放在 service，SQL 放在 repository。
- LLM 调用只能经过 `llm` provider，输出必须通过 Pydantic v2 校验。
- Prompt 放在 PromptRegistry 管理的文件中；修改时提升显式版本并补测试。
- 单元测试必须确定、离线、不需要 API Key，也不得用固定 sleep 模拟等待。
- 日志和错误不得包含正文、完整 Prompt、Authorization、Cookie、密钥或数据库密码。
- 新环境变量必须同步 `.env.example` 和 README。

## Pull Request 检查清单

- [ ] 变更只属于声明的里程碑/问题范围。
- [ ] 测试覆盖正常、失败、事务和安全边界。
- [ ] Ruff、mypy、pytest、coverage 与 `git diff --check` 通过。
- [ ] 模型变化有新 migration，SQLite/PostgreSQL 均已验证。
- [ ] Prompt 变化有版本和结构化输出测试。
- [ ] README、CHANGELOG 和 `docs/progress.md` 已更新。
- [ ] 未提交 `.env`、密钥、数据库、日志、正文或缓存。

参与项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
