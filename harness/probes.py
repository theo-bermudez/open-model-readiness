"""Six original deterministic reliability probes, three sequential repeats.

Uses the existing local Ollama model via native streaming /api/chat, thinking
OFF, explicit context 4096 and output cap 256. No retries, network datasets,
judge APIs or tool execution. Raw responses remain in an ignored run directory.

Run: python -m harness.probes --output runs/<UTC-run-id>_laptop_probes
Summarize: python -m harness.probes --summarize runs/<run> --summary results/probes.json
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

from harness.audit_runs import jsonl, sha256, stats, public_environment
from harness.matched_replay import MODEL, OPTIONS, request, snapshot


def strict_json(text):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError("non-standard JSON constant")
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def score(probe, answer):
    if probe["scoring"] == "exact":
        return answer.strip() == probe["expected"]
    if probe["scoring"] == "json_exact":
        try:
            actual, expected = strict_json(answer), strict_json(probe["expected"])
        except (ValueError, TypeError):
            return False
        # Canonical serialization preserves JSON types: true does not equal 1.
        return json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(expected, sort_keys=True, separators=(",", ":"))
    raise ValueError("unknown scorer")


def load_suite(path):
    rows = jsonl(path)
    ids = set()
    if not rows:
        raise ValueError("empty probe suite")
    for row in rows:
        if not all(isinstance(row.get(k), str) and row[k] for k in ("id", "category", "prompt", "scoring", "expected", "coverage")):
            raise ValueError("probe fields must be nonempty strings")
        if row["id"] in ids:
            raise ValueError("duplicate probe ID")
        ids.add(row["id"])
        if row["scoring"] not in {"exact", "json_exact"}:
            raise ValueError("unknown scorer")
        if row["scoring"] == "json_exact":
            strict_json(row["expected"])
    return rows


def summarize(path):
    path = Path(path)
    meta = json.loads((path / "meta.json").read_text())
    suite = json.loads((path / "suite.json").read_text())
    records = jsonl(path / "requests.jsonl")
    expected = {(p["id"], repeat) for p in suite for repeat in range(3)}
    observed = [(r["fixture_id"], r["repeat"]) for r in records]
    complete = (meta["status"] == "complete" and len(set(observed)) == len(observed) and set(observed) == expected)
    safe = []
    for row in records:
        safe.append({k: row.get(k) for k in ["fixture_id", "repeat", "prompt_sha256", "payload_sha256", "passed", "request_succeeded", "error_type", "finish_reason", "answer_chars", "reasoning_present", "server_prompt_tokens", "server_cached_tokens", "server_completion_tokens", "latency_ms"]} | {"answer": row.get("answer", ""), "answer_sha256": hashlib.sha256(row.get("answer", "").encode()).hexdigest()})
    cases = []
    for probe in suite:
        group = [r for r in records if r["fixture_id"] == probe["id"]]
        passes = [int(r["passed"]) for r in group]
        cases.append({"id": probe["id"], "category": probe["category"], "coverage": probe["coverage"],
            "scoring": probe["scoring"], "repeats": len(group), "passes": sum(passes),
            "pass_rate": sum(passes) / len(passes) if passes else None,
            "pass_population_variance": statistics.pvariance(passes) if passes else None,
            "request_errors": sum(not r["request_succeeded"] for r in group),
            "empty_answers": sum(not r.get("answer", "").strip() for r in group),
            "length_finishes": sum(r.get("finish_reason") == "length" for r in group),
            "unique_answer_hashes": len({hashlib.sha256(r.get("answer", "").encode()).hexdigest() for r in group}),
            "metrics": {k: stats(r.get(k) for r in group) for k in ["latency_ms", "server_prompt_tokens", "server_completion_tokens"]}})
    return {"schema_version": 1, "evidence_cutoff_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": path.name, "status": "complete_original_probe_suite" if complete else "incomplete_excluded",
            "model": meta["model"], "engine": {"name": "ollama", **meta["before"]["ollama"]}, "hardware_class": "laptop", "served_by": "self",
            "settings": meta["settings"] | {"stream": True, "concurrency": 1, "repeats": 3, "retry_count": 0},
            "environment": {"before": public_environment(meta["before"]), "after": public_environment(meta.get("after"))},
            "measured_requests": len(records), "passes": sum(r["passed"] for r in records),
            "request_errors": sum(not r["request_succeeded"] for r in records),
            "wall_time_s": meta["wall_time_s"], "cases": cases, "requests": safe,
            "hash_definitions": {"prompt_sha256": "SHA-256 of the JSON messages array with sorted keys, compact separators and unescaped Unicode encoded as UTF-8", "answer_sha256": "SHA-256 of exact answer text encoded as UTF-8"},
            "source_sha256": {str(file): sha256(file) for file in [path / "meta.json", path / "suite.json", path / "requests.jsonl"]},
            "limitations": ["Six project-authored fixtures, three repeats each; not a representative model-quality estimate.",
                            "Tool-selection probe checks a JSON selection format, not native tools/function calling or execution.",
                            "Context probe is a short inventory lookup below the configured context limit, not a long-context benchmark.",
                            "Supplied-document abstention is one controlled missing-fact case, not a general hallucination or safety test.",
                            "Fixed order, retained cache, no separately measured warmups; timing is descriptive and not an engine or mode comparison.",
                            "Population variance summarizes these three binary outcomes only; zero observed variance does not establish reliability beyond this fixture."]}


def run(output, suite_path):
    suite = load_suite(suite_path)
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    meta = {"schema_version": 1, "kind": "original-reliability-probes", "status": "running",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "before": snapshot(),
            "model": MODEL, "hardware_class": "laptop", "settings": OPTIONS | {"think": False},
            "suite_sha256": sha256(suite_path), "repeats": 3, "warmups": 0, "retries": 0}
    (output / "suite.json").write_text(json.dumps(suite, indent=2) + "\n")
    (output / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    try:
        with (output / "requests.jsonl").open("w") as file:
            for repeat in range(3):
                for probe in suite:
                    try:
                        row = request(probe, "off")
                        row["request_succeeded"] = True
                        row["passed"] = score(probe, row["answer"]) and row["finish_reason"] == "stop"
                    except Exception as error:
                        row = {"fixture_id": probe["id"], "request_succeeded": False,
                               "passed": False, "error_type": type(error).__name__}
                    row.update(repeat=repeat, phase="profiling")
                    file.write(json.dumps(row) + "\n")
                    file.flush()
                    print(json.dumps({k: row.get(k) for k in ["fixture_id", "repeat", "passed", "finish_reason", "error_type"]}), flush=True)
                    if not row["request_succeeded"]:
                        meta["status"] = "failed"
                        return 1  # preserve failure; never retry an unchanged transport failure
        meta["status"] = "complete"
    finally:
        meta["wall_time_s"] = time.perf_counter() - start
        try:
            meta["after"] = snapshot()
        except Exception:
            meta["after"] = None
        (output / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("probes.jsonl"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summarize", type=Path)
    parser.add_argument("--summary", type=Path, default=Path("results/probes.json"))
    args = parser.parse_args(argv)
    if args.summarize:
        result = summarize(args.summarize)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(str(args.summary))
        return 0 if result["status"] == "complete_original_probe_suite" else 1
    if args.output is None:
        parser.error("--output is required to run probes")
    return run(args.output, args.suite)


if __name__ == "__main__":
    raise SystemExit(main())
