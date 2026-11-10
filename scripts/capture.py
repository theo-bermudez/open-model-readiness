#!/usr/bin/env python3
"""Save raw, timestamped, hashed copies of the public pages and APIs our claims rest on.

Why: facts about fast-moving projects (versions, file sizes, merged PRs, model-card text) change
daily. Every figure in a report must trace to a source, and saving the exact bytes plus a UTC
timestamp and sha256 lets a reader (or us, three weeks later) see what the source said THEN.

Usage:  python scripts/capture.py evidence/m1/targets.tsv [--delay 1.0]
  targets file: one "name URL" per line (whitespace-separated); blank lines and # comments are ok.
  Raw bytes are saved next to the targets file. One line per fetch is appended to
  evidence/MANIFEST.tsv:  captured_utc  http_status  sha256  bytes  path  url

Notes
 - Non-200 answers are kept: an error page or a 404 is evidence too (for example a dead docs link).
 - Redirects are followed; the status recorded is the final one.
 - Requests carry a generic User-Agent and nothing else: no keys, no cookies, no personal details.
 - GitHub's unauthenticated search API allows roughly 10 requests a minute, so those URLs wait longer.
Exit codes: 0 all fetches got an HTTP answer, 1 at least one got none (network down), 2 bad targets file.
"""
import argparse
import hashlib
import http.client
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "evidence-capture/1"
MANIFEST_HEADER = "captured_utc\thttp_status\tsha256\tbytes\tpath\turl\n"


def fetch(url, timeout=60):
    """(status, body). status is an int, or "ERR" when no HTTP answer arrived at all."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:  # 404, 403, 429, ...: the body is still evidence
        return e.code, e.read()
    except (OSError, ValueError, http.client.HTTPException):  # DNS, refused, timeout, malformed URL
        return "ERR", b""


def delay_for(url, base):
    return 7.0 if "api.github.com/search" in url else base


def parse_targets(path):
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"{path}:{n}: expected 'name URL'")
        name, url = parts[0], parts[1].strip()
        if name in (".", "..") or name != Path(name).name:  # a name must not point outside its folder
            raise ValueError(f"{path}:{n}: unsafe name {name!r}")
        yield name, url


def main(argv=None):
    ap = argparse.ArgumentParser(description="Save raw, timestamped, hashed copies of public pages.")
    ap.add_argument("targets", help="file with one 'name URL' per line")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = ap.parse_args(argv)

    targets = Path(args.targets)
    try:
        items = list(parse_targets(targets))  # parse everything first: a bad line aborts before any network call
    except (ValueError, OSError) as e:
        print(f"capture: {e}", file=sys.stderr)
        return 2

    out_dir = targets.parent
    manifest = out_dir.parent / "MANIFEST.tsv"
    if not manifest.exists():
        manifest.write_text(MANIFEST_HEADER)

    errors = 0
    for i, (name, url) in enumerate(items):
        if i:
            time.sleep(delay_for(url, args.delay))
        status, body = fetch(url)
        rel = f"{out_dir.name}/{name}"
        if status == "ERR":
            errors += 1
            sha = "-"
        else:
            (out_dir / name).write_bytes(body)
            sha = hashlib.sha256(body).hexdigest()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with manifest.open("a") as f:
            f.write(f"{stamp}\t{status}\t{sha}\t{len(body)}\t{rel}\t{url}\n")
        print(f"{status!s:>4}  {len(body):>9,} B  {rel}")
    print(f"capture: {len(items)} targets, {errors} without an HTTP answer -> {manifest}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
