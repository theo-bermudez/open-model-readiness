# Human calibration protocol

No human labels have been fabricated or inferred from automated answers. Theo supplies approximately 20 labels before any calibrated-judge claim.

Select a deliberately mixed sample of correct, incorrect, incomplete and uncertain responses from the original local reliability probes. Hide mode and model identity where practical. Each row should contain a stable item_id, rubric_version, human_label (accept/reject/uncertain) and a short rationale. Keep sensitive examples private; publish only a reviewed aggregate.

Define accept as a usable answer satisfying the task-specific rubric. Count an empty or truncated answer as reject when a complete answer is required. Uncertain means the task or evidence is insufficient; do not force it into accept.

An automated judge should emit accept/reject/uncertain against the same rubric. Evaluate agreement, abstentions and false accepts (judge accepts a human-rejected response), with denominators. Re-grade for self-consistency separately; judge agreement with itself is not human calibration. Hold out some labels when tuning the rubric. No paid judge execution is authorized by the presence of a historical budget setting in models.yaml.

## Local comparison tool

`harness/calibration.py` is implemented and unit-tested. **No calibrated judge result exists yet.** It generates no labels and makes no API calls. Theo's labels and a permitted source of judge decisions are still required.

Use the header-only [`labels.template.csv`](labels.template.csv) for both files. Each row needs `item_id,rubric_version,label`; `notes` is optional and omitted from the output. The `label` values are exactly `accept`, `reject` or `uncertain`. IDs must refer to actual responses selected for this exercise, and the rubric version must match for each human/judge pair. Do not prefill human decisions with an assistant. Keep completed labels and response text in a private ignored run directory.

After Theo supplies the human file and the judge file exists:

```bash
.venv/bin/python -m harness.calibration \
  --human runs/<calibration-run>/human.csv \
  --judge runs/<calibration-run>/judge.csv \
  --output runs/<calibration-run>/calibration.json
```

The command rejects header-only templates, empty labels, duplicates, missing items, unsupported labels and mismatched rubric versions. The output contains aggregates and source-file SHA-256 hashes, not response text, item IDs or notes. Review the aggregate before publishing it.

False accepts are judge `accept` on human `reject`. The main denominator is **all human-rejected items**, including judge abstentions; a second rate uses only human-rejected items where the judge decided. Read both alongside decision coverage so abstention cannot masquerade as correctness. Agreement uses only determinate human labels with determinate judge decisions. Human `uncertain` is excluded from correctness denominators; judge `uncertain` is counted as abstention. A zero denominator produces `null`, never 0% or 100%.

This tool checks arithmetic and file consistency. It cannot authenticate label authorship, validate a rubric, or establish that a small sample generalizes. Unit-test fixtures are synthetic and are not project calibration results.
