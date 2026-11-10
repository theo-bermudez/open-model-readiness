import json
from pathlib import Path
import tempfile
import unittest

from harness import calibration as C


def labels(values):
    return {str(i): {"label": label, "rubric_version": "v1"} for i, label in enumerate(values)}


class Metrics(unittest.TestCase):
    def test_false_accepts_abstentions_and_uncertain_humans_have_explicit_denominators(self):
        h = labels(["accept", "reject", "reject", "reject", "uncertain"])
        j = labels(["accept", "accept", "reject", "uncertain", "accept"])
        result = C.compare_labels(h, j)
        self.assertEqual(result["false_accepts_over_human_rejects"], C.fraction(1, 3))
        self.assertEqual(result["false_accepts_over_decided_human_rejects"], C.fraction(1, 2))
        self.assertEqual(result["agreement_on_decided_items"], C.fraction(2, 3))
        self.assertEqual(result["decision_coverage"], C.fraction(3, 4))
        self.assertEqual(result["human_uncertain"], 1)
        self.assertEqual(result["judge_abstentions"], 1)

    def test_zero_denominator_is_unknown_not_perfect(self):
        result = C.compare_labels(labels(["uncertain"]), labels(["uncertain"]))
        self.assertIsNone(result["agreement_on_decided_items"]["rate"])
        self.assertIsNone(result["false_accepts_over_human_rejects"]["rate"])

    def test_missing_ids_and_mismatched_rubrics_fail(self):
        with self.assertRaises(ValueError):
            C.compare_labels(labels(["accept"]), labels(["accept", "reject"]))
        h, j = labels(["accept"]), labels(["accept"])
        j["0"]["rubric_version"] = "changed"
        with self.assertRaises(ValueError):
            C.compare_labels(h, j)

    def test_invalid_direct_input_labels_fail(self):
        with self.assertRaises(ValueError):
            C.compare_labels(labels(["invented"]), labels(["accept"]))
        with self.assertRaises(ValueError):
            C.compare_labels({}, {})


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, text, name="labels.csv"):
        path = self.root / name
        path.write_text(text)
        return path

    def test_empty_missing_duplicate_and_malformed_labels_fail(self):
        header = "item_id,rubric_version,label\n"
        for text in [header, header + "a,v1,\n", header + "a,v1,accept\na,v1,reject\n",
                     header + ",v1,accept\n", header + "a,v1,accept,extra\n", "item_id,label\na,accept\n"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                C.read_labels(self.write(text))

    def test_cli_writes_aggregate_hashes_without_private_item_ids_or_notes(self):
        header = "item_id,rubric_version,label,notes\n"
        h = self.write(header + "private-example,v1,reject,private rationale\n", "human.csv")
        j = self.write(header + "private-example,v1,accept,judge rationale\n", "judge.csv")
        output = self.root / "summary.json"
        self.assertEqual(C.main(["--human", str(h), "--judge", str(j), "--output", str(output)]), 0)
        result = json.loads(output.read_text())
        self.assertEqual(result["false_accepts_over_human_rejects"]["numerator"], 1)
        self.assertEqual(len(result["source_sha256"]["human_csv"]), 64)
        self.assertNotIn("private", output.read_text())


if __name__ == "__main__":
    unittest.main()
