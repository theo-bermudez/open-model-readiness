# Coverage and remaining work

Evidence cutoff: 2026-11-10. Status describes executed work, not intended coverage. Laptop, hosted and GPU experiments remain separate.

| Workstream | State | Next dependency / acceptance criterion |
|---|---|---|
| Research and evidence capture (M1) | Complete for initial scope | Date-stamp any later claims |
| Metadata, evidence and secret guards (M2) | Implemented and tested | Apply publication allowlist on every release |
| Local model serving (M3) | Tested on existing M2 laptop installation | Not a clean installation benchmark |
| AIPerf measurement validity (M4) | Historical audit and original matched fixture in first release | Broader frozen full-request replay remains in progress; old stateful runs are not a causal speedup |
| Reliability probes (M5) | Small deterministic fixture implemented; broader suite in progress | Add structured output, tool selection, refusal/abstention and context probes; three repeats per condition |
| Calibrated evaluation (M6) | Human-label workflow prepared; no calibrated judge result | Theo supplies about 20 independent labels; any paid judge requires fresh budget approval |
| NeMo Evaluator (M7) | Planned; not installed or run | Inspect dependency footprint in an isolated environment, select a deterministic-scored small subset; no changes to the historical AIPerf environment |
| First report (M8) | Implemented from reviewed result source | Extend only when new evidence meets gates |
| Hosted Super VL (M9) | Planned; no successful endpoint call recorded | Verified endpoint access and explicit current API budget; text-only scope |
| GPU engines (M10) | Planned; no GPU session provisioned | User supplies available GPU environment; verify driver/CUDA and memory first; no rentals authorized |
| Same-hardware comparison (M11) | Planned | Requires M10; record precision differences, never mix laptop/hosted timing |
| Upstream feedback (M12) | Local drafts and source verification | No issues, PRs or comments sent; review each draft before any future filing |
| Launch brief (M13) | Local-model first-release brief complete; hosted brief deferred | Hosted claims require M9 evidence |
| Independent runbook validation (M14) | Reproducibility guide implemented; Dory validation planned | Additional model download/storage and runtime selection; not run on Dory |

## Next execution sequence

1. Extend the local original probes beyond the small matched fixture; keep objective scorers separate from subjective judgments.
2. Have Theo label a deliberately varied, blinded sample. Compare any automated judge against those labels and report false accepts before using it for readiness decisions.
3. Evaluate a bounded NeMo subset after checking installation size and compatibility. Preserve the environment used for this release.
4. Obtain hosted budget and GPU access decisions; then execute M9/M10 and report only within the appropriate coverage class.
5. Re-verify upstream drafts, extend launch briefs and validate the runbook on Dory when resources are authorized.

An unavailable resource leaves a workstream planned. A partial suite remains partial even when its checks pass. Existing model weights and local services were preserved during this release; no new paid inference or compute was authorized.
