#!/usr/bin/env python3
"""Assemble a complete, preinstalled, relocatable Python runtime with native Core.

No Nuitka compilation, no private Python source in output, no pip on user machine.
The public third-party dependencies are installed into the portable CPython's
own site-packages ON THE PLATFORM-SPECIFIC CI RUNNER.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

from core_handoff_archive import core_metadata

BASE_PROJECTS={"e2e","kol-selection"}
def hashed(file):
    h=hashlib.sha256()
    with Path(file).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def task(label,args,env=None,timeout=900):
    print("PORTABLE_STAGE:",label,flush=True)
    try:
        r=subprocess.run([str(s) for s in args],cwd=None,env=env,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=timeout,check=False)
        if r.returncode: raise RuntimeError("STAGE_"+label+"_FAILED")
        return r.stdout.decode("utf-8",errors="replace").strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("STAGE_"+label+"_TIMEOUT") from None

def find_python(root):
    choices=list(root.rglob("python.exe" if sys.platform=="win32" else "python3.12"))
    for p in choices:
        if not p.is_file(): continue
        try:
            task("VERIFY_PYTHON",[p,"-I","-c",
                 "import ssl,sqlite3,sys; assert sys.version_info[:3]==(3,12,10)"],timeout=15)
            return p
        except RuntimeError: pass
    raise RuntimeError("MANAGED_PYTHON_MISSING")

def get_site(python,root):
    raw=task("FIND_SITE",[python,"-I","-c",
         "import site,json; print(json.dumps(site.getsitepackages()))"],timeout=20)
    paths=json.loads(raw)
    for s in paths:
        p=Path(s)
        if p.resolve().is_relative_to(root.resolve()) and "site-packages" in p.parts:
            p.mkdir(parents=True,exist_ok=True)
            return p
    raise RuntimeError("PORTABLE_SITE_PACKAGES_MISSING")

def lock_path(source,project,platform_name,kind):
    base=Path(source)/project/"skills"/project/"assets"
    return base/("requirements-"+kind+"-"+platform_name+".txt")

def get_archive(path,project,platform_name,version,root):
    core_metadata(path,project,platform_name,version)
    with zipfile.ZipFile(path) as zip:
        zip.extractall(root)
    manifest=json.loads((root/"core-build.json").read_text())
    return manifest

def chrome_for_testing(root,platform_name):
    """Bundle Chrome for Testing, not user Chrome profile, via Google's release JSON."""
    print("PORTABLE_STAGE: DOWNLOAD_CHROME_FOR_TESTING",flush=True)
    url="https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
    with urlopen(url,timeout=40) as f:
        latest=json.load(f)
    plat="mac-arm64" if platform_name=="macos-arm64" else "win64"
    item=next(x for x in latest["channels"]["Stable"]["downloads"]["chrome"] if x["platform"]==plat)
    binary_url=item["url"]
    if not binary_url.startswith("https://storage.googleapis.com/chrome-for-testing-public/"):
        raise RuntimeError("CHROME_URL_UNTRUSTED")
    with urlopen(binary_url,timeout=120) as stream:
        with tempfile.SpooledTemporaryFile(max_size=100_000_000) as temp:
            total=0
            while data:=stream.read(1024*1024):
                total+=len(data)
                if total>400_000_000:raise RuntimeError("CHROME_ARCHIVE_TOO_LARGE")
                temp.write(data)
            temp.seek(0)
            with zipfile.ZipFile(temp) as zip:
                for member in zip.infolist():
                    p=Path(member.filename)
                    if (p.is_absolute() or ".." in p.parts or member.filename.startswith(("/", "\\"))):
                        raise RuntimeError("CHROME_UNSAFE_ARCHIVE")
                zip.extractall(root/"browser")
    relative=("browser/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
              if platform_name=="macos-arm64" else "browser/chrome-win64/chrome.exe")
    executable=root/relative
    if not executable.is_file():
        raise RuntimeError("CHROME_BINARY_MISSING")
    if platform_name=="macos-arm64":
        executable.chmod(executable.stat().st_mode|0o111)
    return relative

