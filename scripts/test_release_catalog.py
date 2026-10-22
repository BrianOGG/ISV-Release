"""Offline tests for the public Skill download table."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("release_catalog", HERE / "update_release_catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def release(project, version, *, prerelease=True, draft=False, asset=True):
    return {
        "tag_name": f"{project}-v{version}",
        "prerelease": prerelease,
        "draft": draft,
        "assets": [{"name": f"{project}-skill-{version}.zip"}] if asset else [],
    }


class ReleaseCatalogTests(unittest.TestCase):
    def test_latest_dev_beats_old_stable_for_higher_core_version(self):
        items = [
            release("product-grabber", "0.5.0", prerelease=False),
            release("product-grabber", "1.0.0-dev.1"),
            release("product-grabber", "1.0.0-dev.2"),
            release("audience-portrait", "1.0.0-dev.2"),
        ]
        selection = catalog.pick_latest(items, "product-grabber")
        self.assertEqual(selection[1], "1.0.0-dev.2")

    def test_stable_outranks_dev_of_same_core_version(self):
        items = [
            release("product-grabber", "1.0.0-dev.99"),
            release("product-grabber", "1.0.0", prerelease=False),
        ]
        self.assertEqual(catalog.pick_latest(items, "product-grabber")[1], "1.0.0")

    def test_draft_or_missing_skill_ignored(self):
        items = [
            release("product-grabber", "1.1.0", draft=True),
            release("product-grabber", "1.0.1-dev.1", asset=False),
            release("product-grabber", "1.0.0-dev.2"),
        ]
        self.assertEqual(catalog.pick_latest(items, "product-grabber")[1], "1.0.0-dev.2")

    def test_readme_update_only_changes_marked_index(self):
        releases = [
            release("product-grabber", "1.0.0-dev.2"),
            release("audience-portrait", "1.0.0-dev.2"),
        ]
        old = "# Tools & Skills\n\n" + catalog.START + "\nstale\n" + catalog.END + "\n\n## 使用\n保留说明。\n"
        result = catalog.replace_table(old, releases, "BrianOGG/ISV-Release")
        self.assertIn("product-grabber-skill-1.0.0-dev.2.zip", result)
        self.assertIn("audience-portrait-skill-1.0.0-dev.2.zip", result)
        self.assertIn("## 使用\n保留说明。", result)
        self.assertNotIn("stale", result)
        self.assertEqual(catalog.replace_table(result, releases, "BrianOGG/ISV-Release"), result)
        self.assertNotIn("EC-AI", result)

    def test_missing_supported_product_fails_instead_of_broken_link(self):
        with self.assertRaisesRegex(ValueError, "audience-portrait"):
            catalog.render_table([release("product-grabber", "1.0.0-dev.2")], "BrianOGG/ISV-Release")


if __name__ == "__main__":
    unittest.main()
