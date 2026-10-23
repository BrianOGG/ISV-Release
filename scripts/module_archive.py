"""Public, source-independent allowlist validator for KOL/E2E module archives."""
from __future__ import annotations
import hashlib
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile

ROOT = {"kol-selection": "kol-selection", "e2e": "e2e-dmp"}
ENTRY = {"kol-selection": "backend.packaged_entry", "e2e": "packaged_entry"}
NATIVE = {"macos-arm64": ".so", "windows-x64": ".pyd"}
STATIC = {".html", ".css", ".js", ".svg", ".png", ".ico", ".woff2", ".jpg", ".jpeg", ".gif", ".webp", ".json", ".txt"}
BAD_NAMES = {".env", "config.json", "credentials.json", "cookies.json", "tokens.json",
             "nuitka-crash-report.xml", "compilation-report.xml", ".ds_store"}
HASH_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9_.!+~-]*"
                       r"(?:[ \t]+--hash=sha256:[0-9a-fA-F]{64})+[ \t]*$")

def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def check_lock(raw):
    if len(raw) > 256_000:
        raise ValueError("DEPENDENCY_LOCK_TOO_LARGE")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeError:
        raise ValueError("DEPENDENCY_LOCK_ENCODING") from None
    entries = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not HASH_LINE.fullmatch(stripped):
            raise ValueError("DEPENDENCY_LOCK_NOT_HASH_PINNED")
        entries += 1
    if not entries:
        raise ValueError("EMPTY_DEPENDENCY_LOCK")

def validate_zip(archive_path, project, platform, version):
    if project not in ROOT or platform not in NATIVE:
        raise ValueError("UNSUPPORTED_PROJECT_OR_PLATFORM")
    prefix = ROOT[project] + "-" + platform + "/"
    required = {prefix + "module-release.json", prefix + "requirements-runtime.txt"}
    seen, native = set(), False
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            path = item.filename
            parts = PurePosixPath(path).parts
            if (not path or path.startswith(("/", "\\")) or "\\" in path or "\x00" in path
                    or ".." in parts or (len(parts) > 16)):
                raise ValueError("UNSAFE_ARCHIVE_PATH")
            if item.is_dir():
                continue
            if not path.startswith(prefix) or path in seen:
                raise ValueError("UNEXPECTED_OR_DUPLICATE_ARCHIVE_FILE")
            if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError("SYMLINK_IN_RUNTIME")
            seen.add(path)
            rel = path[len(prefix):]
            rel_parts = PurePosixPath(rel).parts
            if not rel_parts:
                raise ValueError("EMPTY_RUNTIME_PATH")
            if any(x.startswith(".") and x not in {"."} for x in rel_parts):
                raise ValueError("HIDDEN_RUNTIME_FILE")
            if (any(x.lower() in BAD_NAMES for x in rel_parts)
                    or any(x.lower() in {".git", ".build-venv", "__pycache__", "data", "cookies", "profiles"} for x in rel_parts)):
                raise ValueError("PRIVATE_FILE_IN_RUNTIME")
            suffix = PurePosixPath(rel).suffix.lower()
            if rel in {"module-release.json", "requirements-runtime.txt"}:
                if item.file_size > 256_000:
                    raise ValueError("RUNTIME_MANIFEST_TOO_LARGE")
            elif rel.startswith("modules/"):
                if suffix != NATIVE[platform]:
                    raise ValueError("NON_NATIVE_FILE_IN_COMPILED_MODULES")
                native = True
            elif rel_parts[0] in (("frontend",) if project == "kol-selection" else ("web",)):
                if suffix not in STATIC:
                    raise ValueError("UNAPPROVED_STATIC_FILE")
            elif rel.startswith("licenses/"):
                if suffix not in {".txt", ".md", ""}:
                    raise ValueError("UNAPPROVED_LICENSE_FILE")
            else:
                raise ValueError("UNRECOGNIZED_RUNTIME_FILE")
            total += item.file_size
            if total > 1_000_000_000:
                raise ValueError("RUNTIME_TOO_LARGE")
        if not required.issubset(seen) or not native:
            raise ValueError("MODULE_ARCHIVE_INCOMPLETE")
        meta = json.loads(archive.read(prefix + "module-release.json"))
        if (not isinstance(meta, dict) or meta.get("schema") != 1
                or meta.get("project") != project or meta.get("platform") != platform
                or meta.get("version") != version or meta.get("python") != "3.12"
                or meta.get("entry_module") != ENTRY[project]):
            raise ValueError("MODULE_METADATA_MISMATCH")
        check_lock(archive.read(prefix + "requirements-runtime.txt"))
    return total
