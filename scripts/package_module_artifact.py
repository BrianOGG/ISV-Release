#!/usr/bin/env python3
"""Zip the native module-only build directory without recording private source."""
import argparse
from pathlib import Path
import stat
import zipfile

from module_archive import ROOT, validate_zip

def pack(build_output, platform, project, version, destination):
    expected = build_output / (ROOT[project] + "-" + platform)
    if not expected.is_dir():
        raise ValueError("MODULE_BUILD_OUTPUT_MISSING")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(expected.rglob("*")):
            if path.is_symlink():
                raise ValueError("SYMLINK_IN_BUILD_OUTPUT")
            if not path.is_file():
                continue
            name = path.relative_to(build_output).as_posix()
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, path.read_bytes())
    validate_zip(destination, project, platform, version)
    print("Compiled native module archive passed privacy gate")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", required=True, choices=tuple(ROOT))
    parser.add_argument("--platform", required=True, choices=("macos-arm64", "windows-x64"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pack(args.root, args.platform, args.project, args.version, args.output)
