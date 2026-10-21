#!/usr/bin/env python3
"""Create immutable, per-platform runtimes and <20 MB Agent Skill bootstrap archives.

Only compiled runtime and browser-extension assets may enter public releases.
Never upload the checked-out private tree or its build/debug directories.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

LIMIT = 20_000_000
PLATFORMS = ("macos-arm64", "windows-x64")
BASE_URL = "https://github.com/BrianOGG/ISV-Release/releases/download"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_zip(directory, archive):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(directory.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(directory).as_posix()
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if (rel.endswith(".sh") or p.stat().st_mode & stat.S_IXUSR) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            z.writestr(info, p.read_bytes())


def extract_safe(archive, target):
    with zipfile.ZipFile(archive) as z:
        for m in z.infolist():
            parts = PurePosixPath(m.filename.replace("\\", "/")).parts
            if m.filename.startswith("/") or ".." in parts or m.filename.startswith("\\") or (m.external_attr >> 16 & 0o170000) == stat.S_IFLNK:
                raise ValueError("unsafe runtime archive entry")
        z.extractall(target)


def source_assets(project, source, mac, win, stage, platform):
    dest = stage / "runtime" / platform
    dest.mkdir(parents=True)
    if project == "product-grabber":
        p = mac if platform == "macos-arm64" else win
        name = "product-grabber" if platform == "macos-arm64" else "product-grabber.exe"
        if not (p / name).is_file():
            raise ValueError(f"missing runtime {p / name}")
        shutil.copy2(p / name, dest / name)
        # Both platform archives carry the same extension, alongside the local runtime.
        if True:
            ext = stage / "ext"
            shutil.copytree(p / "ext", ext)
            windows_ext = win / "ext"
            for entry in ext.rglob("*"):
                if entry.is_file() and (not (windows_ext / entry.relative_to(ext)).is_file() or sha(entry) != sha(windows_ext / entry.relative_to(ext))):
                    raise ValueError("cross-platform extension mismatch")
    else:
        p = mac if platform == "macos-arm64" else win
        scratch = stage / "_extract"
        scratch.mkdir()
        extract_safe(p, scratch)
        # macOS ditto --sequesterRsrc adds a sibling __MACOSX directory.
        # Exclude Finder metadata before identifying the actual payload root.
        metadata = scratch / "__MACOSX"
        if metadata.exists():
            shutil.rmtree(metadata)
        for sidecar in scratch.rglob("._*"):
            if sidecar.is_file():
                sidecar.unlink()
        children = [x for x in scratch.iterdir() if x.is_dir()]
        root = children[0] if len(children) == 1 and not any(x.is_file() for x in scratch.iterdir()) else scratch
        for item in root.iterdir():
            if item.is_dir():
                shutil.copytree(item, dest / item.name)
            else:
                shutil.copy2(item, dest / item.name)
        shutil.rmtree(scratch)
        name = "audience-portrait" if platform == "macos-arm64" else "audience-portrait.exe"
        if not (dest / name).is_file():
            raise ValueError(f"missing runtime {dest / name}")
        for file in dest.rglob("*"):
            if file.is_file() and file.suffix.lower() in (".py", ".pyc", ".pdb"):
                raise ValueError(f"uncompiled/debug source in package: {file.name}")


def build(project, version, tag, source, mac, win, output, templates):
    if not version or not all(c.isalnum() or c in "._-" for c in version):
        raise ValueError("invalid release version")
    if not tag.startswith(project + "-"):
        raise ValueError("wrong release tag namespace")
    output.mkdir(parents=True, exist_ok=True)
    hashes, names = {}, {}
    for platform in PLATFORMS:
        filename = f"{project}-runtime-{platform}-{version}.zip"
        names[platform] = filename
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            source_assets(project, source, mac, win, staging, platform)
            write_zip(staging, output / filename)
        hashes[platform] = sha(output / filename)
        (output / (filename + ".sha256")).write_text(f"{hashes[platform]}  {filename}\n")
    source_skill = (source / "product-scraping/product-grabber/skills/product-grabber"
                    if project == "product-grabber" else source / "audience-portrait/skills/audience-portrait")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        (stage / "scripts").mkdir()
        (stage / "references").mkdir()
        (stage / "assets").mkdir()
        for name in ("SKILL.md", "README.md"):
            shutil.copy2(source_skill / name, stage / name)
        for platform_script in ("setup.sh", "setup.ps1"):
            suffix = platform_script.rsplit(".", 1)[-1]
            shutil.copy2(source_skill / "scripts" / platform_script, stage / "scripts" / f"setup-bundled.{suffix}")
            template = (templates / ("bootstrap.sh" if suffix == "sh" else "bootstrap.ps1")).read_text()
            variables = {
                "@@PROJECT@@": project,
                "@@VERSION@@": version,
                "@@MAC_URL@@": f"{BASE_URL}/{tag}/{names['macos-arm64']}",
                "@@WIN_URL@@": f"{BASE_URL}/{tag}/{names['windows-x64']}",
                "@@MAC_SHA@@": hashes["macos-arm64"],
                "@@WIN_SHA@@": hashes["windows-x64"],
            }
            for key, value in variables.items():
                template = template.replace(key, value)
            (stage / "scripts" / platform_script).write_text(template)
        refs = source_skill / "references"
        if refs.exists():
            shutil.copytree(refs, stage / "references", dirs_exist_ok=True)
        skill_text = (stage / "SKILL.md").read_text()
        notice = ("## Runtime 安装说明（此节优先于旧版随包说明）\n"
                  "这是轻量引导型 Skill ZIP，不含可执行程序。首次运行 scripts/setup.sh 或 "
                  "scripts/setup.ps1 时自动下载、校验 SHA256 并缓存当前平台的已编译 Runtime；"
                  "无需 Node.js/Python 开发环境。下载失败应报告错误，禁止自行从源码编译。"
                  "离线使用需先完成安装。项目源码始终在私有仓库，编译程序仍可被逆向分析。\n\n")
        if skill_text.startswith("---"):
            pos = skill_text.find("---", 3)
            skill_text = skill_text[:pos + 3] + "\n\n" + notice + skill_text[pos + 3:]
        else:
            raise ValueError("Skill YAML frontmatter missing")
        skill_text = skill_text.replace("包内自带运行程序，无需安装 Node", "首次启动自动下载已编译运行程序，无需安装 Node")
        skill_text = skill_text.replace("运行程序随技能包分发，用户无需安装 Node、npm 或 Python，也无需自己编译。",
                                       "运行程序首次使用时通过公开 Release 自动下载，用户无需安装 Node、npm 或 Python，也无需自己编译。")
        (stage / "SKILL.md").write_text(skill_text)
        readme = (stage / "README.md").read_text()
        (stage / "README.md").write_text(
            f"# {project} 轻量 Skill\n\n首次使用需联网下载对应系统的编译版 Runtime。"
            "Skill 本身不包含任何编译程序或私有源码。"
            "运行脚本自动验证下载文件 SHA256、安装并缓存；后续启动复用缓存。"
            "完整离线首次安装需另行取得同版本运行文件。\n\n" + readme)
        if project == "product-grabber":
            release = {"name": project, "version": version, "platforms": list(PLATFORMS),
                       "extensionId": "bbnfnhfbjagbmkcfilfnnnjpmoopcgba"}
        else:
            release = {"name": project, "version": version, "platforms": list(PLATFORMS), "workbenchPort": 8766,
                       "workbenchPath": "/", "runtimeEndpoint": "/api/runtime"}
        (stage / "assets" / "release.json").write_text(json.dumps(release, indent=2) + "\n")
        (stage / "assets" / "download.json").write_text(json.dumps({
            "releaseTag": tag, "platforms": {p: {"url": f"{BASE_URL}/{tag}/{names[p]}", "sha256": hashes[p]}
                                            for p in PLATFORMS}
        }, indent=2) + "\n")
        # Full build permissions remain internal; only the Skill and bootstrap go public.
        skill_zip = output / f"{project}-skill-{version}.zip"
        write_zip(stage, skill_zip)
        if skill_zip.stat().st_size >= LIMIT:
            raise ValueError(f"Skill exceeds 20 MB: {skill_zip.stat().st_size}")
        (output / (skill_zip.name + ".sha256")).write_text(f"{sha(skill_zip)}  {skill_zip.name}\n")
    files = sorted(p for p in output.iterdir() if p.is_file() and p.suffix == ".zip")
    (output / "SHA256SUMS.txt").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files))
    print(json.dumps({"skill_size_bytes": skill_zip.stat().st_size, "runtime": names, "tag": tag}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for argument in ("project", "version", "tag", "source", "mac", "win", "output", "templates"):
        parser.add_argument("--" + argument, required=True)
    opts = parser.parse_args()
    build(opts.project, opts.version, opts.tag, Path(opts.source), Path(opts.mac),
          Path(opts.win), Path(opts.output), Path(opts.templates))
