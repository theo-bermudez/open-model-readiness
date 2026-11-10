"""Record the conditions of every run next to its raw output.

Why: a number with no conditions is not evidence. Every runs/<run>/ folder gets a meta.json
saying what served the model (hardware, engine + version, model + quantization), what measured
it (tool + version), when, and whether the endpoint was self-served or NVIDIA-hosted.
report.py will refuse to tabulate a run that has no meta.json.

Deliberately NOT recorded: hostname, username, home paths (the repo may go public). Never put
a secret in engine flags. Anything we cannot detect is null, never guessed.

Stdlib only, so it runs unchanged in a fresh Kaggle notebook.

CLI (what the run wrappers call); prints the new run folder's path:
  python -m harness.runmeta --kind aiperf --model-key nemotron-3-nano-4b \
      --model-id nemotron-3-nano:4b-q4_K_M --quant Q4_K_M --engine ollama \
      --hardware laptop --served-by self --tool aiperf
"""
import argparse
import http.client
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.request import urlopen

SCHEMA_VERSION = 1
# Engine-vs-engine tables may only compare runs that share a hardware class.
HARDWARE_CLASSES = ("laptop", "t4", "hosted")
SERVED_BY = ("self", "nvidia-hosted")
# Parts of a run-folder name: no slashes and no leading dot, so a name can't escape runs/.
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_labels(served_by, hardware_class):
    if served_by not in SERVED_BY:
        raise ValueError(f"served_by must be one of {SERVED_BY}, got {served_by!r}")
    if hardware_class not in HARDWARE_CLASSES:
        raise ValueError(f"hardware_class must be one of {HARDWARE_CLASSES}, got {hardware_class!r}")
    # A hosted run must never be mistaken for a self-served one (or the reverse).
    if (served_by == "nvidia-hosted") != (hardware_class == "hosted"):
        raise ValueError("served_by='nvidia-hosted' pairs with hardware_class='hosted', and only with it")


# --- detectors: each returns None / [] when it cannot tell ----------------------------------

def run(cmd):
    """stdout of a command, or None if it is missing or fails. Never raises."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def parse_nvidia_smi_gpus(csv_text):
    """'Tesla T4, 15360, 535.104.05, 7.5' lines -> [{name, memory_mib, driver, compute_capability}]."""
    gpus = []
    for line in (csv_text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"name": parts[0],
                         "memory_mib": int(parts[1]) if parts[1].isdigit() else None,
                         "driver": parts[2],
                         "compute_capability": parts[3] if len(parts) > 3 else None})
    return gpus


def parse_cuda_version(smi_text):
    """The 'CUDA Version: X.Y' in nvidia-smi's header: the HIGHEST CUDA the driver supports,
    not the installed toolkit. SGLang's CUDA 13 requirement is checked against this."""
    m = re.search(r"CUDA Version:\s*([\d.]+)", smi_text or "")
    return m.group(1) if m else None


def detect_gpus():
    if not shutil.which("nvidia-smi"):
        return [], None
    fields = "--query-gpu=name,memory.total,driver_version"
    csv = (run(["nvidia-smi", fields + ",compute_cap", "--format=csv,noheader,nounits"])
           or run(["nvidia-smi", fields, "--format=csv,noheader,nounits"]))  # old drivers reject compute_cap
    return parse_nvidia_smi_gpus(csv), parse_cuda_version(run(["nvidia-smi"]))


def _linux_cpu_and_ram():
    cpu = ram_gb = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram_gb = round(int(line.split()[1]) / 1024 / 1024, 1)  # kB -> GiB
                break
    except (OSError, ValueError, IndexError):
        pass
    return cpu, ram_gb


