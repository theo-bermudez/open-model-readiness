# A successful request is only the first readiness gate

Independent Open Model Readiness case study · Theo Bermudez · {{RELEASE}} · Evidence cutoff {{CUTOFF}}.

[Overview]({{SITE}}) · [Code]({{REPO}}) · [Reproduce]({{SITE}}reproduce.html) · [Machine-readable evidence](results/m4.json)

## Decision in one minute

Nemotron-3-Nano-4B can support a small, instrumented local demonstration on this laptop. The integration needs explicit checks for reasoning mode, output limits and answer presence. A benchmark success count alone did not establish that the requested experiment ran. These observations justify workflow fixes; they do not validate production deployment, compare GPU engines or establish broad model quality.

## Tested coverage

{{COVERAGE_TABLE}}

The historical local stack is AIPerf 0.13.0, Python 3.12.13, Homebrew Ollama 0.40.15, Q4_K_M weights, Apple M2 and 8 GB unified memory. The original service configuration declared flash attention and a q8_0 KV cache. That declaration is not independent proof of the effective runtime configuration. Historical notes record a default context of 4096; per-request context overrides were not captured. The runs used concurrency 1, temperature 1.0 and top_p 0.95. Exact generation settings and hashes are in the results file.

## Finding 1: the requested reasoning mode changed

**Observed:** the installed AIPerf extra-input parser converts string `"none"` to Python `None`. The JSON request then carries null. The purported OFF run `20261110T040845Z_nemotron-3-nano-4b_ollama_laptop_aiperf` contains reasoning in every profiled response.

**Expected:** a string-valued API option survives configuration parsing unchanged.

**Developer impact:** the run succeeds but its mode label is false. A caller relying on HTTP errors or command-line text alone can compare the wrong conditions.

**Workaround:** the existing loopback proxy injects `reasoning_effort: "none"` after AIPerf parsing. It only changes absent/null values on the chat-completions route; explicit non-null values remain intact. The native Ollama API also accepts `think: false`. The proxy is a local debugging workaround, not a production service.

**Evidence:** parser reproduction, invalid-run response checks and source hashes in [results/m4.json](results/m4.json); [proxy implementation]({{REPO}}/blob/main/harness/reasoning_proxy.py). Upstream status is separately date-stamped in [verification notes]({{REPO}}/blob/main/results/upstream-verification.json).

## Finding 2: identical seed, different complete requests

**Observed:** the successful ON/OFF runs selected the same conversation IDs and turn order. Later turns incorporated each run's own generated answers, changing the full messages payload. Only {{MATCHED_COUNT}} of {{PROFILE_COUNT}} profiled payloads matched exactly.

**Expected for a controlled request-level comparison:** the same complete messages, order, generation options and documented cache treatment in each condition.

**Developer impact:** the mode affects both the current response and future input history. A conversation benchmark may intentionally measure that interaction, but it cannot be read as a fixed-input latency experiment.

**Correction:** retain these runs as descriptive evidence. Hash the entire message array; freeze complete requests for replay; record whether previous answers are fixed or generated. The new short fixture uses identical original prompts and counterbalanced mode order. It is a separate experiment and does not repair the historical dataset comparison retroactively.

{{HEADLINE_TABLE}}

All timing values above are medians across profiling requests; three warmups per historical run are excluded using the recorded phase. First-token latency includes the first reasoning token where present. First-answer latency is the first non-reasoning output token. Neither is the total request duration. Client tokenizer counts and server usage counts are kept separate. High percentiles from such small samples would largely interpolate the slowest observations, so the public summary emphasizes counts, medians and ranges.

## Finding 3: successful transport, unusable answer

**Observed:** the earlier tight-cap runs spent their output allowance on reasoning. The invalid OFF run had {{INVALID_EMPTY}} empty final answers among {{INVALID_N}} profiling requests, and every profiled response finished at the length limit.

**Expected:** the application receives a usable final answer, or identifies a capped result as incomplete.

**Developer impact:** transport success overstates user-visible success. Increasing a cap changes the workload and cannot silently be mixed into an earlier experiment.

