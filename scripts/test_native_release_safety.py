"""Source-free release CI safety contracts for Nuitka native builds."""
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from check_nuitka_source import check
from verify_runtime_archive import check_archive

PROFILE = "# ECAI_NUITKA_JOBS ECAI_NUITKA_LOW_MEMORY --jobs= --low-memory\n"

class NativeReleaseSafetyTests(unittest.TestCase):
    def test_kol_requires_memory_profile_and_bloat_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            script = source / "scripts" / "build_runtime.py"
            script.parent.mkdir(parents=True)
            script.write_text(PROFILE)
            with self.assertRaisesRegex(ValueError, "THIRD_PARTY_TEST_EXCLUSION"):
                check("kol-selection", source)
            script.write_text(PROFILE + "'--nofollow-import-to=*.tests'\n")
            check("kol-selection", source)
            script.write_text("unused")
            with self.assertRaisesRegex(ValueError, "MEMORY_SAFE"):
                check("kol-selection", source)

    def test_e2e_requires_worker_and_compiled_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            script = source / "scripts" / "build_runtime.py"
            script.parent.mkdir(parents=True)
            script.write_text(PROFILE)
            core = source / "Crawler" / "src"
            core.mkdir(parents=True)
            (core / "runtime_control.py").write_text("process_exe")
            (core / "runtime_paths.py").write_text("process_exe")
            with self.assertRaisesRegex(ValueError, "WORKER_ENTRY"):
                check("e2e", source)
            (core / "packaged_entry.py").write_text("# isolated worker")
            check("e2e", source)

    def test_public_runtime_checks_target_and_denies_private_files(self):
        for project, binary in (("kol-selection", "kol-selection"), ("e2e", "e2e-dmp")):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / "artifact.zip"
                root = binary + "-windows-x64"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr(root + "/" + binary + ".exe", b"native")
                    z.writestr(root + "/frontend/app.js", "offline static asset")
                self.assertGreater(check_archive(archive, project, "windows-x64"), 0)
                with zipfile.ZipFile(archive, "a") as z:
                    z.writestr(root + "/backend/main.py", "PRIVATE SOURCE")
                with self.assertRaisesRegex(ValueError, "PRIVATE_OR_DEBUG"):
                    check_archive(archive, project, "windows-x64")

    def test_public_runtime_denies_links_and_malicious_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("e2e-dmp-macos-arm64/e2e-dmp", b"binary")
                item = zipfile.ZipInfo("e2e-dmp-macos-arm64/private")
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, b"../secret")
            with self.assertRaisesRegex(ValueError, "SYMLINK"):
                check_archive(archive, "e2e", "macos-arm64")

if __name__ == "__main__":
    unittest.main()
