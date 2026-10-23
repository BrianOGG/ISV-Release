#!/usr/bin/env python3
"""Validate the independent, public-only CPython + offline Wheelhouse Release."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

PROJECTS={"kol-selection","e2e"}
PLATFORMS={"macos-arm64","windows-x64"}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def inspect(archive, platform_name, version, execute=False):
    with tarfile.open(archive,"r:gz") as tar:
        items=tar.getmembers()
        if len(items)>25000 or sum(x.size for x in items)>1_600_000_000:
            raise ValueError("ENV_ARCHIVE_OVERSIZED")
        indexed={}
        for i in items:
            raw=i.name
            pp=PurePosixPath(raw)
            norm=str(pp)
            if raw.startswith("/") or "\\" in raw or "\x00" in raw or ".." in pp.parts:
                raise ValueError("ENV_UNSAFE_MEMBER_PATH")
            if norm in indexed:
                raise ValueError("ENV_DUPLICATE_MEMBER")
            if norm not in {".","environment.json"} and pp.parts[0] not in {"python","projects"}:
                raise ValueError("ENV_UNEXPECTED_TOP_LEVEL")
            if i.ischr() or i.isblk() or i.isfifo() or i.isdev() or i.islnk():
                raise ValueError("ENV_UNSAFE_FILE_TYPE")
            if i.issym():
                target=PurePosixPath(i.linkname)
                if target.is_absolute() or "\\" in i.linkname:
                    raise ValueError("ENV_UNSAFE_LINK")
                # Symlink must not escape portable Python tree when resolved.
                stack=list(pp.parent.parts)
                for component in target.parts:
                    if component=="..":
                        if len(stack)<=1:
                            raise ValueError("ENV_SYMLINK_ESCAPE")
                        stack.pop()
                    elif component not in {".",""}:
                        stack.append(component)
                if not stack or stack[0]!="python":
                    raise ValueError("ENV_SYMLINK_OUTSIDE_PYTHON")
            if pp.parts and pp.parts[0]=="projects":
                if len(pp.parts)<2 or pp.parts[1] not in PROJECTS:
                    raise ValueError("ENV_UNKNOWN_PROJECT_PATH")
                if i.isfile():
                    rest=pp.parts[2:]
                    if (len(rest)==1 and rest[0] in {
                          "requirements-bootstrap.txt","requirements-runtime.txt","requirements-source.txt"}):
                        pass
                    elif (len(rest)==2 and rest[0]=="wheels" and rest[1].endswith(".whl")):
                        pass
                    else:
                        raise ValueError("ENV_NON_PUBLIC_PROJECT_FILE")
                if i.issym():
                    raise ValueError("ENV_SYMLINK_IN_WHEELHOUSE")
            indexed[norm]=i
        if "environment.json" not in indexed:
            raise ValueError("ENV_MANIFEST_MISSING")
        manifest=json.load(tar.extractfile(indexed["environment.json"]))
        if (manifest.get("schema")!=1 or manifest.get("kind")!="ecai-common-environment"
                or manifest.get("version")!=version or manifest.get("platform")!=platform_name
                or manifest.get("python")!="3.12.10"
                or set(manifest.get("projects",{}))!=PROJECTS):
            raise ValueError("ENV_MANIFEST_MISMATCH")
        pyrel=manifest.get("python_executable","")
        pp=PurePosixPath(pyrel)
        if not pyrel.startswith("python/") or pp.is_absolute() or ".." in pp.parts or str(pp) not in indexed:
            raise ValueError("ENV_PYTHON_EXECUTABLE_NOT_FOUND")
        for project,meta in manifest["projects"].items():
            basename="projects/"+project+"/"
            for label,filename in (
                ("runtime_effective_lock_sha256","requirements-runtime.txt"),
                ("runtime_source_lock_sha256","requirements-source.txt"),
                ("bootstrap_lock_sha256","requirements-bootstrap.txt")
            ):
                key=basename+filename
                if key not in indexed:
                    raise ValueError("ENV_REQUIRED_LOCK_MISSING")
                if digest(tar.extractfile(indexed[key]).read())!=meta.get(label):
                    raise ValueError("ENV_LOCK_SHA_MISMATCH")
            if not meta.get("offline_install_verified"):
                raise ValueError("ENV_OFFLINE_TEST_MISSING")
            whls=meta.get("wheels",{})
            if not whls or len(whls)>300:
                raise ValueError("ENV_WHEELHOUSE_EMPTY")
            for filename,checksum in whls.items():
                key=basename+"wheels/"+filename
                if not filename.endswith(".whl") or not re.fullmatch(r"[0-9a-f]{64}",checksum):
                    raise ValueError("ENV_WHEEL_METADATA_INVALID")
                if key not in indexed or digest(tar.extractfile(indexed[key]).read())!=checksum:
                    raise ValueError("ENV_WHEEL_HASH_MISMATCH")
            files={p[len(basename+"wheels/"):] for p in indexed if p.startswith(basename+"wheels/") and p.endswith(".whl")}
            if files!=set(whls):
                raise ValueError("ENV_UNLISTED_WHEEL")
        if execute:
            host=(sys.platform=="darwin" and platform.machine().lower() in {"arm64","aarch64"}
                  and platform_name=="macos-arm64") or (
                  sys.platform=="win32" and platform.machine().lower() in {"amd64","x86_64"}
                  and platform_name=="windows-x64")
            if not host:
                raise ValueError("ENV_CANNOT_EXECUTE_FOREIGN_PLATFORM")
            with tempfile.TemporaryDirectory(prefix="ecai-env-relocation-") as td:
                # filter=data denies escapes/special devices at extraction time.
                tar.extractall(td,filter="data")
                exe=Path(td)/Path(*pp.parts)
                if not exe.is_file():
                    raise ValueError("ENV_RELOCATED_PYTHON_MISSING")
                proc=subprocess.run([str(exe),"-I","-c",
                          "import sys,ssl,sqlite3,zlib; assert sys.version_info[:3]==(3,12,10)"],
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                          timeout=30,check=False)
                if proc.returncode:
                    raise ValueError("ENV_RELOCATED_PYTHON_FAILED")
    print("Environment archive verified:",platform_name,
          "Python 3.12.10; both offline project dependency sets present")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--platform",choices=sorted(PLATFORMS),required=True)
    p.add_argument("--version",required=True)
    p.add_argument("--execute-python",action="store_true")
    a=p.parse_args()
    try:
        inspect(a.archive,a.platform,a.version,a.execute_python)
    except (ValueError,OSError,KeyError,tarfile.TarError,json.JSONDecodeError):
        raise SystemExit("ENV_ARCHIVE_VERIFICATION_FAILED")
