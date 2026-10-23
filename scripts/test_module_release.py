"""Source-free tests of module-only release files; no business Python source."""
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from assemble_modules import build
from module_archive import check_lock, validate_zip
from module_installer import staging_payload
from package_module_artifact import pack

ROOT = Path(__file__).resolve().parent
HASHES = "a"*64

class ModuleReleaseTests(unittest.TestCase):
    def make(self, td, project, platform, *, extra=None):
        root = Path(td)
        slug = "kol-selection" if project == "kol-selection" else "e2e-dmp"
        payload = root / "build" / (slug + "-" + platform)
        (payload / "modules").mkdir(parents=True, exist_ok=True)
        native = ".so" if platform == "macos-arm64" else ".pyd"
        (payload / "modules" / ("entry" + native)).write_bytes(b"\x7fELF compiled fixture")
        web = payload / ("frontend" if project == "kol-selection" else "web")
        web.mkdir()
        (web / "index.html").write_text("<html>fixture</html>")
        (payload / "module-release.json").write_text(json.dumps({
            "schema": 1, "project": project, "version": "1.0.0-dev.1",
            "python": "3.12", "platform": platform,
            "entry_module": "backend.packaged_entry" if project == "kol-selection" else "packaged_entry"
        }))
        (payload / "requirements-runtime.txt").write_text("demo==1.0 --hash=sha256:" + HASHES + "\n")
        if extra:
            (payload / extra).write_text("private")
        archive = root / (project + "-" + platform + ".zip")
        pack(root / "build", platform, project, "1.0.0-dev.1", archive)
        return archive

    def test_validated_binaries_and_public_light_skill(self):
        for project in ("kol-selection", "e2e"):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                mac = self.make(root / "mac", project, "macos-arm64")
                win = self.make(root / "win", project, "windows-x64")
                skill_path = ("kol-selection/skills/kol-selection" if project == "kol-selection" else "e2e/skills/e2e")
                skill = root / "source" / skill_path
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text("---\nname: fixture\n---\n\nOffline synthetic fixture\n")
                output = root / "release"
                build(project, "1.0.0-dev.1", project + "-v1.0.0-dev.1",
                      root / "source", mac, win, output, ROOT)
                skill_zip = output / (project + "-skill-1.0.0-dev.1.zip")
                self.assertTrue(skill_zip.is_file())
                self.assertLess(skill_zip.stat().st_size, 20_000_000)
                with zipfile.ZipFile(skill_zip) as z:
                    files = set(z.namelist())
                    for filename in ("SKILL.md", "scripts/setup.sh", "scripts/setup.ps1",
                                     "scripts/module_archive.py", "scripts/module_launcher.py",
                                     "scripts/module_installer.py", "assets/download.json"):
                        self.assertIn(filename, files)
                    self.assertTrue(z.read("scripts/setup.ps1").startswith(b"\xef\xbb\xbf"))
                    manifest = json.loads(z.read("assets/download.json"))
                    self.assertEqual(manifest["project"], project)
                    self.assertEqual(manifest["python"], "3.12")
                    self.assertIn("native", z.read("assets/release.json").decode())
                for platform in ("macos-arm64", "windows-x64"):
                    archive = output / (project + "-runtime-" + platform + "-1.0.0-dev.1.zip")
                    self.assertGreater(validate_zip(archive, project, platform, "1.0.0-dev.1"), 0)
                    staged = root / ("stage-" + platform)
                    staging_payload(archive, staged, project, platform, "1.0.0-dev.1")
                    self.assertTrue((staged / "requirements-runtime.txt").is_file())

    def test_private_source_and_unhashed_requirements_are_rejected(self):
        for bad in ("modules/secret.py", "modules/secret.pyc", "modules/private.c",
                    "modules/secret.obj", "modules/runtime.pdb", "data/cookies.json"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as td:
                with self.assertRaisesRegex(ValueError, "NON_NATIVE|PRIVATE|UNRECOGNIZED"):
                    self.make(td, "kol-selection", "windows-x64", extra=bad)
        for bad in ("requests>=2.0", "foo==1.0", "--extra-index-url https://example.com",
                    "bar @ https://example.com/wheel.whl"):
            with self.subTest(lock=bad):
                with self.assertRaisesRegex(ValueError, "NOT_HASH_PINNED"):
                    check_lock((bad + "\n").encode("utf-8"))
        check_lock(("foo==1.0 --hash=sha256:" + HASHES + "\n").encode())

    def test_symlink_in_archive_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            archive = self.make(td, "e2e", "macos-arm64")
            with zipfile.ZipFile(archive, "a") as z:
                link = zipfile.ZipInfo("e2e-dmp-macos-arm64/modules/link.so")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(link, b"secret")
            with self.assertRaisesRegex(ValueError, "SYMLINK"):
                validate_zip(archive, "e2e", "macos-arm64", "1.0.0-dev.1")

if __name__ == "__main__":
    unittest.main()
