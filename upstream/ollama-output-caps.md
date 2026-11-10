# Unsent evidence addendum: output-cap compatibility and reasoning-only responses

**Target:** existing [Ollama issue #7125](https://github.com/ollama/ollama/issues/7125). **Status:** draft only; not posted. Reverified 2026-11-10. The compatibility request already exists, so this is supplementary evidence rather than a duplicate issue.

## Environment and observed behavior

The local cap-mechanism run `20261110T015629Z_nemotron-3-nano-4b_ollama_laptop_captest` used Homebrew Ollama **0.40.15**, `nemotron-3-nano:4b-q4_K_M`, Apple M2/8 GB, temperature zero and a requested output cap of 64 tokens. It compared `/v1/chat/completions` using `max_completion_tokens` or `max_tokens` with native `num_predict`, with thinking enabled and disabled.

The modern OpenAI field did not bound generation in that run. `max_tokens` and native `num_predict` did. With thinking enabled, the honored tight budget could end during reasoning, returning a length finish reason and empty answer text. That is a bounded generation, but it is not an answer-ready response. This is a small mechanism test, not a quality benchmark or universal statement about every model.

The [v0.40.15 request structure and conversion](https://github.com/ollama/ollama/blob/v0.40.15/openai/openai.go) contain `max_tokens` and map it to `num_predict`. The [inspected main commit](https://github.com/ollama/ollama/blob/3f3fa58f7fcf18de43ec126ad8676b4281b6923c/openai/openai.go) retains that path and has no `max_completion_tokens` field in this file. The [current compatibility documentation](https://docs.ollama.com/api/openai-compatibility) lists supported request fields. Source inspection supplements the pinned-version run; main was not installed or benchmarked.

## Safe reproduction request

For a local model that is already installed, compare the following original request with a second request changing only the cap field's name to `max_completion_tokens`:

```json
{
  "model": "nemotron-3-nano:4b-q4_K_M",
  "messages": [{"role": "user", "content": "Write a 200-word paragraph about organizing a public library."}],
  "temperature": 0,
  "max_tokens": 64
}
```

This is a small safe example for a future reproduction, not a claim that its exact wording was the historical prompt. Record usage, finish reason, reasoning and answer lengths separately. The uncapped variant may run longer; it should not be started as part of a documentation build.

## Workaround and proposed improvement

For the tested AIPerf/Ollama combination, use AIPerf's legacy-max-tokens option and inspect the actual request. Check answer text and finish reason before treating a successful request as a usable completion. Keep requested output budget distinct from observed output length and from client tokenizer estimates.

Adding the modern alias would reduce integration friction. Define precedence or reject conflicting values when both fields are present, test both streaming and non-streaming requests, and document that a reasoning model can consume a shared generation budget before producing an answer. A compatibility preflight should warn about unsupported critical fields instead of allowing them to silently change benchmark conditions.
