# ISV-Release

EC-AI 私有源码的**公开编译和二进制发布仓库**。不托管业务源码、账号配置、Cookie、API Key 或编译中间源码。

## 目录与流程

- 私有源码：`BrianOGG/EC-AI`。Node SEA / Nuitka 的原始编译脚本仍保留在私有仓库。
- 公开构建：`.github/workflows/product-grabber.yml` 和 `.github/workflows/audience-portrait.yml`，使用 GitHub Actions macOS ARM64、Windows x64 标准 Runner。
- 访问私有仓库：仅在可信 Actions 运行时使用 `EC_AI_SOURCE_TOKEN`，要求最小化 `Contents: read` 权限，`persist-credentials: false`。
- 分发产物：每个平台一份**已编译 Runtime** ZIP；一个小于 20,000,000 字节的**轻量 Skill** ZIP（根目录 `SKILL.md`）；SHA256 校验文件。
- 首次运行 Skill：按系统下载指定 Release 的 Runtime、校验 SHA256、缓存到用户目录，再调用原有安装脚本；无需安装 Node、Python 或编译工具。后续运行直接复用缓存。浏览器扩展仍可能需要用户手动加载。

## 日常使用

只需向私有 `EC-AI/main` 推送代码，公开仓库的定时构建任务会自动检查更新，约每两小时运行一次（GitHub schedule 可能延迟）。如需立即运行：在 [Actions](../../actions) 手动启动对应工作流。

| 项目 | 版本规则 | 自动发布条件 |
|---|---|---|
| Product Grabber | 私有 `product-scraping/product-grabber/package.json` 中的 `version` | **必须增加版本号**；相同版本不会重复构建，手动选择 `force` 可覆盖 |
| Audience Portrait | 私有 `audience-portrait/` 目录 Git tree hash（`g<12位>`） | 该项目目录有代码改动、且相应版本尚未发布时自动构建 |

旧的私有仓库 Actions 工作流将在公开迁移完成验证后删除，避免消耗私有 Actions 额度。业务和打包脚本不必从私有仓库迁移。

## 安全边界

1. 公开工作流**不接受 PR 或任意用户提供的 Git ref**；只使用私有 `main` 的已提交源码。不要随意扩大 workflow 触发范围。
2. 构建 Artifact 只上传产物目录，不上传完整 checkout、日志凭据、构建缓存或源码。公开 Release 只包含编译后的 Runtime 和轻量 Skill。
3. 不要把 `EC_AI_SOURCE_TOKEN` 放在文件、日志、Release 描述或提交中；90 天过期后需在 Actions Secrets 中轮换。
4. Node SEA / Nuitka 增加阅读门槛，并非不可逆向保护。公开下载编译产物不等于公开原始源码。
5. 首次使用需要网络连接；仅限 Apple Silicon macOS 和 Windows x64。真正的安装与浏览器登录须在用户本机验证。
