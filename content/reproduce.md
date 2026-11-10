# Reproduce the checks

[Overview]({{SITE}}) · [Full report]({{SITE}}report.html) · [Code]({{REPO}})

## 1. Verify the published artifact without inference

Use Python 3.12, the tested interpreter. No API keys are required.

```bash
git clone https://github.com/theo-bermudez/open-model-readiness.git
cd open-model-readiness
git config core.hooksPath scripts/githooks
python3 -m unittest discover -s tests -t .
python3 scripts/build_public.py --check
python3 scripts/check_site.py
```

The core tests are standard-library-only. Optional YAML/NumPy checks skip when their dependencies are absent. `scripts/test.sh` uses the project venv when available, otherwise `python3`. A clean scan is necessary but does not establish dataset redistribution rights.

## 2. Inspect evidence before comparing results

Open `results/m4.json`. It preserves run IDs, request counts, warmup exclusion, generation settings, prompt hashes, finish reasons and file digests. Historical runs with mismatched full requests remain descriptive. Failed or invalid-as-OFF runs are marked and excluded; a missing artifact is never a zero.

The public release does not include raw ShareGPT text or original terminal exports. If you have the original research artifacts locally, run the audit command documented by `python3 -m harness.audit_runs --help`. Do not add raw prompts, answers or `inputs.json` to a public commit. AIPerf may export an entire dataset into `inputs.json`.

## 3. Smoke-test an existing local Ollama model

The tested model tag is `nemotron-3-nano:4b-q4_K_M`, served by Ollama 0.40.15. The published result does not apply automatically to another tag or version. Installing Ollama or pulling weights is a separate resource decision; the following command assumes they already exist.

```bash
curl --fail http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"nemotron-3-nano:4b-q4_K_M","messages":[{"role":"user","content":"Reply with exactly one word: pong"}],"think":false,"stream":false,"options":{"temperature":0,"num_ctx":4096,"num_predict":64}}'
```

Check the answer, thinking field, stop reason and token counts. HTTP 200 alone is insufficient. Avoid parallel benchmarks and record machine load, power state and server version.

## 4. Re-run the matched original fixture

Read `python3 -m harness.matched_replay --help` before execution. Create a unique output folder:

```bash
python3 -m harness.matched_replay --output runs/new-local-check_ollama_laptop_matched
```

Choose a new directory for each run; an existing output path is refused. The runner uses only the local endpoint, preserves request order and original prompts, records warmups separately, and saves a fresh run directory. It does not download a model or call a paid provider. The saved design in `results/m4.json` states the exact options, cap, repetitions and cache treatment used in this release.

Do not call a native-API microfixture a repeat of the ShareGPT/AIPerf benchmark. Compare within its own model, endpoint, hardware and conditions. Review truncated/empty responses before reporting latency medians.

## 5. Run the original reliability probes

Read the [original prompts and expected answers]({{REPO}}/blob/main/probes.jsonl), [objective scorers]({{REPO}}/blob/main/harness/probes.py) and [release results]({{REPO}}/blob/main/results/probes.json). The suite covers JSON extraction, tool-selection format, arithmetic, short-context lookup, supplied-document abstention and instruction following. It uses the existing local model with thinking OFF, three repeats, sequential requests and no paid calls.

```bash
python3 -m harness.probes --output runs/new-local-check_ollama_laptop_probes
python3 -m harness.probes --summarize runs/new-local-check_ollama_laptop_probes --summary runs/new-local-check_ollama_laptop_probes/summary.json
```

Choose a fresh run folder. Review every failed or capped response before updating the maintained release results. Transport failures are preserved and stop the run; they do not become passing or missing observations. These original cases are a small integration suite, not a standard benchmark or a calibrated quality score. Tool-selection formatting does not establish native tool calling, and the short sentinel does not establish long-context capability.

## 6. Reproduce the AIPerf integration issue

AIPerf 0.13.0 is the tested version; preserve the original environment when reproducing it. Use an isolated Python 3.12 environment if installing it elsewhere.

```python
from aiperf.config.flags.cli_config import CLIConfig

config = CLIConfig(model=["nemotron-3-nano:4b-q4_K_M"],
                   extra_inputs='{"reasoning_effort":"none"}')
print(config.extra_inputs)
print(CLIConfig.model_validate(config.model_dump()).extra_inputs)
# First parse retains the string; revalidation changes it to None.
```

Inspect both JSON and key:value input paths; do not assume quoting preserves a string. The local workaround is:

```bash
python3 -m harness.reasoning_proxy
```

It listens on loopback port 11435 and forwards to Ollama on 11434. In a separate terminal, point AIPerf at `http://127.0.0.1:11435`. Label results **OFF via proxy**. Use `--use-legacy-max-tokens`, an explicit output cap, streaming, raw export, a verified tokenizer and documented warmups. Check emitted payloads and response reasoning before starting a long run. No proxy is needed for the native matched fixture.

A fixed-input replay must freeze the complete message arrays, including prior assistant turns. Fixing just the dataset seed or conversation IDs does not fix generated conversation history. Cache state and run order must also be documented; an OFF-only replay against an old ON run does not control elapsed time or machine conditions.

## 7. Build and publish documentation safely

```bash
python3 scripts/build_public.py
python3 scripts/check_site.py
```

Edit `content/` and `results/`, then regenerate. `docs/` is the static deployment root, with relative paths that work under `/open-model-readiness/`. It contains no inference service and needs no keys. `PUBLICATION_FILES.txt` is the explicit reviewed publication list. The original research repository is never pushed wholesale.

## Further evaluation

The [NeMo integration guide]({{REPO}}/blob/main/reports/nemo-feasibility.md) records the tested isolated setup, original fixture adapter and preserved failed attempt. It also documents a read-only first-cell GPU guard; no GPU benchmark has run.

The next sequence is broader reliability probes, human calibration, a standard NeMo benchmark subset, hosted testing, GPU comparisons and a second-model runbook test. Obtain explicit resource authorization before paid calls or large downloads. Human calibration labels must be supplied by the human reviewer; automated grades are not substitutes. GPU and hosted results belong in separate tables. See [ROADMAP.md]({{REPO}}/blob/main/ROADMAP.md).
