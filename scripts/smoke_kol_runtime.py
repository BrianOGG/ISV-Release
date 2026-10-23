#!/usr/bin/env python3
"""Black-box first-run KOL smoke; only interacts with the compiled executable.

Runs with isolated synthetic data. No third-party accounts or private sources.
The startup, task list, bundled demo and report are all release blockers.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def safe_errors(data_dir):
    """Print only known-safe diagnosis metadata, never raw service stderr."""
    path = data_dir / "logs" / "diagnostics.jsonl"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
        try:
            record = json.loads(line)
            print("Safe diagnostic:", {
                "stage": record.get("stage"),
                "error_type": record.get("error_type"),
            }, file=sys.stderr)
        except (ValueError, TypeError, AttributeError):
            pass


def run_command(binary, args, env, timeout=80):
    return subprocess.run([str(binary), *args], cwd=binary.parent, env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def fetch(opener, url, *, kind="json"):
    try:
        with opener.open(url, timeout=15) as res:
            if res.status != 200:
                raise AssertionError("Packaged endpoint returned a non-200 status")
            data = res.read(2_000_000)
            content_type = res.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise AssertionError("Packaged endpoint returned HTTP " + str(exc.code) +
                             " at " + url.split("/", 3)[-1]) from None
    if kind == "html":
        if b"<html" not in data.lower():
            raise AssertionError("Packaged endpoint did not return HTML")
        return data
    if kind == "javascript":
        if "javascript" not in content_type and "text/plain" not in content_type:
            raise AssertionError("Packaged frontend JS has an unexpected media type")
        return data
    if "json" not in content_type:
        raise AssertionError("Packaged API returned non-JSON content type")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise AssertionError("Packaged API returned invalid JSON") from None


def verify_app(opener, base):
    health = fetch(opener, base + "/api/health")
    if health.get("status") != "ok":
        raise AssertionError("Packaged API health check failed")
    fetch(opener, base + "/", kind="html")
    fetch(opener, base + "/assets/app.js", kind="javascript")
    options = fetch(opener, base + "/api/workflows/industry-options")
    if not isinstance(options, dict) or not isinstance(options.get("categories"), list):
        raise AssertionError("Packaged category configuration unavailable")
    tasks = fetch(opener, base + "/api/workflows")
    if not isinstance(tasks, list):
        raise AssertionError("Packaged workbench task list is not an array")
    demo = next((t for t in tasks if isinstance(t, dict) and t.get("archived_demo")), None)
    if demo is None:
        raise AssertionError("Packaged read-only KOL demo was not initialized")
    if len(demo.get("config", {}).get("targets", [])) != 23:
        raise AssertionError("Packaged KOL demo does not have 23 candidates")
    detail = fetch(opener, base + "/api/workflows/" + demo["id"])
    if detail.get("id") != demo["id"] or not detail.get("archived_demo"):
        raise AssertionError("Packaged demo detail API failed")
    screening = detail.get("modules", {}).get("screening", {})
    if screening.get("status") != "COMPLETED" or not any(
        x.get("id") == "report.html" for x in screening.get("artifacts", [])
    ):
        raise AssertionError("Packaged demo report was not generated")
    report = fetch(opener, base + "/api/workflows/" + demo["id"] +
                   "/modules/screening/download/report.html", kind="html")
    if len(report) < 1000:
        raise AssertionError("Packaged demo report is unexpectedly empty")
    # A second GET checks that re-opening the workbench works with persisted demo.
    again = fetch(opener, base + "/api/workflows")
    if not any(t.get("id") == demo["id"] for t in again):
        raise AssertionError("Packaged demo is not stable across requests")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    binary = Path(args.binary).resolve()
    if not binary.is_file():
        raise RuntimeError("Compiled executable not found")

    with tempfile.TemporaryDirectory(prefix="kol-packaged-smoke-") as folder:
        data_dir = Path(folder) / "data"
        env = os.environ.copy()
        env["KOL_DATA_DIR"] = str(data_dir)
        env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        port = free_port()
        cmd_port = ["--port", str(port)]
        base = "http://127.0.0.1:" + str(port)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        version = run_command(binary, ["version"], env, timeout=25)
        if version.returncode or version.stdout.strip() != args.version:
            raise AssertionError("Compiled binary has an unexpected version")

        started = False
        try:
            # Test the actual user-facing lifecycle. Direct 'serve' previously
            # passed even when Windows 'start' failed with FileNotFoundError.
            start = run_command(binary, ["start", *cmd_port], env, timeout=85)
            if start.returncode != 0:
                safe_errors(data_dir)
                raise AssertionError("Compiled start command failed (exit " +
                                     str(start.returncode) + ")")
            started = True

            deadline = time.monotonic() + 30
            while True:
                try:
                    verify_app(opener, base)
                    break
                except (OSError, urllib.error.URLError) as exc:
                    if time.monotonic() >= deadline:
                        raise AssertionError("Packaged service not reachable") from None
                    time.sleep(0.5)
            status = run_command(binary, ["status", *cmd_port], env, timeout=15)
            if status.returncode:
                raise AssertionError("Compiled status command failed")
            try:
                value = json.loads(status.stdout)
            except (ValueError, UnicodeError):
                raise AssertionError("Compiled status output is not JSON") from None
            if not value.get("running") or value.get("url") != base:
                raise AssertionError("Compiled status does not identify the service")
            print("KOL compiled runtime lifecycle, workbench and demo passed", args.version)
        finally:
            if started:
                stop = run_command(binary, ["stop", *cmd_port], env, timeout=45)
                if stop.returncode != 0:
                    safe_errors(data_dir)
                    raise AssertionError("Compiled stop command failed")
                status = run_command(binary, ["status", *cmd_port], env, timeout=15)
                if status.returncode == 0:
                    raise AssertionError("Compiled service still running after stop")


if __name__ == "__main__":
    main()
