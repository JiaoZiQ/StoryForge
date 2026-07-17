# Security Policy

## Supported versions

当前仓库处于 pre-alpha，只有主分支最新提交接受安全修复；尚无稳定发布分支或长期支持版本。

## Reporting a vulnerability

请通过 GitHub 仓库 Security 页面使用 private vulnerability reporting（如该功能可用）提交报告。若私密报告入口不可用，请先创建不包含利用细节、密钥或个人数据的普通 Issue，请维护者提供私密沟通方式。

不要在公开 Issue、讨论、日志或复现仓库中发布真实 API Key、数据库密码、Authorization/Cookie、未公开正文或读者数据。报告应尽量包含受影响版本、影响、最小复现条件和建议缓解方式。

## Current security boundary

- API 当前没有认证、授权、多租户、速率限制或 CSRF 防护，不能直接暴露到公网。
- Compose 默认凭据仅用于绑定到 `127.0.0.1` 的本地开发，不能用于生产。
- MockLLM 是默认验证路径；真实 provider 密钥只应通过运行时环境注入。
- 生产使用者必须在反向代理、网络访问控制、TLS、密钥管理、数据库备份和监控方面自行加固。
- StoryForge 会避免在应用日志中记录请求体、响应体、完整 Prompt、正文和凭据，但部署者仍应保护容器与平台日志。
