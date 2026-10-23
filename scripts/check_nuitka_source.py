#!/usr/bin/env python3
"""Fast, read-only contract gate for private E2E/KOL Nuitka builders.

Only public pass/fail markers are printed. No source text, file paths, or
compiler reports are copied to the public build logs.
"""
import argparse
from pathlib import Path

def check(project: str, root: Path):
    script = root / "scripts" / "build_runtime.py"
    if not script.is_file():
        raise ValueError("BUILD_SCRIPT_MISSING")
    source = script.read_text(encoding="utf-8")
    # The build profile must be honored by the private compiler command.
    needed = ("ECAI_NUITKA_JOBS", "ECAI_NUITKA_LOW_MEMORY",
              "--jobs=", "--low-memory")
    if any(marker not in source for marker in needed):
        raise ValueError("MEMORY_SAFE_BUILD_PROFILE_MISSING")
    if project == "kol-selection":
        if "--nofollow-import-to=*.tests" not in source:
            raise ValueError("THIRD_PARTY_TEST_EXCLUSION_MISSING")
    elif project == "e2e":
        private = root / "Crawler" / "src"
        for name in ("runtime_control.py", "runtime_paths.py"):
            file = private / name
            if not file.is_file() or "process_exe" not in file.read_text(encoding="utf-8"):
                raise ValueError("COMPILED_PROCESS_RESTART_MISSING")
        if not (private / "packaged_entry.py").is_file():
            raise ValueError("WORKER_ENTRY_MISSING")
    else:
        raise ValueError("UNSUPPORTED_PROJECT")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=("kol-selection", "e2e"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.project, args.source)
    except (ValueError, OSError, UnicodeError) as error:
        raise SystemExit("Build preflight blocked: " + (
            str(error) if isinstance(error, ValueError) else "BUILD_SCRIPT_UNAVAILABLE"))
    print("Memory-safe Nuitka build source contract passed")

if __name__ == "__main__":
    main()
