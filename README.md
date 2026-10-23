# Tools & Skills

提供以下工具的 Agent Skill 安装包，支持 **macOS（Apple Silicon）** 和 **Windows（x64）**。

## KOL / E2E Mac 测试版下载

以下两个便携测试版仅支持 **macOS Apple Silicon（ARM64）**。已通过 CI 的核心导入、浏览器检查、服务启动、状态、首页访问和停止检查；实际设备安装、登录及业务任务仍需测试。Windows 版本正在排查启动问题。

| 项目 | Mac 测试版本 | 下载 |
| --- | --- | --- |
| KOL Selection | `1.0.0-dev.2` | [下载 Mac Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/kol-selection-portable-mac-1.0.0-dev.2/kol-selection-portable-mac-skill-1.0.0-dev.2.zip) · [完整运行时与校验文件](https://github.com/BrianOGG/ISV-Release/releases/tag/kol-selection-portable-mac-1.0.0-dev.2) |
| E2E | `1.0.0-dev.1` | [下载 Mac Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/e2e-portable-mac-1.0.0-dev.1/e2e-portable-mac-skill-1.0.0-dev.1.zip) · [完整运行时与校验文件](https://github.com/BrianOGG/ISV-Release/releases/tag/e2e-portable-mac-1.0.0-dev.1) |

下载并解压对应的 **Mac Skill ZIP**，按其中的 SKILL.md 导入客户端或执行安装。首次安装需要联网下载完整运行时（KOL 约 377 MB，E2E 约 272 MB）；已包含 Python、公开依赖和浏览器，无需在 Mac 上自行安装 Python 或运行 pip。请使用上面的 Mac 便携版入口测试；下面的通用版本目录保留历史分发入口。

## KOL / E2E Windows 测试版下载

以下便携测试版仅支持 **Windows x64**。自带 Python、运行依赖和浏览器，不需要自行配置 Python 或运行 pip。已通过 CI 中中文及空格路径下的安装、重复安装、启动、状态、网页访问和停止检查；真实设备、平台登录和业务任务仍需测试。

| 项目 | Windows 测试版本 | 下载 |
| --- | --- | --- |
| E2E | `1.0.0-dev.1` | [下载 Windows Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/e2e-portable-win-1.0.0-dev.1/e2e-portable-win-skill-1.0.0-dev.1.zip) · [完整运行时与校验文件](https://github.com/BrianOGG/ISV-Release/releases/tag/e2e-portable-win-1.0.0-dev.1) |

下载并解压 Skill ZIP，按其中 SKILL.md 安装；首次安装自动下载同一 Release 的完整运行时。KOL Windows 测试版发布后将在此补充下载入口。

## 通用版本目录

<!-- RELEASES:START -->
| 工具 | 功能 | 最新版本 | 下载 |
| --- | --- | --- | --- |
| **Product Grabber** | 天猫、京东商品信息采集与管理 | `1.0.0-dev.3`（开发版） | [下载 Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/product-grabber-v1.0.0-dev.3/product-grabber-skill-1.0.0-dev.3.zip) · [版本详情](https://github.com/BrianOGG/ISV-Release/releases/tag/product-grabber-v1.0.0-dev.3) |
| **Audience Portrait** | 多平台人群画像采集与 Excel 导出 | `1.0.0-dev.2`（开发版） | [下载 Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/audience-portrait-v1.0.0-dev.2/audience-portrait-skill-1.0.0-dev.2.zip) · [版本详情](https://github.com/BrianOGG/ISV-Release/releases/tag/audience-portrait-v1.0.0-dev.2) |
| **KOL Selection** | KOL 筛选、画像分析与报告工作台 | `1.0.0-dev.2`（开发版） | [下载 Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/kol-selection-v1.0.0-dev.2/kol-selection-skill-1.0.0-dev.2.zip) · [版本详情](https://github.com/BrianOGG/ISV-Release/releases/tag/kol-selection-v1.0.0-dev.2) |
| **E2E** | 达摩盘、灵犀及巨量云图 E2E 工作台 | `1.0.0-dev.1`（开发版） | [下载 Skill ZIP](https://github.com/BrianOGG/ISV-Release/releases/download/e2e-v1.0.0-dev.1/e2e-skill-1.0.0-dev.1.zip) · [版本详情](https://github.com/BrianOGG/ISV-Release/releases/tag/e2e-v1.0.0-dev.1) |
<!-- RELEASES:END -->

## 使用

下载对应工具的 **Skill ZIP**，导入支持 Agent Skills 的客户端，按提示完成安装。首次安装需要联网。

[查看全部版本与历史发布](https://github.com/BrianOGG/ISV-Release/releases)
