#!/usr/bin/env python3
"""
Prepopulate a RunPod serverless endpoint with all models and dependencies.

Downloads ALL models needed for the LTX-2.5 + SeedVR2 pipeline to the
RunPod network volume, plus installs custom node pip dependencies. Everything
goes through the serverless function's ``download_models`` and ``diagnostic``
actions — no SSH required.

Models downloaded:
  - All LTX-2.5 models for 48GB (full_48gb profile from config/ltx-2.5-models.json)
    Includes: int8-convrot dev + distilled transformers, BF16 + int8 text
    encoders, distilled LoRA, IC-LoRA pixel upscaler, spatial + temporal
    upscalers, video + audio VAEs, text enhancer, duration head patch.
  - SeedVR2 3B FP16 + VAE (from numz/SeedVR2_comfyUI on HuggingFace)
  - SeedVR2 7B FP16 (optional, from numz/SeedVR2_comfyUI)

LTX-2.5 downloads are batched by estimated size so each serverless job stays
within the 55-minute timeout. SeedVR2 models are downloaded via diagnostic
shell commands. The script is fully resumable — re-run it and it skips
files that already exist on the volume.

Usage:
    set -a && source .env && set +a

    # Full prepopulation (LTX-2.5 models + SeedVR2 + deps + verify)
    uv run python scripts/models/prepopulate_serverless.py

    # Specify endpoint ID explicitly
    uv run python scripts/models/prepopulate_serverless.py --endpoint-id cyas3eys1k3ihe

    # LTX-2.5 models only (skip SeedVR2 and deps)
    uv run python scripts/models/prepopulate_serverless.py --models-only

    # SeedVR2 only
    uv run python scripts/models/prepopulate_serverless.py --seedvr2-only

    # Deps only (custom node pip packages)
    uv run python scripts/models/prepopulate_serverless.py --deps-only

    # Dry run (show what would be downloaded, no API calls)
    uv run python scripts/models/prepopulate_serverless.py --dry-run

    # Verify only (check what's already on the volume)
    uv run python scripts/models/prepopulate_serverless.py --verify-only

    # Use a specific LTX-2.5 profile instead of full
    uv run python scripts/models/prepopulate_serverless.py --profile mid_vram_24gb

    # Include 7B SeedVR2 model (larger, better quality, ~15GB)
    uv run python scripts/models/prepopulate_serverless.py --seedvr2-7b

Environment:
    RUNPOD_API_KEY   RunPod API key (required, from .env)
    HF_TOKEN         HuggingFace token for gated LTX-2.5 repos (required for LTX-2.5)
    RUNPOD_ENDPOINT_ID  Override default endpoint ID

Prerequisites:
    - The serverless endpoint must be running the updated handler with
      action="download_models" and action="diagnostic" support.
    - HF_TOKEN must be set — LTX-2.5 is auto-gated on HuggingFace.
      Visit https://huggingface.co/Lightricks/LTX-2.5 and click "Agree and Access".
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_env_file = _PROJECT_ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k, _v)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: uv sync")
    sys.exit(1)


# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
class C:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    NC = "\033[0m"


def log_info(msg):  print(f"{C.BLUE}[INFO]{C.NC} {msg}")
def log_ok(msg):    print(f"{C.GREEN}[OK]{C.NC} {msg}")
def log_warn(msg):  print(f"{C.YELLOW}[WARN]{C.NC} {msg}")
def log_err(msg):   print(f"{C.RED}[ERROR]{C.NC} {msg}")
def log_step(msg):
    print(f"\n{C.BOLD}{C.BLUE}{'='*60}{C.NC}")
    print(f"{C.BOLD}{C.BLUE} {msg}{C.NC}")
    print(f"{C.BOLD}{C.BLUE}{'='*60}{C.NC}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq")
DEFAULT_PROFILE = "full_48gb"
MANIFEST_PATH = _PROJECT_ROOT / "config" / "ltx-2.5-models.json"
MODELS_OUTPUT_DIR = "/runpod-volume/models"
SEEDVR2_DIR = "/runpod-volume/models/SEEDVR2"
JOB_TIMEOUT = 3300        # 55 min (RunPod serverless max ~60 min)
POLL_INTERVAL = 5          # seconds between status polls
MAX_BATCH_SIZE_GB = 25     # group small models, split large ones

# SeedVR2 model definitions (from ComfyUI-SeedVR2_VideoUpscaler model_registry.py)
SEEDVR2_MODELS = [
    {
        "name": "SeedVR2 3B DiT (FP16)",
        "repo": "numz/SeedVR2_comfyUI",
        "file": "seedvr2_ema_3b_fp16.safetensors",
        "dest": SEEDVR2_DIR,
        "size_gb": 6.8,
        "required": True,
    },
    {
        "name": "SeedVR2 VAE (FP16)",
        "repo": "numz/SeedVR2_comfyUI",
        "file": "ema_vae_fp16.safetensors",
        "dest": SEEDVR2_DIR,
        "size_gb": 0.5,
        "required": True,
    },
    {
        "name": "SeedVR2 7B DiT (FP16)",
        "repo": "numz/SeedVR2_comfyUI",
        "file": "seedvr2_ema_7b_fp16.safetensors",
        "dest": SEEDVR2_DIR,
        "size_gb": 15.0,
        "required": False,  # optional, only with --seedvr2-7b
    },
]


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_model_ids(manifest: dict, profile: str) -> list[dict]:
    """Resolve a profile name to a list of model dicts."""
    models_by_id = {m["id"]: m for m in manifest["models"]}
    profiles = manifest.get("profiles", {})
    if profile not in profiles:
        available = ", ".join(sorted(profiles))
        raise SystemExit(f"Unknown profile '{profile}'. Available: {available}")
    wanted = profiles[profile]
    if wanted == ["all"]:
        wanted = list(models_by_id.keys())
    resolved = []
    for model_id in wanted:
        if model_id not in models_by_id:
            raise SystemExit(f"Unknown model id: {model_id}")
        resolved.append(models_by_id[model_id])
    return resolved


def estimate_size_gb(model: dict) -> float:
    """Estimate model size in GB from its description."""
    desc = model.get("desc", "")
    match = re.search(r"~?(\d+(?:\.\d+)?)\s*GB", desc)
    if match:
        return float(match.group(1))
    if model.get("symlink_target"):
        return 0.0
    return 1.0  # default for small files


def create_batches(models: list[dict], max_batch_gb: float = MAX_BATCH_SIZE_GB) -> list[list[dict]]:
    """Group models into batches, each under max_batch_gb.

    Large models (> max_batch_gb) get their own batch. Small models are
    greedily packed together.
    """
    # Sort largest-first so big models are handled individually
    sorted_models = sorted(models, key=estimate_size_gb, reverse=True)
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_size = 0.0

    for model in sorted_models:
        size = estimate_size_gb(model)
        if size >= max_batch_gb:
            # Flush current batch first
            if current:
                batches.append(current)
                current = []
                current_size = 0.0
            batches.append([model])
        elif current_size + size > max_batch_gb:
            batches.append(current)
            current = [model]
            current_size = size
        else:
            current.append(model)
            current_size += size

    if current:
        batches.append(current)
    return batches


# ---------------------------------------------------------------------------
# RunPod API helpers
# ---------------------------------------------------------------------------
def submit_job(endpoint_id: str, job_input: dict, api_key: str) -> str:
    """Submit a job to the serverless endpoint and return the job ID."""
    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"input": job_input},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Job submission failed: {resp.status_code} {resp.text[:500]}")
    data = resp.json()
    job_id = data.get("id")
    if not job_id:
        raise RuntimeError(f"No job ID in response: {json.dumps(data)[:300]}")
    return job_id


def poll_job(endpoint_id: str, job_id: str, api_key: str,
             timeout: int = JOB_TIMEOUT, label: str = "") -> dict:
    """Poll a job until it reaches a terminal state or timeout."""
    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
    start = time.time()
    while True:
        elapsed = int(time.time() - start)
        if elapsed > timeout:
            return {"status": "TIMEOUT", "elapsed": elapsed}
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            data = resp.json()
        except Exception as exc:
            print(f"  [{elapsed}s] poll error: {exc}", end="\r")
            time.sleep(POLL_INTERVAL)
            continue
        status = data.get("status", "")
        if status == "COMPLETED":
            return data
        elif status in ("FAILED", "CANCELLED"):
            return data
        else:
            print(f"  [{elapsed}s] {label or status}...", end="\r")
            time.sleep(POLL_INTERVAL)


def run_download_batch(endpoint_id: str, api_key: str, model_ids: list[str],
                       hf_token: Optional[str], dry_run: bool = False,
                       force: bool = False) -> tuple[str, dict]:
    """Submit a download_models job for a batch of LTX-2.5 model IDs."""
    job_input = {
        "action": "download_models",
        "manifest": "ltx-2.5",
        "ids": model_ids,
        "dry_run": dry_run,
        "force": force,
    }
    if hf_token:
        job_input["hf_token"] = hf_token
    job_id = submit_job(endpoint_id, job_input, api_key)
    result = poll_job(endpoint_id, job_id, api_key, label=f"batch {model_ids[0]}")
    return job_id, result


def run_diagnostic(endpoint_id: str, api_key: str, commands: list[str],
                   timeout: int = 30) -> list[dict]:
    """Run diagnostic commands on the endpoint and return results.

    Returns a list of per-command result dicts on success, or an empty
    list on failure — but always logs the actual job status and any error
    so the caller can see WHY it failed instead of a generic "no response".
    """
    job_input = {
        "action": "diagnostic",
        "commands": commands,
        "timeout": timeout,
    }
    job_id = submit_job(endpoint_id, job_input, api_key)
    # Poll timeout must account for: cold start + (num_commands × per_cmd_timeout)
    poll_timeout = len(commands) * timeout + 120
    result = poll_job(endpoint_id, job_id, api_key, timeout=poll_timeout,
                      label="diagnostic")
    status = result.get("status", "UNKNOWN")

    if status == "COMPLETED":
        output = result.get("output", {})
        if isinstance(output, dict):
            results = output.get("output", {}).get("results", [])
            if results:
                return results
            # COMPLETED but no results — log for debugging
            log_warn("Job COMPLETED but returned no results")
            log_warn(f"  Output: {json.dumps(output)[:500]}")
            return []
        else:
            log_warn(f"Job COMPLETED but output is not a dict: {type(output).__name__}")
            log_warn(f"  Raw: {json.dumps(result)[:500]}")
            return []

    # Non-COMPLETED — log the actual status and error details
    if status == "TIMEOUT":
        log_err(f"Diagnostic job timed out after {poll_timeout}s "
                f"(per-cmd timeout: {timeout}s, {len(commands)} commands)")
        log_err("  The endpoint may be cold-starting or the commands are too slow.")
        log_err("  Try reducing the number of commands or increasing the timeout.")
    elif status == "FAILED":
        error = result.get("error", "no error field in response")
        log_err(f"Diagnostic job FAILED: {error[:500]}")
    elif status == "CANCELLED":
        log_warn("Diagnostic job was CANCELLED")
    else:
        log_err(f"Diagnostic job returned unexpected status: {status}")
        log_err(f"  Raw response: {json.dumps(result)[:500]}")

    return []


# ---------------------------------------------------------------------------
# Download phases
# ---------------------------------------------------------------------------
def download_ltx_models(endpoint_id: str, api_key: str, models: list[dict],
                         hf_token: Optional[str], dry_run: bool = False,
                         force: bool = False, batch_size_gb: float = MAX_BATCH_SIZE_GB) -> bool:
    """Download all LTX-2.5 models in batches."""
    batches = create_batches(models, max_batch_gb=batch_size_gb)
    total = len(models)
    log_info(f"Downloading {total} LTX-2.5 models in {len(batches)} batches "
             f"(max {batch_size_gb}GB per batch)")

    total_dl = 0
    total_skip = 0
    total_fail = 0

    for i, batch in enumerate(batches, 1):
        batch_ids = [m["id"] for m in batch]
        batch_size = sum(estimate_size_gb(m) for m in batch)
        log_step(f"Batch {i}/{len(batches)}: {', '.join(batch_ids)} (~{batch_size:.1f}GB)")

        if dry_run:
            for m in batch:
                tag = f"~{estimate_size_gb(m):.1f}GB" if estimate_size_gb(m) > 0 else "tiny"
                print(f"  [dry-run] {m['id']}: {tag} — {m.get('desc', '')[:80]}")
            continue

        job_id, result = run_download_batch(
            endpoint_id, api_key, batch_ids, hf_token,
            dry_run=False, force=force,
        )
        status = result.get("status", "UNKNOWN")

        if status == "COMPLETED":
            output = result.get("output", {})
            if isinstance(output, dict):
                dl = output.get("downloaded", 0)
                sk = output.get("skipped", 0)
                fl = output.get("failed", 0)
                total_dl += dl
                total_skip += sk
                total_fail += fl
                if fl > 0:
                    log_warn(f"  Downloaded: {dl}, Skipped: {sk}, Failed: {fl}")
                    stdout = output.get("stdout", "")
                    for line in stdout.splitlines():
                        if "[FAIL]" in line:
                            print(f"    {line.strip()}")
                else:
                    log_ok(f"  Downloaded: {dl}, Skipped: {sk}")
        elif status == "TIMEOUT":
            log_warn(f"  Batch timed out — re-run to resume (skips existing files)")
            total_fail += len(batch)
        elif status == "FAILED":
            total_fail += len(batch)
            error = result.get("error", "")
            log_err(f"  Batch failed: {error[:300]}")
        else:
            log_warn(f"  Batch status: {status}")

    log_step("LTX-2.5 Download Summary")
    log_info(f"  Total models: {total}")
    log_ok(f"  Downloaded:   {total_dl}")
    log_info(f"  Skipped:      {total_skip} (already on volume)")
    if total_fail:
        log_err(f"  Failed:       {total_fail}")
        log_info("  Re-run the script to retry failed downloads (resumable).")
    else:
        log_ok(f"  Failed:       0")
    return total_fail == 0


def download_seedvr2(endpoint_id: str, api_key: str, hf_token: Optional[str],
                      include_7b: bool = False, dry_run: bool = False) -> bool:
    """Download SeedVR2 models via diagnostic shell commands."""
    models = [m for m in SEEDVR2_MODELS if m["required"] or include_7b]
    log_info(f"Downloading {len(models)} SeedVR2 models to {SEEDVR2_DIR}")

    if dry_run:
        for m in models:
            tag = "REQUIRED" if m["required"] else "optional"
            print(f"  [dry-run] [{tag}] {m['name']} ({m['size_gb']}GB)")
            print(f"           {m['repo']}/{m['file']} -> {m['dest']}/{m['file']}")
        return True

    all_ok = True
    for model in models:
        dest_file = f"{model['dest']}/{model['file']}"
        log_step(f"SeedVR2: {model['name']} ({model['size_gb']}GB)")

        # Check if already exists
        check_cmd = f"test -f '{dest_file}' && echo 'EXISTS' || echo 'MISSING'"
        results = run_diagnostic(endpoint_id, api_key, [check_cmd], timeout=15)
        if results and "EXISTS" in results[0].get("stdout", ""):
            log_ok(f"  Already exists, skipping")
            continue

        # Download via hf (new HuggingFace CLI) or huggingface-cli (legacy)
        # The worker may have either `hf` or `huggingface-cli` installed
        hf_cmd = (
            f"mkdir -p {model['dest']} && "
            f"(hf download {model['repo']} {model['file']} "
            f"--local-dir {model['dest']} 2>&1 || "
            f"huggingface-cli download {model['repo']} {model['file']} "
            f"--local-dir {model['dest']} --local-dir-use-symlinks False 2>&1 || "
            f"python -c \"from huggingface_hub import hf_hub_download; "
            f"hf_hub_download('{model['repo']}', '{model['file']}', "
            f"local_dir='{model['dest']}')\" 2>&1)"
        )
        # Set HF token if available
        if hf_token:
            hf_cmd = f"export HF_TOKEN={hf_token} && {hf_cmd}"

        timeout = max(300, int(model["size_gb"] * 60))
        log_info(f"  Downloading from {model['repo']} (timeout: {timeout}s)...")

        results = run_diagnostic(endpoint_id, api_key, [hf_cmd], timeout=timeout)
        if results:
            stdout = results[0].get("stdout", "")
            stderr = results[0].get("stderr", "")
            rc = results[0].get("returncode", -1)
            if rc == 0:
                log_ok(f"  Downloaded successfully")
            else:
                log_err(f"  Download failed (exit {rc})")
                if stderr:
                    log_err(f"  stderr: {stderr[:300]}")
                if stdout:
                    print(f"  stdout: {stdout[-300:]}")
                all_ok = False
        else:
            log_err(f"  No response from diagnostic")
            all_ok = False

    return all_ok


def install_deps(endpoint_id: str, api_key: str, dry_run: bool = False) -> bool:
    """Install custom node pip dependencies on the worker."""
    log_step("Custom Node Dependencies")

    if dry_run:
        log_info("  [dry-run] Would check and install custom node deps via uv pip")
        return True

    # Check what's already installed
    results = run_diagnostic(endpoint_id, api_key, [
        "ls /comfyui/custom_nodes/ | head -30",
        "test -f /workspace/custom-nodes-requirements.txt && echo 'EXISTS' || echo 'MISSING'",
        "/comfyui/venv/bin/python -c 'import torch; print(f\"torch {torch.__version__}\")' 2>&1",
    ], timeout=30)

    if not results:
        log_err("Failed to check worker state")
        return False

    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
        if r.get("stderr") and r.get("returncode", 0) != 0:
            log_warn(f"  {r['stderr'][:200]}")

    # Install deps using uv pip (batched to avoid timeout)
    install_cmd = (
        "cd /workspace && "
        "uv pip install --python /comfyui/venv/bin/python "
        "-r custom-nodes-requirements.txt 2>&1 | tail -30"
    )
    log_info("Installing custom node dependencies (may take several minutes)...")
    results = run_diagnostic(endpoint_id, api_key, [install_cmd], timeout=300)

    if results:
        stdout = results[0].get("stdout", "")
        stderr = results[0].get("stderr", "")
        rc = results[0].get("returncode", -1)
        if rc == 0:
            log_ok("Custom node dependencies installed")
        else:
            log_warn(f"Installation exited with code {rc}")
        if stdout:
            print(stdout[-500:])
        if stderr:
            print(stderr[-500:])

    return True


def verify(endpoint_id: str, api_key: str) -> bool:
    """Verify models and deps are in place on the volume.

    Commands are split into two batches to avoid timeout — the handler runs
    them sequentially, so 7 commands at 60s each could take 420s, exceeding
    a single poll window.
    """
    log_step("Verification")

    # Batch 1: system info + model listing (fast commands)
    results = run_diagnostic(endpoint_id, api_key, [
        "echo '=== GPU ===' && nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv",
        "echo '=== Disk ===' && df -h /runpod-volume",
        "echo '=== LTX-2.5 Models ===' && find /runpod-volume/models -type f \\( -name '*ltx-2.5*' -o -name '*gemma4*' \\) 2>/dev/null | sort",
        "echo '=== SeedVR2 Models ===' && ls -lh /runpod-volume/models/SEEDVR2/ 2>/dev/null",
    ], timeout=30)

    if not results:
        log_err("Verification failed — no response from endpoint (batch 1)")
        return False

    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
        if r.get("stderr") and r.get("returncode", 0) != 0:
            log_warn(f"  {r['stderr'][:200]}")

    # Batch 2: disk usage + environment (potentially slower commands)
    results = run_diagnostic(endpoint_id, api_key, [
        "echo '=== Model Dirs ===' && du -sh /runpod-volume/models/*/ 2>/dev/null",
        "echo '=== Custom Nodes ===' && ls /comfyui/custom_nodes/ | wc -l",
        "echo '=== Python ===' && /comfyui/venv/bin/python -c 'import torch; print(f\"torch {torch.__version__}, CUDA {torch.version.cuda}\")' 2>&1",
    ], timeout=60)

    if not results:
        log_err("Verification failed — no response from endpoint (batch 2)")
        return False

    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
        if r.get("stderr") and r.get("returncode", 0) != 0:
            log_warn(f"  {r['stderr'][:200]}")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Prepopulate a RunPod serverless endpoint with all models and dependencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--endpoint-id", default=DEFAULT_ENDPOINT_ID,
        help=f"Serverless endpoint ID (default: {DEFAULT_ENDPOINT_ID})",
    )
    parser.add_argument(
        "--profile", default=DEFAULT_PROFILE,
        help=f"LTX-2.5 model profile (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument("--models-only", action="store_true", help="Only download LTX-2.5 models")
    parser.add_argument("--seedvr2-only", action="store_true", help="Only download SeedVR2 models")
    parser.add_argument("--deps-only", action="store_true", help="Only install custom node deps")
    parser.add_argument("--verify-only", action="store_true", help="Only verify what's on the volume")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    parser.add_argument("--seedvr2-7b", action="store_true", help="Also download SeedVR2 7B model (~15GB)")
    parser.add_argument("--batch-size", type=float, default=MAX_BATCH_SIZE_GB,
                        help=f"Max batch size in GB (default: {MAX_BATCH_SIZE_GB})")
    args = parser.parse_args()

    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        log_err("RUNPOD_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    # Header
    print("=" * 60)
    print(f"{C.BOLD}RunPod Serverless Prepopulation{C.NC}")
    print(f"  Endpoint:  {args.endpoint_id}")
    print(f"  Profile:   {args.profile}")
    print(f"  HF Token:  {'set' if hf_token else 'NOT SET'}")
    print(f"  SeedVR2:   {'3B + 7B' if args.seedvr2_7b else '3B only'}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"  Force:     {args.force}")
    print(f"  Batch:     {args.batch_size}GB max")
    print("=" * 60)

    if not hf_token and not args.dry_run and not args.seedvr2_only and not args.deps_only:
        log_warn("HF_TOKEN not set — gated LTX-2.5 repos will fail.")
        log_warn("Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'.")

    # Verify only
    if args.verify_only:
        verify(args.endpoint_id, api_key)
        return

    ok = True

    # LTX-2.5 models
    if not args.seedvr2_only and not args.deps_only:
        manifest = load_manifest()
        models = resolve_model_ids(manifest, args.profile)
        ok = download_ltx_models(
            args.endpoint_id, api_key, models, hf_token,
            dry_run=args.dry_run, force=args.force,
            batch_size_gb=args.batch_size,
        ) and ok

    # SeedVR2 models
    if not args.models_only and not args.deps_only:
        ok = download_seedvr2(
            args.endpoint_id, api_key, hf_token,
            include_7b=args.seedvr2_7b, dry_run=args.dry_run,
        ) and ok

    # Custom node deps
    if not args.models_only and not args.seedvr2_only:
        install_deps(args.endpoint_id, api_key, dry_run=args.dry_run)

    # Verify
    if not args.dry_run:
        verify(args.endpoint_id, api_key)

    # Summary
    print()
    print("=" * 60)
    if ok:
        log_ok(f"{C.BOLD}Prepopulation complete!{C.NC}")
    else:
        log_warn(f"{C.BOLD}Prepopulation completed with issues.{C.NC}")
        log_info("Re-run the script to retry failed downloads (resumable).")
    print("=" * 60)


if __name__ == "__main__":
    main()
