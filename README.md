# ISV-Release

EC-AI 私有源码的**公开编译和二进制发布仓库**。不托管业务源码、账号配置、Cookie、API Key 或编译中间源码。

## 目录与流程

- 私有源码：`BrianOGG/EC-AI`。Node SEA / Nuitka 的原始编译脚本仍保留在私有仓库。
- 公开构建：`.github/workflows/product-grabber.yml` 和 `.github/workflows/audience-portrait.yml`，使用 GitHub Actions macOS ARM64、Windows x64 标准 Runner。
- 访问私有仓库：仅在可信 Actions 运行时使用 `EC_AI_SOURCE_TOKEN`，要求最小化 `Contents: read` 权限，`persist-credentials: false`。
- 分发产物：每个平台一份**已编译 Runtime** ZIP；一个小于 20,000,000 字节的**轻量 Skill** ZIP（根目录 `SKILL.md`）；SHA256 校验文件。
- 首次运行 Skill：按系统下载指定 Release 的 Runtime、校验 SHA256、缓存到用户目录，再调用原有安装脚本；无需安装 Node、Python 或编译工具。后续运行直接复用缓存。浏览器扩展仍可能需要用户手动加载。

## 版本管理（自动 Dev / 手动正式版）

**每个项目独立维护 SemVer 版本号，计数只以成功发布的公开 GitHub Release 为准。** 失败的构建不占版本，历史版本不覆盖。

- 开发版本：首次为 `1.0.0-dev.1`，下次项目源码有变化时 `1.0.0-dev.2`、`1.0.0-dev.3`，依此递增。GitHub Release 标记为 Pre-release。
- 手动正式版：在 [Actions](../../actions) 找到项目的公开构建工作流，选择 **Run workflow**，在 `release_version` 中输入 `1.0.0` 或 `1.1.0`。必须大于该项目现有最新版本；留空即自动 Dev。
- 正式版之后：例如手动发布 `1.0.0` 后，下次改动自动进入 `1.0.1-dev.1`；手动发布 `1.1.0` 后，下次改动自动进入 `1.1.1-dev.1`。
- 更新检测：公开仓库定时约每两小时读取私有 `EC-AI/main`，只检查对应项目 Git Tree SHA；不变则跳过，变化则自动编译。多个提交被一次定时构建检测到时，合并为一个 Dev 版本。
- 唯一历史计数在 GitHub Release 标签中，格式分别为 `product-grabber-v1.0.0-dev.1`、`audience-portrait-v1.0.0-dev.1`。旧的 `product-grabber-v0.5.0` 属于历史包，不参与新版本计数。
- 构建时仅在临时工作副本里修改 Product Grabber `package.json` 与 Chrome 扩展 `manifest.json`，确保 SEA 内置版本与 GitHub Release 相同。Chrome 要求 `manifest.version` 为数字，如 `1.0.0.1`；真实 Dev 版本显示在 `manifest.version_name` 中。稳定版 Chrome 数字末段为 `65535`。
- Audience Portrait 通过 `PORTRAIT_BUILD_VERSION` 将相同版本号传给 macOS 和 Windows Nuitka 构建，无需修改私有源码。
- 只上传编译后的单平台 Runtime 和根目录包含 `SKILL.md` 的小于 20 MB Skill ZIP，所有 Runtime SHA256 值锁定在对应的 Skill ZIP 内。用户安装老版本时仍能取得老 Runtime。

### 两个仓库如何操作

| 仓库 | 日常操作 |
|---|---|
| `EC-AI`（私有） | 正常提交、Push 业务源码和原有编译脚本。**不用更新项目版本号，不用配置 Actions，不用管理 Release** |
| `ISV-Release`（公开） | 维护构建 Workflow 与轻量安装器；每两小时自动检查源码，也可以手动指定正式版本构建 |

注意：Actions Secrets 里的 `EC_AI_SOURCE_TOKEN` 需要维持对私有 `EC-AI` 仓库 `Contents: read` 的最小权限，并在过期前轮换。不要开放接受不受信任 PR 的构建触发器。

## 安全边界

1. 公开工作流**不接受 PR 或任意用户提供的 Git ref**；只使用私有 `main` 的已提交源码。不要随意扩大 workflow 触发范围。
2. 构建 Artifact 只上传产物目录，不上传完整 checkout、日志凭据、构建缓存或源码。公开 Release 只包含编译后的 Runtime 和轻量 Skill。
3. 不要把 `EC_AI_SOURCE_TOKEN` 放在文件、日志、Release 描述或提交中；90 天过期后需在 Actions Secrets 中轮换。
4. Node SEA / Nuitka 增加阅读门槛，并非不可逆向保护。公开下载编译产物不等于公开原始源码。
5. 首次使用需要网络连接；仅限 Apple Silicon macOS 和 Windows x64。真正的安装与浏览器登录须在用户本机验证。
