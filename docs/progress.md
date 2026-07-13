# 开发进度

## Milestone 0：仓库初始化

状态：已完成并验收。

交付了 Python 3.12 工程、质量工具、最小健康检查与基础文档。

## Milestone 1：领域模型与数据库

状态：已完成并验收。

交付了基础领域表、schema、repository、SQLite/PostgreSQL 配置、Alembic 初始迁移与数据层测试。

## Milestone 2：LLM 抽象与结构化输出

状态：已完成并验收。

交付了统一 LLM 边界、确定性 Mock、OpenAI-compatible provider、版本化 Prompt、重试与脱敏错误策略。

## Milestone 3：规划与单章生成

状态：已完成并通过最终独立验收。

已完成：

- 规划、写作、事实抽取三个单一职责 Agent。
- 六个独立且版本化的 system/user Prompt。
- 原子保存完整计划的 `PlanningService`。
- 防未来信息泄漏、秘密隔离、事实相关性筛选与字符预算。
- 章节生成、事实抽取、人物状态与伏笔更新。
- 章节完整版本快照与显式失败状态。
- 第二个 Alembic 迁移。
- 最小 M3 CLI 与 `demo-m3` 完全离线演示。
- 103 项自动化测试全部通过；当前总覆盖率 95.71%。

明确未开始：

- Milestone 4 的 MechanicalEvaluator、LLMCritic、ConsistencyAgent 和评分。
- Milestone 5 的 LangGraph、checkpoint、RevisionAgent 与自动修订循环。
- Milestone 6 的完整业务 API 和生产 CLI。
- Milestone 7 与后续基础设施、前端及多媒体能力。

M3 验收命令：

```powershell
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic upgrade head
uv run alembic check
uv run storyforge demo-m3 --database .\storyforge-m3-demo.sqlite3 --reset
```

2026-07-13 最终验收结果：删除本仓库虚拟环境和工具缓存后，使用锁文件与 CPython 3.12.12 重装 51 个包；Ruff format/check、strict mypy 和 103 项 pytest 全部通过，总覆盖率 95.71%；全新 SQLite 的 Alembic upgrade/current/check/downgrade 通过；`demo-m3` 在同一数据库连续执行两次成功，分别创建 project 1 和 project 2，且每次都持久化 3 章计划、1 个生成章节、1 条事实与 1 个完整版本快照。README 的分步 CLI 和真实 Uvicorn `/health` 也已执行成功。未启动 Milestone 4。
