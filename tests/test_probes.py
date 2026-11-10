import json
from pathlib import Path
import tempfile
import unittest

from harness import probes as P


class Scoring(unittest.TestCase):
    def test_json_order_and_whitespace_do_not_change_result(self):
        probe = {"scoring": "json_exact", "expected": '{"label":"open","priority":2}'}
        self.assertTrue(P.score(probe, '{ "priority": 2, "label": "open" }'))

    def test_json_extra_keys_wrong_types_duplicate_keys_and_invalid_wrappers_fail(self):
        probe = {"scoring": "json_exact", "expected": '{"priority":1}'}
        for answer in ['{"priority":true}', '{"priority":"1"}', '{"priority":1.0}',
                       '{"priority":1,"extra":2}', '{"priority":0,"priority":1}',
                       '```json\n{"priority":1}\n```', '{"priority":1} explanation', '{"priority":NaN}']:
            with self.subTest(answer=answer):
                self.assertFalse(P.score(probe, answer))

    def test_exact_abstention_rejects_explanation_or_case_change(self):
        probe = {"scoring": "exact", "expected": "NOT_IN_DOCUMENT"}
        self.assertTrue(P.score(probe, "NOT_IN_DOCUMENT\n"))
        self.assertFalse(P.score(probe, "not_in_document"))
        self.assertFalse(P.score(probe, "NOT_IN_DOCUMENT because it was absent"))

    def test_unknown_scorer_cannot_silently_pass(self):
        with self.assertRaises(ValueError):
            P.score({"scoring": "unregistered"}, "anything")


class Summary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.probe = {"id": "test", "category": "test", "prompt": "Question", "expected": "answer", "scoring": "exact", "coverage": "fixture"}
        (self.path / "suite.json").write_text(json.dumps([self.probe]))
        snapshot = {"timestamp_utc": "test", "os": "test", "python": "test", "ollama": {"version": "test"}}
        self.meta = {"status": "complete", "before": snapshot, "after": snapshot,
                     "wall_time_s": 1, "model": "test", "settings": {"num_predict": 256}}
        (self.path / "meta.json").write_text(json.dumps(self.meta))

    def write_rows(self, passes, repeats=None):
        rows = [{"fixture_id": "test", "repeat": repeat, "passed": passed,
                 "answer": "answer" if passed else "wrong", "request_succeeded": True,
                 "finish_reason": "stop" if passed else "length"}
                for repeat, passed in zip(repeats or range(len(passes)), passes)]
        (self.path / "requests.jsonl").write_text("\n".join(json.dumps(row) for row in rows))

    def test_failure_and_variance_are_retained(self):
        self.write_rows([True, True, False])
        result = P.summarize(self.path)
        self.assertEqual(result["status"], "complete_original_probe_suite")
        case = result["cases"][0]
        self.assertEqual(case["passes"], 2)
        self.assertEqual(case["repeats"], 3)
        self.assertEqual(case["length_finishes"], 1)
        self.assertAlmostEqual(case["pass_population_variance"], 2 / 9)

    def test_missing_or_duplicate_repeat_excludes_complete_claim(self):
        self.write_rows([True, True])
        self.assertEqual(P.summarize(self.path)["status"], "incomplete_excluded")
        self.write_rows([True, True, True], [0, 0, 2])
        self.assertEqual(P.summarize(self.path)["status"], "incomplete_excluded")

    def test_suite_duplicate_ids_rejected(self):
        file = self.path / "suite.jsonl"
        file.write_text(json.dumps(self.probe) + "\n" + json.dumps(self.probe) + "\n")
        with self.assertRaises(ValueError):
            P.load_suite(file)


if __name__ == "__main__":
    unittest.main()
