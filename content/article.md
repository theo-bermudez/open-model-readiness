# I thought I was benchmarking thinking-off. The requests told a different story.

A small open-model readiness audit uncovered two ways a successful benchmark can answer the wrong question.

I wanted a straightforward comparison: run the same local model with reasoning enabled and disabled, then measure how long a developer waits for an answer. I used Nemotron-3-Nano-4B through Ollama on my Apple M2 laptop, with NVIDIA AIPerf generating requests and collecting streaming metrics. The useful outcome was supposed to be a reproducible integration recipe, with enough evidence to explain its limitations.

Instead, the most useful result was a lesson in experiment validity. A command that appeared to request thinking-off did not send that setting as intended. After that was corrected, two runs with the same dataset seed still did not contain the same complete prompts.

I am publishing the code, reviewed aggregates and reproduction guide in [Open Model Readiness]({{SITE}}). I ran the original setup and benchmarks with Claude Code assistance; Codex helped continue the investigation, implement checks and prepare this release. The claims below come from saved requests, responses and installed source code, not from an assistant's description of what should have happened.

## The first failure was a type conversion

On the tested Ollama compatible endpoint, the intended switch was the string-valued option `reasoning_effort: "none"`. AIPerf accepts extra request fields through its command line, so supplying that value looked reasonable. The request completed successfully. That was the misleading part.

AIPerf 0.13.0's configuration parser interprets strings equal to `none` or `null` as Python `None`. When serialized to JSON, that becomes null. This conversion also applies to values supplied inside the JSON form of extra inputs; wrapping the option in JSON did not protect the string.

A minimal local check exposes the difference:

```python
from aiperf.config.flags.cli_config import CLIConfig

config = CLIConfig(model=["nemotron-3-nano:4b-q4_K_M"],
                   extra_inputs='{"reasoning_effort":"none"}')
print(config.extra_inputs)
print(CLIConfig.model_validate(config.model_dump()).extra_inputs)
# First parse retains the string; revalidation changes it to None.
```

The intent and the request were different:

```json
{"reasoning_effort": "none"}
```

became a field with a null value. On this tested path, the returned responses still contained reasoning. The run I had intended to be OFF is now explicitly marked invalid-as-OFF and excluded from valid OFF comparisons. It remains useful evidence of the failure.

This is a narrow, version-specific finding. It is not evidence that all AIPerf configurations mishandle strings or that all Ollama versions behave identically. There is also an [existing upstream issue](https://github.com/ai-dynamo/aiperf/issues/1562) covering the coercion path. My feedback is saved as an unsent evidence addendum, rather than a duplicate issue.

## A small workaround, followed by a behavior check

The project already had a loopback proxy that sits between AIPerf and Ollama. For the chat-completions route, it inserts the literal string `"none"` when the setting is missing or null. Explicit non-null values are preserved. The proxy streams responses and does not log request bodies.

That makes the workaround easy to inspect: the correction happens after the client configuration has been parsed, immediately before forwarding the request. The [implementation and tests]({{REPO}}/blob/main/harness/reasoning_proxy.py) are public. It is a local diagnostic tool, not a production inference gateway.

The correction alone was not enough. I also needed to inspect the returned behavior. A printed command is evidence of intent; the serialized payload is evidence of what was sent; reasoning and answer fields show what came back. Those are three separate checks.

For a new native-API fixture, I could avoid the compatibility conversion altogether and use Ollama's `think` boolean. That fixture is reported separately from the AIPerf experiment. Changing the API path is a method change, not something to hide in a footnote.

## The second failure survived the seed check

The corrected historical ON and OFF runs each completed {{PROFILE_COUNT}} profiled requests. Their latency summaries looked very different. It would have been tempting to turn the ratio into a headline.

But the input-token distributions were different too. A shared seed did not resolve that discrepancy. The continuation audit hashed the complete message arrays and compared their conversation and turn identifiers.

The surprising result was that the conversation IDs and turn order actually matched. Only {{MATCHED_COUNT}} of the {{PROFILE_COUNT}} full profiled message payloads matched exactly. The later turns included assistant answers generated earlier in each run. Once the two modes produced different answers, the history fed into subsequent requests diverged.

The sampler was therefore not simply choosing arbitrary different conversations. The workload was stateful. The treatment changed an answer, and that answer became part of a later input.

That can be a legitimate conversation-level experiment. It is not the same question as “how does changing this option affect latency for an identical request?” To answer the latter, I need to freeze the entire request, including prior assistant turns, and verify its hash in both conditions. Fixing the latest user message is not sufficient.

The public report retains the original timing summaries as descriptive observations. It makes no controlled speedup claim from them. Replaying only OFF later would also leave time, cache and machine-state differences unresolved; it would improve one control without establishing all the others.

## A successful response can still contain no answer

Output budgets exposed another readiness problem. In an earlier tight-cap run, reasoning consumed the available generation budget. The invalid-as-OFF run contained {{INVALID_EMPTY}} empty final answers among {{INVALID_N}} profiled responses, with every response stopping at the length limit.

For a developer integrating the model, “no request error” is a poor substitute for “the application received something usable.” I now want the harness to record answer presence and finish reason alongside transport success. Reasoning tokens and answer tokens also need separate accounting.

The historical cap test found that this Ollama version honored `max_tokens` on its compatible endpoint and native `num_predict`, while `max_completion_tokens` was not enforced. AIPerf's legacy-max-tokens option is relevant to that integration. These observations belong to the tested versions and endpoint; they should not become general assumptions about every OpenAI-compatible server.

Latency needs the same care. Time to first token can mean the first reasoning token. Time to first answer is when non-reasoning content starts arriving. Total request duration is different again. A product that displays only final answers should not describe a reasoning-token timestamp as the user's wait for an answer.

## What I would make a release gate

The correction is more useful than a bigger benchmark table. Before a long evaluation, I would require a small contract check that answers four questions:

- Did the complete serialized request preserve the requested mode and generation limits?
- Did the returned fields demonstrate the expected behavior?
- Were full prompts, ordering and relevant settings actually matched for the comparison being claimed?
- Did successful requests produce nonempty, uncapped answers where the application requires them?

The first release includes a small original matched fixture with counterbalanced mode order and explicitly recorded warmup/cache treatment. It helps test the measurement path and basic behavior. It does not establish representative answer quality or sustained reliability. Repeated tiny prompts are not a substitute for diverse tasks and independent human labels.

That distinction matters to the product decision. I can recommend an instrumented local demonstration with documented workarounds. I cannot recommend production deployment from this evidence. A separate NeMo Evaluator integration smoke now runs the project's original fixtures; standard benchmark evaluation, human-calibrated quality, hosted testing and same-hardware GPU comparisons still require further work.

The [full report]({{SITE}}report.html) explains the gates and exclusions. The [reproduction guide]({{SITE}}reproduce.html) starts with checks that require no model or API keys. Public aggregates preserve run identifiers, settings and hashes; raw dataset conversations and private terminal exports are not redistributed.

My main takeaway is practical: validate the meaning of a benchmark before optimizing its numbers. If a setting changes type on the way to the server, or a previous answer changes the next prompt, the benchmark can run perfectly and still measure a different experiment from the one I intended.

Evidence cutoff: {{CUTOFF}}. This article and the linked report use the {{RELEASE}} results source. Independent project by Theo Bermudez; no NVIDIA affiliation or endorsement is implied.
