#!/usr/bin/env python3
"""Public KOL/E2E Skill installer for native extensions and third-party Python wheels.

No private project source is delivered. Requires host CPython 3.12. Reuses the
same isolated dependency environment across versions with identical lock files.
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
import tempfile
from urllib.request import Request, urlopen
import uuid
import zipfile

from module_archive import check_lock, file_sha256, validate_zip, ROOT

INSTALL_NAMES = {"kol-selection": "KOLSelection", "e2e": "E2E"}
PORTS = {"kol-selection": 8788, "e2e": 8787}

def platform_id():
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    if sys.platform == "win32" and machine in {"amd64", "x86_64"}:
        return "windows-x64"
    raise ValueError("UNSUPPORTED_PLATFORM")

def cache_root(project):
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ISV-Release" / project / "modules"
    return Path.home() / "Library/Caches/ISV-Release" / project / "modules"

def app_root(project, override):
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Programs" / INSTALL_NAMES[project]
    return Path.home() / "Applications" / INSTALL_NAMES[project]

def python_in(venv):
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"

def configuration(skill_root):
    manifest = json.loads((skill_root / "assets/download.json").read_text(encoding="utf-8"))
    project = manifest.get("project")
    version = manifest.get("version")
    if project not in ROOT or not isinstance(version, str) or not version:
        raise ValueError("INVALID_SKILL_MANIFEST")
    target = platform_id()
    spec = manifest.get("platforms", {}).get(target, {})
    sha = spec.get("sha256")
    url = spec.get("url")
    if (not isinstance(sha, str) or len(sha) != 64
            or not all(ch in "0123456789abcdef" for ch in sha)
            or not isinstance(url, str)
            or not url.startswith("https://github.com/BrianOGG/ISV-Release/releases/download/")):
        raise ValueError("INVALID_RUNTIME_DOWNLOAD")
    return project, version, target, url, sha

def download_verified(url, target, expected_sha):
    if target.is_file() and file_sha256(target) == expected_sha:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        request = Request(url, headers={"User-Agent": "ISV-Release-module-installer/1"})
        with urlopen(request, timeout=90) as response, open(temporary, "wb") as out:
            if not response.geturl().startswith("https://"):
                raise ValueError("RUNTIME_DOWNLOAD_NOT_HTTPS")
            copied = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                copied += len(block)
                if copied > 750_000_000:
                    raise ValueError("RUNTIME_ARCHIVE_TOO_LARGE")
                out.write(block)
        if file_sha256(temporary) != expected_sha:
            raise ValueError("RUNTIME_CHECKSUM_MISMATCH")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)

def staging_payload(archive_path, target, project, platform_name, version):
    validate_zip(archive_path, project, platform_name, version)
    prefix = ROOT[project] + "-" + platform_name + "/"
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            relative = member.filename[len(prefix):]
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as reader, open(destination, "wb") as writer:
                shutil.copyfileobj(reader, writer)
    return target

def ensure_environment(project, lock_path):
    raw = lock_path.read_bytes()
    check_lock(raw)
    lock_sha = hashlib.sha256(raw).hexdigest()
    base = cache_root(project) / "envs"
    target = base / lock_sha
    python = python_in(target)
    if python.is_file() and (target / ".ready-lock-sha256").is_file():
        if (target / ".ready-lock-sha256").read_text(encoding="ascii").strip() == lock_sha:
            return python, lock_sha
    base.mkdir(parents=True, exist_ok=True)
    staging = base / (".new-" + uuid.uuid4().hex)
    try:
        subprocess.run([sys.executable, "-m", "venv", str(staging)], check=True)
        stage_python = python_in(staging)
        subprocess.run([str(stage_python), "-m", "pip", "install", "--no-input",
                        "--disable-pip-version-check", "--require-hashes", "-r",
                        str(lock_path)], check=True)
        (staging / ".ready-lock-sha256").write_text(lock_sha + "\n", encoding="ascii")
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return python_in(target), lock_sha

def installation_metadata(root):
    file = root / "module-release.json"
    if not file.is_file():
        raise ValueError("MODULE_NOT_INSTALLED")
    return json.loads(file.read_text(encoding="utf-8"))

def installed_python(project, root):
    manifest = installation_metadata(root)
    if manifest.get("project") != project:
        raise ValueError("INSTALLED_PROJECT_MISMATCH")
    req = root / "requirements-runtime.txt"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    venv = cache_root(project) / "envs" / digest
    python = python_in(venv)
    if (not python.is_file()
            or not (venv / ".ready-lock-sha256").is_file()
            or (venv / ".ready-lock-sha256").read_text(encoding="ascii").strip() != digest):
        raise ValueError("PYTHON_ENVIRONMENT_MISSING_RUN_INSTALL")
    return python

def invoke(root, executable, action, port):
    command = [str(executable), str(root / "module_launcher.py"), action]
    if action in {"start", "status", "stop", "serve"}:
        command += ["--port", str(port)]
    result = subprocess.run(command, cwd=str(root), check=False)
    return result.returncode

def install(skill_root, root, project, version, target_platform, url, sha, archive_override):
    cache = cache_root(project)
    cache.mkdir(parents=True, exist_ok=True)
    archive = Path(archive_override).resolve() if archive_override else cache / "archives" / (sha + ".zip")
    if archive_override:
        if file_sha256(archive) != sha:
            raise ValueError("LOCAL_ARCHIVE_CHECKSUM_MISMATCH")
    else:
        download_verified(url, archive, sha)
    # Validate before staging, and again while extracting.
    validate_zip(archive, project, target_platform, version)
    root.parent.mkdir(parents=True, exist_ok=True)
    staged = root.parent / (root.name + ".new-" + uuid.uuid4().hex)
    backup = root.parent / (root.name + ".previous-" + uuid.uuid4().hex)
    had_previous = root.exists()
    try:
        staging_payload(archive, staged, project, target_platform, version)
        shutil.copy2(skill_root / "scripts/module_launcher.py", staged / "module_launcher.py")
        executable, _ = ensure_environment(project, staged / "requirements-runtime.txt")
        # A running old process must not be replaced under its own feet.
        if had_previous:
            try:
                old_python = installed_python(project, root)
                if invoke(root, old_python, "idle", PORTS[project]) != 0:
                    raise ValueError("RUNNING_SERVICE_STOP_BEFORE_UPDATE")
            except ValueError as error:
                if str(error) == "RUNNING_SERVICE_STOP_BEFORE_UPDATE":
                    raise
                # The previous standalone layout has no module launcher; it is
                # not silently replaced while running. Operator must stop it.
                if (root / ("kol-selection.exe" if os.name == "nt" else "kol-selection")).is_file() or (
                    root / ("e2e-dmp.exe" if os.name == "nt" else "e2e-dmp")).is_file():
                    raise ValueError("LEGACY_INSTALL_STOP_AND_MIGRATE_FIRST") from None
        if had_previous:
            root.rename(backup)
        try:
            staged.rename(root)
        except BaseException:
            if had_previous and backup.exists() and not root.exists():
                backup.rename(root)
            raise
        print("Module install complete:", project, version)
        return 0
    finally:
        if staged.exists():
            shutil.rmtree(staged)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "install", "start", "status", "stop", "setup", "doctor", "version", "idle"))
    parser.add_argument("--install-dir", default="")
    parser.add_argument("--port", type=int)
    parser.add_argument("--archive", default="", help="Offline verified archive for CI or operator-managed installations")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Requires CPython 3.12; ask the Agent to install Python 3.12 first.")
    skill_root = Path(__file__).resolve().parents[1]
    try:
        project, version, target, url, sha = configuration(skill_root)
        root = app_root(project, args.install_dir)
        port = args.port or PORTS[project]
        if not 1 <= port <= 65535:
            raise ValueError("INVALID_PORT")
        if args.action == "prepare":
            print(json.dumps({"ok": True, "project": project, "version": version,
                              "python": "3.12", "platform": target}))
            return 0
        if args.action == "install":
            return install(skill_root, root, project, version, target, url, sha, args.archive)
        return invoke(root, installed_python(project, root), args.action, port)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        # Do not echo raw exceptions with filesystem paths, network URLs or sensitive
        # user information into public support logs.
        if isinstance(exc, ValueError) and str(exc).isupper():
            code = str(exc)
        elif isinstance(exc, subprocess.CalledProcessError):
            code = "DEPENDENCY_INSTALL_FAILED"
        else:
            code = "MODULE_INSTALL_OR_RUNTIME_FAILED"
        print(json.dumps({"ok": False, "code": code}), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
