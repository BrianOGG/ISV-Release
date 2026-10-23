#!/usr/bin/env python3
"""Publish Codex v2 native Core and source-independent Skill assets.

The public install/launch/bootstrap code comes verbatim from EC-AI's audited
skills folder. Private source and compiler intermediates are never packaged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from core_handoff_archive import core_metadata

BASE="https://github.com/BrianOGG/ISV-Release/releases/download"
PROJECT_SKILL={"e2e":"e2e/skills/e2e","kol-selection":"kol-selection/skills/kol-selection"}
ALLOWED=[
    "SKILL.md",
    "scripts/ecai_launcher.py","scripts/ecai_install.py","scripts/setup.sh","scripts/setup.ps1",
    "assets/requirements-bootstrap-macos-arm64.txt",
    "assets/requirements-bootstrap-windows-x64.txt",
    "assets/requirements-runtime-macos-arm64.txt",
    "assets/requirements-runtime-windows-x64.txt",
]
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def assemble(project,version,tag,source,mac,win,out):
    if project not in PROJECT_SKILL or tag != project+"-v"+version:
        raise ValueError("INVALID_RELEASE_IDENTIFIERS")
    skill=Path(source)/PROJECT_SKILL[project]
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    attrs={}
    for platform,core in (("macos-arm64",Path(mac)),("windows-x64",Path(win))):
        meta=core_metadata(core,project,platform,version)
        locked=skill/"assets"/("requirements-runtime-"+platform+".txt")
        bootstrap=skill/"assets"/("requirements-bootstrap-"+platform+".txt")
        if (sha(locked)!=meta["lock_sha256"]):
            raise ValueError("CORE_RUNTIME_LOCK_MISMATCH")
        name=project+"-core-"+platform+"-"+version+".zip"
        shutil.copyfile(core,out/name)
        attrs[platform]={
            "url":BASE+"/"+tag+"/"+name,
            "sha256":sha(out/name),
            "core_version":meta["core_version"],
            "lock_sha256":sha(locked),
            "bootstrap_sha256":sha(bootstrap)
        }
    example=json.loads((skill/"assets/release.example.json").read_text(encoding="utf-8"))
    if example.get("schema_version")!=2 or example.get("project")!=project:
        raise ValueError("SKILL_DESCRIPTOR_UNEXPECTED")
    example["skill_version"]=version
    example["platforms"]=attrs
    entries={}
    for rel in ALLOWED:
        path=skill/rel
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(skill.resolve()):
            raise ValueError("SKILL_PUBLIC_FILE_MISSING")
        if rel.endswith(".ps1") and not path.read_bytes().startswith(b"\xef\xbb\xbf"):
            raise ValueError("POWERSHELL_51_BOM_MISSING")
        entries[rel]=path.read_bytes()
    entries["assets/release.json"]=(json.dumps(example,ensure_ascii=False,indent=2)+"\n").encode()
    zipname=project+"-skill-"+version+".zip"
    with zipfile.ZipFile(out/zipname,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for rel,raw in sorted(entries.items()):
            z.writestr(rel,raw)
    if (out/zipname).stat().st_size>=20_000_000: raise ValueError("SKILL_OVER_20MB")
    with zipfile.ZipFile(out/zipname) as z:
        if set(z.namelist())!=set(entries): raise ValueError("SKILL_FILE_WHITELIST_FAILURE")
        if b"REPLACE_WITH_CORE_ZIP_SHA256" in z.read("assets/release.json"):
            raise ValueError("RELEASE_DESCRIPTOR_NOT_FILLED")
    (out/"SHA256SUMS.txt").write_text("".join(
        sha(p)+"  "+p.name+"\n" for p in sorted(out.glob("*.zip"))),encoding="ascii")
    print("Validated v2 native Core and public-only Skill assembled")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for item in ("project","version","tag","source","mac","win","output"):
        p.add_argument("--"+item,required=True)
    args=p.parse_args()
    try:
        assemble(args.project,args.version,args.tag,args.source,args.mac,args.win,args.output)
    except (OSError,ValueError,json.JSONDecodeError,zipfile.BadZipFile) as error:
        # Error codes from this public assembler are fixed uppercase tokens.
        # Do not expose arbitrary exception text (paths, URLs, private data).
        code = str(error) if type(error) is ValueError and re.fullmatch(
            r"[A-Z_]{1,80}", str(error)) else "CORE_OR_SKILL_CONTRACT_FAILURE"
        raise SystemExit("Release assemble blocked: " + code)
