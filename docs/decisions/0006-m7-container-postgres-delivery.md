# ADR 0006: Container, PostgreSQL, and delivery boundary

- Status: Accepted
- Date: 2026-07-14

## Context

Milestone 6 已有稳定 API/CLI 和 SQLite 离线闭环，但新机器缺少可重复的 PostgreSQL、迁移顺序、容器健康、生产配置和 CI 约束。

## Decision

1. Docker 使用 Python 3.12.12 slim 多阶段构建。uv 只在 builder 出现，依赖由 `uv.lock` 安装；runtime 只复制虚拟环境和迁移文件。
2. runtime 固定 UID/GID 10001 非 root，并只保证 `/tmp/storyforge` 等必要目录可写；CMD 使用 exec form 让 Uvicorn 接收停止信号。
3. Compose 使用独立 one-shot migrate 服务：PostgreSQL healthy 后迁移，迁移成功后 API 启动。API 不在 import time 或默认启动时擅自迁移。
4. PostgreSQL 16 用于 Compose 和显式 marker 集成测试；SQLite 保留为默认本地开发和单实例 checkpoint。两者共享 SQLAlchemy 模型与 Alembic 历史。
5. PostgreSQL 测试数据库名必须以 `_test` 结尾，测试会清理该库；CI 通过 service container 运行 migration、Alembic check、API/workflow/demo 测试。
6. CI 划分 quality、postgres-tests、docker-build，使纯 Python 回归、真实数据库差异和镜像可运行性分别可定位。CI 只用 MockLLM，不需要真实密钥。
7. development 可默认 SQLite/Mock；test 必须显式数据库；production 必须 PostgreSQL、非 Mock provider、非开发密码，并禁止 credentialed wildcard CORS。
8. `/health` 是无依赖 liveness；`/api/v1/ready` 检查数据库和精确 migration head。Compose API healthcheck 使用 readiness。
9. 同章节活跃工作流使用 SQLite/PostgreSQL 部分唯一索引，补足应用层检查的并发竞态。
10. 继续采用仓库已有 MIT License，以便宽松开源使用；贡献与安全边界分别由 CONTRIBUTING/SECURITY 说明。
11. 当前镜像和 Compose 是本地/单机交付边界：API 无认证、SQLite checkpoint 非共享，不应直接暴露公网。
12. 不自动发布镜像。仓库尚无稳定版本、签名、SBOM、registry 命名与发布审批策略，CI 只构建和检查本地镜像。
13. 不引入 Redis/Celery。当前工作流是同步单实例语义，队列会扩大状态、重试与运维范围，留待后续明确里程碑。

## Consequences

新机器可以只用 Docker Compose 或 Python 3.12 + uv 完成迁移、API、CLI 和 Mock 演示。迁移失败会阻止 API ready，PostgreSQL 差异进入 CI。代价是当前只支持单机同步运行；部署者仍需提供认证、TLS、密钥管理、备份、高可用和多实例 checkpoint 方案。
