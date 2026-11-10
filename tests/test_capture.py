"""Tests for scripts/capture.py: raw, timestamped, hashed copies of the pages our claims rest on."""
import contextlib
import functools
import hashlib
import http.server
import io
import tempfile
import threading
import unittest
from pathlib import Path

from scripts import capture

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / ".scratch"
BODY = b'{"stars": 123}\n'


class Handler(http.server.SimpleHTTPRequestHandler):
    seen_headers = []

    def do_GET(self):
        Handler.seen_headers.append(dict(self.headers))
        super().do_GET()

    def log_message(self, *args):  # keep test output quiet
        pass


class CaptureTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        site = self.root / "site"
        site.mkdir()
        (site / "ok.json").write_bytes(BODY)
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(site)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"
        Handler.seen_headers = []
        self.evidence = self.root / "evidence"
        (self.evidence / "m1").mkdir(parents=True)
        self.targets = self.evidence / "m1" / "targets.tsv"
        self.manifest = self.evidence / "MANIFEST.tsv"

    def capture(self, targets_text):
        self.targets.write_text(targets_text)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return capture.main([str(self.targets), "--delay", "0"])

    def manifest_rows(self):
        lines = self.manifest.read_text().splitlines()
        return lines[0], [ln.split("\t") for ln in lines[1:]]

    def test_saves_raw_bytes_and_a_manifest_row_with_hash_size_and_url(self):
        code = self.capture(f"# a comment\n\nok.json {self.base}/ok.json\n")
        self.assertEqual(code, 0)
        self.assertEqual((self.evidence / "m1" / "ok.json").read_bytes(), BODY)
        header, rows = self.manifest_rows()
        self.assertEqual(header, "captured_utc\thttp_status\tsha256\tbytes\tpath\turl")
        ts, status, sha, size, path, url = rows[0]
        self.assertRegex(ts, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual((status, size, path), ("200", str(len(BODY)), "m1/ok.json"))
        self.assertEqual(sha, hashlib.sha256(BODY).hexdigest())
        self.assertEqual(url, f"{self.base}/ok.json")

    def test_error_pages_are_kept_as_evidence_and_are_not_fatal(self):
        code = self.capture(f"gone.html {self.base}/nope.html\nok.json {self.base}/ok.json\n")
        self.assertEqual(code, 0)
        _, rows = self.manifest_rows()
        self.assertEqual([r[1] for r in rows], ["404", "200"])
        self.assertTrue((self.evidence / "m1" / "gone.html").exists())

    def test_unreachable_host_is_recorded_as_ERR_and_the_run_continues(self):
        code = self.capture(f"dead.json http://127.0.0.1:1/x\nok.json {self.base}/ok.json\n")
        self.assertEqual(code, 1)  # non-zero so a dead network is noticed
        _, rows = self.manifest_rows()
        self.assertEqual([r[1] for r in rows], ["ERR", "200"])
        self.assertFalse((self.evidence / "m1" / "dead.json").exists())  # nothing fabricated

    def test_unsafe_names_abort_before_any_network_call(self):
        code = self.capture(f"ok.json {self.base}/ok.json\n../evil {self.base}/ok.json\n")
        self.assertEqual(code, 2)
        self.assertEqual(Handler.seen_headers, [])
        self.assertFalse(self.manifest.exists())
        self.assertFalse((self.evidence / "evil").exists())

    def test_requests_carry_only_a_generic_user_agent(self):
        self.capture(f"ok.json {self.base}/ok.json\n")
        headers = {k.lower(): v for k, v in Handler.seen_headers[0].items()}
        self.assertTrue(headers["user-agent"].startswith("evidence-capture"))
        for forbidden in ("authorization", "cookie", "x-api-key", "from"):
            self.assertNotIn(forbidden, headers)

    def test_second_run_appends_without_a_second_header(self):
        self.capture(f"ok.json {self.base}/ok.json\n")
        self.capture(f"ok.json {self.base}/ok.json\n")
        lines = self.manifest.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(sum(ln.startswith("captured_utc") for ln in lines), 1)

    def test_github_search_gets_a_longer_wait_for_its_rate_limit(self):
        self.assertEqual(capture.delay_for("https://api.github.com/search/issues?q=x", 1.0), 7.0)
        self.assertEqual(capture.delay_for("https://api.github.com/repos/o/r", 1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
