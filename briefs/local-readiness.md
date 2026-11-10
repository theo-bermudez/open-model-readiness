# Local readiness brief: Nemotron-3-Nano-4B

Evidence cutoff 2026-11-10 · First-release scope: Homebrew Ollama 0.40.15, Q4_K_M, Apple M2 with 8 GB memory.

**Recommendation:** enable a small local demonstration with explicit checks and documented workarounds. Do not claim production readiness, representative quality or GPU performance.

**Developer need:** a reproducible path from a working endpoint to a valid measurement and usable answer.

**Blocking defects for the tested measurement path:** requested reasoning mode can change during AIPerf parsing; a success-only gate accepts empty answers; conversation history prevents fixed-input interpretation of historical ON/OFF timing.

**Release requirements:** inspect outgoing mode/cap; check answer presence and finish reason; hash complete prompts; keep warmups out of profile summaries; attach versions, hardware and cache treatment to every result. Use the loopback proxy only where the compatible API setting needs correction. Native probes use the native boolean directly.

**Evidence:** [full report](../reports/first-release.md), [maintained result source](../results/m4.json), [reproduction guide](../RUNBOOK.md). These establish narrow integration behavior and measurement pitfalls. They do not establish task-level quality.

**Next priorities:** representative deterministic probes, human calibration, bounded NeMo evaluation, then separately authorized hosted and GPU experiments. Use readiness criteria, not an arbitrary numerical score, to decide whether each new workflow can be recommended.
