# 开发进度

## Milestone 0：仓库初始化

状态：已完成并通过质量门禁。

已完成：

- 初始化 Git 仓库与 Python 3.12 `src` 布局。
- 创建未来模块、测试、文档、迁移和脚本目录。
- 配置运行依赖和 `dev` 依赖组。
- 配置 pytest/coverage、Ruff 和 strict mypy。
- 实现带 Pydantic 响应模型的 `GET /health`。
- 添加健康检查测试及基础项目文档。

未开始：

- Milestone 2 及之后的 LLM、Agent、工作流、业务 API、CLI 和部署功能。

验收命令：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -c "from storyforge.api.app import app; print(app.title)"
```

2026-07-13 验收结果：Python 3.12.12；Ruff format/check 通过；strict mypy 通过；pytest 1 passed；总覆盖率 100%；`/health` 返回 HTTP 200。

## Milestone 1：领域模型与数据库

状态：已完成并通过最终质量门禁。

已完成：

- 实现 Project、Character、Location、StoryRule、Chapter、Fact、Foreshadowing、Evaluation、Revision 和 WorkflowRun 的 SQLAlchemy 2 映射。
- 为全部实体提供 Pydantic v2 create/update/read schema。
- 默认使用 SQLite，并通过 `DATABASE_URL` 支持 `postgresql+psycopg://`。
- 实现外键启用、engine、session factory、事务 context manager 和类型化 repository。
- 配置 Alembic，并从模型 metadata 生成首迁移。
- 覆盖 CRUD、project/chapter 级联、事务回滚、迁移和关键约束。

关键不变量：

- 删除 project 会删除全部直接和间接子数据。
- chapter number 在 project 内唯一。
- fact 结束章节不得早于起始章节，confidence 必须在 0..1。
- evaluation 全部分数必须在 0..100。
- revision 必须推进版本号，新版本号在 chapter 内唯一。

验收命令：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade base
```

2026-07-13 独立验收结果：从锁文件无缓存重建 Python 3.12.12 环境；Ruff format/check 通过；strict mypy（src + tests）通过；pytest 29 passed；总覆盖率 100%；Alembic upgrade/current/check/downgrade 通过；迁移后 repository 实际写入 1 个 project 和 1 个 chapter；PostgreSQL 方言离线迁移编译通过。
