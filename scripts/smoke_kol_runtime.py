#!/usr/bin/env python3
"""Black-box test a compiled KOL Selection runtime. No private source required."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", required=True)
    p.add_argument("--version", required=True)
    a = p.parse_args()
    binary = Path(a.binary).resolve()
    if not binary.is_file():
        raise RuntimeError("Missing compiled executable")
    with tempfile.TemporaryDirectory(prefix="kol-smoke-") as root:
        environment = os.environ.copy()
        environment["KOL_DATA_DIR"] = str(Path(root) / "data")
        environment["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
        port = 18788
        cmd = [str(binary)]
        version = subprocess.run(cmd + ["version"], cwd=binary.parent, env=environment,
                                 capture_output=True, text=True, timeout=25, check=True)
        if version.stdout.strip() != a.version:
            raise AssertionError("Compiled runtime version does not match release")
        proc = subprocess.Popen(cmd + ["serve", "--port", str(port)],
                                cwd=binary.parent, env=environment,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = "http://127.0.0.1:%d" % port
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 45
            health = None
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError("Compiled server exited unexpectedly")
                try:
                    with opener.open(url + "/api/health", timeout=2) as res:
                        health = json.load(res)
                    break
                except (OSError, ValueError, urllib.error.URLError):
                    time.sleep(0.5)
            if not isinstance(health, dict) or health.get("status") != "ok":
                raise AssertionError("Compiled API health check failed")
            with opener.open(url + "/", timeout=5) as res:
                html = res.read(16384).lower()
            if b"<html" not in html:
                raise AssertionError("Compiled UI missing HTML")
            status = subprocess.run(cmd + ["status", "--port", str(port)],
                                    cwd=binary.parent, env=environment,
                                    capture_output=True, text=True, timeout=15)
            if status.returncode != 0 or not json.loads(status.stdout).get("running"):
                raise AssertionError("Runtime status command failed")
            stopped = subprocess.run(cmd + ["stop", "--port", str(port)],
                                     cwd=binary.parent, env=environment,
                                     capture_output=True, text=True, timeout=35)
            if stopped.returncode != 0:
                raise AssertionError("Runtime stop command failed")
            proc.wait(timeout=15)
            print("KOL compiled runtime smoke passed", a.version)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

if __name__ == "__main__":
    main()
