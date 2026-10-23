#!/usr/bin/env python3
"""Hash *only* the tracked inputs capable of changing a published project.

This runs in the public builder but reads Git tree metadata, not private file
contents; it does not write or upload any source or intermediate compiler data.
Use the digest as resolve_version.py --source-tree for incremental releases.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

INCLUDE = {
    "e2e": (
        "e2e/.python-version",
        "e2e/Crawler/src/",
        "e2e/Crawler/web/",
        "e2e/config/",
        "e2e/scripts/",
        "e2e/packaging/",
        "e2e/skills/e2e/",
    ),
    "kol-selection": (
        "kol-selection/.python-version",
        "kol-selection/backend/",
        "kol-selection/frontend/",
        "kol-selection/config/",
        "kol-selection/templates/",
        "kol-selection/prompts/",
        "kol-selection/scripts/",
        "kol-selection/packaging/",
        "kol-selection/skills/kol-selection/",
    ),
}

def fingerprint(entries: bytes, project: str) -> tuple[str, int]:
    allowed = INCLUDE[project]
    digest = hashlib.sha1()
    count = 0
    for entry in sorted(x for x in entries.split(b"\x00") if x):
        header, sep, raw_path = entry.partition(b"\t")
        if not sep:
            raise ValueError("invalid Git tree record")
        path = raw_path.decode("utf-8")
        if not any(path == prefix or path.startswith(prefix) for prefix in allowed):
            continue
        tokens = header.decode("ascii").split(" ")
        if len(tokens) != 3 or tokens[0] != "100644" and tokens[0] != "100755" or tokens[1] != "blob":
            raise ValueError("untrusted file mode in build input tree")
        digest.update(entry + b"\x00")
        count += 1
    if count == 0:
        raise ValueError("no release inputs were found for " + project)
    return digest.hexdigest(), count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, choices=tuple(INCLUDE))
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    raw = subprocess.run(["git", "-C", str(args.repo), "ls-tree", "-r", "-z", "HEAD"],
                         check=True, stdout=subprocess.PIPE).stdout
    result, count = fingerprint(raw, args.project)
    # Only a digest and a count: no paths or source file content in public logs.
    print(result)
    print(f"Verified {count} tracked release inputs", file=__import__("sys").stderr)

if __name__ == "__main__":
    main()
