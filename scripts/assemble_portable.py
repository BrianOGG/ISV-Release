#!/usr/bin/env python3
"""Assemble immutable, preinstalled portable KOL/E2E release candidates."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import zipfile

ROOT="https://github.com/BrianOGG/ISV-Release/releases/download"
PORTS={"kol-selection":8788,"e2e":8787}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def manifest(path):
    with tarfile.open(path,"r:gz") as tar:
        selected=[m for m in tar.getmembers() if m.name.rstrip("/") in ("portable.json","./portable.json")]
        if len(selected)!=1:raise ValueError("PORTABLE_MANIFEST_MISSING")
        return json.load(tar.extractfile(selected[0]))

def assemble(source,project,version,tag,mac,win,out):
    if project not in PORTS or tag!=project+"-portable-"+version:
        raise ValueError("INVALID_PORTABLE_RELEASE_TAG")
    skillroot=Path(source)/project/"skills"/project
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    config={}
    for platform,archive in (("macos-arm64",Path(mac)),("windows-x64",Path(win))):
        meta=manifest(archive)
        if (meta.get("schema")!=1 or meta.get("project")!=project or meta.get("platform")!=platform
                or meta.get("version")!=version or meta.get("python")!="3.12.10"
                or meta.get("packages_preinstalled") is not True):
            raise ValueError("PORTABLE_ARCHIVE_MISMATCH")
        exe=meta.get("python_executable","")
        if not re.fullmatch(r"python/[a-zA-Z0-9_./-]+",exe) or ".." in Path(exe).parts:
            raise ValueError("PORTABLE_PYTHON_PATH_INVALID")
        filename=project+"-portable-"+platform+"-"+version+".tar.gz"
        dst=out/filename;shutil.copyfile(archive,dst)
        config[platform]="\n".join((
            "PORTABLE_URL="+ROOT+"/"+tag+"/"+filename,
            "PORTABLE_SHA256="+sha(dst),
            "PORTABLE_VERSION="+version,
            "PORTABLE_PYTHON="+exe,
            ""
        )).encode("ascii")
    skill_text=(skillroot/"SKILL.md").read_text(encoding="utf-8")
    skill_text=skill_text.replace(
        "首次安装需要 Python 3.12 和网络连接。若缺少 Python，请从 python.org 安装对应版本后重试。",
        "此便携版已附带 CPython 3.12.10、公开依赖及浏览器，不需系统 Python，也不在本机运行 pip。")
    skill_text+=("\n## 便携版本安装\n"
        "macOS ARM64: 使用 scripts/setup.sh install。"
        "Windows x64: 使用 powershell -NoProfile -File scripts/setup.ps1 -Action install。"
        "然后使用 start、status、stop、doctor。初次安装下载 Release 资产，"
        "以后复用下载缓存。报错时保留 PORTABLE_ 错误码，不要反复尝试。\n")
    entries={
      "SKILL.md":skill_text.encode("utf-8"),
      "scripts/setup.sh":(skillroot/"scripts/setup-portable.sh").read_bytes(),
      "scripts/setup.ps1":(skillroot/"scripts/setup-portable.ps1").read_bytes(),
      "scripts/ecai_launcher.py":(skillroot/"scripts/ecai_launcher.py").read_bytes(),
      "assets/portable-macos-arm64.conf":config["macos-arm64"],
      "assets/portable-windows-x64.conf":config["windows-x64"]
    }
    if not entries["scripts/setup.ps1"].startswith(b"\xef\xbb\xbf"):
        raise ValueError("PORTABLE_POWERSHELL_BOM_MISSING")
    if not skill_text.startswith("---\n"):
        raise ValueError("PORTABLE_SKILL_FRONTMATTER_MISSING")
    output=out/(project+"-portable-skill-"+version+".zip")
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for name,value in sorted(entries.items()):z.writestr(name,value)
    if output.stat().st_size>=20_000_000:
        raise ValueError("PORTABLE_SKILL_TOO_LARGE")
    (out/"SHA256SUMS.txt").write_text("".join(
        sha(file)+"  "+file.name+"\n" for file in sorted(out.iterdir()) if file.suffix in (".gz",".zip")
        ),encoding="ascii")
    print("Portable runtime assets and Skill validated:",project,version)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("source","project","version","tag","mac","win","output"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    try:
        assemble(a.source,a.project,a.version,a.tag,a.mac,a.win,a.output)
    except (OSError,ValueError,json.JSONDecodeError,tarfile.TarError):
        raise SystemExit("PORTABLE_ASSEMBLY_FAILED")
