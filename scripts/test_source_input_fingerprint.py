"""Public fixture regression for release-only Git tree input fingerprints."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("inputs", HERE / "source_input_fingerprint.py")
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)

def blob(path, sha="a" * 40, mode="100644"):
    return (mode + " blob " + sha + "\t" + path + "\x00").encode()

class SourceInputTests(unittest.TestCase):
    def test_e2e_business_code_updates_digest_but_docs_and_tests_do_not(self):
        baseline = (blob("e2e/Crawler/src/runtime_control.py") +
                    blob("e2e/Crawler/web/app.js") +
                    blob("e2e/skills/e2e/SKILL.md"))
        initial, count = inputs.fingerprint(baseline, "e2e")
        self.assertEqual(count, 3)
        with_docs = baseline + blob("e2e/README.md", "b" * 40) + blob(
            "e2e/Crawler/tests/test_yuntu.py", "c" * 40) + blob(
            "e2e/Crawler/uploads/输入数据-测试.xlsx", "d" * 40)
        self.assertEqual(inputs.fingerprint(with_docs, "e2e")[0], initial)
        modified = blob("e2e/Crawler/src/runtime_control.py", "b" * 40) + (
            blob("e2e/Crawler/web/app.js") + blob("e2e/skills/e2e/SKILL.md"))
        self.assertNotEqual(inputs.fingerprint(modified, "e2e")[0], initial)

    def test_kol_dependencies_are_included_and_development_logs_excluded(self):
        base = blob("kol-selection/backend/runtime_control.py") + blob(
            "kol-selection/config/requirements-build.txt")
        digest, count = inputs.fingerprint(base, "kol-selection")
        self.assertEqual(count, 2)
        self.assertEqual(inputs.fingerprint(base + blob("kol-selection/DEVELOPMENT_LOG.md"), "kol-selection")[0], digest)
        self.assertNotEqual(inputs.fingerprint(
            blob("kol-selection/backend/runtime_control.py") +
            blob("kol-selection/config/requirements-build.txt", "b" * 40), "kol-selection")[0], digest)

    def test_symlinks_and_missing_release_inputs_rejected(self):
        with self.assertRaises(ValueError):
            inputs.fingerprint(blob("e2e/Crawler/src/worker.py", mode="120000"), "e2e")
        with self.assertRaises(ValueError):
            inputs.fingerprint(blob("e2e/README.md"), "e2e")

if __name__ == "__main__":
    unittest.main()
