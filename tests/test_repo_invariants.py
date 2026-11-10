"""Repo-level guards for hard rule 1 (secrets). These fail loudly if the safety net is not in place."""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


class SecretSafetyNet(unittest.TestCase):
    def test_env_is_ignored_and_never_tracked(self):
        self.assertEqual(git("check-ignore", "-q", ".env", check=False).returncode, 0, ".env must be gitignored")
        self.assertNotEqual(git("ls-files", "--error-unmatch", ".env", check=False).returncode, 0,
                            ".env must not be tracked")

    def test_env_example_is_not_ignored_and_holds_names_only(self):
        self.assertNotEqual(git("check-ignore", "-q", ".env.example", check=False).returncode, 0)
        for line in (ROOT / ".env.example").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                self.assertRegex(line, r"^[A-Z][A-Z0-9_]*=$", f"values are not allowed in .env.example: {line.split('=')[0]}")

    def test_pre_commit_hook_is_enabled_and_executable(self):
        self.assertEqual(git("config", "--get", "core.hooksPath").stdout.strip(), "scripts/githooks",
                         "run: git config core.hooksPath scripts/githooks")
        self.assertTrue(os.access(ROOT / "scripts" / "githooks" / "pre-commit", os.X_OK))

    def test_working_tree_is_free_of_key_shapes_and_of_any_value_from_dot_env(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "secret_scan.py"), "--tree"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_gitignore_comment_is_on_its_own_line(self):
        # gitignore has no trailing comments: "pattern  # note" silently becomes one literal pattern.
        for n, line in enumerate((ROOT / ".gitignore").read_text().splitlines(), 1):
            if not line.startswith("#"):
                self.assertIsNone(re.search(r"\s#", line), f".gitignore:{n} has a trailing comment")


if __name__ == "__main__":
    unittest.main()
