# Upstream feedback — unsent drafts

These files are reviewable project artifacts. No issue, comment or PR was filed or sent during this continuation. Project publication does not authorize upstream submission.

| Draft | Status and target | What this project contributes |
|---|---|---|
| [Reasoning setting addendum](aiperf-reasoning-setting.md) | Existing [AIPerf issue #1562](https://github.com/ai-dynamo/aiperf/issues/1562); unsent addendum | A server can accept the altered setting and return successful requests in the wrong mode; verify the effective request, not only CLI intent. |
| [Output cap addendum](ollama-output-caps.md) | Existing [Ollama issue #7125](https://github.com/ollama/ollama/issues/7125); unsent addendum | Measured compatibility-field differences and a reasoning-only, length-limited response on the tested local stack. |
| [Dory model-card update](dory-vllm-model-card.md) | Proposed documentation update; unsent | The card's pending-PR wording is stale relative to merged code, the tagged registry and published package metadata. Runtime verification remains separate. |

Rechecked **2026-11-10**. Source URLs, response statuses, capture times and exact response hashes are in [the verification ledger](../results/upstream-verification.json). Full upstream mirrors remain private. A source-code check establishes the inspected implementation; it is not an execution test of every current build.

The startup/dataset timeout, output-length warning and suspicious effective-throughput maximum remain investigation items. Their local observations are retained in the friction logs. No new issue text asserts an upstream root cause for them without a minimal reproduction. This is partial M12 completion, not a claim that every queued item has been resolved.
