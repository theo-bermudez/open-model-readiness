"""Tests for scripts/secret_scan.py: the guard behind hard rule 1 (no keys in the repo).

Fake keys are built at runtime from pieces so this file never contains a key-shaped
literal itself (otherwise the scanner would block its own test file).
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import secret_scan

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "scripts" / "secret_scan.py"
HOOK = ROOT / "scripts" / "githooks" / "pre-commit"
SCRATCH = ROOT / ".scratch"  # gitignored; keeps test files inside the project folder

FAKE_NVIDIA = "nvapi-" + "A1b2C3d4" * 5
FAKE_ANTHROPIC = "sk-ant-" + "api03-" + "Zy9x8W7v" * 4
FAKE_HF = "hf_" + "AbCdEfGhIj" * 4
FAKE_BEARER = "Authorization: Bearer " + "q1w2e3r4t5" * 3
CANARY = "canary-value-" + "9f8e7d6c5b4a"


class ScanTextTests(unittest.TestCase):
    def test_known_key_shapes_are_flagged(self):
        for label, secret in [("nvidia-api-key", FAKE_NVIDIA), ("anthropic-api-key", FAKE_ANTHROPIC),
                              ("huggingface-token", FAKE_HF), ("bearer-token", FAKE_BEARER)]:
            findings = secret_scan.scan_text("f.json", f"x {secret} y", {}, ".env")
            self.assertEqual(len(findings), 1, label)
            self.assertIn(label, findings[0])
            self.assertNotIn(secret, findings[0])  # the report must never echo the secret

    def test_documentation_placeholders_are_not_flagged(self):
        text = ("curl -H 'Authorization: Bearer $NVIDIA_API_KEY' ...\n"
                "NVIDIA_API_KEY=\nANTHROPIC_API_KEY=\nexport key=nvapi-xxxx\n"
                "hf_overrides and hf_repo are ordinary identifiers\n")
        self.assertEqual(secret_scan.scan_text("README.md", text, {}, ".env"), [])

    def test_env_value_is_caught_verbatim_and_reported_by_key_name_only(self):
        findings = secret_scan.scan_text("notes.md", f"oops {CANARY} oops", {"SOME_KEY": CANARY}, ".env")
        self.assertEqual(len(findings), 1)
        self.assertIn("SOME_KEY", findings[0])
        self.assertNotIn(CANARY, findings[0])


class LoadCanariesTests(unittest.TestCase):
    def write_env(self, body):
        SCRATCH.mkdir(exist_ok=True)
        d = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "test.env"
        p.write_text(body)
        return p

    def test_parses_plain_export_quoted_and_inline_comment_forms(self):
        p = self.write_env(
            "# comment\n\nPLAIN=plainvalue-12345\nexport EXPORTED=exportedvalue-12345\n"
            "QUOTED=\"quotedvalue-12345\"\nSINGLE='singlevalue-12345'\n"
            "WITHCOMMENT=commentvalue-12345 # trailing note\nEQUALS=abc=def=ghi-12345\n")
        got = secret_scan.load_canaries(p)
        self.assertEqual(got["PLAIN"], "plainvalue-12345")
        self.assertEqual(got["EXPORTED"], "exportedvalue-12345")
        self.assertEqual(got["QUOTED"], "quotedvalue-12345")
        self.assertEqual(got["SINGLE"], "singlevalue-12345")
        self.assertEqual(got["WITHCOMMENT"], "commentvalue-12345")
        self.assertEqual(got["EQUALS"], "abc=def=ghi-12345")

    def test_blank_and_short_values_are_ignored(self):
        p = self.write_env("BLANK=\nSHORT=abc\nREAL=long-enough-value\n")
        self.assertEqual(list(secret_scan.load_canaries(p)), ["REAL"])

    def test_missing_env_file_means_no_canaries(self):
        self.assertEqual(secret_scan.load_canaries(SCRATCH / "does-not-exist.env"), {})


class CliTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def scan(self, *args, env_file=None):
        env = {"PATH": "/usr/bin:/bin"}
        if env_file:
            env["ENV_FILE"] = str(env_file)
        return subprocess.run([sys.executable, str(SCAN), *args], capture_output=True, text=True,
                              env=env, cwd=self.dir)

    def test_clean_file_exits_zero(self):
        f = self.dir / "ok.json"
        f.write_text('{"ttft_ms": 123.4}')
        r = self.scan("--files", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_key_shaped_file_exits_one_and_never_prints_the_key(self):
        f = self.dir / "export.json"
        f.write_text(f'{{"cmd": "aiperf --api-key {FAKE_NVIDIA}"}}')
        r = self.scan("--files", str(f))
        self.assertEqual(r.returncode, 1)
        self.assertIn("export.json", r.stderr)
        self.assertNotIn(FAKE_NVIDIA, r.stdout + r.stderr)

    def test_env_canary_catches_a_key_in_an_unknown_format(self):
        env = self.dir / "test.env"
        env.write_text(f"MYSTERY_KEY={CANARY}\n")
        f = self.dir / "log.txt"
        f.write_text(f"request headers: {CANARY}")
        r = self.scan("--files", str(f), env_file=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MYSTERY_KEY", r.stderr)
        self.assertNotIn(CANARY, r.stdout + r.stderr)

    def test_a_file_named_dot_env_is_blocked_even_when_values_are_blank(self):
        f = self.dir / ".env"
        f.write_text("NVIDIA_API_KEY=\n")
        self.assertEqual(self.scan("--files", str(f)).returncode, 1)
        ok = self.dir / ".env.example"
        ok.write_text("NVIDIA_API_KEY=\n")
        self.assertEqual(self.scan("--files", str(ok)).returncode, 0)

    def test_unreadable_target_exits_two(self):
        self.assertEqual(self.scan("--files", str(self.dir / "missing.txt")).returncode, 2)


class StagedModeAndHookTests(unittest.TestCase):
    """Uses a throwaway git repo INSIDE .scratch so the real repo is never touched."""

    def setUp(self):
        SCRATCH.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def run_hook(self):
        return subprocess.run([str(HOOK)], cwd=self.repo, capture_output=True, text=True)

    def test_hook_blocks_a_staged_key_and_passes_once_it_is_removed(self):
        f = self.repo / "runs_export.json"
        f.write_text(f'{{"auth": "{FAKE_ANTHROPIC}"}}')
        self.git("add", "runs_export.json")
        blocked = self.run_hook()
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertNotIn(FAKE_ANTHROPIC, blocked.stdout + blocked.stderr)
        f.write_text('{"auth": "removed"}')
        self.git("add", "runs_export.json")
        self.assertEqual(self.run_hook().returncode, 0)

    def test_hook_scans_the_staged_version_not_the_working_copy(self):
        f = self.repo / "notes.txt"
        f.write_text(f"leaked {FAKE_HF}")
        self.git("add", "notes.txt")
        f.write_text("cleaned in the working tree only")  # index still holds the key
        self.assertEqual(self.run_hook().returncode, 1)

    def test_hook_passes_when_nothing_is_staged(self):
        self.assertEqual(self.run_hook().returncode, 0)


if __name__ == "__main__":
    unittest.main()
