"""Tests for harness/models.py: models.yaml's labelling rules are enforced, not just documented."""
import copy
import unittest
from pathlib import Path

from harness import models

ROOT = Path(__file__).resolve().parent.parent

GOOD = {
    "audit": {"as_of": "2026-11-09", "kind": "retrospective", "probe_repeats": 3,
              "judge_calibration_labels": 20, "judge_budget_usd": 5},
    "hardware": {"laptop": "laptop desc", "t4": "t4 desc", "hosted": "hosted desc"},
    "models": {
        "big": {"role": "A", "display": "Big", "label": "NVIDIA-hosted, text-only",
                "columns": [{"engine": "nvidia-api", "hardware": "hosted", "served_by": "nvidia-hosted"}]},
        "small": {"role": "B", "display": "Small", "label": "self-served",
                  "columns": [{"engine": "ollama", "hardware": "laptop", "served_by": "self"},
                              {"engine": "vllm", "hardware": "t4", "served_by": "self"}]},
    },
}


def mutated(fn):
    doc = copy.deepcopy(GOOD)
    fn(doc)
    return models.validate(doc)


class ValidateTests(unittest.TestCase):
    def assertOneErrorMentioning(self, errors, text):
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(text, errors[0])

    def test_a_good_document_has_no_errors(self):
        self.assertEqual(models.validate(GOOD), [])

    def test_as_of_must_be_a_quoted_iso_date_string(self):
        import datetime
        self.assertOneErrorMentioning(
            mutated(lambda d: d["audit"].update(as_of=datetime.date(2026, 11, 9))), "as_of")
        self.assertOneErrorMentioning(mutated(lambda d: d["audit"].update(as_of="Nov 9")), "as_of")

    def test_kind_is_retrospective_or_day0(self):
        self.assertEqual(mutated(lambda d: d["audit"].update(kind="day0")), [])
        self.assertOneErrorMentioning(mutated(lambda d: d["audit"].update(kind="launch")), "kind")

    def test_judge_budget_is_capped_at_five_dollars(self):
        self.assertEqual(mutated(lambda d: d["audit"].update(judge_budget_usd=4.5)), [])
        self.assertOneErrorMentioning(mutated(lambda d: d["audit"].update(judge_budget_usd=5.01)),
                                      "judge_budget_usd")

    def test_probes_repeat_at_least_three_times(self):
        self.assertOneErrorMentioning(mutated(lambda d: d["audit"].update(probe_repeats=1)),
                                      "probe_repeats")

    def test_hardware_classes_are_exactly_the_ones_runmeta_knows(self):
        self.assertOneErrorMentioning(mutated(lambda d: d["hardware"].update(tpu="x")), "hardware")
        self.assertOneErrorMentioning(mutated(lambda d: d["hardware"].pop("t4")), "hardware")

    def test_hosted_and_hosted_hardware_must_pair(self):
        def bad(d):
            d["models"]["big"]["columns"][0]["hardware"] = "t4"
        self.assertOneErrorMentioning(mutated(bad), "big")

    def test_a_hosted_model_must_say_hosted_in_its_label(self):
        def bad(d):
            d["models"]["big"]["label"] = "text-only"
        self.assertOneErrorMentioning(mutated(bad), "label")

    def test_roles_must_be_unique(self):
        def bad(d):
            d["models"]["small"]["role"] = "A"
        self.assertOneErrorMentioning(mutated(bad), "role")

    def test_missing_fields_are_reported_by_model_name(self):
        def bad(d):
            del d["models"]["small"]["label"]
        self.assertOneErrorMentioning(mutated(bad), "small")


class RealFileTests(unittest.TestCase):
    def test_the_real_models_yaml_validates(self):
        try:
            import yaml  # noqa: F401  (PyYAML is installed from M3 on)
        except ImportError:
            self.skipTest("PyYAML not installed yet; validated once via Ruby in M2")
        self.assertEqual(models.validate(models.load(ROOT / "models.yaml")), [])


if __name__ == "__main__":
    unittest.main()
