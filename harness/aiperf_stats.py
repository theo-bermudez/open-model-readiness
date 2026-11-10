"""Percentiles and per-request tables from AIPerf's per-request export (profile_export.jsonl).

Why this exists: AIPerf 0.13.0's summary shows p50/p90/p99 but no p95, and its export mixes the
warm-up and profiling phases. Tail latency (p95) is what a user feels, so we compute it ourselves
from the raw per-request records, profiling phase only. Stdlib only.

Usage:  python -m harness.aiperf_stats runs/<run>/aiperf      # writes runs/<run>/analysis/*
"""
import csv
import json
import sys
from pathlib import Path

QS = (50, 90, 95, 99)
# AIPerf metric tag -> why we report it. All times in ms, rates in tokens/s/user.
HEADLINE = [
    "time_to_first_token", "time_to_first_output_token", "inter_token_latency", "request_latency",
    "output_token_throughput_per_user", "e2e_output_token_throughput",
    "output_sequence_length", "reasoning_token_count", "output_token_count",
    "usage_completion_tokens", "input_sequence_length", "osl_mismatch_diff_pct",
]


def percentile(values, q):
    """q-th percentile with linear interpolation (the same as numpy's default)."""
    if not values:
        raise ValueError("percentile of an empty list is undefined")
    s = sorted(values)
    pos = (len(s) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def load_records(path, phase="profiling"):
    """One flat {metric: value} dict per request of the given phase. List-valued metrics are dropped."""
    rows = []
    for line in Path(path).read_text().splitlines():
        r = json.loads(line)
        if r["metadata"].get("benchmark_phase") != phase:
            continue
        rows.append({k: m["value"] for k, m in r["metrics"].items() if not isinstance(m["value"], list)})
    return rows


def summarize(rows, names):
    out = {}
    for name in names:
        vals = [r[name] for r in rows if name in r]
        out[name] = ({"n": len(vals), "min": min(vals), "max": max(vals),
                      **{f"p{q}": percentile(vals, q) for q in QS}} if vals else {"n": 0})
    return out


def sign_counts(values):
    return {"positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values),
            "zero": sum(v == 0 for v in values)}


def markdown_table(summary):
    lines = ["| metric | n | min | p50 | p90 | p95 | p99 | max |", "|---|---|---|---|---|---|---|---|"]
    for name, s in summary.items():
        if s["n"] == 0:
            lines.append(f"| {name} | 0 | not reported | | | | | |")
        else:
            lines.append(f"| {name} | {s['n']} | " + " | ".join(
                f"{s[k]:,.2f}" for k in ("min", "p50", "p90", "p95", "p99", "max")) + " |")
    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    aiperf_dir = Path(argv[0])
    rows = load_records(aiperf_dir / "profile_export.jsonl")
    out = aiperf_dir.parent / "analysis"
    out.mkdir(exist_ok=True)
    summary = summarize(rows, HEADLINE)
    (out / "stats.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (out / "stats.md").write_text(markdown_table(summary) + "\n")
    cols = sorted({k for r in rows for k in r})
    with (out / "per_request.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(markdown_table(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
