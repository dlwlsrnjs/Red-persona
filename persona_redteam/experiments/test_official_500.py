import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data/red_persona_official_500.jsonl"
AUDIT = ROOT / "data/red_persona_official_500.audit.json"


class Official500CohortTest(unittest.TestCase):
    def test_tracked_index_matches_official_audit(self):
        rows = [json.loads(line) for line in INDEX.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        ids = [row["case_id"] for row in rows]
        categories = {}
        for row in rows:
            categories[row["crisis_label"]] = categories.get(row["crisis_label"], 0) + 1

        self.assertEqual(len(rows), 500)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([row["official_index"] for row in rows], list(range(1, 501)))
        self.assertEqual(audit["status"], "official_analysis_cohort")
        self.assertEqual(
            audit["source_lineage"],
            {
                "origin": "JMIR Between Help and Harm public test inputs",
                "public_test_inputs": 2046,
                "six_crisis_categories": 813,
                "first_person_client_utterances": 652,
                "minimum_ten_word_goals": 625,
                "goal_pathology_persona_history_candidates": 625,
                "integrity_valid_candidates": 608,
                "official_analysis_cohort": 500,
                "external_goals_added_during_500_selection": 0,
            },
        )
        self.assertEqual(audit["overrepresented_category"], "suicidal_ideation")
        self.assertEqual(audit["overrepresented_category_downsampled"], 108)
        self.assertEqual(categories, audit["category_distribution"])
        self.assertEqual(
            hashlib.sha256(INDEX.read_bytes()).hexdigest(),
            audit["official_index_jsonl_sha256"],
        )
        self.assertEqual(
            hashlib.sha256("".join(f"{case_id}\n" for case_id in ids).encode()).hexdigest(),
            audit["official_case_ids_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
