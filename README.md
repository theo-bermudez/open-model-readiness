# Open Model Readiness

**Can a developer trust the behavior behind a successful model request?** This project audits the path from model setup to usable answers: request settings, benchmark validity, developer friction and evidence-based readiness gates.

For developers integrating open models and product teams deciding what is ready to document or launch. The first release tests **Nemotron-3-Nano-4B Q4_K_M on an Apple M2 laptop with Homebrew Ollama 0.40.15 and AIPerf 0.13.0**. It is an independent, AI-assisted case study by Theo Bermudez, not NVIDIA production validation.

- **A requested mode can change before it reaches the server.** The tested AIPerf parser converts the string `"none"` to null; a purported thinking-OFF run still produced reasoning. Verify the serialized request and returned behavior before accepting benchmark labels.
- **Same seed does not mean same complete prompts.** The successful runs use the same conversation/turn order, but model-generated history changes later requests. Compare full request hashes, not just dataset IDs.
- **An HTTP success can contain no answer.** Tight output budgets can be consumed by reasoning. Gate on answer presence and finish reason as well as request errors.

[Project site](https://theo-bermudez.github.io/open-model-readiness/) · [Full report](https://theo-bermudez.github.io/open-model-readiness/report.html) · [Reproduce](RUNBOOK.md) · [Case study](articles/benchmarking-the-wrong-mode.md)

| Historical observation — not a causal comparison | ON · direct | OFF · proxy |
| --- | --- | --- |
| Client input tokens (median) | 2,617.00 | 1,244.50 |
| Server input tokens (median) | 2,197.50 | 1,510.00 |
| First token (median, seconds) | 12.73 | 5.02 |
| First answer (median, seconds) | 36.34 | 5.02 |
| Request latency (median, seconds) | 110.50 | 52.33 |
| Profiled requests | 20 | 20 |
| Length-limit stops | 3 | 0 |

The historical latency columns are **descriptive and confounded**, not a controlled mode speedup. These values derive from [results/m4.json](results/m4.json), including per-request hashes, settings, run IDs and source digests. The [maintained results](results/) also contain the NeMo integration and original reliability suite evidence. Raw dataset text is intentionally excluded from this public release.

## Get started without a model

Python 3.12 is the tested interpreter. The core harness and documentation builder use the standard library.

```bash
git clone https://github.com/theo-bermudez/open-model-readiness.git
cd open-model-readiness
git config core.hooksPath scripts/githooks
python3 -m unittest discover -s tests -t .
python3 scripts/build_public.py --check
```

No credentials or hosted API calls are needed. The NumPy cross-check and YAML validation tests skip when those optional dependencies are absent. To reproduce local inference, use the [runbook](RUNBOOK.md); model downloads are separate, explicit steps.

## Tested coverage

| Model | Runtime / precision | Hardware | Coverage |
| --- | --- | --- | --- |
| Nemotron-3-Nano-4B | Ollama 0.40.15 / Q4_K_M | Apple M2 · 8 GB | Tested: request semantics and small local workloads |
| Nemotron 3.5 Super VL | NVIDIA-hosted · text only planned | Undisclosed | Planned: endpoint access and budget required |
| Nemotron-3-Nano-4B | Ollama / vLLM / SGLang | Single T4 planned | Planned: GPU access required |
| Dory 1.0 4B | Runtime to be selected | Not run | Planned: independent runbook validation |

The local original reliability suite tested 6 cases with 3 repeats each: 18/18 objective checks passed. These are narrow fixture checks, not a representative reliability estimate. See [case outcomes and limits](https://theo-bermudez.github.io/open-model-readiness/report.html#original-reliability-probes).

## Readiness decision

**Ready for an instrumented local demonstration, with workarounds.** Require verified request semantics, explicit context and output budgets, a nonempty final answer, complete provenance and honest scope. **Not ready for a broad deployment recommendation:** representative quality evaluation, calibrated human labels, load/reliability testing and GPU/hosted comparisons are unfinished. See [readiness gates](https://theo-bermudez.github.io/open-model-readiness/report.html#readiness-gates).

## Repository guide

- `harness/`: existing metadata guards, AIPerf analysis, loopback reasoning proxy, request audit and matched replay.
- `results/`: reviewed aggregates and provenance; the maintained source for report, site and article numbers.
- `reports/`, `articles/`, `briefs/`: findings translated into technical and product decisions.
- `content/`, `site/`, `scripts/build_public.py`: maintained text, styles and deterministic static-site build.
- `upstream/`: feedback drafts only; nothing filed upstream.
- `ROADMAP.md`: tested, in-progress and planned work with exact dependencies.

## Reuse and limitations

See [LICENSE](LICENSE) for original project code and [ATTRIBUTION.md](ATTRIBUTION.md) for third-party boundaries. Models, datasets, upstream source snapshots and private research history are not redistributed. Prompt hashes permit exact local comparison; they do not reconstruct omitted dataset text. Small samples do not support population-level tail-latency or quality claims. The original local research history is preserved; the public history begins with a reviewed snapshot derived from it.

Evidence cutoff: **2026-11-10** · Release: **v0.1.0**. Build with `python3 scripts/build_public.py`; generated files should not be edited directly.
