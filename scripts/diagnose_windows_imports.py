"""Read-only, no-Core Windows check of public portable-Python dependencies.
Never echoes pip output, tracebacks, file paths, credentials, or private modules.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from build_portable_bundle import find_python, get_site, lock_path, task

IMPORTS = {
    "kol-selection": ["requests", "uvicorn", "fastapi", "playwright", "openpyxl", "pydantic", "PIL"],
    "e2e": ["requests", "uvicorn", "fastapi", "selenium", "numpy", "pandas", "undetected_chromedriver", "openpyxl"],
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=sorted(IMPORTS), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--managed-python", required=True)
    args = parser.parse_args()
    project = args.project
    with tempfile.TemporaryDirectory(prefix="ecai-public-import-") as td:
        pythondir = Path(td) / "assembled" / "python"
        shutil.copytree(Path(args.managed_python), pythondir, symlinks=True)
        exe = find_python(pythondir)
        site = get_site(exe, pythondir)
        bootstrap = lock_path(Path(args.source), project, "windows-x64", "bootstrap")
        runtime = lock_path(Path(args.source), project, "windows-x64", "runtime")
        base = [sys.executable, "-m", "pip", "install", "--isolated",
                "--disable-pip-version-check", "--no-input", "--no-cache-dir",
                "--require-hashes", "--no-deps", "--target", str(site)]
        task("INSTALL_PINNED_BOOTSTRAP", base + ["--only-binary=:all:", "-r", bootstrap])
        flags = ["--only-binary=:all:"]
        if project == "e2e":
            task("INSTALL_PUBLIC_BUILD_TOOLS", [sys.executable, "-m", "pip",
                "install", "--disable-pip-version-check", "--no-input",
                "setuptools==80.9.0", "wheel==0.45.1", "packaging==25.0"])
            flags += ["--no-build-isolation", "--no-binary=undetected-chromedriver"]
        task("INSTALL_PINNED_RUNTIME", base + flags + ["-r", runtime], timeout=1200)
        failed = False
        for module in IMPORTS[project]:
            try:
                probe = subprocess.run([str(exe), "-I", "-c", "import " + module],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=65,
                    check=False)
                stderr = probe.stderr.decode("utf-8", errors="replace")
                types = re.findall(r"(?m)^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception)):", stderr)
                classes = {"ImportError", "ModuleNotFoundError", "OSError",
                           "RuntimeError", "AttributeError", "TypeError", "ValueError",
                           "DLLLoadError", "FileNotFoundError", "PermissionError"}
                err = next((x for x in reversed(types) if x in classes), "UNKNOWN")
                status = "PASS" if probe.returncode == 0 else "FAIL"
                print(f"PUBLIC_IMPORT project={project} module={module} status={status}"
                      f" error_type={err} return_code={probe.returncode}", flush=True)
                failed |= probe.returncode != 0
            except subprocess.TimeoutExpired:
                print(f"PUBLIC_IMPORT project={project} module={module} status=TIMEOUT",
                      flush=True)
                failed = True
        # Also test the exact aggregate import used by the production packager.
        # Per-module imports can pass even when cross-package DLL imports conflict.
        modules = IMPORTS[project]
        for count in range(2, len(modules) + 1):
            probe = subprocess.run([str(exe), "-I", "-c",
                "import " + ",".join(modules[:count])],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=65, check=False)
            stderr = probe.stderr.decode("utf-8", errors="replace")
            types = re.findall(r"(?m)^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception)):", stderr)
            classes = {"ImportError", "ModuleNotFoundError", "OSError",
                       "RuntimeError", "AttributeError", "TypeError", "ValueError",
                       "DLLLoadError", "FileNotFoundError", "PermissionError"}
            err = next((x for x in reversed(types) if x in classes), "UNKNOWN")
            status = "PASS" if probe.returncode == 0 else "FAIL"
            print(f"COMBINED_IMPORT project={project} upto={modules[count-1]}"
                  f" status={status} error_type={err} return_code={probe.returncode}", flush=True)
            failed |= probe.returncode != 0
            if probe.returncode != 0:
                break
        if failed:
            raise SystemExit("PUBLIC_IMPORT_CHECK_FAILED")
        print("ALL_PUBLIC_IMPORTS_PASSED", project, flush=True)

if __name__ == "__main__":
    main()
