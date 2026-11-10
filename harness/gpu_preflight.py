"""Read-only first-cell guard for the planned single-T4 notebook.

Run before installing engines or downloading model weights:
  python -m harness.gpu_preflight --output runs/<run>/gpu_preflight.json

Exit 0 means only that the requested hardware is visible. It does not validate
an engine, CUDA toolkit, memory fit, quota, or benchmark. No services are started.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from harness.runmeta import detect_gpus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-gpus", type=int, default=1)
    parser.add_argument("--name-contains", default="T4")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.expected_gpus < 1:
        parser.error("--expected-gpus must be positive")
    gpus, driver_cuda = detect_gpus()
    blockers = []
    if len(gpus) != args.expected_gpus:
        blockers.append(f"expected {args.expected_gpus} NVIDIA GPU(s), detected {len(gpus)}")
    if any(args.name_contains.casefold() not in gpu["name"].casefold() for gpu in gpus):
        blockers.append("detected GPU name does not match requested hardware class")
    if gpus and driver_cuda is None:
        blockers.append("driver-supported CUDA version could not be observed")
    result = {"schema_version": 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "status": "blocked" if blockers else "hardware_visible",
              "requested": {"gpu_count": args.expected_gpus, "name_contains": args.name_contains},
              "gpus": gpus, "driver_max_cuda_version": driver_cuda, "blockers": blockers,
              "next_action": "Stop before installs or model downloads." if blockers else
                             "Choose engine versions against the observed driver capability, then record quantization and serve a smoke request.",
              "limitations": "nvidia-smi CUDA Version is the driver's supported maximum, not an installed toolkit. GPU visibility does not establish engine support, quota or model fit. Do not mix laptop or hosted results into a GPU engine table."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
