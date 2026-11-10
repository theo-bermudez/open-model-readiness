# Unsent evidence addendum: successful requests can use the wrong reasoning mode

**Target:** existing [AIPerf issue #1562](https://github.com/ai-dynamo/aiperf/issues/1562). **Status:** draft only; not posted. Reverified 2026-11-10. This issue predates the project's measurements; the project independently reproduced its developer impact.

## Problem and local evidence

With AIPerf **0.13.0**, Homebrew Ollama **0.40.15**, and `nemotron-3-nano:4b-q4_K_M` on an Apple M2 laptop, a run intended to disable thinking sent JSON null instead of the string `"none"`. The local server accepted the request and generated reasoning. An HTTP-success check therefore did not verify the intended experiment.

Local evidence: `20261110T040845Z_nemotron-3-nano-4b_ollama_laptop_aiperf`, explicitly **invalid as thinking OFF**. The retained raw requests contain the altered setting; raw responses contain reasoning. Public aggregates and hashes are provided through the report; dataset text is withheld. The later ON/OFF runs are not a controlled speed comparison because their effective request payloads differ.

## Minimal configuration reproduction

This uses the existing installed environment and does not start inference or download a model:

```python
from aiperf.config.flags.cli_config import CLIConfig

config = CLIConfig(model=["nemotron-3-nano:4b-q4_K_M"],
                   extra_inputs='{"reasoning_effort":"none"}')
print(config.extra_inputs)
print(CLIConfig.model_validate(config.model_dump()).extra_inputs)
```

On the tested version, the first value is the string `"none"`; revalidating the configuration changes it to Python `None`. The `reasoning_effort:none` spelling converts on its first parse. This isolates the conversion mechanism; the recorded benchmark request verifies that it reaches the transmitted payload. The local configuration check agrees with the earlier reproduction in issue #1562.

The same coercion is present in the [v0.13.0 parser](https://github.com/ai-dynamo/aiperf/blob/v0.13.0/src/aiperf/config/loader/parsing.py#L149-L156) and in [main at the inspected commit](https://github.com/ai-dynamo/aiperf/blob/4710831f100b5933372e14ed4b6b5fb955a64a73/src/aiperf/config/loader/parsing.py#L152-L159). This is source verification of main, not a new installation or runtime test of main.

## Workaround used here

The project's [loopback proxy](../harness/reasoning_proxy.py) inserts the string after AIPerf has built the request. It does not log request bodies. Runs using it are labelled as such. The intended field is:

```json
{"reasoning_effort": "none"}
```

The existing issue describes a nested reasoning object as another possible route. It was not the workaround used for these recorded runs and is not presented as validated by this project's benchmark.

## Suggested acceptance criteria

- Preserve explicit JSON string values through configuration revalidation; distinguish them from JSON null.
- Verify the final serialized request in a regression test, including both CLI spellings and a true null input.
- Add a request-inspection preflight that displays effective nonsecret settings before a long run, with headers and user text redacted.
- Treat response reasoning fields as a verification signal when a run declares thinking disabled. Do not infer correctness solely from status codes.

The library fix and any upstream submission remain outside this project's completed scope.
