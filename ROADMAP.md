# Coverage and remaining work

Evidence cutoff: 2026-11-10. Status describes executed work, not intended coverage. Laptop, hosted and GPU experiments remain separate.

| Workstream | State | Next dependency / acceptance criterion |
|---|---|---|
| Research and evidence capture | Complete for initial scope | Date-stamp any later claims |
| Metadata, evidence and secret guards | Implemented and tested | Apply publication allowlist on every release |
| Local model serving | Tested on existing Apple M2 laptop installation | Not a clean installation benchmark |
| AIPerf measurement validity | Historical audit and original matched fixture in first release | Broader frozen full-request replay remains in progress; old stateful runs are not a causal speedup |
| Reliability probes | Six original cases implemented and tested with three repeats each; broader coverage partial | Add representative variations, adversarial cases and runtime conditions; retain objective scores and failures |
| Calibrated evaluation | Human-label workflow prepared; no calibrated judge result | Theo supplies about 20 independent labels; any paid judge requires fresh budget approval |
| NeMo Evaluator | Integrated and tested: isolated 0.3.0 with four original prompts; standard benchmarks pending | Check dataset footprint/license and freeze a deterministic benchmark subset; original AIPerf environment preserved |
| First report | Implemented from reviewed result source | Extend only when new evidence meets gates |
| Hosted Super VL | Planned; no successful endpoint call recorded | Verified endpoint access and explicit current API budget; text-only scope |
| GPU engines | Planned; no GPU session provisioned | User supplies available GPU environment; verify driver/CUDA and memory first; no rentals authorized |
| Same-hardware comparison | Planned | Requires GPU engine runs; record precision differences, never mix laptop/hosted timing |
| Upstream feedback | Local drafts and source verification | No issues, PRs or comments sent; review each draft before any future filing |
| Launch brief | Local-model first-release brief complete; hosted brief deferred | Hosted claims require hosted-model evidence |
| Independent runbook validation | Reproducibility guide implemented; Dory validation planned | Additional model download/storage and runtime selection; not run on Dory |

## Next execution sequence

1. Extend the six-case original probe suite with representative variations and adversarial cases; keep objective scorers separate from subjective judgments.
2. Have Theo label a deliberately varied, blinded sample. Compare any automated judge against those labels and report false accepts before using it for readiness decisions.
3. Extend the tested NeMo integration to a standard deterministic-scored subset after checking dataset size, license and frozen IDs. Preserve the historical environment.
4. Obtain hosted budget and GPU access decisions; then test those environments and report only within the appropriate coverage class.
5. Re-verify upstream drafts, extend launch briefs and validate the runbook on Dory when resources are authorized.

An unavailable resource leaves a workstream planned. A partial suite remains partial even when its checks pass. Existing model weights and local services were preserved during this release; no new paid inference or compute was authorized.
