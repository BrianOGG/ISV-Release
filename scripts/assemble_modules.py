#!/usr/bin/env python3
"""Assemble immutable native-module Runtime archives and small public Skills.

For KOL/E2E ONLY. Existing standalone tools use assemble_lite.py unchanged.
"""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from assemble_lite import BASE_URL, write_zip
from module_archive import file_sha256, validate_zip, ROOT, ENTRY

SKILL = {"kol-selection": "kol-selection/skills/kol-selection",
         "e2e": "e2e/skills/e2e"}
PORT = {"kol-selection": 8788, "e2e": 8787}

def build(project, version, tag, source, mac, win, output, templates):
    if project not in ROOT or tag != project + "-v" + version:
        raise ValueError("INVALID_MODULE_RELEASE_ID")
    output.mkdir(parents=True, exist_ok=True)
    names, sha = {}, {}
    for platform, archive in (("macos-arm64", mac), ("windows-x64", win)):
        validate_zip(archive, project, platform, version)
        filename = project + "-runtime-" + platform + "-" + version + ".zip"
        dest = output / filename
        shutil.copy2(archive, dest)
        names[platform] = filename
        sha[platform] = file_sha256(dest)
        (output / (filename + ".sha256")).write_text(sha[platform] + "  " + filename + "\n", encoding="ascii")
    with tempfile.TemporaryDirectory(prefix="public-module-skill-") as temp:
        stage = Path(temp)
        (stage / "scripts").mkdir()
        (stage / "assets").mkdir()
        source_skill = source / SKILL[project]
        if not (source_skill / "SKILL.md").is_file():
            raise ValueError("SOURCE_SKILL_MISSING")
        text = (source_skill / "SKILL.md").read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise ValueError("SKILL_FRONTMATTER_MISSING")
        text += ("\n\n## 模块版运行方式（优先）\n"
                 "仅编译私有业务模块。首次安装由本 Skill 的 scripts/setup.sh 或 "
                 "scripts/setup.ps1 检测 Python 3.12，自动创建隔离虚拟环境，"
                 "安装 SHA256 锁定的公开依赖，再下载校验并安装本平台的原生扩展。"
                 "无需安装 Nuitka，也不从源码编译。\n"
                 "支持 prepare、install、start、status、stop、setup、doctor、version。"
                 "安装前请确认本机 Python 3.12 可用；缺失时由 Agent 从官方渠道协助安装。"
                 "KOL 首次安装后请执行 scripts/setup.sh setup（Windows 使用 setup.ps1 -Action setup）"
                 "安装匹配的 Playwright Chromium；E2E 登录需要本机 Google Chrome。"
                 "报告和登录凭证保存在用户私有数据目录，更新程序不清除它们。\n")
        (stage / "SKILL.md").write_text(text, encoding="utf-8")
        if (source_skill / "README.md").is_file():
            shutil.copy2(source_skill / "README.md", stage / "README.md")
        else:
            (stage / "README.md").write_text("Compiled-module Skill: requires CPython 3.12 on the target machine.\n", encoding="utf-8")
        for name in ("module_archive.py", "module_installer.py", "module_launcher.py"):
            shutil.copy2(templates / name, stage / "scripts" / name)
        shutil.copy2(templates / "bootstrap_module.sh", stage / "scripts/setup.sh")
        ps = (templates / "bootstrap_module.ps1").read_text(encoding="utf-8-sig")
        (stage / "scripts/setup.ps1").write_bytes(b"\xef\xbb\xbf" + ps.encode("utf-8"))
        manifest = {
            "schema": 1, "project": project, "version": version, "python": "3.12",
            "entry_module": ENTRY[project],
            "platforms": {
                platform: {"url": f"{BASE_URL}/{tag}/{names[platform]}", "sha256": sha[platform]}
                for platform in ("macos-arm64", "windows-x64")
            }
        }
        (stage / "assets/download.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "assets/release.json").write_text(json.dumps({
            "name": project, "version": version, "platforms": list(manifest["platforms"]),
            "workbenchPort": PORT[project], "workbenchPath": "/",
            "runtimeEndpoint": "/api/runtime", "architecture": "nuitka-native-module"
        }, indent=2) + "\n", encoding="utf-8")
        skill_archive = output / (project + "-skill-" + version + ".zip")
        write_zip(stage, skill_archive)
        if skill_archive.stat().st_size >= 20_000_000:
            raise ValueError("SKILL_OVER_20MB")
        (output / (skill_archive.name + ".sha256")).write_text(
            file_sha256(skill_archive) + "  " + skill_archive.name + "\n", encoding="ascii")
    (output / "SHA256SUMS.txt").write_text("".join(
        file_sha256(f) + "  " + f.name + "\n"
        for f in sorted(output.glob("*.zip"))), encoding="ascii")
    print(json.dumps({"project": project, "tag": tag, "skill_size": skill_archive.stat().st_size,
                      "kind": "nuitka-native-module"}, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for arg in ("project", "version", "tag", "source", "mac", "win", "output", "templates"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    build(args.project, args.version, args.tag, Path(args.source), Path(args.mac),
          Path(args.win), Path(args.output), Path(args.templates))
