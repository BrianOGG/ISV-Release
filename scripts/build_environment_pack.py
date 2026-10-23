#!/usr/bin/env python3
"""Build a portable CPython + *public* offline dependency bundle for EC-AI.

No EC-AI business source, Nuitka output or credentials are read or distributed.
Packages come exclusively from verified PyPI artifacts. On CI the sole public
sdist (undetected-chromedriver) is converted to a wheel and re-hashed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

PYTHON_VERSION = "3.12.10"
PROJECTS = ("kol-selection", "e2e")
PLATFORMS = ("macos-arm64", "windows-x64")
NAME = "ecai-environment-cp312"
UC = re.compile(r"(?m)^undetected-chromedriver==3\.5\.5\s*\\\s*\n\s*--hash=sha256:([0-9a-f]{64})(?:\s|$)")

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def sh(*args):
    proc = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, errors="replace", check=False)
    if proc.returncode:
        # Never emit raw pip logs or private environment details in public Actions.
        raise RuntimeError("PUBLIC_DEPENDENCY_STEP_FAILED")
    return proc.stdout.strip()

def host_platform():
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in ("arm64", "aarch64"):
        return "macos-arm64"
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    raise RuntimeError("UNSUPPORTED_BUILD_HOST")

def pip_install_lock(python, lock, wheel_dir):
    sh(python, "-I", "-m", "pip", "install", "--disable-pip-version-check",
       "--no-input", "--no-index", "--find-links", wheel_dir, "--require-hashes",
       "--only-binary=:all:", "-r", lock)

def pip_download(python, lock, wheel_dir):
    sh(python, "-m", "pip", "download", "--disable-pip-version-check",
       "--no-input", "--no-deps", "--require-hashes", "--only-binary=:all:",
       "-r", lock, "-d", wheel_dir)

def portable_python(python_dir):
    root = Path(python_dir)
    if not root.is_dir():
        raise RuntimeError("MANAGED_PYTHON_MISSING")
    candidates = [p for p in root.rglob("python.exe" if os.name == "nt" else "python3.12")
                  if p.is_file() and ("install" in p.parts or "bin" in p.parts)]
    for candidate in candidates:
        result = subprocess.run(
            [str(candidate), "-I", "-c",
             "import sys, ssl, sqlite3, zlib; assert sys.version_info[:3]==(3,12,10); print(sys.version.split()[0])"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if result.returncode == 0:
            return candidate
    raise RuntimeError("MANAGED_PYTHON_EXECUTION_FAILED")

def original_lock(source, project, plat, kind):
    relative = Path(project)/"config"/("requirements-runtime-"+plat+".txt") if kind=="runtime" else (
        Path(project)/"skills"/project/"assets"/("requirements-bootstrap-"+plat+".txt"))
    file = Path(source)/relative
    raw = file.read_bytes().replace(b"\r\n", b"\n")
    paired = Path(source)/project/"skills"/project/"assets"/("requirements-runtime-"+plat+".txt") if kind=="runtime" else file
    if paired.read_bytes().replace(b"\r\n", b"\n") != raw:
        raise RuntimeError("SOURCE_SKILL_LOCK_MISMATCH")
    example = json.loads((Path(source)/project/"skills"/project/"assets"/"release.example.json").read_text())
    expected = example["platforms"][plat]["lock_sha256" if kind=="runtime" else "bootstrap_sha256"]
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise RuntimeError("LOCK_REFERENCE_SHA_MISMATCH")
    return raw

def uc_wheel(host_python, original, work, wheels):
    match = UC.search(original)
    if not match:
        raise RuntimeError("UC_SOURCE_HASH_MISSING")
    req = work/"uc-source-pin.txt"
    req.write_text("undetected-chromedriver==3.5.5 --hash=sha256:"+match.group(1)+"\n")
    incoming = work/"source-dist"
    incoming.mkdir()
    sh(host_python, "-m", "pip", "download", "--disable-pip-version-check",
       "--no-deps", "--no-input", "--require-hashes", "--no-binary=:all:",
       "-r", req, "-d", incoming)
    sdists = list(incoming.glob("undetected*"))
    if len(sdists)!=1 or sha(sdists[0])!=match.group(1):
        raise RuntimeError("UC_SDIST_HASH_VERIFICATION_FAILED")
    sh(host_python,"-m","pip","install","--disable-pip-version-check","--no-input",
       "setuptools==80.9.0","wheel==0.45.1","packaging==25.0")
    sh(host_python, "-m", "pip", "wheel", "--disable-pip-version-check",
       "--no-input", "--no-deps", "--no-build-isolation", "--wheel-dir", wheels,
       sdists[0])
    found=list(wheels.glob("undetected_chromedriver-3.5.5-*.whl"))
    if len(found)!=1:
        raise RuntimeError("UC_PREBUILT_WHEEL_MISSING")
    return found[0]

def update_uc_lock(raw, wheel_hash):
    if not UC.search(raw):
        raise RuntimeError("UC_SOURCE_HASH_MISSING")
    replaced, n = UC.subn("undetected-chromedriver==3.5.5 --hash=sha256:"+wheel_hash+"\n",raw)
    if n != 1:
        raise RuntimeError("UC_REPLACEMENT_NOT_UNIQUE")
    return replaced

def test_offline(python, project_dir, work):
    # A fresh venv per project is required; the two locks may pin different
    # versions of urllib3 and must never install into the same environment.
    venv = work/"verify-venv"
    sh(python, "-I", "-m", "venv", venv)
    exe=venv/("Scripts/python.exe" if os.name=="nt" else "bin/python")
    if not exe.is_file():
        raise RuntimeError("VENV_PYTHON_MISSING")
    wheels=project_dir/"wheels"
    pip_install_lock(exe,project_dir/"requirements-bootstrap.txt",wheels)
    pip_install_lock(exe,project_dir/"requirements-runtime.txt",wheels)
    sh(exe,"-I","-m","pip","check")
    if (project_dir.name=="kol-selection"):
        sh(exe,"-I","-c",
           "import fastapi,playwright,pydantic,openpyxl,PIL,requests,uvicorn")
    else:
        sh(exe,"-I","-c",
           "import fastapi,pandas,numpy,selenium,undetected_chromedriver,openpyxl,uvicorn")
    shutil.rmtree(venv)
    return True

def build(source, managed, target, platform_name, bundle_version):
    if host_platform()!=platform_name:
        raise RuntimeError("CROSS_PLATFORM_BUILD_FORBIDDEN")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z_.-]{0,99}",bundle_version):
        raise RuntimeError("INVALID_ENV_VERSION")
    source, managed, target = Path(source), Path(managed), Path(target)
    python = portable_python(managed)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ecai-env-pack-") as temp:
        work=Path(temp)
        stage=work/"payload"
        stage.mkdir()
        python_root=stage/"python"
        shutil.copytree(managed,python_root,symlinks=True)
        rel_python=python.relative_to(managed)
        relocated=python_root/rel_python
        sh(relocated,"-I","-c",
           "import ssl,sqlite3,sys,zlib; assert sys.version_info[:3]==(3,12,10)")
        payload={"schema":1,"kind":"ecai-common-environment","version":bundle_version,
                 "platform":platform_name,"python":"3.12.10",
                 "python_executable":(Path("python")/rel_python).as_posix(),
                 "projects":{},"build_tools":{"uc_sdist_wheel_built_in_ci":True},
                 "install_instruction":"Extract using tar preserving symlinks; create project-specific venv and install wheels offline"}
        for project in PROJECTS:
            project_root=stage/"projects"/project
            wheels=project_root/"wheels"
            wheels.mkdir(parents=True)
            bootstrap = original_lock(source,project,platform_name,"bootstrap")
            original = original_lock(source,project,platform_name,"runtime")
            effective=original
            if project=="e2e":
                # Only this public dependency has an sdist instead of wheels.
                isolated=work/"uc-build"
                isolated.mkdir()
                built=uc_wheel(sys.executable,original,isolated,wheels)
                effective=update_uc_lock(original,sha(built))
            (project_root/"requirements-bootstrap.txt").write_bytes(bootstrap)
            (project_root/"requirements-runtime.txt").write_bytes(effective)
            (project_root/"requirements-source.txt").write_bytes(original)
            pip_download(sys.executable,project_root/"requirements-bootstrap.txt",wheels)
            # E2E's original sdist is replaced by our exact verified wheel.
            remainder=work/(project+"-without-uc.txt")
            if project=="e2e":
                # The wheel is already in wheels/; avoid pip downloading UC's sdist.
                raw=effective
                without=re.sub(r"(?m)^undetected-chromedriver==3\.5\.5[^\n]*\n","",raw)
                remainder.write_bytes(without)
                pip_download(sys.executable,remainder,wheels)
            else:
                pip_download(sys.executable,project_root/"requirements-runtime.txt",wheels)
            with tempfile.TemporaryDirectory(prefix="offline-",dir=work) as vt:
                test_offline(relocated,project_root,Path(vt))
            payload["projects"][project]={
                "runtime_source_lock_sha256":hashlib.sha256(original).hexdigest(),
                "runtime_effective_lock_sha256":sha(project_root/"requirements-runtime.txt"),
                "bootstrap_lock_sha256":hashlib.sha256(bootstrap).hexdigest(),
                "wheels":{p.name:sha(p) for p in sorted(wheels.glob("*.whl"))},
                "offline_install_verified":True}
        (stage/"environment.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
        # tar, not ZIP: macOS managed CPython contains real symlinks.
        with tarfile.open(target,"w:gz",compresslevel=3) as archive:
            archive.add(stage,arcname=".",recursive=True)
    print(json.dumps({"platform":platform_name,"python":PYTHON_VERSION,
                      "projects":list(payload["projects"]),
                      "size_bytes":target.stat().st_size,
                      "source_code_included":False,"offline_env_verified":True}))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--python-dir",required=True)
    parser.add_argument("--platform",choices=PLATFORMS,required=True)
    parser.add_argument("--version",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        build(args.source,args.python_dir,args.output,args.platform,args.version)
    except (RuntimeError,OSError,ValueError,subprocess.SubprocessError):
        raise SystemExit("ENVIRONMENT_BUILD_FAILED: see isolated stage; no private source leaked")
