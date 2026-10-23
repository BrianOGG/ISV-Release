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
import socket
import subprocess
import urllib.request
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
        if r.returncode:
            if label=="NATIVE_CORE_VERSION":
                stdout=r.stdout.decode("utf-8",errors="replace")
                stderr=r.stderr.decode("utf-8",errors="replace")
                cls=("PUBLIC_LAUNCHER_CATCH" if "启动检查未通过" in stderr
                     else "PRIVATE_MAIN_CATCH" if "操作未完成" in stderr
                     else "OTHER")
                print("PORTABLE_CLI_FAIL_CLASS="+cls,flush=True)
                import re
                match=re.search(r"PORTABLE_LAUNCHER_EXCEPTION_CLASS=([A-Za-z]{3,60})",stderr)
                if match: print("PORTABLE_CLI_EXCEPTION_TYPE="+match.group(1),flush=True)
                print("PORTABLE_CLI_EXIT_NONZERO",flush=True)
                print("PORTABLE_CLI_PRINTED_VERSION="+str("1.0.0" in stdout).lower(),flush=True)
            raise RuntimeError("STAGE_"+label+"_FAILED")
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
                if platform_name=="macos-arm64":
                    # ditto retains signed macOS app bundle symlink layout.
                    import subprocess
                    with tempfile.NamedTemporaryFile(suffix=".zip") as z:
                        temp.seek(0)
                        shutil.copyfileobj(temp,z)
                        z.flush()
                        (root/"browser").mkdir(parents=True,exist_ok=True)
                        task("EXTRACT_SIGNED_CHROME_APP",["ditto","-xk",z.name,root/"browser"])
                else:
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
        if project == "e2e":
            # Host CI pip builds the one verified public UC sdist into portable
            # installed files; these build tools do NOT run on the user device.
            task("INSTALL_PUBLIC_BUILD_TOOLS",[
                sys.executable,"-m","pip","install","--disable-pip-version-check",
                "--no-input","setuptools==80.9.0","wheel==0.45.1","packaging==25.0"])
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
        env["ECAI_PORTABLE_CI_DIAG"]="1"
        if project=="kol-selection":
            env["PLAYWRIGHT_BROWSERS_PATH"]=str(stage/"browsers")
        else:
            env["E2E_CHROME_PATH"]=str(stage/browser_path)
        task("CREATE_NO_PIP_VENV",[exe,"-I","-m","venv","--without-pip",
                                     "--system-site-packages",stage/"venv"],env=env,timeout=60)
        venv_python=stage/"venv"/("Scripts/python.exe" if sys.platform=="win32" else "bin/python")
        try:
            task("NATIVE_CORE_VERSION",[venv_python,"-I",stage/"ecai_launcher.py",
                                       "--release",release,"version"],env=env,timeout=45)
        except RuntimeError:
            # Diagnose using only stage/error-type codes; never print private
            # import traceback, source or user-specific filesystem locations.
            print("PORTABLE_STAGE: SAFE_NATIVE_CORE_IMPORT_PROBE",flush=True)
            probe=Path(__file__).with_name("probe_portable_core.py")
            res=subprocess.run([str(venv_python),"-I",str(probe),"--launcher",
                                str(stage/"ecai_launcher.py"),"--core",str(release)],
                               stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                               env=env,timeout=60,check=False)
            for line in res.stdout.decode("utf-8",errors="replace").splitlines():
                if line.startswith("PORTABLE_DIAG="):
                    import re
                    if re.fullmatch(r"PORTABLE_DIAG=[A-Z_]+(?:[A-Za-z]+)?(?:_[A-Z_]+)*",line):
                        print(line,flush=True)
            raise
        task("NATIVE_CORE_DOCTOR",[venv_python,"-I",stage/"ecai_launcher.py",
                                  "--release",release,"doctor"],env=env,timeout=60)
        env["KOL_DATA_DIR"]=str(stage/"test-kol-data")
        env["E2E_DATA_DIR"]=str(stage/"test-e2e-data")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0))
            checked_port=probe.getsockname()[1]
        cmd=[venv_python,"-I",stage/"ecai_launcher.py","--release",release]
        started=False
        try:
            task("NATIVE_CORE_START",cmd+["start","--port",str(checked_port)],env=env,timeout=95)
            started=True
            task("NATIVE_CORE_STATUS",cmd+["status","--port",str(checked_port)],env=env,timeout=30)
            print("PORTABLE_STAGE: VERIFY_WEB_UI",flush=True)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open("http://127.0.0.1:"+str(checked_port)+"/",timeout=20) as response:
                    if response.status!=200 or b"<html" not in response.read(30000).lower():
                        raise RuntimeError("WEB_UI_UNAVAILABLE")
            except Exception:
                raise RuntimeError("WEB_UI_UNAVAILABLE") from None
        finally:
            if started:task("NATIVE_CORE_STOP",cmd+["stop","--port",str(checked_port)],env=env,timeout=60)
        # pyvenv.cfg contains absolute host paths, so do not distribute this
        # staging venv. The Skill creates it locally in milliseconds without pip.
        shutil.rmtree(stage/"venv")
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
