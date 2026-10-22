#!/usr/bin/env python3
"""Resolve independent SemVer dev or manually requested stable releases.

A successful public GitHub Release is the ONLY version counter. Failed builds
never consume an increment. The checked-out private repository is read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

MIN_VERSION = (1, 0, 0)
STABLE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-dev\.([1-9]\d*))?$")


def version_key(version: str):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError("Invalid version: " + version)
    major, minor, patch = (int(match.group(n)) for n in (1, 2, 3))
    dev = match.group(4)
    # 1.0.0-dev.2 < 1.0.0 (stable).
    return (major, minor, patch, 1 if dev is None else 0, int(dev or 0))


def releases_for_project(releases, project):
    prefix = project + "-v"
    eligible = []
    for item in releases:
        if item.get("draft") or not item.get("tag_name", "").startswith(prefix):
            continue
        version = item["tag_name"][len(prefix):]
        if VERSION.fullmatch(version) and version_key(version)[:3] >= MIN_VERSION:
            eligible.append((version_key(version), version, item))
    return sorted(eligible, key=lambda item: item[0], reverse=True)


def resolve(releases, project, source_tree, stable_version=""):
    previous = releases_for_project(releases, project)
    latest = previous[0] if previous else None
    if stable_version:
        match = STABLE.fullmatch(stable_version)
        if not match or tuple(int(x) for x in match.groups()) < MIN_VERSION:
            raise ValueError("Manual version must be stable SemVer >=1.0.0, e.g. 1.0.0, 1.1.0")
        if latest and version_key(stable_version) <= latest[0]:
            raise ValueError("Manual stable version must be greater than the latest release: " + latest[1])
        version = stable_version
    else:
        # Metadata is written into every Release by our new workflow.
        # Compare the most recent successfully published source tree.
        if latest and f"Source-Tree: {source_tree}" in (latest[2].get("body") or ""):
            return {"build": False, "reason": "latest Release already has this project source tree",
                    "version": latest[1], "tag": latest[2]["tag_name"], "prerelease": "-dev." in latest[1]}
        if latest:
            major, minor, patch, stable_rank, dev_n = latest[0]
            if stable_rank == 0:
                version = f"{major}.{minor}.{patch}-dev.{dev_n + 1}"
            else:
                version = f"{major}.{minor}.{patch + 1}-dev.1"
        else:
            version = "1.0.0-dev.1"
    tag = f"{project}-v{version}"
    if any(item.get("tag_name") == tag for item in releases):
        raise ValueError("Release tag already exists (immutable): " + tag)
    return {"build": True, "version": version, "tag": tag,
            "prerelease": "-dev." in version, "reason": "new stable version" if stable_version else "new source tree"}


def list_releases(repository):
    results = []
    for page in range(1, 101):
        endpoint = f"repos/{repository}/releases?per_page=100&page={page}"
        raw = subprocess.run(["gh", "api", endpoint], text=True, capture_output=True, check=True)
        batch = json.loads(raw.stdout)
        if not isinstance(batch, list):
            raise ValueError("GitHub releases endpoint did not return an array")
        results.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError("Release history pagination exceeded safety limit")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=("product-grabber", "audience-portrait", "kol-selection"), required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--manual-version", default="")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--releases-json", default="", help="Test-only local Release response")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_tree):
        raise ValueError("invalid git tree SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        raise ValueError("invalid git commit SHA")
    releases = json.load(open(args.releases_json, encoding="utf8")) if args.releases_json else list_releases(args.repository)
    result = resolve(releases, args.project, args.source_tree, args.manual_version.strip())
    result["source_tree"] = args.source_tree
    result["source_sha"] = args.source_sha
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf8") as output:
            for key, value in result.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                print(f"{key}={value}", file=output)


if __name__ == "__main__":
    main()
