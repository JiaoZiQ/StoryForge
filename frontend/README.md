# StoryForge Web

Milestone 9 的可信本地控制中心。它只调用 FastAPI 公开接口，不包含数据库访问、LLM SDK 或业务规则。

## 本地开发

先在仓库根目录启动 API，再启动 Web：

```powershell
uv run uvicorn storyforge.api.app:create_app --factory
Set-Location frontend
npm ci
npm run dev
```

开发模式默认把 `/backend/*` 转发到 `http://127.0.0.1:8000`。生产/Compose 必须在服务端设置 `STORYFORGE_INTERNAL_API_URL`；它不会进入浏览器 bundle。浏览器不得持有 `STORYFORGE_LLM_API_KEY`、embedding key 或数据库 URL。

## 质量命令

```powershell
npm run generate:api
npm run check:api
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
$env:PLAYWRIGHT_EXTERNAL_SERVER="1"
npm run test:e2e
```

`generate:api` 从 FastAPI 应用导出 `docs/openapi.json`，再生成 `lib/api/generated.ts`。生成类型用于编译期校验，`lib/api/schemas.ts` 的 Zod schema 负责运行时边界；两者不能互相替代。

Playwright 场景各自创建项目，不依赖执行顺序。真实 E2E 需要 PostgreSQL + pgvector、MockLLM/MockEmbedding 和已经运行的 Compose。浏览器截图只在失败时保留；trace 被关闭，避免响应正文进入构建制品。

## 数据与安全边界

- 项目、章节、版本列表默认不请求正文；章节正文只在 Content tab 打开时请求。
- Fact 请求固定 `status=accepted`；未来边界继续由 API 强制。
- 工作流只在非终态时每 3 秒轮询；completed/failed/cancelled 不显示 resume/cancel。
- Graph 查询只允许 1 或 2 hops，并提供与 Canvas 等价的文本列表。
- 检索调试只复制计数与来源摘要，不复制 embedding。
- server proxy 只允许固定上游和有限 header，拒绝超过 1 MiB 的请求体，不转发 cookie。

当前没有登录、RBAC、WebSocket、异步任务队列、多人协作或公网部署安全保证。
