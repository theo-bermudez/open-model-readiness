"""Small original-fixture, paired reasoning-mode check against local Ollama.

No model downloads, remote calls, or service changes. Each timed request follows
an identical same-mode warmup. Both modes use native streaming /api/chat. This is
a warm-cache semantic microfixture, not a representative throughput benchmark.

Run: python -m harness.matched_replay --output runs/<new-run-id>
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
from urllib.request import Request, urlopen

MODEL = "nemotron-3-nano:4b-q4_K_M"
BASE = "http://127.0.0.1:11434"
OPTIONS = {"num_ctx": 4096, "num_predict": 256, "temperature": 0,
           "top_p": 1, "seed": 42}
# Original, project-authored text; exact-answer checks are deliberately narrow.
FIXTURES = [
    {"id": "echo", "prompt": "Reply with exactly the word READY and nothing else.", "expected": "READY"},
    {"id": "arithmetic", "prompt": "What is 7 plus 5? Reply with only the integer.", "expected": "12"},
    {"id": "extract", "prompt": "The reference code is B42. Reply with only the reference code.", "expected": "B42"},
    {"id": "classify", "prompt": "Classify the integer 8 as even or odd. Reply with only the lowercase label.", "expected": "even"},
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def schedule(repeats=3):
    """Alternate which mode goes first within each exact-prompt pair."""
    for repeat in range(repeats):
        for index, fixture in enumerate(FIXTURES):
            modes = ("on", "off") if (repeat + index) % 2 == 0 else ("off", "on")
            for mode in modes:
                yield repeat, fixture, mode


def get(path):
    with urlopen(BASE + path, timeout=15) as response:
        return json.load(response)


def snapshot():
    def command(argv):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "os": platform.platform(), "python": platform.python_version(),
            "ollama": get("/api/version"), "models": get("/api/ps"),
            "swap": command(["sysctl", "vm.swapusage"]),
            "thermal": command(["pmset", "-g", "therm"]),
            "power": command(["pmset", "-g", "batt"])}


def request(fixture, mode):
    messages = [{"role": "user", "content": fixture["prompt"]}]
    payload = {"model": MODEL, "messages": messages, "think": mode == "on",
               "stream": True, "options": OPTIONS, "keep_alive": "10m"}
    req = Request(BASE + "/api/chat", data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"})
    start = time.perf_counter_ns()
    first_token = first_answer = None
    answer, reasoning, chunks = "", "", []
    final = None
    with urlopen(req, timeout=120) as response:
        for line in response:
            now = (time.perf_counter_ns() - start) / 1e6
            value = json.loads(line)
            chunks.append({"elapsed_ms": now, "response": value})
            msg = value.get("message", {})
            content, thinking = msg.get("content", ""), msg.get("thinking", "")
            if (content or thinking) and first_token is None:
                first_token = now
            if content and first_answer is None:
                first_answer = now
            answer += content
            reasoning += thinking
            if value.get("done"):
                final = value
    if final is None:
        raise ValueError("stream ended without done=true")
    return {"fixture_id": fixture["id"], "mode": mode,
            "prompt_sha256": digest(messages), "payload_sha256": digest(payload),
            "latency_ms": (time.perf_counter_ns() - start) / 1e6,
            "ttft_ms": first_token, "first_answer_ms": first_answer,
            "answer": answer, "reasoning_present": bool(reasoning),
            "reasoning_chars": len(reasoning), "answer_chars": len(answer),
            "exact_answer_pass": answer.strip() == fixture["expected"],
            "finish_reason": final.get("done_reason"),
            "server_prompt_tokens": final.get("prompt_eval_count"),
            "server_cached_tokens": final.get("prompt_eval_cached_count"),
            "server_completion_tokens": final.get("eval_count"),
            "server_load_ms": final.get("load_duration", 0) / 1e6,
            "server_total_ms": final.get("total_duration", 0) / 1e6,
            "server_decode_ms": final.get("eval_duration", 0) / 1e6,
            "chunks": chunks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 4))
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    metadata = {"schema_version": 1, "kind": "matched-native-replay",
                "model": {"id": MODEL, "quantization": "Q4_K_M"},
                "hardware_class": "laptop", "served_by": "self",
                "engine": {"name": "ollama", "version": get("/api/version")["version"]},
                "settings": OPTIONS, "fixtures": FIXTURES, "repeats": args.repeats,
                "design": "Each measured request follows an identical same-mode warmup; modes alternate first position by fixture and repeat; sequential native streaming requests; no service restart or cache flush.",
                "before": snapshot(), "status": "running"}
    meta_path = args.output / "meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    try:
        with (args.output / "requests.jsonl").open("w") as file:
            for repeat, fixture, mode in schedule(args.repeats):
                for phase in ("warmup", "profiling"):
                    result = request(fixture, mode)
                    result.update(repeat=repeat, phase=phase)
                    file.write(json.dumps(result) + "\n")
                    file.flush()
                    print(json.dumps({k: result[k] for k in ["fixture_id", "mode", "repeat", "phase", "latency_ms", "exact_answer_pass", "finish_reason"]}), flush=True)
        metadata["status"] = "complete"
    except Exception as error:
        metadata.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        metadata["wall_time_s"] = time.perf_counter() - started
        try:
            metadata["after"] = snapshot()
        except Exception as error:
            metadata["after"] = None
            metadata["environment_capture_error_type"] = type(error).__name__
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
