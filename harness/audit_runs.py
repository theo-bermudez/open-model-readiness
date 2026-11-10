"""Publishable summaries from private AIPerf exports and original-fixture replay.

Filters warmups, joins raw responses to metrics by request ID, hashes prompts
without publishing their text, and keeps failed or invalid runs explicitly out
of comparisons. No inputs.json or raw dataset payloads are copied.

Run: python -m harness.audit_runs --runs runs --output results/m4.json
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import re

from harness.matched_replay import digest

ON = "20261110T045803Z_nemotron-3-nano-4b_ollama_laptop_aiperf"
OFF = "20261110T061636Z_nemotron-3-nano-4b_ollama_laptop_aiperf"
INVALID = "20261110T040845Z_nemotron-3-nano-4b_ollama_laptop_aiperf"
FAILED = "20261110T054444Z_nemotron-3-nano-4b_ollama_laptop_aiperf"
METRICS = ["request_latency", "time_to_first_token", "time_to_first_output_token",
           "input_sequence_length", "usage_prompt_tokens", "usage_completion_tokens",
           "reasoning_token_count", "output_token_count", "output_sequence_length",
           "usage_prompt_cache_read_tokens"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def stats(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values),
            "max": max(values)}


def raw_summary(record):
    """Read SSE JSON packets. A missing answer stays missing, never latency zero."""
    answer = reasoning = ""
    finish = []
    for response in record.get("responses", []):
        for packet in response.get("packets", []):
            if packet.get("name") != "data" or packet.get("value") == "[DONE]":
                continue
            value = json.loads(packet["value"])
            for choice in value.get("choices", []):
                delta = choice.get("delta", {})
                answer += delta.get("content") or ""
                reasoning += delta.get("reasoning") or ""
                if choice.get("finish_reason"):
                    finish.append(choice["finish_reason"])
    messages = record["payload"]["messages"]
    return {"prompt_sha256": digest(messages),
            "user_messages_sha256": digest([m for m in messages if m.get("role") == "user"]),
            "settings_sha256": digest({k: v for k, v in record["payload"].items() if k != "messages"}),
            "finish_reason": finish[-1] if finish else None,
            "answer_chars": len(answer), "reasoning_chars": len(reasoning),
            "empty_answer": not bool(answer.strip()), "reasoning_present": bool(reasoning)}


def audit_run(path):
    path = Path(path)
    out = {"run_id": path.name, "status": "excluded", "source_sha256": {}}
    meta = path / "meta.json"
    raw = path / "aiperf/profile_export_raw.jsonl"
    metrics = path / "aiperf/profile_export.jsonl"
    summary = path / "aiperf/profile_export_aiperf.json"
    for file in (meta, raw, metrics, summary):
        if file.exists():
            out["source_sha256"][str(file.relative_to(path.parent.parent))] = sha256(file)
    if not meta.exists():
        out["exclusion_reason"] = "missing meta.json"
        return out
    if not raw.exists() or not metrics.exists() or not summary.exists():
        out["exclusion_reason"] = "missing completed raw/metric/summary exports; no result inferred"
        return out
    metadata = json.loads(meta.read_text())
    exported = json.loads(summary.read_text())
    raw_rows, metric_rows = jsonl(raw), jsonl(metrics)
    out["raw_records"] = len(raw_rows)
    out["warmup_requests"] = sum(r["metadata"].get("benchmark_phase") == "warmup" for r in raw_rows)
    raw_rows = [r for r in raw_rows if r["metadata"].get("benchmark_phase") == "profiling"]
    metric_rows = [r for r in metric_rows if r["metadata"].get("benchmark_phase") == "profiling"]
    raw_ids = [r["metadata"]["x_request_id"] for r in raw_rows]
    metric_ids = [r["metadata"]["x_request_id"] for r in metric_rows]
    if len(set(raw_ids)) != len(raw_ids) or len(set(metric_ids)) != len(metric_ids) or set(raw_ids) != set(metric_ids):
        out["exclusion_reason"] = "raw/metric request IDs are duplicated or unmatched"
        return out
    if not exported.get("is_complete") or exported.get("was_cancelled") or not raw_rows:
        out["exclusion_reason"] = "incomplete, cancelled, or empty profiling run"
        return out
    if any(r.get("status") != 200 or r["metadata"].get("was_cancelled") for r in raw_rows):
        out["exclusion_reason"] = "failed or cancelled request in profiling run"
        return out
    if exported.get("error_summary") or exported.get("request_error_rate", {}).get("avg", 0) != 0:
        out["exclusion_reason"] = "summary reports request errors"
        return out
    if exported.get("request_count", {}).get("avg", len(raw_rows)) != len(raw_rows):
        out["exclusion_reason"] = "summary/raw profiling request counts differ"
        return out
    by_id = {r["metadata"]["x_request_id"]: r for r in metric_rows}
    raw_rows.sort(key=lambda r: r["metadata"]["request_start_ns"])
    requests = []
    for order, row in enumerate(raw_rows):
        values = by_id[row["metadata"]["x_request_id"]]["metrics"]
        requests.append({"order": order, "conversation_id": row["metadata"]["conversation_id"],
                         "turn_index": row["metadata"]["turn_index"], **raw_summary(row),
                         "metrics": {k: values[k]["value"] for k in METRICS if k in values}})
    out.update(status="descriptive_only", exclusion_reason=None, profiled_requests=len(requests),
               request_errors=0, http_statuses=dict(Counter(str(r["status"]) for r in raw_rows)),
               summary_error_rate_pct=exported.get("request_error_rate", {}).get("avg"),
               requests=requests, finish_reasons=dict(Counter(r["finish_reason"] for r in requests)),
               empty_answers=sum(r["empty_answer"] for r in requests),
               requests_with_reasoning=sum(r["reasoning_present"] for r in requests),
               metrics={k: {**stats(r["metrics"].get(k) for r in requests),
                            "unit": next((r["metrics"][k]["unit"] for r in metric_rows if k in r["metrics"]), None)} for k in METRICS},
               benchmark_duration_s=exported["benchmark_duration"]["avg"],
               wall_time_s=None,
               hardware_class=metadata["hardware_class"], engine=metadata["engine"], model=metadata["model"],
               settings={"max_tokens_values": sorted(set(r["payload"].get("max_tokens") for r in raw_rows)),
                         "temperature": raw_rows[0]["payload"].get("temperature"),
                         "top_p": raw_rows[0]["payload"].get("top_p"),
                         "model": raw_rows[0]["payload"].get("model"),
                         "reasoning_effort_in_client_payload": raw_rows[0]["payload"].get("reasoning_effort", "absent"),
                         "dataset": exported["input_config"].get("datasets"),
                         "tokenizer": exported["input_config"].get("tokenizer"),
                         "context": "4096 default in historical notes; no per-request override recorded",
                         "route": "local proxy forcing none" if path.name == OFF else "direct local OpenAI-compatible endpoint"})
    if path.name == INVALID:
        out.update(status="invalid_as_off", exclusion_reason="requested OFF serialized as null; all profiled responses contain reasoning; excluded from mode comparison")
    return out


def compare(on, off):
    if on.get("status") != "descriptive_only" or off.get("status") != "descriptive_only":
        return {"status": "excluded", "causal_speedup_supported": False,
                "explanation": "Both runs require complete validated raw exports."}
    if on.get("hardware_class") != off.get("hardware_class"):
        return {"status": "excluded", "causal_speedup_supported": False,
                "explanation": "Different hardware classes cannot enter an engine comparison."}
    a, b = on["requests"], off["requests"]
    full_a, full_b = [r["prompt_sha256"] for r in a], [r["prompt_sha256"] for r in b]
    return {"on_run": on["run_id"], "off_run": off["run_id"],
            "same_conversation_order": [(r["conversation_id"], r["turn_index"]) for r in a] == [(r["conversation_id"], r["turn_index"]) for r in b],
            "same_user_messages_order": [r["user_messages_sha256"] for r in a] == [r["user_messages_sha256"] for r in b],
            "matching_full_payloads": sum(x == y for x, y in zip(full_a, full_b)),
            "full_payload_intersection": len(set(full_a) & set(full_b)),
            "matched_full_payload_order": full_a == full_b,
            "causal_speedup_supported": False,
            "explanation": "Identical sampled conversation/turn order and user messages, but generated assistant history changes later payloads. Only first-turn payloads match. Separate runs also differ in route, cached tokens, sampling outcomes and run conditions; their latency ratio is not an isolated reasoning-mode effect."}


def audit_replay(path):
    path = Path(path)
    metadata = json.loads((path / "meta.json").read_text())
    rows = jsonl(path / "requests.jsonl")
    measured = [r for r in rows if r["phase"] == "profiling"]
    safe = [{k: v for k, v in r.items() if k != "chunks"} for r in measured]
    out = {"status": metadata["status"], "run_id": path.name, "design": metadata["design"],
           "settings": metadata["settings"], "fixtures": metadata["fixtures"],
           "warmup_requests": len(rows) - len(measured), "profiled_requests": len(measured),
           "wall_time_s": metadata["wall_time_s"], "timed_requests_total_s": sum(r["latency_ms"] for r in measured) / 1000,
           "environment": {"before": public_environment(metadata["before"]), "after": public_environment(metadata["after"])},
           "requests": safe, "by_mode": {},
           "source_sha256": {str(p.relative_to(path.parent.parent)): sha256(p) for p in [path / "meta.json", path / "requests.jsonl"]},
           "limitations": ["Four original short fixtures repeated three times; exact-answer checks are not a model-quality benchmark.",
                           "Native API microfixture, not an AIPerf ShareGPT rerun; no general speedup claim.",
                           "Every timed request has an identical same-mode warmup. Cache is retained and reported; no forced cache flush or service restart.",
                           "Counterbalanced order reduces order bias but does not eliminate thermal, scheduling, memory, or autocorrelation effects.",
                           "Client latency measures first nonempty streamed text. Native server token counts include reasoning and answer together; reasoning_chars is not a token count."]}
    for mode in ("on", "off"):
        group = [r for r in measured if r["mode"] == mode]
        out["by_mode"][mode] = {"requests": len(group),
            "exact_answer_passes": sum(r["exact_answer_pass"] for r in group),
            "empty_answers": sum(not r["answer"].strip() for r in group),
            "truncated": sum(r["finish_reason"] == "length" for r in group),
            "reasoning_present": sum(r["reasoning_present"] for r in group),
            "metrics": {key: stats(r.get(key) for r in group) for key in
                ["latency_ms", "ttft_ms", "first_answer_ms", "server_prompt_tokens", "server_cached_tokens", "server_completion_tokens", "server_load_ms", "server_decode_ms"]}}
    pairs = {}
    for r in measured:
        pairs.setdefault((r["fixture_id"], r["repeat"]), {})[r["mode"]] = r
    out["complete_matched_pairs"] = sum(set(v) == {"on", "off"} and v["on"]["prompt_sha256"] == v["off"]["prompt_sha256"] for v in pairs.values())
    out["pairs_with_equal_server_prompt_counts"] = sum(set(v) == {"on", "off"} and v["on"]["server_prompt_tokens"] == v["off"]["server_prompt_tokens"] for v in pairs.values())
    out["pairs_with_equal_cached_token_counts"] = sum(set(v) == {"on", "off"} and v["on"]["server_cached_tokens"] == v["off"]["server_cached_tokens"] for v in pairs.values())
    expected_pairs = len(metadata["fixtures"]) * metadata["repeats"]
    if metadata["status"] != "complete" or len(measured) != 2 * expected_pairs or out["complete_matched_pairs"] != expected_pairs:
        out["status"] = "excluded_incomplete_or_unmatched"
    return out


def public_environment(snapshot):
    """Allowlist observations; omit battery identifiers and service-expiry data."""
    if not snapshot:
        return {"status": "unavailable"}
    swap = re.search(r"total = ([\d.]+)M\s+used = ([\d.]+)M\s+free = ([\d.]+)M", snapshot.get("swap") or "")
    power = snapshot.get("power") or ""
    return {"timestamp_utc": snapshot["timestamp_utc"], "os": snapshot["os"],
            "python": snapshot["python"], "ollama": snapshot["ollama"],
            "power_source": "AC" if "AC Power" in power else "battery" if "Battery Power" in power else "unknown",
            "swap_reported_M": dict(zip(("total", "used", "free"), map(float, swap.groups()))) if swap else None,
            "thermal_observation": snapshot.get("thermal"),
            "loaded_models": [{k: model[k] for k in ("name", "digest", "context_length", "runner", "size_vram") if k in model}
                              for model in snapshot.get("models", {}).get("models", [])]}


def cap_check(runs):
    path = runs / "20261110T015629Z_nemotron-3-nano-4b_ollama_laptop_captest"
    cases = []
    for file in sorted(path.glob("*.json")):
        if file.name == "meta.json":
            continue
        value = json.loads(file.read_text())
        native = "native" in file.name
        message = value.get("message", {}) if native else value["choices"][0]["message"]
        cases.append({"case": file.stem, "requested_cap": 64,
            "requested_cap_field": "num_predict" if native else "max_completion_tokens" if "max_completion_tokens" in file.name else "max_tokens",
            "mode": "off" if "thinking-off" in file.name else "on",
            "server_completion_tokens": value.get("eval_count") if native else value["usage"]["completion_tokens"],
            "finish_reason": value.get("done_reason") if native else value["choices"][0].get("finish_reason"),
            "empty_answer": not bool(message.get("content", "").strip()),
            "reasoning_present": bool(message.get("thinking") or message.get("reasoning")),
            "source_path": str(file), "source_sha256": sha256(file)})
    return {"run_id": path.name, "capture_date": "2026-11-10", "status": "historical_observation",
            "conditions": "One prompt per non-streaming case, temperature 0, cap 64; not a controlled speed comparison. Requested settings verified from saved case names and summary.txt.",
            "cases": cases, "source_sha256": {str(p): sha256(p) for p in [path / "meta.json", path / "summary.txt"] if p.exists()}}


def installed_checks():
    """Reproduce parsing without requests, upgrades, or environment mutation."""
    try:
        import aiperf
        from aiperf.config.flags.cli_config import CLIConfig
        from aiperf.config.loader.parsing import coerce_value
        from importlib.metadata import version
    except ImportError:
        return {"status": "unavailable", "reason": "AIPerf is not installed; do not infer parser behavior"}, {}
    package = Path(aiperf.__file__).parent
    value = CLIConfig(model_names=["nemotron-3-nano:4b-q4_K_M"], extra_inputs='{"reasoning_effort":"none"}')
    parser = {"status": "reproduced", "capture_date": datetime.now(timezone.utc).date().isoformat(),
              "aiperf_version": version("aiperf"), "coerce_value_none": coerce_value("none"),
              "json_first_parse": value.extra_inputs,
              "config_roundtrip": CLIConfig.model_validate(value.model_dump()).extra_inputs,
              "reproduction": "from aiperf.config.flags.cli_config import CLIConfig; c = CLIConfig(model_names=['nemotron-3-nano:4b-q4_K_M'], extra_inputs='{\"reasoning_effort\":\"none\"}'); print(c.extra_inputs); print(CLIConfig.model_validate(c.model_dump()).extra_inputs)",
              "source_sha256": {"aiperf/config/loader/parsing.py": sha256(package / "config/loader/parsing.py")}}
    sources = ["dataset/dataset_samplers.py", "dataset/loader/sharegpt.py", "workers/session_manager.py", "workers/worker.py", "endpoints/base_endpoint.py"]
    sampler = {"aiperf_version": version("aiperf"),
               "findings": ["ShareGPT loader get_preferred_sampling_strategy returns SEQUENTIAL (sharegpt.py:236).",
                            "SequentialSampler.next_conversation_id advances through a fixed conversation list (dataset_samplers.py:46).",
                            "UserSession.should_store_response retains live replies in DELTAS_WITHOUT_RESPONSES; store_response appends the assistant turn (session_manager.py:225-237).",
                            "Worker stores the built assistant turn after each response (worker.py:1768-1780); endpoint builds it from response content/reasoning (base_endpoint.py:137-184).",
                            "Observed raw exports have equal conversation/turn and user-message sequences; generated assistant history makes later full payloads unequal."],
               "source_sha256": {"aiperf/" + p: sha256(package / p) for p in sources}}
    return parser, sampler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=Path("runs"))
    ap.add_argument("--output", type=Path, default=Path("results/m4.json"))
    args = ap.parse_args(argv)
    runs = [audit_run(args.runs / name) for name in [ON, OFF, INVALID, FAILED]]
    replay = sorted(args.runs.glob("*_matched"))
    output = {"schema_version": 1, "evidence_cutoff_utc": datetime.now(timezone.utc).isoformat(),
              "historical_runs": runs, "historical_comparison": compare(runs[0], runs[1]),
              "controlled_replay": audit_replay(replay[-1]) if replay else {"status": "not_run"}}
    output["parser_check"], output["sampler_check"] = installed_checks()
    output["cap_check"] = cap_check(args.runs)
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
