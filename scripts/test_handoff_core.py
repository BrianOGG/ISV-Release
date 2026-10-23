"""Public synthetic tests for the Codex v2 compiled Core / Skill handoff."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from core_handoff_archive import core_metadata, build_archive
from assemble_handoff import assemble

def sha(data):
    return hashlib.sha256(data).hexdigest()

class HandoffContractTests(unittest.TestCase):
    def fixture(self,root,project,platform,version="1.0.0-dev.1",with_source=False):
        root=Path(root)
        build=root/"build"
        build.mkdir(parents=True)
        ui="frontend" if project=="kol-selection" else "web"
        native="backend.cpython-312-darwin.so" if project=="kol-selection" else "packaged_entry.cp312-win_amd64.pyd"
        if project=="e2e" and platform=="macos-arm64":
            native="packaged_entry.cpython-312-darwin.so"
        if project=="kol-selection" and platform=="windows-x64":
            native="backend.cp312-win_amd64.pyd"
        (build/"core").mkdir()
        (build/ui).mkdir()
        (build/"core"/native).write_bytes(b"\x7fELFnative_fixture")
        if project=="e2e":
            for k in range(34):
                name="fake_module_"+str(k)+(".pyd" if platform=="windows-x64" else ".so")
                (build/"core"/name).write_bytes(b"\0native_fixture")
        (build/ui/"index.html").write_text("<html>fixture</html>")
        if with_source: (build/"core"/"secrets.py").write_text("SECRET")
        payload=[
            {"path":p.relative_to(build).as_posix(),
             "sha256":sha(p.read_bytes()),"size":p.stat().st_size}
            for p in sorted(build.rglob("*")) if p.is_file()]
        lock=b"sample==1.0.0 --hash=sha256:"+b"a"*64+b"\n"
        manifest={"schema_version":2,"project":project,
                  "version":version,"core_version":version,"bundle_version":version,
                  "platform":platform,"python_abi":"cp312",
                  "core_format":"nuitka-package-v1" if project=="kol-selection" else "nuitka-modules-v1",
                  "lock_sha256":sha(lock),"modules_count":60 if project=="kol-selection" else 38,
                  "artifacts":payload}
        (build/"core-build.json").write_text(json.dumps(manifest))
        result=root/"native.zip"
        build_archive(build,result,project,platform,version)
        return result,lock

    def test_reject_compiler_source_and_wrong_platform(self):
        for project in ("kol-selection","e2e"):
            with self.subTest(project=project),tempfile.TemporaryDirectory() as temp:
                archive,_=self.fixture(temp,project,"windows-x64")
                self.assertEqual(core_metadata(archive,project,"windows-x64","1.0.0-dev.1")["schema_version"],2)
                with self.assertRaisesRegex(ValueError,"SOURCE_OR_WRONG_NATIVE_EXTENSION|CORE_METADATA_CONTRACT"):
                    core_metadata(archive,project,"macos-arm64","1.0.0-dev.1")
            with self.subTest(project=project),tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError,"SOURCE_OR_WRONG_NATIVE_EXTENSION"):
                    self.fixture(temp,project,"windows-x64",with_source=True)

    def test_assemble_skill_uses_exact_ecai_installer_and_lock_hashes(self):
        for project in ("kol-selection","e2e"):
            with self.subTest(project=project),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                mac,lock=self.fixture(root/"mac",project,"macos-arm64")
                win,_=self.fixture(root/"win",project,"windows-x64")
                skill=root/"source"/project/"skills"/project
                (skill/"assets").mkdir(parents=True)
                (skill/"scripts").mkdir()
                example={"schema_version":2,"project":project,"skill_version":"RELEASE_ASSIGNED","platforms":{}}
                (skill/"assets/release.example.json").write_text(json.dumps(example))
                for rel in ("SKILL.md","scripts/ecai_launcher.py","scripts/ecai_install.py","scripts/setup.sh"):
                    path=skill/rel
                    path.write_text("synthetic fixture")
                (skill/"scripts/setup.ps1").write_bytes(b"\xef\xbb\xbfWrite-Output fixture\n")
                for p in ("macos-arm64","windows-x64"):
                    (skill/"assets"/("requirements-runtime-"+p+".txt")).write_bytes(lock)
                    (skill/"assets"/("requirements-bootstrap-"+p+".txt")).write_bytes(lock)
                out=root/"release"
                assemble(project,"1.0.0-dev.1",project+"-v1.0.0-dev.1",root/"source",mac,win,out)
                zipfile_path=out/(project+"-skill-1.0.0-dev.1.zip")
                with zipfile.ZipFile(zipfile_path) as z:
                    self.assertEqual(z.read("scripts/ecai_install.py"),b"synthetic fixture")
                    desc=json.loads(z.read("assets/release.json"))
                    self.assertEqual(desc["platforms"]["windows-x64"]["lock_sha256"],sha(lock))
                    self.assertNotIn(b"RELEASE_ASSIGNED",z.read("assets/release.json"))

if __name__=="__main__":
    unittest.main()
