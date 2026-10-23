#!/usr/bin/env python3
"""Public generic process entry for compiled E2E/KOL native Python modules.

No EC-AI business logic is shipped as Python source here.
"""
import importlib
import json
import os
from pathlib import Path
import sys

ENTRIES = {"kol-selection": "backend.packaged_entry", "e2e": "packaged_entry"}

def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "module-release.json").read_text(encoding="utf-8"))
    project = manifest.get("project")
    if (project not in ENTRIES or manifest.get("entry_module") != ENTRIES[project]
            or manifest.get("python") != "3.12"):
        raise SystemExit("Installed module metadata is invalid")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("This compiled module requires CPython 3.12")
    os.environ["EC_AI_MODULE_MODE"] = "1"
    os.environ["EC_AI_RUNTIME_ROOT"] = str(root)
    sys.path.insert(0, str(root / "modules"))
    module = importlib.import_module(ENTRIES[project])
    entry = getattr(module, "main", None)
    if not callable(entry):
        raise SystemExit("Compiled module does not expose the application entry")
    result = entry()
    return int(result) if isinstance(result, int) else 0

if __name__ == "__main__":
    sys.exit(main())
