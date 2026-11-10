"""Load and validate models.yaml, so its labelling rules are enforced and not just documented.

Rules checked (each traces to a decision or hard rule in PLAN.md):
  - audit.as_of is a quoted ISO date; audit.kind is "retrospective" or "day0"
  - judge_budget_usd <= 5 (hard rule 4); probe_repeats >= 3 (probes run 3x)
  - hardware classes are exactly the ones runmeta knows
  - every column pairs served_by with hardware the way runmeta requires
  - a model with a hosted column says "hosted" in its label (hosted is labelled everywhere)
  - roles are unique
validate() takes a plain dict and returns a list of error strings (empty = OK), so it needs no
YAML library. Only load() imports PyYAML, which is installed from M3 on.
"""
import re
from pathlib import Path

from harness.runmeta import HARDWARE_CLASSES, validate_labels

MAX_JUDGE_BUDGET_USD = 5
MIN_PROBE_REPEATS = 3
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def validate(doc):
    errors = []
    audit = doc.get("audit") or {}
    as_of = audit.get("as_of")
    if not (isinstance(as_of, str) and ISO_DATE.fullmatch(as_of)):
        errors.append(f"audit.as_of must be a quoted ISO date string like \"2026-11-09\", got {as_of!r}")
    if audit.get("kind") not in ("retrospective", "day0"):
        errors.append(f"audit.kind must be 'retrospective' or 'day0', got {audit.get('kind')!r}")
    budget = audit.get("judge_budget_usd")
    if not isinstance(budget, (int, float)) or budget > MAX_JUDGE_BUDGET_USD:
        errors.append(f"audit.judge_budget_usd must be a number <= {MAX_JUDGE_BUDGET_USD}, got {budget!r}")
    repeats = audit.get("probe_repeats")
    if not isinstance(repeats, int) or repeats < MIN_PROBE_REPEATS:
        errors.append(f"audit.probe_repeats must be an integer >= {MIN_PROBE_REPEATS}, got {repeats!r}")

    if set(doc.get("hardware") or {}) != set(HARDWARE_CLASSES):
        errors.append(f"hardware must define exactly {sorted(HARDWARE_CLASSES)}")

    roles = {}
    for name, m in (doc.get("models") or {}).items():
        missing = [f for f in ("role", "display", "label", "columns") if f not in m]
        if missing:
            errors.append(f"model {name!r} is missing {missing}")
            continue
        if m["role"] in roles:
            errors.append(f"model {name!r} reuses role {m['role']!r} already used by {roles[m['role']]!r}")
        roles[m["role"]] = name
        for i, col in enumerate(m["columns"]):
            try:
                validate_labels(col.get("served_by"), col.get("hardware"))
            except ValueError as e:
                errors.append(f"model {name!r} column {i}: {e}")
        if any(c.get("served_by") == "nvidia-hosted" for c in m["columns"]) and "hosted" not in m["label"].lower():
            errors.append(f"model {name!r} has a hosted column, so its label must say 'hosted' (got {m['label']!r})")
    return errors


def load(path="models.yaml"):
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML is required to read models.yaml: install it into .venv first") from e
    return yaml.safe_load(Path(path).read_text())
