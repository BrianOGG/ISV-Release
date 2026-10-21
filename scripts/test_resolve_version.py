import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_version import resolve, version_key

TREE_A = "a" * 40
TREE_B = "b" * 40


def release(project, version, tree=TREE_A):
    return {"tag_name": f"{project}-v{version}", "draft": False, "body": f"Source-Tree: {tree}"}


class VersionResolutionTests(unittest.TestCase):
    def test_initial_dev_per_project(self):
        self.assertEqual(resolve([], "product-grabber", TREE_A)["version"], "1.0.0-dev.1")
        self.assertEqual(resolve([release("product-grabber", "1.0.0-dev.15")],
                                 "audience-portrait", TREE_A)["version"], "1.0.0-dev.1")

    def test_source_not_changed_does_not_rebuild(self):
        result = resolve([release("product-grabber", "1.0.0-dev.1")], "product-grabber", TREE_A)
        self.assertFalse(result["build"])

    def test_dev_iteration(self):
        result = resolve([release("product-grabber", "1.0.0-dev.1")], "product-grabber", TREE_B)
        self.assertEqual(result["version"], "1.0.0-dev.2")
        self.assertTrue(result["prerelease"])

    def test_stable_after_dev_and_next_patch(self):
        dev = release("product-grabber", "1.0.0-dev.9")
        stable = resolve([dev], "product-grabber", TREE_A, "1.0.0")
        self.assertEqual(stable["version"], "1.0.0")
        self.assertFalse(stable["prerelease"])
        next_dev = resolve([dev, release("product-grabber", "1.0.0")], "product-grabber", TREE_B)
        self.assertEqual(next_dev["version"], "1.0.1-dev.1")

    def test_manual_minor_then_automatic_patch(self):
        prior = release("audience-portrait", "1.0.0")
        newer = resolve([prior], "audience-portrait", TREE_B, "1.1.0")
        self.assertEqual(newer["version"], "1.1.0")
        followup = resolve([prior, release("audience-portrait", "1.1.0", TREE_B)],
                           "audience-portrait", TREE_A)
        self.assertEqual(followup["version"], "1.1.1-dev.1")

    def test_legacy_release_is_not_version_counter(self):
        old = release("product-grabber", "0.5.0")
        self.assertEqual(resolve([old], "product-grabber", TREE_B)["version"], "1.0.0-dev.1")

    def test_invalid_stable_not_allowed(self):
        with self.assertRaises(ValueError):
            resolve([], "product-grabber", TREE_A, "1.0.0-dev.3")
        with self.assertRaises(ValueError):
            resolve([release("product-grabber", "1.1.0")], "product-grabber", TREE_B, "1.0.9")

    def test_release_comparison(self):
        self.assertLess(version_key("1.0.0-dev.9"), version_key("1.0.0"))
        self.assertLess(version_key("1.0.0"), version_key("1.0.1-dev.1"))


if __name__ == "__main__":
    unittest.main()