def build(project,platform_name,version,source,core,managed,output):
    if project not in BASE_PROJECTS or platform_name not in ("macos-arm64","windows-x64"):
        raise RuntimeError("INVALID_PORTABLE_TARGET")
    machine=platform.machine().lower()
    host=("macos-arm64" if sys.platform=="darwin" and machine in ("arm64","aarch64")
          else "windows-x64" if sys.platform=="win32" and machine in ("amd64","x86_64") else "")
    if host!=platform_name:raise RuntimeError("WRONG_NATIVE_PLATFORM")
    source=Path(source);core=Path(core);managed=Path(managed);output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ecai-portable-") as tmp:
        stage=Path(tmp)/"assembled"
        stage.mkdir()
        pythondir=stage/"python"
        print("PORTABLE_STAGE: COPY_MANAGED_PYTHON",flush=True)
        shutil.copytree(managed,pythondir,symlinks=True)
        exe=find_python(pythondir)
        exe_rel=exe.relative_to(stage).as_posix()
        site=get_site(exe,pythondir)
        bootstrap=lock_path(source,project,platform_name,"bootstrap")
        runtime=lock_path(source,project,platform_name,"runtime")
        if hashlib.sha256(runtime.read_bytes().replace(b"\r\n",b"\n")).hexdigest() != json.loads(
                (source/project/"skills"/project/"assets"/"release.example.json").read_text())[
                "platforms"][platform_name]["lock_sha256"]:
            raise RuntimeError("DEPENDENCY_LOCK_REFERENCE_MISMATCH")
        install_base=[sys.executable,"-m","pip","install","--isolated","--disable-pip-version-check",
                      "--no-input","--no-cache-dir","--require-hashes","--no-deps","--target",site]
        task("INSTALL_PINNED_BOOTSTRAP",install_base+["--only-binary=:all:","-r",bootstrap])
        flags=["--only-binary=:all:"]
        if project=="e2e":
            # The single pinned public sdist is converted to installed files on CI,
            # never on the user's machine. All other dependencies use binary wheels.
            flags += ["--no-build-isolation","--no-binary=undetected-chromedriver"]
        task("INSTALL_PINNED_RUNTIME",install_base+flags+["-r",runtime],timeout=1200)
        smoke=("import requests,uvicorn,fastapi,playwright,openpyxl,pydantic,PIL"
               if project=="kol-selection" else
               "import requests,uvicorn,fastapi,selenium,numpy,pandas,undetected_chromedriver,openpyxl")
        task("VERIFY_RELOCATABLE_IMPORTS",[exe,"-I","-c",smoke],timeout=45)
        release=stage/"release"
        release.mkdir()
        meta=get_archive(core,project,platform_name,version,release)
        lock_digest=hashlib.sha256(runtime.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
        if meta["lock_sha256"]!=lock_digest:
            raise RuntimeError("CORE_DEPENDENCY_LOCK_MISMATCH")
        shutil.copy2(source/project/"skills"/project/"scripts"/"ecai_launcher.py",stage/"ecai_launcher.py")
        browser_path=""
        if project=="kol-selection":
            env=os.environ.copy()
            env["PLAYWRIGHT_BROWSERS_PATH"]=str(stage/"browsers")
            task("BUNDLE_PLAYWRIGHT_CHROMIUM",[exe,"-I","-m","playwright","install","chromium"],
                 env=env,timeout=600)
            if not any((stage/"browsers").glob("chromium-*")):
                raise RuntimeError("PLAYWRIGHT_BROWSER_NOT_FOUND")
            browser_path="browsers"
        else:
            browser_path=chrome_for_testing(stage,platform_name)
        manifest={"schema":1,"project":project,"platform":platform_name,"version":version,
                  "python":"3.12.10","python_executable":exe_rel,"core_sha256":hashed(core),
                  "core_lock_sha256":lock_digest,"browser_path":browser_path,
                  "packages_preinstalled":True,"dependency_install_on_user_machine":False}
        (stage/"portable.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        # Verify actual CLI with the preinstalled portable interpreter, not a host venv.
        env=os.environ.copy()
        env["ECAI_PORTABLE_ROOT"]=str(stage)
        if project=="kol-selection":
            env["PLAYWRIGHT_BROWSERS_PATH"]=str(stage/"browsers")
        else:
            env["E2E_CHROME_PATH"]=str(stage/browser_path)
        task("NATIVE_CORE_VERSION",[exe,"-I",stage/"ecai_launcher.py",
                                   "--release",release,"version"],env=env,timeout=45)
        task("NATIVE_CORE_DOCTOR",[exe,"-I",stage/"ecai_launcher.py",
                                  "--release",release,"doctor"],env=env,timeout=60)
        print("PORTABLE_STAGE: ARCHIVE_PREINSTALLED_RUNTIME",flush=True)
        with tarfile.open(output,"w:gz",compresslevel=3) as tar:
            tar.add(stage,arcname=".",recursive=True)
    print(json.dumps({"ok":True,"project":project,"platform":platform_name,
                      "version":version,"bytes":output.stat().st_size,
                      "python":exe_rel,"native_core_compilation":"reused"}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for arg in ("project","platform","version","source","core","managed-python","output"):
        p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    try:
        build(a.project,a.platform,a.version,a.source,a.core,
              getattr(a,"managed_python"),a.output)
    except (OSError,RuntimeError,ValueError,KeyError,zipfile.BadZipFile,tarfile.TarError):
        raise SystemExit("PORTABLE_BUILD_FAILED: see last PORTABLE_STAGE label")
