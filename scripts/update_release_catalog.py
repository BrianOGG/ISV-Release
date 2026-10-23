#!/usr/bin/env python3
"""Keep the public Skill download table in README synchronized with Releases."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

START = "<!-- RELEASES:START -->"
END = "<!-- RELEASES:END -->"
PROJECTS = (
    ("product-grabber", "Product Grabber", "天猫、京东商品信息采集与管理"),
    ("audience-portrait", "Audience Portrait", "多平台人群画像采集与 Excel 导出"),
    ("kol-selection", "KOL Selection", "KOL 筛选、画像分析与报告工作台"),
    ("e2e", "E2E", "达摩盘、灵犀及巨量云图 E2E 工作台"),
)
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-dev\.([1-9]\d*))?$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def version_key(version: str) -> tuple[int, int, int, int, int] | None:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        return None
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    dev = match.group(4)
    # A full release ranks above pre-releases of the same semantic version.
    return major, minor, patch, int(dev is None), int(dev or 0)


def pick_latest(releases: list[dict], project: str) -> tuple[dict, str, str]:
    options = []
    prefix = project + "-v"
    for entry in releases:
        tag = entry.get("tag_name", "")
        if entry.get("draft") or not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        version = tag[len(prefix):]
        parsed = version_key(version)
        if parsed is None:
            continue
        asset_name = f"{project}-skill-{version}.zip"
        names = {a.get("name") for a in entry.get("assets", []) if isinstance(a, dict)}
        if asset_name not in names:
            continue
        options.append((parsed, entry, version, asset_name))
    if not options:
        raise ValueError("no published Skill asset found for " + project)
    _, entry, version, asset_name = max(options, key=lambda x: x[0])
    return entry, version, asset_name


def render_table(releases: list[dict], repository: str) -> str:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("invalid repository name")
    result = [
        "| 工具 | 功能 | 最新版本 | 下载 |",
        "| --- | --- | --- | --- |",
    ]
    for slug, name, description in PROJECTS:
        try:
            entry, version, asset = pick_latest(releases, slug)
        except ValueError:
            if slug in {"kol-selection", "e2e"}:
                continue  # Display KOL only after first verified Skill is published.
            raise
        tag = entry["tag_name"]
        base = f"https://github.com/{repository}/releases"
        download = f"{base}/download/{quote(tag)}/{quote(asset)}"
        detail = f"{base}/tag/{quote(tag)}"
        state = "（开发版）" if entry.get("prerelease") else "（正式版）"
        result.append(
            f"| **{name}** | {description} | `{version}`{state} "
            f"| [下载 Skill ZIP]({download}) · [版本详情]({detail}) |"
        )
    return "\n".join(result)


def replace_table(readme: str, releases: list[dict], repository: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("expected a single pair of release index markers")
    left, tail = readme.split(START, 1)
    _, right = tail.split(END, 1)
    return left + START + "\n" + render_table(releases, repository) + "\n" + END + right


def get_releases(repository: str) -> list[dict]:
    all_releases: list[dict] = []
    for page in range(1, 21):
        result = subprocess.run(
            ["gh", "api", f"repos/{repository}/releases?per_page=100&page={page}"],
            check=True, text=True, capture_output=True,
        )
        chunk = json.loads(result.stdout)
        if not isinstance(chunk, list):
            raise ValueError("invalid Releases API response")
        all_releases.extend(chunk)
        if len(chunk) < 100:
            break
    else:
        raise ValueError("release pagination exceeded supported limit")
    return all_releases


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY", "BrianOGG/ISV-Release")
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("invalid repository name")
    target = Path(os.environ.get("README_PATH", "README.md"))
    releases = get_releases(repository)
    original = target.read_text(encoding="utf-8")
    updated = replace_table(original, releases, repository)
    if original != updated:
        target.write_text(updated, encoding="utf-8")
        print("Latest Skill download table updated")
    else:
        print("Latest Skill download table is current")


if __name__ == "__main__":
    main()
