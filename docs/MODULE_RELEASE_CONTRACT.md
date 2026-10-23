# E2E / KOL Native Module Release Contract (v1)

Applies **only** to `kol-selection` and `e2e`. Product Grabber and Audience Portrait use their unchanged legacy release paths.

## 1. Source-only build interface (EC-AI)

On macOS ARM64 or Windows x64, with Python 3.12 and Nuitka installed:

```
python scripts/build_runtime.py --platform macos-arm64 --version 1.0.0-dev.2 --output-dir <absolute-outside-source-dir>
python scripts/build_runtime.py --platform windows-x64 --version 1.0.0-dev.2 --output-dir <absolute-outside-source-dir>
```

The command **must compile the private business modules only**, using Nuitka extension/module/package mode (no standalone executable, no third-party module inclusion). Pin Nuitka and build dependencies via `config/requirements-build.txt`. Build output is, respectively:

```
<output-dir>/kol-selection-macos-arm64/
  modules/backend/...  # importable compiled CPython 3.12 extensions
  frontend/...
  requirements-runtime.txt
  module-release.json

<output-dir>/e2e-dmp-windows-x64/
  modules/...          # flat importable compiled CPython 3.12 extensions
  web/...
  requirements-runtime.txt
  module-release.json
```

Produce the analogous directories on the opposite platforms. `modules/` must contain NO private `.py` or `.pyc`; names may use CPython extension suffixes (`.pyd` or `.so`). Modules are loadable with `modules/` on `sys.path`.

**Public module metadata** `module-release.json`:

```json
{
  "schema": 1,
  "project": "kol-selection",
  "platform": "macos-arm64",
  "version": "1.0.0-dev.2",
  "python": "3.12",
  "entry_module": "backend.packaged_entry"
}
```

For E2E use `project: "e2e"`, `entry_module: "packaged_entry"`. Include a callable `main()` accepting `sys.argv` semantics; KOL CLI: `version`, `idle`, `setup`, `start`, `stop`, `status`; E2E additionally supports `worker run-batch ...`. The public `module_launcher.py` supplied by ISV-Release uses the metadata to select these entries. The app modules should resolve the installed static root from `EC_AI_RUNTIME_ROOT`, and the installed launcher sets `EC_AI_MODULE_MODE=1`. Child/background processes must invoke the installed venv Python and public launcher, not Nuitka standalone `process_exe` or a relative source file.

`requirements-runtime.txt` contains the **complete pinned public third-party transitive dependency set** (do not include Nuitka or the private project). Require `name==version --hash=sha256:...` for each distribution/wheel, with hashes for the target platform, compatible with `pip install --require-hashes -r requirements-runtime.txt`. Do not include editable packages, VCS URLs, custom indexes, local paths, secrets, or executable pip options. Playwright Python SDK is included here; Chromium remains a separate optional install at setup time. E2E requires Google Chrome for live login.

Only publicly distributable static files may be included in `frontend/` or `web/`. Compile any private config/prompt/templates into native extensions or provide only explicitly approved non-sensitive assets. Private credentials, captured HAR, cookies, build reports, Python source, C/OBJ intermediates and debug files must NEVER enter the output directory.

## 2. Installer / updates

The public lightweight Skill embeds `module_installer.py`, `module_launcher.py`, the macOS/Windows wrapper scripts, URLs and SHA256 hashes. At first install, the agent must have an official Python **3.12.x** installation. It will:
- Download only GitHub Release artifacts, verify SHA256 and verify the archive structure.
- Create a per-project venv in a user-private cache **keyed by the dependency-lock SHA256**, install pinned public packages with `--require-hashes`. Subsequent business-code updates reuse an unchanged venv.
- Stage compiled modules and public static assets; activate the new version only after staging.
- Start through the venv Python + public launcher; status/stop use the same launcher. Existing user data is outside the install directory.
- Warn if Python/Chrome is missing, instead of executing arbitrary runtime installers.

Source privacy is enforced by allowlist-based archive checks before **any public Actions artifact upload**. `.py` only appears in the **public, independently authored Skill launcher/installer**, never in the private compiled-runtime ZIP.

## 3. CI gates

Preflight: verify new build contract, source compile and offline business regression tests.
Build: native macOS ARM64 and Windows x64, compile **only private modules**, no private-source or generated C/OBJ caching.
Pre-upload: inspect archive format, filename restrictions, module extensions, metadata and dependency lock; fail closed.
Test-runtime: create clean Python 3.12 venv, pip install locked third-party dependencies, execute compiled `main()`, verify start/status/stop and offline web/worker/report API.
Assembly: create immutable public Runtime ZIPs and small Skill ZIP, hash all assets.
Final Skill: on Windows PowerShell 5.1, exercise the actual installer against the locally staged verified archive.
Publish: only if all gates succeed.

Do not run the old standalone pipeline for the two projects after the migration. The legacy releases and other two projects are unaffected. NEVER state that Nuitka binary modules are impossible to reverse-engineer.

## 4. Required EC-AI changes

- `kol-selection/scripts/build_runtime.py`, `e2e/scripts/build_runtime.py`: module-only build and directory output above; preserve existing `--platform`, `--version`, `--output-dir` CLI.
- Each project's `config/requirements-runtime.txt`: fully pinned hash-locked public runtime requirements.
- KOL `backend/runtime_paths.py`, `backend/runtime_control.py`: module-install root and venv Python launcher semantics; keep browser setup, user data and CLI compatible.
- E2E `Crawler/src/runtime_paths.py`, `Crawler/src/runtime_control.py`, `Crawler/src/packaged_entry.py`: module-install root, worker and server child-process launching via Python + public launcher; `web_app.py` resource/worker path adaptation only where necessary.
- Runtime/entrypoint regressions on both platforms; NO changes to tested collection/analysis/report business logic.
