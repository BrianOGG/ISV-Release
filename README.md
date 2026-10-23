# Agent Skills

支持 **macOS Apple Silicon（ARM64）** 与 **Windows x64**。导入对应 Skill 后，安装入口按平台选择、下载并校验对应的完整运行包，无需手动选择 Runtime。

- [商品信息采集（Product Grabber）](https://github.com/BrianOGG/ISV-Release/releases/download/product-grabber-v1.0.0-dev.3/product-grabber-skill-1.0.0-dev.3.zip)
- [人群画像（Audience Portrait）](https://github.com/BrianOGG/ISV-Release/releases/download/audience-portrait-v1.0.0-dev.2/audience-portrait-skill-1.0.0-dev.2.zip)
- [KOL 筛选（固定 Skill v1.0.1）](https://github.com/BrianOGG/ISV-Release/releases/download/skills-fixed-v1.0.1/kol-selection-skill-1.0.1.zip)
- [E2E（固定 Skill v1.0.1）](https://github.com/BrianOGG/ISV-Release/releases/download/skills-fixed-v1.0.1/e2e-skill-1.0.1.zip)

KOL/E2E 的 Skill 文件与链接固定，后续只发布新的便携 Runtime。首次执行 `install`、后续显式执行 `update` 时获取对应项目、对应平台的最新已发布运行包，并验证 SHA256；日常 `start` 使用本地已安装版本。更新前先停止服务，无需重新导入 Skill。
