#!/usr/bin/env python3
"""Fail closed before public upload of compiled Nuitka runtime archives.

This validates archive shape, file names and safety only. It cannot prove a
native executable is impossible to reverse engineer; there must be no secrets
or high-value server credentials embedded in the code.
"""
import argparse
from pathlib import PurePosixPath
import stat
import zipfile

FORBIDDEN_EXTENSIONS = frozenset((
    ".py", ".pyc", ".pyo", ".pyi", ".pdb", ".c", ".h", ".obj",
    ".o", ".har", ".ipynb", ".pem", ".key", ".env", ".log",
))
FORBIDDEN_NAMES = frozenset((
    ".env", ".env.local", "config.json", "credentials.json",
    "cookies.json", "tokens.json", "nuitka-crash-report.xml",
    "compilation-report.xml", "resolved-dependencies.txt",
))
EXE = {"kol-selection": "kol-selection", "e2e": "e2e-dmp"}

def check_archive(path, project, platform):
    expected = EXE[project] + (".exe" if platform == "windows-x64" else "")
    root_name = EXE[project] + "-" + platform
    total = 0
    found = False
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            item = entry.filename.replace("\\", "/")
            bits = PurePosixPath(item)
            if (item.startswith("/") or ".." in bits.parts or
                    item.startswith("\\") or "\x00" in item):
                raise ValueError("UNSAFE_ARCHIVE_MEMBER")
            if bits.name.lower() in FORBIDDEN_NAMES or bits.suffix.lower() in FORBIDDEN_EXTENSIONS:
                raise ValueError("PRIVATE_OR_DEBUG_CONTENT_IN_ARCHIVE")
            if bits.name.lower().startswith(".env."):
                raise ValueError("PRIVATE_OR_DEBUG_CONTENT_IN_ARCHIVE")
            if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError("SYMLINK_IN_PUBLIC_ARCHIVE")
            if item.startswith("__MACOSX/"):
                # ditto may emit AppleDouble sidecars; accept only small, opaque
                # AppleDouble files, never arbitrary payloads concealed here.
                if entry.is_dir():
                    continue
                if not bits.name.startswith("._") or entry.file_size > 131072:
                    raise ValueError("UNEXPECTED_MACOS_METADATA")
                continue
            if bits.name.startswith("._"):
                if entry.file_size > 131072:
                    raise ValueError("UNEXPECTED_MACOS_METADATA")
                continue
            if not item.startswith(root_name + "/"):
                raise ValueError("UNEXPECTED_ARCHIVE_ROOT")
            if entry.is_dir():
                continue
            if ".git" in bits.parts or ".build-venv" in bits.parts:
                raise ValueError("PRIVATE_SOURCE_DIRECTORY_IN_ARCHIVE")
            total += entry.file_size
            if total > 1_500_000_000:
                raise ValueError("ARCHIVE_EXCEEDS_UNCOMPRESSED_LIMIT")
            if item == root_name + "/" + expected:
                found = True
        if not found:
            raise ValueError("COMPILED_BINARY_MISSING")
    return total

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--project", choices=tuple(EXE), required=True)
    parser.add_argument("--platform", choices=("macos-arm64", "windows-x64"), required=True)
    args = parser.parse_args()
    try:
        total = check_archive(args.zip, args.project, args.platform)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "CORRUPT_ARCHIVE"
        raise SystemExit("Public upload denied: " + reason)
    print("Compiled runtime archive passed source/privacy guard; bytes:", total)

if __name__ == "__main__":
    main()
