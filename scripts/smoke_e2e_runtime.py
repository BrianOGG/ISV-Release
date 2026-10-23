#!/usr/bin/env python3
"""Offline E2E compiled runtime test. No real account, Cookie or platform requests."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

def run(binary, args, env, timeout=90):
    return subprocess.run([str(binary), *args], cwd=binary.parent, env=env,
                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)

def free_port():
    with socket.socket() as conn:
        conn.bind(("127.0.0.1", 0))
        return conn.getsockname()[1]

def safe_diagnostics(root):
    f = root / "logs" / "diagnostics.jsonl"
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]:
        try:
            record = json.loads(line)
            print("Safe diagnostic:", {x: record.get(x) for x in ("stage", "error_type", "error_code")})
        except (TypeError, ValueError, AttributeError):
            pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    binary = Path(args.binary).resolve()
    if not binary.is_file():
        raise AssertionError("Compiled executable is missing")
    with tempfile.TemporaryDirectory(prefix="e2e-compiled-smoke-") as tmp:
        root = Path(tmp)
        data = root / "data"
        browser = root / ("chrome.exe" if os.name == "nt" else "chrome")
        browser.write_bytes(b"offline browser sentinel")
        env = os.environ.copy()
        env["E2E_DATA_DIR"] = str(data)
        env["E2E_CHROME_PATH"] = str(browser)
        env["PYTHONIOENCODING"] = "utf-8"
        port = free_port()
        port_args = ["--port", str(port)]
        version = run(binary, ["version"], env, 25)
        if version.returncode or version.stdout.strip() != args.version:
            raise AssertionError("Compiled runtime version mismatch")
        worker = run(binary, ["worker", "run-batch", "--help"], env, 30)
        if worker.returncode or "--auth-stdin" not in worker.stdout:
            raise AssertionError("Compiled worker entrypoint is unavailable")
        started = False
        try:
            start = run(binary, ["start", *port_args], env, 85)
            if start.returncode:
                safe_diagnostics(data)
                raise AssertionError("Compiled E2E start failed (exit " + str(start.returncode) + ")")
            started = True
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = "http://127.0.0.1:" + str(port)
            deadline = time.monotonic() + 25
            while True:
                try:
                    with opener.open(url + "/", timeout=4) as res:
                        html = res.read(300_000)
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise AssertionError("Compiled E2E workbench did not start") from None
                    time.sleep(0.5)
            if b"<html" not in html.lower():
                raise AssertionError("Workbench HTML missing")
            with opener.open(url + "/static/app.js", timeout=8) as res:
                if res.status != 200 or not res.read(100):
                    raise AssertionError("E2E JS static asset missing")
            with opener.open(url + "/api/brands", timeout=8) as res:
                json.load(res)
            status = run(binary, ["status", *port_args], env, 20)
            if status.returncode or not json.loads(status.stdout).get("running"):
                raise AssertionError("Compiled status check failed")
            print("E2E compiled start, workbench, assets, API, worker and status passed")
        finally:
            if started:
                stop = run(binary, ["stop", *port_args], env, 50)
                if stop.returncode:
                    safe_diagnostics(data)
                    raise AssertionError("Compiled E2E stop command failed")
                status = run(binary, ["status", *port_args], env, 20)
                if status.returncode == 0:
                    raise AssertionError("Compiled E2E service remained running after stop")

if __name__ == "__main__":
    main()
