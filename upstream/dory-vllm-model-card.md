# Unsent model-card draft: replace stale pending-PR wording with versioned support

**Target:** [NVIDIA Dory BF16 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16). **Status:** documentation draft only; no PR or discussion filed. Reverified 2026-11-10. No Dory inference or GPU validation has been performed by this project.

## Evidence and scope

The current card's vLLM section still describes support as under review and directs installation from PR head. In contrast:

- [vLLM PR #60149](https://github.com/vllm-project/vllm/pull/60149) reports a merge on 2026-10-25.
- The [v0.33.0 registry](https://github.com/vllm-project/vllm/blob/v0.33.0/vllm/model_executor/models/registry.py#L101) includes `DoryForCausalLM`.
- [PyPI's v0.33.0 metadata](https://pypi.org/pypi/vllm/0.33.0/json) lists published wheel and source artifacts from 2026-11-02.

These sources support correcting the pending-PR statement. They do not establish that a particular wheel, GPU, quantization or command has passed the project's smoke test. The GitHub formal-release API for this tag returned 404 during re-verification, so no claim rests on unavailable release notes. A Git tag and a published package are distinguished from a GitHub Release object.

The current BF16 Community listing was reviewed, including the open response-template PR #15. Its fetched discussion did not mention vLLM or #60149. No exact duplicate of this documentation update was identified in that bounded check; this is not an exhaustive search of every variant repository or unindexed PR.

## Proposed replacement paragraph

> Dory support has merged into vLLM. The v0.33.0 model registry includes Dory, and that version has published package artifacts. Use a versioned vLLM installation compatible with your hardware, and verify the serving command below against that version. Installing from the original PR head is no longer necessary merely to obtain the merged model registration.

Link the paragraph to the merged PR, tagged registry and versioned package. Keep the existing model-specific serving flags until a maintainer verifies them on the recommended release. Avoid promising compatibility with all GPUs or implying that model registration alone is a successful runtime test.

## Maintainer checks before submission

Confirm the recommended released version and CUDA/PyTorch environment, run the documented load-and-generate smoke test, and retain any model-specific caveats. If the package's documented command still requires an unreleased fix, explain that specific dependency and pin its commit instead of describing the already-merged base support as pending review.

Exact capture timestamps, statuses and hashes are in [upstream-verification.json](../results/upstream-verification.json). Full source bodies are not redistributed by this project.
