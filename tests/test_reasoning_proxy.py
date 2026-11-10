"""Tests for harness/reasoning_proxy.py against a fake Ollama upstream."""
import http.client
import http.server
import json
import threading
import time
import unittest

from harness import reasoning_proxy as P


class FakeOllama(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen = []

    def log_message(self, *a):
        pass

    def _record(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        FakeOllama.seen.append((self.command, self.path, body))
        return body

    def do_GET(self):
        self._record()
        out = b'{"version":"fake"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        body = self._record()
        if b'"stream": true' in body or b'"stream":true' in body:  # chunked SSE with a pause between chunks
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i, part in enumerate((b"data: first\n\n", b"data: second\n\n")):
                if i:
                    time.sleep(0.8)
                self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            return
        out = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


class RewriteBody(unittest.TestCase):
    def test_sets_none_when_absent_or_null_and_keeps_every_other_field(self):
        for src in ({"model": "m", "stream": True}, {"model": "m", "stream": True, "reasoning_effort": None}):
            out = json.loads(P.rewrite_body("/v1/chat/completions", json.dumps(src).encode()))
            self.assertEqual(out, {"model": "m", "stream": True, "reasoning_effort": "none"})

    def test_an_explicit_value_is_kept_byte_for_byte(self):
        body = b'{"reasoning_effort": "low"}'
        self.assertEqual(P.rewrite_body("/v1/chat/completions", body), body)

    def test_other_paths_and_non_json_bodies_are_untouched(self):
        body = b'{"model":"m"}'
        self.assertEqual(P.rewrite_body("/api/chat", body), body)
        self.assertEqual(P.rewrite_body("/v1/completions", body), body)
        for junk in (b"not json", b"[1,2]", b""):
            self.assertEqual(P.rewrite_body("/v1/chat/completions", junk), junk)

    def test_query_strings_do_not_hide_the_chat_path(self):
        out = json.loads(P.rewrite_body("/v1/chat/completions?x=1", b'{"a":1}'))
        self.assertEqual(out["reasoning_effort"], "none")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        FakeOllama.seen = []
        up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        self.up_port = serve(up)
        self.addCleanup(up.server_close)
        self.addCleanup(up.shutdown)
        proxy = P.make_server(port=0, upstream=("127.0.0.1", self.up_port))
        self.port = serve(proxy)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)

    def request(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=body, headers={"Content-Type": "application/json"})
        return c, c.getresponse()

    def test_chat_request_reaches_upstream_with_reasoning_effort_none(self):
        c, r = self.request("POST", "/v1/chat/completions", json.dumps({"model": "m", "reasoning_effort": None}))
        self.assertEqual((r.status, r.read()), (200, b'{"ok":true}'))
        c.close()
        sent = json.loads(FakeOllama.seen[0][2])
        self.assertEqual(sent, {"model": "m", "reasoning_effort": "none"})

    def test_everything_else_is_forwarded_byte_for_byte(self):
        c, r = self.request("POST", "/api/chat", b'{"model": "m",  "x":1}')
        r.read()
        c.close()
        self.assertEqual(FakeOllama.seen[0], ("POST", "/api/chat", b'{"model": "m",  "x":1}'))
        c, r = self.request("GET", "/api/version")
        self.assertEqual((r.status, r.read()), (200, b'{"version":"fake"}'))
        c.close()

    def test_a_streamed_response_arrives_incrementally(self):
        t0 = time.time()
        c, r = self.request("POST", "/v1/chat/completions", json.dumps({"model": "m", "stream": True}))
        first = r.read1(100)
        t_first = time.time() - t0
        rest = r.read()
        c.close()
        self.assertIn(b"data: first", first)
        self.assertLess(t_first, 0.6, "first chunk must not wait for the whole stream")
        self.assertEqual((first + rest).count(b"data:"), 2)
        self.assertEqual(r.getheader("Content-Type"), "text/event-stream")

    def test_unreachable_upstream_is_a_502_not_a_hang(self):
        proxy = P.make_server(port=0, upstream=("127.0.0.1", 1))
        port = serve(proxy)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/api/version")
        self.assertEqual(c.getresponse().status, 502)
        c.close()


class Safety(unittest.TestCase):
    def test_it_refuses_to_listen_on_a_non_loopback_address(self):
        with self.assertRaises(ValueError):
            P.make_server(host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
