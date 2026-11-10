"""Compare supplied human and judge labels; never generate labels or call APIs.

CSV columns: item_id,rubric_version,label (optional notes). Labels are exactly
accept, reject, or uncertain. Missing, duplicate, empty and unmatched labels
fail closed. Human uncertainty is excluded from correctness denominators;
judge uncertainty is an abstention, not an incorrect or correct prediction.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

LABELS = {"accept", "reject", "uncertain"}


def read_labels(path):
    """Return validated rows indexed by item ID; do not invent missing labels."""
    labels = {}
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"item_id", "rubric_version", "label"}.issubset(reader.fieldnames):
            raise ValueError("CSV must contain item_id,rubric_version,label columns")
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("duplicate CSV column")
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(k) is None for k in ("item_id", "rubric_version", "label")):
                raise ValueError(f"malformed CSV row at line {line}")
            item_id = row["item_id"].strip()
            rubric = row["rubric_version"].strip()
            label = row["label"].strip()
            if not item_id or not rubric:
                raise ValueError(f"missing item ID or rubric at line {line}")
            if label not in LABELS:
                raise ValueError(f"missing or unsupported label at line {line}")
            if item_id in labels:
                raise ValueError(f"duplicate item ID at line {line}")
            labels[item_id] = {"rubric_version": rubric, "label": label}
    if not labels:
        raise ValueError("no labels supplied; a blank template is not calibration evidence")
    return labels


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def compare_labels(human, judge):
    if not human or not judge:
        raise ValueError("both label sets must be nonempty")
    if set(human) != set(judge):
        raise ValueError(f"unmatched item IDs: {len(set(human) - set(judge))} missing judge labels; "
                         f"{len(set(judge) - set(human))} missing human labels")
    counts = Counter()
    rubrics = set()
    for item_id, h in human.items():
        j = judge[item_id]
        if h.get("label") not in LABELS or j.get("label") not in LABELS:
            raise ValueError("unsupported or missing label")
        if not h.get("rubric_version") or h["rubric_version"] != j.get("rubric_version"):
            raise ValueError("human/judge rubric versions must match for every item")
        rubrics.add(h["rubric_version"])
        counts[(h["label"], j["label"])] += 1
    determinate = sum(n for (h, _), n in counts.items() if h != "uncertain")
    decided = sum(n for (h, j), n in counts.items() if h != "uncertain" and j != "uncertain")
    rejected = sum(n for (h, _), n in counts.items() if h == "reject")
    rejected_decided = sum(n for (h, j), n in counts.items() if h == "reject" and j != "uncertain")
    agreements = counts[("accept", "accept")] + counts[("reject", "reject")]
    false_accepts = counts[("reject", "accept")]
    return {"schema_version": 1, "status": "computed_from_supplied_labels",
            "items": len(human), "rubric_versions": sorted(rubrics),
            "human_uncertain": len(human) - determinate,
            "judge_abstentions": sum(n for (_, j), n in counts.items() if j == "uncertain"),
            "judge_abstentions_on_determinate_human": determinate - decided,
            "decision_coverage": fraction(decided, determinate),
            "agreement_on_decided_items": fraction(agreements, decided),
            "false_accepts_over_human_rejects": fraction(false_accepts, rejected),
            "false_accepts_over_decided_human_rejects": fraction(false_accepts, rejected_decided),
            "confusion": {h: {j: counts[(h, j)] for j in sorted(LABELS)} for h in sorted(LABELS)},
            "limitations": "Agreement on supplied labels; this tool does not authenticate the label author or establish broad judge validity. Zero denominator produces null, not a perfect score. No judge API was called."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_labels(read_labels(args.human), read_labels(args.judge))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    result["source_sha256"] = {"human_csv": hashlib.sha256(args.human.read_bytes()).hexdigest(),
                               "judge_csv": hashlib.sha256(args.judge.read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
