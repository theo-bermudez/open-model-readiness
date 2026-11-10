"""Streaming passthrough proxy that forces thinking OFF on Ollama's OpenAI-compatible chat endpoint.

Why: AIPerf 0.13.0 coerces the string "none" to null in --extra-inputs
(aiperf/config/loader/parsing.py:155), so it cannot send reasoning_effort="none". Ollama does honour
that field, so this proxy sits between AIPerf and Ollama and sets it. Only POST /v1/chat/completions
JSON bodies change (reasoning_effort is set to "none" when absent or null; an explicit non-null value is
kept). Everything else is forwarded byte-for-byte. Request bodies are never logged. Stdlib only.

Run:   python -m harness.reasoning_proxy            # 127.0.0.1:11435 -> 127.0.0.1:11434
Point AIPerf at http://127.0.0.1:11435 and label the run "thinking OFF via proxy".
"""
import argparse
import http.client
import http.server
import json
import sys
from urllib.parse import urlsplit

CHAT_PATH = "/v1/chat/completions"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
# Hop-by-hop headers describe one connection, not the message, so a proxy must not forward them.
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade"}


def rewrite_body(path, body):
    """Return the request body to forward: only chat-completions JSON objects are modified."""
    if urlsplit(path).path != CHAT_PATH:
        return body
    try:
        obj = json.loads(body)
    except ValueError:
        return body
    if not isinstance(obj, dict) or obj.get("reasoning_effort") is not None:
        return body
    obj["reasoning_effort"] = "none"
    return json.dumps(obj).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.0: the response ends when the connection closes, so streamed (SSE) bodies need no chunk framing.
    protocol_version = "HTTP/1.0"
    upstream = ("127.0.0.1", 11434)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = rewrite_body(self.path, self.rfile.read(length) if length else b"")
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {"host", "content-length"}}
        if body or self.command in ("POST", "PUT", "PATCH"):
            headers["Content-Length"] = str(len(body))
        try:
            conn = http.client.HTTPConnection(*self.upstream, timeout=600)
            conn.request(self.command, self.path, body=body or None, headers=headers)
            resp = conn.getresponse()
        except OSError:
            self.send_error(502, "upstream unreachable")
            return
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.end_headers()
        try:
            while self.command != "HEAD":
                chunk = resp.read1(65536)  # returns as soon as any bytes arrive: keeps streaming streaming
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away mid-stream
        finally:
            conn.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _proxy

    def log_message(self, *args):  # request lines can carry prompts: stay silent
        pass


def make_server(host="127.0.0.1", port=11435, upstream=("127.0.0.1", 11434)):
    if host not in LOOPBACK:
        raise ValueError(f"refusing to listen on {host!r}: this proxy rewrites requests and is loopback-only")
    handler = type("BoundHandler", (Handler,), {"upstream": upstream})
    return http.server.ThreadingHTTPServer((host, port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inject reasoning_effort=none into Ollama /v1/chat/completions.")
    ap.add_argument("--port", type=int, default=11435)
    ap.add_argument("--upstream-port", type=int, default=11434)
    a = ap.parse_args(argv)
    server = make_server(port=a.port, upstream=("127.0.0.1", a.upstream_port))
    print(f"reasoning_proxy: http://127.0.0.1:{a.port} -> http://127.0.0.1:{a.upstream_port} "
          f"(reasoning_effort=none on {CHAT_PATH}); Ctrl-C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