**Workaround:** on the tested Ollama version, use `max_tokens` on the compatible route or `num_predict` natively. The saved cap test shows `max_completion_tokens` was not enforced. Always retain the finish reason, answer-presence check and reasoning/answer split. Treat a tight-budget failure as a configuration-specific result, not a universal model defect.

## Controlled local replay

{{REPLAY_SUMMARY}}

This microfixture is a semantic and reproducibility check. Its original prompts are deliberately small enough for local execution. It does not estimate representative task quality, long-context accuracy, sustained load, production reliability or performance on NVIDIA hardware. Counterbalancing reduces systematic mode-order bias; it does not remove all cache, thermal, background-load or deterministic-decoding effects. Repeats are not independent tasks.

## NeMo Evaluator integration

{{NEMO_SUMMARY}}

## Original reliability probes

{{PROBES_SUMMARY}}

The JSON scorer rejects duplicate keys, nonstandard numeric values, extra fields and wrong value types. Exact-text cases trim outer whitespace without changing case or punctuation. The tool-selection case checks JSON format only; no native function-call protocol or tool execution was tested. The context sentinel is a short inventory lookup, not a long-context test. The supplied-document case checks one explicit missing-fact instruction, not general hallucination or safety behavior.

Observed variance describes only the repeated binary outcomes on each fixture. The cases ran in fixed order with retained cache and no separately measured warmups, so timing is descriptive. Repeating deterministic prompts on one laptop does not establish population reliability, calibrated quality or production readiness.

## Context, caching and timing caveats

Historical client input lengths exceeded the configured context on some requests, while server usage counts were lower. Tokenizer/template differences and cache accounting also affect those counts. A count difference alone is not proof of exactly which text was truncated. Full per-request truncation attribution requires server trace evidence or a controlled sentinel test. Do not present the advertised model context as the context actually configured by the runtime.

Benchmark duration excludes parts of configuration, warmup and teardown. Historical terminal wall times are not interchangeable with per-request or profiling duration; the raw AIPerf log and terminal reference remain local. The audit keeps source digests rather than reprinting terminal exports. Failed startup `20261110T054444Z` has no completed benchmark summary and is excluded. The earlier invalid-as-OFF run is preserved and excluded from valid OFF comparisons.

Startup diagnostics also exposed coupled dataset/service configuration timeouts. Raising one timeout without its dependent configuration can fail before profiling. The observed behavior is version-specific; the runbook recommends inspecting the installed help and configuration validation, not blindly raising every limit. No environment upgrade was made to reinterpret old evidence.

## Readiness gates

| Gate | Criterion | First-release assessment |
|---|---|---|
| Endpoint behavior | Smoke request returns a valid, nonempty answer | Tested on the local model |
| Request semantics | Requested mode and cap reach the server and affect responses | Workaround required on the tested AIPerf path |
| Comparison validity | Full prompts and relevant settings match; cache and order recorded | Historical comparison fails; short replay scoped separately |
| Answer usability | Nonempty answer; finish reason and cap recorded | Must be checked per request; tight caps exposed failures |
| Evidence integrity | Run IDs, versions, phases, hashes and exclusions retained | Implemented for reviewed results |
| Quality calibration | Representative tasks plus independent human labels | Pending |
| Deployment coverage | Reliability/load tests on target hardware and serving engines | Pending |

## Method and provenance

The audit reads existing raw exports locally, selects records by benchmark phase, joins request/response evidence by request ID, hashes complete message arrays and summarizes explicit fields. Generated results contain no ShareGPT messages or answers. The public history is a reviewed snapshot of the existing project; original commits and research artifacts remain local. This preserves the work without distributing dataset payloads or unrelated private material.

Theo ran the original setup and benchmarks with Claude Code assistance. Codex continued the request audit, implementation, checks and publication preparation. AI assistance does not supply missing measurements or human labels. Claims are grounded in recorded runs, not prior assistant summaries.

## Remaining work

The next validation step is broader, representative probe coverage followed by human-label calibration. The original reliability suite and NeMo Evaluator integration smoke are tested; standard NeMo benchmarks, hosted testing, same-hardware GPU engine comparisons and independent Dory runbook validation remain separate planned work. See the [roadmap]({{REPO}}/blob/main/ROADMAP.md) for dependencies and the [launch brief]({{REPO}}/blob/main/briefs/local-readiness.md) for the release decision.