def detect_hardware():
    """What THIS machine is. Only used for self-served runs, where this machine serves the model."""
    cpu = ram_gb = None
    if sys.platform == "darwin":
        cpu = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        mem = run(["sysctl", "-n", "hw.memsize"])
        ram_gb = round(int(mem) / 2**30, 1) if mem and mem.isdigit() else None
    elif sys.platform.startswith("linux"):
        cpu, ram_gb = _linux_cpu_and_ram()
    gpus, max_cuda = detect_gpus()
    return {"os": platform.platform(), "machine": platform.machine(), "cpu": cpu, "ram_gb": ram_gb,
            "gpus": gpus, "driver_max_cuda_version": max_cuda}


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def ollama_server_version(base_url="http://localhost:11434"):
    """Ask the running server, not the CLI: the server is what actually served the run."""
    try:
        with urlopen(f"{base_url}/api/version", timeout=3) as r:
            return json.load(r).get("version")
    except (OSError, ValueError, http.client.HTTPException):
        return None


def detect_engine_version(engine):
    if engine == "ollama":
        return ollama_server_version()
    if engine in ("vllm", "sglang"):
        return package_version(engine)
    return None  # e.g. nvidia-api: the provider does not disclose its engine


# --- the record -----------------------------------------------------------------------------

def collect_meta(*, kind, model_key, model_id, quantization, engine_name, engine_version,
                 hardware_class, served_by, tool_name=None, tool_version=None,
                 engine_flags=None, notes=None, now=None):
    validate_labels(served_by, hardware_class)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "served_by": served_by,
        "hardware_class": hardware_class,
        # Hosted: the provider's hardware is not ours to detect, so say "undisclosed" instead of guessing.
        "serving_hardware": detect_hardware() if served_by == "self" else {"disclosed": False},
        # Where the load generator ran. For hosted runs this is the laptop and only affects network latency.
        "client": {"os": platform.platform(), "python": platform.python_version()},
        "model": {"key": model_key, "id": model_id, "quantization": quantization},
        "engine": {"name": engine_name, "version": engine_version, "flags": list(engine_flags or [])},
        "tool": {"name": tool_name, "version": tool_version},
        "notes": notes,
    }


def new_run_dir(runs_root, *, kind, model_key, engine, hardware_class, now=None):
    for part in (kind, model_key, engine, hardware_class):
        if not SLUG.fullmatch(part):
            raise ValueError(f"unsafe run-name part: {part!r}")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    path = Path(runs_root) / f"{now:%Y%m%dT%H%M%SZ}_{model_key}_{engine}_{hardware_class}_{kind}"
    path.mkdir(parents=True, exist_ok=False)  # never reuse a folder: a rerun is a new run
    return path


def write_meta(run_dir, meta):
    (Path(run_dir) / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Create runs/<run>/ with a meta.json and print its path.")
    ap.add_argument("--kind", required=True, help="aiperf | nemo-eval | probes | judge | ...")
    ap.add_argument("--model-key", required=True, help="key in models.yaml")
    ap.add_argument("--model-id", required=True, help="tag or repo the engine was given")
    ap.add_argument("--quant", required=True, help="e.g. Q4_K_M, fp16, undisclosed")
    ap.add_argument("--engine", required=True, help="ollama | vllm | sglang | nvidia-api")
    ap.add_argument("--hardware", required=True, choices=HARDWARE_CLASSES)
    ap.add_argument("--served-by", required=True, choices=SERVED_BY)
    ap.add_argument("--engine-version", help="default: asked from the running server / installed package")
    ap.add_argument("--engine-flag", action="append", default=[], help="repeatable; never a secret")
    ap.add_argument("--tool", help="package name of the measuring tool, e.g. aiperf")
    ap.add_argument("--tool-version", help="default: installed package version")
    ap.add_argument("--notes")
    ap.add_argument("--runs-root", default="runs")
    a = ap.parse_args(argv)
    try:
        meta = collect_meta(
            kind=a.kind, model_key=a.model_key, model_id=a.model_id, quantization=a.quant,
            engine_name=a.engine, engine_version=a.engine_version or detect_engine_version(a.engine),
            hardware_class=a.hardware, served_by=a.served_by, tool_name=a.tool,
            tool_version=a.tool_version or (package_version(a.tool) if a.tool else None),
            engine_flags=a.engine_flag, notes=a.notes)
        path = new_run_dir(a.runs_root, kind=a.kind, model_key=a.model_key, engine=a.engine,
                           hardware_class=a.hardware)
    except ValueError as e:
        ap.error(str(e))
    write_meta(path, meta)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
