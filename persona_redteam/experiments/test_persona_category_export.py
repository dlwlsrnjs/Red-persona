import json
from pathlib import Path
import tempfile
import unittest

from pipeline.export_persona_categories import export_partitions, verify_partitions
from pipeline.persona_pool import CATEGORIES, CATEGORY_LABEL_VERSION


class PersonaCategoryExportTests(unittest.TestCase):
    def labels(self):
        rows = []
        for index, category in enumerate(sorted(CATEGORIES)):
            rows.append({
                "persona_id": f"p-{index}", "goal_category": category,
                "category_fit": "direct", "harm_direction": "none",
                "category_reason": "fixture", "category_label_version": CATEGORY_LABEL_VERSION,
                "category_label_model": "fixture", "category_label_method": "fixture",
            })
        return rows

    def write_labels(self, path):
        path.write_text("".join(
            json.dumps(row, sort_keys=True) + "\n" for row in self.labels()
        ), encoding="utf-8")

    def test_export_and_verify_cover_each_persona_exactly_once(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            labels = root / "labels.jsonl"
            output = root / "by_category"
            self.write_labels(labels)
            index = export_partitions(labels, output)
            verified = verify_partitions(labels, output)
            self.assertEqual(index, verified)
            self.assertEqual(index["total_rows"], len(CATEGORIES))
            self.assertEqual(set(index["categories"]), CATEGORIES)

    def test_verify_rejects_a_modified_partition(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            labels = root / "labels.jsonl"
            output = root / "by_category"
            self.write_labels(labels)
            index = export_partitions(labels, output)
            category = sorted(CATEGORIES)[0]
            path = output / index["categories"][category]["file"]
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                verify_partitions(labels, output)


if __name__ == "__main__":
    unittest.main()
