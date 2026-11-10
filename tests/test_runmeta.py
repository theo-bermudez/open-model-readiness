"""Tests for harness/runmeta.py: every run folder says what produced its numbers."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from harness import runmeta

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / ".scratch"
NOW = datetime(2026, 11, 9, 15, 30, 45, tzinfo=timezone.utc)
STUB_HW = {"os": "stub-os", "machine": "arm64", "cpu": "stub cpu", "ram_gb": 8.0, "gpus": [],
           "driver_max_cuda_version": None}


def make_meta(**overrides):
    args = dict(kind="aiperf", model_key="nemotron-3-nano-4b", model_id="nemotron-3-nano:4b-q4_K_M",
                quantization="Q4_K_M", engine_name="ollama", engine_version="0.30.10",
                hardware_class="laptop", served_by="self", tool_name="aiperf", tool_version="0.13.0",
                now=NOW)
    args.update(overrides)
    with mock.patch.object(runmeta, "detect_hardware", return_value=STUB_HW):
        return runmeta.collect_meta(**args)


def scratch_dir(test):
    SCRATCH.mkdir(exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class LabellingRules(unittest.TestCase):
    """Hosted and self-served numbers must never be mistaken for each other."""

    def test_self_served_laptop_run_records_detected_hardware(self):
        m = make_meta()
        self.assertEqual(m["hardware_class"], "laptop")
        self.assertEqual(m["serving_hardware"], STUB_HW)

    def test_hosted_must_pair_with_hosted_and_only_that(self):
        with self.assertRaises(ValueError):
            make_meta(served_by="nvidia-hosted", hardware_class="t4")
        with self.assertRaises(ValueError):
            make_meta(served_by="self", hardware_class="hosted")

    def test_unknown_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            make_meta(hardware_class="gpu-box")
        with self.assertRaises(ValueError):
            make_meta(served_by="cloud")

    def test_hosted_run_says_hardware_is_undisclosed_and_never_probes_ours(self):
        with mock.patch.object(runmeta, "detect_hardware") as probe:
            m = runmeta.collect_meta(kind="aiperf", model_key="nemotron-3.5-super-vl",
                                     model_id="nvidia/nemotron-3.5-super-vl-120b-a12b",
                                     quantization="undisclosed", engine_name="nvidia-api",
                                     engine_version=None, hardware_class="hosted",
                                     served_by="nvidia-hosted", now=NOW)
        probe.assert_not_called()
        self.assertEqual(m["serving_hardware"], {"disclosed": False})
        self.assertIsNone(m["engine"]["version"])  # unknown stays null, never guessed


class MetaShape(unittest.TestCase):
    def test_required_fields_and_timestamp_format(self):
        m = make_meta()
        for key in ("schema_version", "kind", "timestamp_utc", "served_by", "hardware_class",
                    "serving_hardware", "client", "model", "engine", "tool", "notes"):
            self.assertIn(key, m)
        self.assertEqual(m["timestamp_utc"], "2026-11-09T15:30:45Z")
        self.assertEqual(m["engine"], {"name": "ollama", "version": "0.30.10", "flags": []})
        self.assertEqual(m["tool"], {"name": "aiperf", "version": "0.13.0"})

    def test_no_personal_identifiers_are_recorded(self):
        text = json.dumps(make_meta())
        self.assertNotIn(Path.home().as_posix(), text)

        def keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from keys(v)

        self.assertFalse({"hostname", "user", "username", "home"} & set(keys(make_meta())))


class RunDirectories(unittest.TestCase):
    def test_name_sorts_by_time_and_describes_the_run(self):
        root = scratch_dir(self)
        p = runmeta.new_run_dir(root, kind="aiperf", model_key="nemotron-3-nano-4b", engine="ollama",
                                hardware_class="laptop", now=NOW)
        self.assertEqual(p.name, "20261109T153045Z_nemotron-3-nano-4b_ollama_laptop_aiperf")
        self.assertTrue(p.is_dir())

    def test_a_run_folder_is_never_reused(self):
        root = scratch_dir(self)
        kw = dict(kind="aiperf", model_key="m", engine="ollama", hardware_class="laptop", now=NOW)
        runmeta.new_run_dir(root, **kw)
        with self.assertRaises(FileExistsError):
            runmeta.new_run_dir(root, **kw)

    def test_path_traversal_in_name_parts_is_rejected(self):
        root = scratch_dir(self)
        with self.assertRaises(ValueError):
            runmeta.new_run_dir(root, kind="aiperf", model_key="../escape", engine="ollama",
                                hardware_class="laptop", now=NOW)

    def test_write_meta_is_stable_sorted_json(self):
        d = scratch_dir(self)
        m = make_meta()
        runmeta.write_meta(d, m)
        text = (d / "meta.json").read_text()
        self.assertEqual(text, json.dumps(m, indent=2, sort_keys=True) + "\n")


class Detectors(unittest.TestCase):
    def test_parse_nvidia_smi_with_and_without_compute_capability(self):
        self.assertEqual(runmeta.parse_nvidia_smi_gpus("Tesla T4, 15360, 535.104.05, 7.5\n"),
                         [{"name": "Tesla T4", "memory_mib": 15360, "driver": "535.104.05",
                           "compute_capability": "7.5"}])
        old = runmeta.parse_nvidia_smi_gpus("Tesla T4, 15360, 470.82.01")  # old drivers lack compute_cap
        self.assertIsNone(old[0]["compute_capability"])
        self.assertEqual(runmeta.parse_nvidia_smi_gpus(None), [])

    def test_parse_cuda_version_from_nvidia_smi_header(self):
        hdr = "| NVIDIA-SMI 535.104.05   Driver Version: 535.104.05   CUDA Version: 12.2     |"
        self.assertEqual(runmeta.parse_cuda_version(hdr), "12.2")
        self.assertIsNone(runmeta.parse_cuda_version("no gpu here"))
        self.assertIsNone(runmeta.parse_cuda_version(None))

    def test_package_version_is_none_when_not_installed_and_never_guessed(self):
        self.assertIsNone(runmeta.package_version("definitely-not-a-real-package-xyz"))
        with mock.patch.object(runmeta.metadata, "version", return_value="1.2.3"):
            self.assertEqual(runmeta.package_version("aiperf"), "1.2.3")

    def test_ollama_version_comes_from_the_running_server(self):
        with mock.patch.object(runmeta, "urlopen", return_value=io.BytesIO(b'{"version":"0.30.10"}')):
            self.assertEqual(runmeta.ollama_server_version(), "0.30.10")
        with mock.patch.object(runmeta, "urlopen", side_effect=OSError("connection refused")):
            self.assertIsNone(runmeta.ollama_server_version())

    def test_detect_hardware_smoke_returns_the_documented_keys(self):
        hw = runmeta.detect_hardware()
        self.assertTrue({"os", "machine", "cpu", "ram_gb", "gpus", "driver_max_cuda_version"} <= set(hw))
        self.assertTrue(hw["ram_gb"] is None or hw["ram_gb"] > 0)


class Cli(unittest.TestCase):
    ARGS = ["--kind", "aiperf", "--model-key", "nemotron-3-nano-4b", "--model-id",
            "nemotron-3-nano:4b-q4_K_M", "--quant", "Q4_K_M", "--engine", "ollama",
            "--hardware", "laptop", "--served-by", "self"]

    def run_cli(self, extra):
        root = scratch_dir(self)
        out = io.StringIO()
        with mock.patch.object(runmeta, "detect_hardware", return_value=STUB_HW), \
                mock.patch.object(runmeta, "ollama_server_version", return_value="9.9.9"), \
                contextlib.redirect_stdout(out):
            code = runmeta.main(self.ARGS + ["--runs-root", str(root)] + extra)
        return code, Path(out.getvalue().strip())

    def test_cli_creates_the_run_folder_with_meta_and_prints_its_path(self):
        code, path = self.run_cli(["--tool", "aiperf", "--tool-version", "0.13.0"])
        self.assertEqual(code, 0)
        meta = json.loads((path / "meta.json").read_text())
        self.assertEqual(meta["tool"]["version"], "0.13.0")

    def test_cli_asks_the_running_ollama_server_when_no_version_is_given(self):
        _, path = self.run_cli([])
        self.assertEqual(json.loads((path / "meta.json").read_text())["engine"]["version"], "9.9.9")


if __name__ == "__main__":
    unittest.main()
