#!/usr/bin/env python3
"""Block commits that contain API keys.

Why this exists: the project calls two keyed services (NVIDIA, Anthropic), and the tools it
wraps (AIPerf, NeMo Evaluator) record their own command lines and request logs into files we
commit. A key that lands in runs/ or a notebook is public the moment we push.

Three independent checks, so one blind spot doesn't leave a hole:
  1. File names: .env and .env.* (except .env.example) must never be committed.
  2. Key shapes: nvapi-..., sk-ant-..., hf_..., "Bearer <long token>".
  3. Exact-value canaries: every non-trivial value in .env is searched for verbatim, so a key
     in a format we don't know about is still caught.
Findings name the file and the rule (or the .env KEY NAME). They never print the secret.

Usage:
  python scripts/secret_scan.py --staged         # what pre-commit runs: scans what WOULD be committed
  python scripts/secret_scan.py --tree           # scans every non-ignored file in the working tree
  python scripts/secret_scan.py --files A B ...  # scans the given files
Environment: ENV_FILE (default ".env") is the file whose values are used as canaries.
Exit codes: 0 clean, 1 secret found, 2 could not scan.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SHAPES = {
    "nvidia-api-key": re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"),
    "anthropic-api-key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "huggingface-token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "bearer-token": re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/=-]{24,}"),
}
# Shorter values are placeholders ("changeme") and would match innocent text everywhere.
MIN_CANARY_LEN = 8


def is_env_file(path):
    name = Path(path).name
    return name != ".env.example" and (name == ".env" or name.startswith(".env."))


def load_canaries(env_file):
    """{KEY: value} for every entry in the env file that is long enough to be a real secret.

    Values stay inside this process: they are compared with `in`, never put on a command
    line (visible in `ps`) and never printed.
    """
    path = Path(env_file)
    if not path.is_file():
        return {}
    canaries = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if value[:1] in ("'", '"'):  # quoted: take what is between the quotes
            end = value.find(value[0], 1)
            value = value[1:end] if end != -1 else value[1:]
        else:  # unquoted: an inline "# comment" is not part of the value
            value = value.split(" #", 1)[0].strip()
        if len(value) >= MIN_CANARY_LEN:
            canaries[key] = value
    return canaries


def scan_text(label, text, canaries, env_name):
    """Findings for one file's text. Messages never contain the secret itself."""
    findings = [f"{label}: looks like a {name}" for name, rx in SHAPES.items() if rx.search(text)]
    findings += [f"{label}: contains the value of {key} from {env_name}"
                 for key, value in canaries.items() if value in text]
    return findings


def _git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_items():
    """(path, bytes) for what the index holds: that is what a commit would publish."""
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    for raw in filter(None, out.split(b"\0")):
        path = raw.decode()
        yield path, _git("show", f":{path}")


def tree_items():
    out = _git("ls-files", "-co", "--exclude-standard", "-z")
    for raw in filter(None, out.split(b"\0")):
        path = raw.decode()
        if Path(path).is_file():
            yield path, Path(path).read_bytes()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Block commits that contain API keys.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--tree", action="store_true")
    mode.add_argument("--files", nargs="+", metavar="FILE")
    args = ap.parse_args(argv)

    env_file = os.environ.get("ENV_FILE", ".env")
    canaries = load_canaries(env_file)
    env_name = Path(env_file).name
    findings, scanned = [], 0
    try:
        if args.staged:
            items = staged_items()
        elif args.tree:
            items = tree_items()
        else:
            items = ((f, Path(f).read_bytes()) for f in args.files)
        for path, data in items:
            scanned += 1
            if is_env_file(path):
                findings.append(f"{path}: env files must never be committed")
            findings += scan_text(path, data.decode("utf-8", "ignore"), canaries, env_name)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"secret_scan: could not scan: {type(e).__name__}: {getattr(e, 'filename', '') or e}",
              file=sys.stderr)
        return 2

    if findings:
        print("secret_scan: BLOCKED", *findings, sep="\n  ", file=sys.stderr)
        print("Remove the secret (pass keys through environment variables). "
              "If it was ever pushed anywhere, rotate the key.", file=sys.stderr)
        return 1
    print(f"secret_scan: clean ({scanned} files, {len(canaries)} .env canaries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
