#!/usr/bin/env python3
"""Strict scanner for EC-AI native Core ZIP: no private source or C intermediates.

Input/output ZIP has core/, frontend|web/, core-build.json at the ZIP root.
No source text, module names or raw build errors are printed into public logs.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.machinery
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

FORMATS = {"kol-selection":"nuitka-package-v1", "e2e":"nuitka-modules-v1"}
STEMS = {"kol-selection":"backend"}
UI_EXT = {".html",".css",".js",".svg",".png",".ico",".woff2"}
PLAT_SUFFIX = {"windows-x64":".pyd","macos-arm64":".so"}
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
VER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def core_metadata(path, project, platform, version):
    if project not in FORMATS or platform not in PLAT_SUFFIX or not VER_RE.fullmatch(version):
        raise ValueError("INVALID_CORE_REQUEST")
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        if len(items) > 4096 or sum(i.file_size for i in items) > 1024*1024*1024:
            raise ValueError("CORE_ZIP_LIMIT")
        names = {}
        for item in items:
            name = item.filename.rstrip("/") if item.is_dir() else item.filename
            pp = PurePosixPath(name)
            if (not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name
                    or any(x in {"",".",".."} or x.startswith(".") for x in name.split("/"))
                    or len(pp.parts)>12 or (item.flag_bits&1)):
                raise ValueError("UNSAFE_CORE_ZIP_PATH")
            folded=name.casefold()
            if folded in names or stat.S_IFMT(item.external_attr>>16)==stat.S_IFLNK:
                raise ValueError("DUPLICATE_OR_LINK_IN_CORE")
            names[folded]=item
            if item.is_dir(): continue
            if name == "core-build.json":
                if item.file_size > 512_000: raise ValueError("CORE_METADATA_TOO_LARGE")
                continue
            if len(pp.parts)<2:
                raise ValueError("UNAPPROVED_TOP_LEVEL")
            if pp.parts[0] == "core":
                if len(pp.parts)!=2 or pp.suffix.lower()!=PLAT_SUFFIX[platform]:
                    raise ValueError("SOURCE_OR_WRONG_NATIVE_EXTENSION")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_-]+)*\.(?:so|pyd)",pp.name):
                    raise ValueError("UNSAFE_NATIVE_MODULE_NAME")
            elif pp.parts[0] == ("frontend" if project=="kol-selection" else "web"):
                if pp.suffix.lower() not in UI_EXT: raise ValueError("NONPUBLIC_UI_FILE")
            else:
                raise ValueError("UNAPPROVED_CORE_ARCHIVE_FILE")
        if "core-build.json" not in names: raise ValueError("CORE_METADATA_MISSING")
        meta=json.loads(archive.read("core-build.json"))
        if (not isinstance(meta,dict) or meta.get("schema_version")!=2
                or meta.get("project")!=project or meta.get("core_format")!=FORMATS[project]
                or meta.get("platform")!=platform or meta.get("python_abi")!="cp312"
                or meta.get("bundle_version")!=version
                or not isinstance(meta.get("core_version"),str)
                or not VER_RE.fullmatch(meta["core_version"])
                or not SHA_RE.fullmatch(str(meta.get("lock_sha256")))):
            raise ValueError("CORE_METADATA_CONTRACT_MISMATCH")
        listed=meta.get("artifacts")
        if not isinstance(listed,list) or len(listed)>4095:
            raise ValueError("CORE_ARTIFACTS_INVALID")
        included=set()
        for artifact in listed:
            if not isinstance(artifact,dict): raise ValueError("CORE_ARTIFACT_INVALID")
            file=artifact.get("path")
            if not isinstance(file,str) or file.casefold() not in names or file == "core-build.json" or file in included:
                raise ValueError("UNLISTED_OR_DUPLICATE_CORE_ARTIFACT")
            included.add(file)
            blob=archive.read(file)
            if artifact.get("size")!=len(blob) or not SHA_RE.fullmatch(str(artifact.get("sha256"))) or sha(blob)!=artifact["sha256"]:
                raise ValueError("CORE_ARTIFACT_HASH_MISMATCH")
        payload={i.filename for i in items if not i.is_dir() and i.filename!="core-build.json"}
        if included!=payload: raise ValueError("CORE_ARTIFACT_INVENTORY_MISMATCH")
        modules=[p for p in included if p.startswith("core/")]
        if project=="kol-selection" and (len(modules)!=1 or not Path(modules[0]).name.startswith("backend.")):
            raise ValueError("KOL_NATIVE_PACKAGE_MISSING")
        if project=="e2e" and (len(modules)<35 or not any(Path(n).name.startswith("packaged_entry.") for n in modules)):
            raise ValueError("E2E_NATIVE_MODULE_SET_MISSING")
        if not any(p.startswith(("frontend/" if project=="kol-selection" else "web/")) for p in included):
            raise ValueError("CORE_UI_MISSING")
        return meta

def build_archive(directory, destination, project, platform, version):
    root=Path(directory)
    if not root.is_dir(): raise ValueError("CORE_OUTPUT_DIR_MISSING")
    with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(root.rglob("*")):
            if f.is_symlink(): raise ValueError("CORE_SYMLINK")
            if f.is_file():
                z.write(f,arcname=f.relative_to(root).as_posix())
    return core_metadata(destination,project,platform,version)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--project",choices=tuple(FORMATS),required=True)
    p.add_argument("--platform",choices=tuple(PLAT_SUFFIX),required=True)
    p.add_argument("--version",required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--zip",type=Path)
    group.add_argument("--directory",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        if a.directory:
            if not a.output: raise ValueError("OUTPUT_REQUIRED")
            core=build_archive(a.directory,a.output,a.project,a.platform,a.version)
        else:
            core=core_metadata(a.zip,a.project,a.platform,a.version)
    except (ValueError,OSError,zipfile.BadZipFile,json.JSONDecodeError) as error:
        reason=str(error) if type(error) is ValueError and re.fullmatch(r"[A-Z_]+",str(error)) else "CORE_VALIDATION_FAILED"
        raise SystemExit("Public artifact rejected: "+reason)
    print("Native Core passed strict private-source and artifact-hash validation")
    print("CORE_VERSION="+core["core_version"])
if __name__=="__main__":
    main()
