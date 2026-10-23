#!/usr/bin/env python3
"""Native CI test of final ECAI Skill and the actual compiled Core.
Only stable test stage names print to public Actions logs.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

def run(argv,env,label,timeout=900, expect=0):
    try:
        result=subprocess.run(list(map(str,argv)),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              encoding="utf-8",errors="replace",timeout=timeout)
    except Exception:
        raise AssertionError("SMOKE_"+label+"_LAUNCH_FAILED") from None
    if result.returncode!=expect:
        raise AssertionError("SMOKE_"+label+"_EXIT_"+str(result.returncode))
    return result.stdout

def freeport():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--project",choices=["kol-selection","e2e"],required=True)
    parser.add_argument("--skill",type=Path,required=True)
    parser.add_argument("--core",type=Path,required=True)
    parser.add_argument("--source",type=Path,required=True)
    p=parser.parse_args()
    root_source=p.source.resolve()
    with tempfile.TemporaryDirectory(prefix="native-handoff-smoke-") as folder:
        base=Path(folder)
        skill=base/"skill"
        skill.mkdir()
        with zipfile.ZipFile(p.skill) as zip:
            for item in zip.infolist():
                name=item.filename
                if name.startswith(("/","\\")) or "\\" in name or ".." in Path(name).parts:
                    raise AssertionError("SKILL_UNSAFE_ARCHIVE")
            zip.extractall(skill)
        installed=base/"install"
        if sys.platform=="win32":
            command=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(skill/"scripts/setup.ps1")]
            def call(action,**kw):
                argv=[*command,"-Action",action,"-InstallDir",str(installed)]
                if "archive" in kw: argv.extend(["-CoreArchive",str(kw["archive"])])
                if "port" in kw: argv.extend(["-Port",str(kw["port"])])
                return argv
        else:
            def call(action,**kw):
                argv=["sh",str(skill/"scripts/setup.sh"),action,"--install-dir",str(installed)]
                if "archive" in kw: argv.extend(["--core-archive",str(kw["archive"])])
                if "port" in kw: argv.extend(["--port",str(kw["port"])])
                return argv
        env=os.environ.copy()
        env["PYTHONIOENCODING"]="utf-8"
        env["ECAI_PYTHON"]=sys.executable
        env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"]="1"
        browser=base/("synthetic-chrome.exe" if os.name=="nt" else "synthetic-chrome")
        browser.write_text("synthetic-browser",encoding="ascii")
        env["KOL_BROWSER_EXECUTABLE"]=str(browser)
        env["E2E_CHROME_PATH"]=str(browser)
        env["KOL_DATA_DIR"]=str(base/"kol-data")
        env["E2E_DATA_DIR"]=str(base/"e2e-data")
        core=p.core.resolve()
        run(call("prepare"),env,"PREPARE",40)
        run(call("install",archive=core),env,"INSTALL",1200)
        state=json.loads((installed/"current.json").read_text(encoding="utf-8"))
        release=installed/state["release"]
        venvpython=installed/state["environment"]/("Scripts/python.exe" if os.name=="nt" else "bin/python")
        if not venvpython.is_file(): raise AssertionError("SMOKE_VENV_MISSING")
        check=run([venvpython,"-I",root_source/"scripts/verify_native_core.py","--release",release],
                  env,"NATIVE_IMPORT_POC",150)
        if "Native import POC passed" not in check:
            raise AssertionError("SMOKE_NATIVE_IMPORT_POC_MISSING")
        run(call("install",archive=core),env,"REPEAT_INSTALL",70)
        selected=freeport()
        started=False
        try:
            run(call("start",port=selected),env,"START",90)
            started=True
            status=run(call("status",port=selected),env,"STATUS",30)
            if not json.loads(status).get("running"):
                raise AssertionError("SMOKE_NOT_RUNNING")
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            baseurl="http://127.0.0.1:"+str(selected)
            if p.project=="kol-selection":
                # Existing comprehensive 23-KOL fixture, UI and HTML report assertions.
                from smoke_kol_runtime import verify_app
                verify_app(opener,baseurl)
            else:
                for endpoint in ["/","/static/app.js","/api/brands"]:
                    try:
                        with opener.open(baseurl+endpoint,timeout=20) as response:
                            data=response.read(2_000_000)
                            if response.status!=200: raise AssertionError("SMOKE_HTTP_NON_200")
                        if endpoint=="/" and b"<html" not in data.lower(): raise AssertionError("SMOKE_FRONTEND_MISSING")
                        if endpoint=="/api/brands" and not isinstance(json.loads(data),dict):
                            raise AssertionError("SMOKE_API_BROKEN")
                    except Exception:
                        raise AssertionError("SMOKE_E2E_HTTP_"+endpoint.strip("/").replace("/","_")) from None
            print("Native Core POC and final Skill lifecycle passed:",p.project)
        finally:
            if started:
                run(call("stop",port=selected),env,"STOP",65)
                run(call("stop",port=selected),env,"REPEAT_STOP",50)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (AssertionError,ValueError,FileNotFoundError) as exc:
        print("Native validation blocked:",str(exc),file=sys.stderr)
        sys.exit(1)
