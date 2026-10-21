"""Public, synthetic packaging contract tests. No private source checkout required."""
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("assemble_lite", HERE / "assemble_lite.py")
assemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble)


class OfflineDiagnosticsAssembly(unittest.TestCase):
    def test_both_projects_include_offline_exporters_without_source(self):
        for project in ("product-grabber", "audience-portrait"):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = root / "source"
                slug = ("product-scraping/product-grabber/skills/product-grabber"
                        if project == "product-grabber" else
                        "audience-portrait/skills/audience-portrait")
                skill = source / slug
                (skill / "scripts").mkdir(parents=True)
                (skill / "SKILL.md").write_text("---\nname: safe-fixture\n---\n\nFixture Skill\n")
                (skill / "README.md").write_text("Synthetic fixture\n")
                (skill / "scripts/setup.sh").write_text("#!/bin/sh\nexit 0\n")
                (skill / "scripts/setup.ps1").write_text("exit 0\n")
                mac = root / "mac"
                win = root / "win"
                if project == "product-grabber":
                    for folder, name in ((mac, "product-grabber"), (win, "product-grabber.exe")):
                        folder.mkdir(parents=True)
                        (folder / name).write_bytes(b"compiled-fixture")
                        (folder / "ext").mkdir()
                        (folder / "ext/manifest.json").write_text('{"name":"fixture"}')
                else:
                    mac = root / "mac.zip"
                    win = root / "win.zip"
                    for archive, parent, name in ((mac, "mac-dist", "audience-portrait"),
                                                  (win, "win-dist", "audience-portrait.exe")):
                        with zipfile.ZipFile(archive, "w") as z:
                            z.writestr(parent + "/" + name, b"compiled-fixture")
                            z.writestr(parent + "/start.sh", "#!/bin/sh\n")
                version = "1.0.0-dev.1"
                output = root / "dist"
                assemble.build(project, version, project + "-v" + version,
                               source, mac, win, output, HERE)
                archive = output / (project + "-skill-" + version + ".zip")
                with zipfile.ZipFile(archive) as z:
                    names = set(z.namelist())
                    for name in ("SKILL.md", "scripts/setup.sh",
                                 "scripts/setup.ps1", "scripts/export-diagnostics.sh",
                                 "scripts/export-diagnostics.ps1",
                                 "scripts/export-diagnostics.jxa"):
                        self.assertIn(name, names)
                    self.assertNotIn("@@PROJECT@@", z.read("scripts/export-diagnostics.sh").decode())
                    self.assertIn(project, z.read("scripts/export-diagnostics.ps1").decode())
                    self.assertIn("export-diagnostics", z.read("SKILL.md").decode())
                    self.assertFalse(any(n.endswith((".py", ".mjs", ".pdb")) for n in names))
                self.assertLess(archive.stat().st_size, 20_000_000)
                for platform in assemble.PLATFORMS:
                    self.assertTrue((output / (project + "-runtime-" + platform +
                                               "-" + version + ".zip")).is_file())


if __name__ == "__main__":
    unittest.main()
