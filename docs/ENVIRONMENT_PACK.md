# EC-AI 公共环境层（独立于 KOL/E2E 核心编译）

## 目标

让 Windows x64、macOS ARM64 用户只下载一次已验证的 Python 3.12.10 和预构建公开依赖，避免每次从 PyPI 获取 30–40 个包或在用户电脑构建 C 扩展。**本环境包不包含 EC-AI 私有源码、不包含 Core，不修改 Audience Portrait 或 Product Grabber，也不覆盖旧 Release。**

* 发布标签：`environment-cp312-2026.10.23.1`
* 依据 EC-AI 源码提交：`175539044e02735b353af1b78143018507316d5a`
* 一个平台一个 `ecai-environment-cp312-<platform>-2026.10.23.1.tar.gz`
* Python：uv 下载 Astral python-build-standalone CPython 3.12.10，打包整个可移动运行树。
* 依赖：每个平台包含 KOL 和 E2E 两套彼此隔离的 wheelhouse 和 SHA256 锁定清单；不会合并两项目不同版本的包。
* E2E `undetected-chromedriver==3.5.5`：先验证官方 PyPI sdist 哈希，再在 CI 生成 Wheel，记录生成后的 Wheel 哈希；用户端不再编译该项目。
* GitHub Release 附带 `SHA256SUMS.txt`；内容有 `environment.json`，记录 Python 位置、两项目原始锁哈希、转换后离线锁哈希及 Wheel 哈希。

## 解包结构

```text
environment.json
python/                      # 平台专用 CPython 3.12.10 完整分发目录
projects/
  kol-selection/
    wheels/                  # 所有版本固定的 Wheels
    requirements-source.txt  # EC-AI 原始锁文件
    requirements-runtime.txt # 当前有效的离线 Wheel 锁
    requirements-bootstrap.txt
  e2e/
    wheels/
    requirements-source.txt
    requirements-runtime.txt
    requirements-bootstrap.txt
```

保留 Python 目录内的原始符号链接，因此打包为 TAR.GZ 而不是普通 ZIP。**解压时必须保留符号链接；Windows 10/11 可使用 tar.exe。** 不应直接复制一个在 Runner 创建的 venv：venv 包含绝对路径，且 KOL/E2E 依赖存在版本冲突。

## 发布前强制测试

1. 读取 EC-AI 锁文件并验证哈希与其 Skill 原始描述文件一致。
2. 在目标原生 Runner 使用 uv 安装**指定** 3.12.10。
3. 将 Python 完整复制到另一目录执行，确认 SSL / SQLite / zlib 正常。
4. 官方 PyPI Wheel 下载，所有原始包校验锁定哈希。
5. E2E UC 源码包验签后仅在 Runner 编译一次 Wheel；生成离线锁文件。
6. 从空 venv 和仅本地 Wheelhouse 安装 KOL 和 E2E 各自依赖，执行 `pip check`、关键库导入。
7. 解包后复验 manifest、全部 Wheel SHA256、Python 可执行性。
8. 双平台全部通过才发布独立 Environment Release；任何失败不触发业务 Nuitka 编译。

## 与现有 Skill 对接

此阶段**先把环境发布出来**。已发布的 KOL `v1.0.0-dev.2`、E2E `v1.0.0-dev.1` Skill **尚未自动使用环境包**。后续需更新两项目公共 `ecai_install.py`，使其：

1. 从环境包按目标平台下载并校验解包，优先使用随包 Python 创建项目 venv；
2. 使用各自的 `requirements-runtime.txt` 配合 `--no-index --find-links` 安装本地预编译 Wheel；
3. 核验原始 `lock_sha256` 保持 Core 对接契约（UC 生成 Wheel 的新哈希仅用于离线安装锁）；
4. 区分 ENV / CORE_IMPORT / BROWSER_SETUP / SERVICE 等独立错误码；
5. 复用相同版本环境包和依赖缓存，不修改已发布 Core、已安装业务数据或原来成功的依赖。

**提醒**：便携 Python、离线 Wheel 环境包属于额外独立的 Release，不代表安装器自动接入已经完成。真实业务登录、页面采集、账号绑定仍须由用户实机验证。
