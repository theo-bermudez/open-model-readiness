"""Tests for harness/aiperf_stats.py: percentiles (incl. the p95 AIPerf 0.13.0 does not report)
computed from the per-request export, profiling phase only."""
import json
import tempfile
import unittest
from pathlib import Path

from harness import aiperf_stats as S

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / ".scratch"


def rec(phase, **metrics):
    return {"metadata": {"benchmark_phase": phase},
            "metrics": {k: {"value": v, "unit": "x"} for k, v in metrics.items()}}


def write_jsonl(rows):
    SCRATCH.mkdir(exist_ok=True)
    d = tempfile.TemporaryDirectory(dir=SCRATCH)
    p = Path(d.name) / "profile_export.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return d, p


class Percentile(unittest.TestCase):
    def test_linear_interpolation_like_numpy_default(self):
        v = [1, 2, 3, 4]
        self.assertEqual(S.percentile(v, 50), 2.5)
        self.assertEqual(S.percentile(v, 0), 1)
        self.assertEqual(S.percentile(v, 100), 4)
        self.assertAlmostEqual(S.percentile(v, 95), 3.85)
        self.assertAlmostEqual(S.percentile([10, 20, 30, 40, 50], 90), 46.0)

    def test_order_of_input_does_not_matter_and_one_sample_is_itself(self):
        self.assertEqual(S.percentile([4, 1, 3, 2], 50), 2.5)
        self.assertEqual(S.percentile([7], 99), 7)

    def test_empty_input_is_an_error_not_a_made_up_number(self):
        with self.assertRaises(ValueError):
            S.percentile([], 50)

    def test_agrees_with_numpy_when_available(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        vals = [3.1, 9.9, 0.4, 5.5, 5.5, 12.0, 7.7, 1.2, 8.8, 2.2, 6.1]
        for q in (50, 90, 95, 99):
            self.assertAlmostEqual(S.percentile(vals, q), float(np.percentile(vals, q)))


class Loading(unittest.TestCase):
    def test_only_the_profiling_phase_is_kept(self):
        d, p = write_jsonl([rec("warmup", request_latency=999.0), rec("profiling", request_latency=1.0),
                            rec("profiling", request_latency=2.0)])
        self.addCleanup(d.cleanup)
        rows = S.load_records(p)
        self.assertEqual([r["request_latency"] for r in rows], [1.0, 2.0])

    def test_list_valued_metrics_are_dropped_and_missing_ones_are_absent(self):
        d, p = write_jsonl([rec("profiling", request_latency=1.0, inter_chunk_latency=[0.0, 1.0])])
        self.addCleanup(d.cleanup)
        row = S.load_records(p)[0]
        self.assertNotIn("inter_chunk_latency", row)
        self.assertNotIn("reasoning_token_count", row)


class Summaries(unittest.TestCase):
    def test_summarize_reports_n_and_the_four_percentiles_per_metric(self):
        rows = [{"request_latency": float(x)} for x in range(1, 21)]
        s = S.summarize(rows, ["request_latency"])["request_latency"]
        self.assertEqual(s["n"], 20)
        self.assertAlmostEqual(s["p50"], 10.5)
        self.assertAlmostEqual(s["p95"], 19.05)

    def test_summarize_counts_n_per_metric_when_some_requests_lack_it(self):
        rows = [{"a": 1.0, "b": 5.0}, {"a": 3.0}]
        s = S.summarize(rows, ["a", "b"])
        self.assertEqual((s["a"]["n"], s["b"]["n"]), (2, 1))

    def test_a_metric_with_no_samples_is_reported_as_n_zero(self):
        self.assertEqual(S.summarize([{"a": 1.0}], ["zzz"])["zzz"], {"n": 0})

    def test_sign_counts_split_positive_negative_and_zero(self):
        self.assertEqual(S.sign_counts([5.0, -1.0, 0.0, 3.0]), {"positive": 2, "negative": 1, "zero": 1})


if __name__ == "__main__":
    unittest.main()
