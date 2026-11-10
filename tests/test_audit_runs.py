"""Guardrails for warmup exclusion, request matching and failure handling."""
import json
from pathlib import Path
import tempfile
import unittest

from harness import audit_runs as A
from harness import matched_replay as R


def raw(request_id, phase, content="answer", reasoning="", messages=None):
    return {"status": 200, "metadata": {"x_request_id": request_id, "benchmark_phase": phase,
            "request_start_ns": int(request_id), "conversation_id": "c", "turn_index": 0},
            "payload": {"messages": messages or [{"role": "user", "content": "test"}],
                        "max_tokens": 256, "temperature": 0},
            "responses": [{"packets": [{"name": "data", "value": json.dumps({"choices": [
                {"delta": {"content": content, "reasoning": reasoning}, "finish_reason": "stop"}]})}]}]}


def metric(request_id, phase, latency):
    return {"metadata": {"x_request_id": request_id, "benchmark_phase": phase},
            "metrics": {"request_latency": {"value": latency, "unit": "ms"}}}


class Audit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "runs" / "fixture"
        (self.path / "aiperf").mkdir(parents=True)
        (self.path / "meta.json").write_text(json.dumps({"hardware_class": "laptop", "engine": {}, "model": {}}))
        (self.path / "aiperf/profile_export_aiperf.json").write_text(json.dumps({"is_complete": True,
            "benchmark_duration": {"avg": 2}, "input_config": {}}))

    def write(self, raws, metrics):
        for name, rows in [("profile_export_raw.jsonl", raws), ("profile_export.jsonl", metrics)]:
            (self.path / "aiperf" / name).write_text("\n".join(json.dumps(r) for r in rows))

    def test_warmup_excluded_and_metrics_joined_by_id_not_line_order(self):
        self.write([raw("1", "warmup"), raw("2", "profiling"), raw("3", "profiling")],
                   [metric("3", "profiling", 30), metric("1", "warmup", 999), metric("2", "profiling", 10)])
        result = A.audit_run(self.path)
        self.assertEqual(result["warmup_requests"], 1)
        self.assertEqual(result["profiled_requests"], 2)
        self.assertEqual(result["metrics"]["request_latency"]["median"], 20)
        self.assertEqual(result["requests"][0]["metrics"]["request_latency"], 10)
        self.assertNotIn('"content"', json.dumps(result))

    def test_missing_metadata_or_exports_cannot_become_zero_latency(self):
        self.assertEqual(A.audit_run(self.path)["status"], "excluded")
        (self.path / "meta.json").unlink()
        self.assertEqual(A.audit_run(self.path)["exclusion_reason"], "missing meta.json")

    def test_duplicate_or_unmatched_request_ids_excluded(self):
        for ids in [["2", "2"], ["2", "3"]]:
            self.write([raw("2", "profiling")], [metric(i, "profiling", 1) for i in ids])
            self.assertEqual(A.audit_run(self.path)["status"], "excluded")

    def test_http_error_excluded(self):
        row = raw("2", "profiling")
        row["status"] = 500
        self.write([row], [metric("2", "profiling", 1)])
        self.assertEqual(A.audit_run(self.path)["status"], "excluded")

    def test_summary_error_not_in_raw_success_records_is_not_dropped(self):
        self.write([raw("2", "profiling")], [metric("2", "profiling", 1)])
        path = self.path / "aiperf/profile_export_aiperf.json"
        summary = json.loads(path.read_text())
        summary["request_error_rate"] = {"avg": 10}
        path.write_text(json.dumps(summary))
        self.assertEqual(A.audit_run(self.path)["status"], "excluded")

    def test_empty_answer_distinct_from_reasoning(self):
        result = A.raw_summary(raw("1", "profiling", content="", reasoning="some thinking"))
        self.assertTrue(result["empty_answer"])
        self.assertTrue(result["reasoning_present"])

    def test_identical_user_prompt_does_not_mean_identical_history(self):
        user = {"role": "user", "content": "follow up"}
        a = A.raw_summary(raw("1", "profiling", messages=[{"role": "assistant", "content": "one"}, user]))
        b = A.raw_summary(raw("1", "profiling", messages=[{"role": "assistant", "content": "two"}, user]))
        for row in (a, b):
            row.update(conversation_id="same", turn_index=1)
        result = A.compare({"run_id": "on", "status": "descriptive_only", "requests": [a]},
                           {"run_id": "off", "status": "descriptive_only", "requests": [b]})
        self.assertTrue(result["same_conversation_order"])
        self.assertTrue(result["same_user_messages_order"])
        self.assertFalse(result["matched_full_payload_order"])
        self.assertEqual(result["matching_full_payloads"], 0)
        self.assertFalse(result["causal_speedup_supported"])

    def test_missing_value_stays_missing(self):
        self.assertEqual(A.stats([None, None]), {"n": 0})

    def test_hardware_classes_cannot_be_mixed(self):
        result = A.compare({"status": "descriptive_only", "hardware_class": "laptop"},
                           {"status": "descriptive_only", "hardware_class": "hosted"})
        self.assertEqual(result["status"], "excluded")

    def test_public_environment_uses_allowlist(self):
        snapshot = {"timestamp_utc": "now", "os": "os", "python": "3", "ollama": {},
                    "power": "AC Power; battery (id=private-device-id)",
                    "models": {"models": [{"name": "m", "expires_at": "private-extra"}]}}
        serialized = json.dumps(A.public_environment(snapshot))
        self.assertNotIn("private", serialized)
        self.assertEqual(A.public_environment(snapshot)["power_source"], "AC")
        self.assertEqual(A.public_environment(None), {"status": "unavailable"})


class ReplayDesign(unittest.TestCase):
    def test_pair_schedule_covers_each_fixture_three_times_per_mode(self):
        from collections import Counter
        sequence = list(R.schedule())
        counts = Counter((f["id"], mode) for _, f, mode in sequence)
        self.assertEqual(len(sequence), 24)
        self.assertEqual(set(counts.values()), {3})
        first_modes = []
        for a, b in zip(sequence[::2], sequence[1::2]):
            self.assertEqual(a[:2], b[:2])
            self.assertNotEqual(a[2], b[2])
            first_modes.append(a[2])
        self.assertEqual(Counter(first_modes), {"on": 6, "off": 6})


if __name__ == "__main__":
    unittest.main()
