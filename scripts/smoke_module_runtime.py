#!/usr/bin/env python3
"""Black-box smoke against compiled native-module runtime and fresh locked wheels."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from module_archive import validate_zip
from module_installer import ensure_environment, staging_payload

def launch(python, root, args, env, timeout=75):
    return subprocess.run([str(python), str(root / "module_launcher.py"), *args],
                          cwd=str(root), env=env, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=timeout)

def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=("kol-selection", "e2e"), required=True)
    parser.add_argument("--platform", choices=("macos-arm64", "windows-x64"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    validate_zip(args.archive, args.project, args.platform, args.version)
    with tempfile.TemporaryDirectory(prefix="native-module-smoke-") as temporary:
        base = Path(temporary)
        installed = base / "app"
        staging_payload(args.archive, installed, args.project, args.platform, args.version)
        shutil.copy2(Path(__file__).resolve().with_name("module_launcher.py"), installed / "module_launcher.py")
        python, _ = ensure_environment(args.project, installed / "requirements-runtime.txt")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
        key = "KOL_DATA_DIR" if args.project == "kol-selection" else "E2E_DATA_DIR"
        env[key] = str(base / "data")
        fake_browser = base / ("synthetic-chrome.exe" if os.name == "nt" else "synthetic-chrome")
        fake_browser.write_text("offline fixture", encoding="utf-8")
        if args.project == "kol-selection":
            env["KOL_BROWSER_EXECUTABLE"] = str(fake_browser)
        else:
            env["E2E_CHROME_PATH"] = str(fake_browser)
        check = launch(python, installed, ["version"], env, timeout=25)
        if check.returncode or check.stdout.strip() != args.version:
            raise AssertionError("COMPILED_VERSION_ENTRY_FAILED")
        if args.project == "e2e":
            worker = launch(python, installed, ["worker", "run-batch", "--help"], env, timeout=25)
            if worker.returncode or "--auth-stdin" not in worker.stdout:
                raise AssertionError("COMPILED_E2E_WORKER_FAILED")
        selected_port = port()
        port_args = ["--port", str(selected_port)]
        running = False
        try:
            start = launch(python, installed, ["start", *port_args], env, timeout=90)
            if start.returncode:
                raise AssertionError("COMPILED_SERVICE_START_FAILED")
            running = True
            status = launch(python, installed, ["status", *port_args], env, timeout=25)
            if status.returncode or not json.loads(status.stdout).get("running"):
                raise AssertionError("COMPILED_SERVICE_STATUS_FAILED")
            base_url = "http://127.0.0.1:" + str(selected_port)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for suffix in ("/", "/api/health" if args.project == "kol-selection" else "/api/brands"):
                with opener.open(base_url + suffix, timeout=20) as reply:
                    data = reply.read(2_000_000)
                    if reply.status != 200:
                        raise AssertionError("COMPILED_WORKBENCH_BAD_STATUS")
                    if suffix == "/" and b"<html" not in data.lower():
                        raise AssertionError("COMPILED_WORKBENCH_HTML_MISSING")
                    if suffix != "/":
                        json.loads(data)
            if args.project == "kol-selection":
                # Preserve the existing offline 23-KOL demo/report quality gate.
                from smoke_kol_runtime import verify_app
                verify_app(opener, base_url)
            print("Compiled module smoke passed: entry, worker, service, API, HTML and KOL demo")
        finally:
            if running:
                stop = launch(python, installed, ["stop", *port_args], env, timeout=60)
                if stop.returncode:
                    raise AssertionError("COMPILED_SERVICE_STOP_FAILED")
                status = launch(python, installed, ["status", *port_args], env, timeout=25)
                if status.returncode == 0:
                    raise AssertionError("COMPILED_SERVICE_STILL_RUNNING")

if __name__ == "__main__":
    main()
