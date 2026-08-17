#!/usr/bin/env python3
"""
Set up a 48GB RunPod serverless endpoint for LTX-2.5 near-1080p generation.

Steps:
  1. List current models on the volume (via existing endpoint diagnostic)
  2. Purge unnecessary models (FP8, GGUF Q8, LTX-2.3 models)
  3. Create a new 48GB (A6000) serverless endpoint
  4. Download required models (int8-convrot dev, upscalers, IC-LoRAs)
  5. Test the new endpoint with a simple workflow
  6. Optionally destroy the old 24GB endpoint

Usage:
    set -a && source .env && set +a

    # Full setup (interactive — asks before each destructive step)
    uv run python scripts/setup_48gb_endpoint.py

    # List models only (no changes)
    uv run python scripts/setup_48gb_endpoint.py --list-only

    # Skip confirmation prompts (automated)
    uv run python scripts/setup_48gb_endpoint.py --yes

    # Don't destroy old endpoint
    uv run python scripts/setup_48gb_endpoint.py --keep-old
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Run: uv sync")
    sys.exit(1)


class C:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def log_info(msg): print(f"{C.BLUE}[INFO]{C.NC} {msg}")
def log_ok(msg): print(f"{C.GREEN}[OK]{C.NC} {msg}")
def log_warn(msg): print(f"{C.YELLOW}[WARN]{C.NC} {msg}")
def log_err(msg): print(f"{C.RED}[ERROR]{C.NC} {msg}")


# Old endpoint (24GB) — used for diagnostics before the new one is ready
OLD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq")
VOLUME_ID = "el6aj9vatl"
DOCKER_IMAGE = "ghcr.io/alterpeace/runpod-comfy:latest"

# Models to KEEP on the volume
KEEP_MODELS = [
    "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",  # text encoder
    "ltx-2.5-video-vae-bf16.safetensors",  # VAE
    "ltx-2.5-22b-distilled-lora-450-bf16.safetensors",  # distilled LoRA
    "LTX-2.5-Distilled-Q4_K_M.gguf",  # GGUF Q4 (fallback for 24GB)
]

# Models to PURGE (unnecessary for 48GB int8-convrot workflow)
PURGE_PATTERNS = [
    "ltx-2.5-fp8",  # FP8 model (~19GB) — not needed, using int8
    "LTX-2.5-Distilled-Q8_0.gguf",  # GGUF Q8 (~20GB) — not needed
    "ltx-2.3-",  # All LTX-2.3 models — not needed for 2.5
    "ltx-2-19b-",  # Old LTX-2 19b models
]

# Models to DOWNLOAD for the 48GB workflow
DOWNLOAD_MODELS = [
    {
        "name": "int8-convrot dev transformer",
        "file": "ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors",
        "repo": "Lightricks/LTX-2.5",
        "path": "diffusion_models/",
        "dest": "checkpoints",
        "size_gb": 22,
        "required": True,
    },
    {
        "name": "latent spatial upscaler x2",
        "file": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
        "repo": "Lightricks/LTX-2.5",
        "path": "latent_upscale_models/",
        "dest": "latent_upscale_models",
        "size_gb": 1,
        "required": True,
    },
    {
        "name": "IC-LoRA pixel-spatial upscaler x2",
        "file": "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        "repo": "Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler",
        "path": "",
        "dest": "loras",
        "size_gb": 1,
        "required": True,
    },
    {
        "name": "IC-LoRA decompression (optional)",
        "file": "ltx-2.3-22b-ic-lora-decompression-0.9.safetensors",
        "repo": "Lightricks/LTX-2.3-22b-IC-LoRA-Decompression",
        "path": "",
        "dest": "loras",
        "size_gb": 1,
        "required": False,
    },
]


def run_diagnostic(endpoint_id, commands, timeout=30):
    """Run diagnostic commands on a serverless endpoint."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(endpoint_id)

    job = endpoint.run({
        "input": {
            "action": "diagnostic",
            "commands": commands,
            "timeout": timeout,
        }
    })

    start = time.time()
    while job.status() in ["IN_QUEUE", "IN_PROGRESS"]:
        time.sleep(5)
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] {job.status()}...", end="\r")

    status = job.status()
    elapsed = int(time.time() - start)
    print(f"  {status} ({elapsed}s)")

    output = job.output()
    if output is None:
        log_err(f"Diagnostic job {status} with no output")
        return None

    if output.get("status") != "success":
        log_err(f"Diagnostic failed: {output.get('error', 'unknown')}")
        return None

    return output.get("output", {}).get("results", [])


def list_models_on_volume(endpoint_id):
    """List all model files on the volume."""
    log_info("Listing models on volume...")
    results = run_diagnostic(endpoint_id, [
        "find /runpod-volume/models -type f -name '*.safetensors' -o -name '*.gguf' -o -name '*.pth' 2>/dev/null | sort",
        "du -sh /runpod-volume/models/checkpoints/ /runpod-volume/models/unet/ /runpod-volume/models/loras/ /runpod-volume/models/vae/ /runpod-volume/models/latent_upscale_models/ 2>/dev/null",
        "df -h /runpod-volume",
    ], timeout=30)

    if not results:
        return

    print()
    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
        if r.get("stderr") and r["returncode"] != 0:
            log_warn(f"stderr: {r['stderr'][:200]}")
    print()


def purge_models(endpoint_id, dry_run=False):
    """Purge unnecessary models from the volume."""
    log_info("Checking for models to purge...")

    # First, list all model files
    results = run_diagnostic(endpoint_id, [
        "find /runpod-volume/models -type f \\( -name '*.safetensors' -o -name '*.gguf' \\) 2>/dev/null | sort",
    ], timeout=30)

    if not results:
        return

    all_files = results[0].get("stdout", "").strip().split("\n")
    all_files = [f for f in all_files if f]

    # Identify files to purge
    to_purge = []
    for filepath in all_files:
        filename = os.path.basename(filepath)
        should_keep = any(keep in filename for keep in KEEP_MODELS)
        should_purge = any(pattern in filename for pattern in PURGE_PATTERNS)
        if should_purge and not should_keep:
            to_purge.append(filepath)

    if not to_purge:
        log_ok("No unnecessary models found to purge.")
        return

    log_warn(f"Found {len(to_purge)} files to purge:")
    for f in to_purge:
        print(f"  {f}")

    if dry_run:
        log_info("Dry run — not deleting. Run without --dry-run to purge.")
        return

    # Delete the files
    delete_commands = [f"rm -f {' '.join(to_purge)}"]
    # Also clean up empty directories
    delete_commands.append("find /runpod-volume/models -type d -empty -delete 2>/dev/null")

    log_info("Purging models...")
    results = run_diagnostic(endpoint_id, delete_commands, timeout=30)
    if results:
        log_ok(f"Purged {len(to_purge)} files")
        # Show remaining space
        results = run_diagnostic(endpoint_id, ["df -h /runpod-volume"], timeout=15)
        if results and results[0].get("stdout"):
            print(f"  {results[0]['stdout']}")


def create_48gb_endpoint():
    """Create a new 48GB serverless endpoint."""
    log_info("Creating 48GB (A6000) serverless endpoint...")

    runpod.api_key = os.environ["RUNPOD_API_KEY"]

    endpoint_config = {
        "name": "comfyui-48gb",
        "imageName": DOCKER_IMAGE,
        "gpuTypeId": "NVIDIA RTX A6000",
        "scalerType": "QUEUE_DELAY",
        "scalerValue": 5,
        "workersMin": 0,
        "workersMax": 3,
        "volumeMountPath": "/runpod-volume",
        "networkVolumeId": VOLUME_ID,
        "env": [
            {"key": "MODE", "value": "serverless"},
            {"key": "COMFYUI_PORT", "value": "8188"},
            # NO --lowvram on 48GB — model fits in VRAM at full speed
            {"key": "COMFYUI_ARGS", "value": ""},
        ],
    }

    try:
        response = runpod.create_endpoint(**endpoint_config)
        endpoint_id = response.get("id", "N/A")
        log_ok(f"Endpoint created: {endpoint_id}")
        log_info(f"  GPU: NVIDIA RTX A6000 (48GB)")
        log_info(f"  Image: {DOCKER_IMAGE}")
        log_info(f"  Volume: {VOLUME_ID}")
        log_info(f"  COMFYUI_ARGS: (empty — no --lowvram, model fits in VRAM)")
        return endpoint_id
    except Exception as e:
        log_err(f"Failed to create endpoint: {e}")
        return None


def download_models(endpoint_id, models, dry_run=False):
    """Download models to the volume via diagnostic action."""
    if dry_run:
        log_info("Dry run — would download:")
        for m in models:
            status = "REQUIRED" if m["required"] else "optional"
            print(f"  [{status}] {m['name']} ({m['size_gb']}GB) -> {m['dest']}/{m['file']}")
        return

    for model in models:
        log_info(f"Downloading: {model['name']} ({model['size_gb']}GB)...")

        # Build the download command using huggingface-cli or wget
        # The worker has huggingface-cli installed (via the Docker image)
        hf_path = f"{model['path']}{model['file']}" if model["path"] else model["file"]
        dest_dir = f"/runpod-volume/models/{model['dest']}"
        dest_file = f"{dest_dir}/{model['file']}"

        # Check if file already exists
        check_cmd = f"test -f '{dest_file}' && echo 'EXISTS' || echo 'MISSING'"
        results = run_diagnostic(endpoint_id, [check_cmd], timeout=15)

        if results and "EXISTS" in results[0].get("stdout", ""):
            log_ok(f"  Already exists, skipping")
            continue

        # Download using huggingface-cli
        download_cmd = (
            f"mkdir -p {dest_dir} && "
            f"huggingface-cli download {model['repo']} {hf_path} "
            f"--local-dir {dest_dir} --local-dir-use-symlinks False 2>&1"
        )

        # Use a longer timeout for large models
        timeout = max(300, model["size_gb"] * 30)
        log_info(f"  Downloading from {model['repo']} (timeout: {timeout}s)...")

        results = run_diagnostic(endpoint_id, [download_cmd], timeout=timeout)

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
                    print(f"  stdout: {stdout[:300]}")


def test_endpoint(endpoint_id):
    """Test the new endpoint with a simple diagnostic."""
    log_info(f"Testing endpoint {endpoint_id}...")

    results = run_diagnostic(endpoint_id, [
        "nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv",
        "ls -la /runpod-volume/models/checkpoints/ 2>/dev/null | head -10",
        "ls -la /runpod-volume/models/loras/ 2>/dev/null | head -10",
        "ls -la /runpod-volume/models/latent_upscale_models/ 2>/dev/null | head -10",
    ], timeout=30)

    if not results:
        log_err("Test failed — no response from endpoint")
        return False

    print()
    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
    print()

    # Check if GPU has 48GB
    gpu_info = results[0].get("stdout", "")
    if "A6000" in gpu_info or "48" in gpu_info:
        log_ok("GPU verified: 48GB A6000")
        return True
    else:
        log_warn(f"GPU info: {gpu_info.strip()}")
        return True  # Don't fail on this — might be different GPU name


def destroy_endpoint(endpoint_id):
    """Destroy a serverless endpoint."""
    log_warn(f"Destroying endpoint {endpoint_id}...")

    runpod.api_key = os.environ["RUNPOD_API_KEY"]

    try:
        # RunPod SDK doesn't have a direct delete_endpoint method
        # We need to use the API directly
        import requests
        headers = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"}
        url = f"https://api.runpod.ai/v2/{endpoint_id}"
        response = requests.delete(url, headers=headers)

        if response.status_code == 200:
            log_ok(f"Endpoint {endpoint_id} destroyed")
        else:
            log_err(f"Failed to destroy endpoint: {response.status_code} {response.text[:200]}")
    except Exception as e:
        log_err(f"Failed to destroy endpoint: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Set up a 48GB RunPod serverless endpoint for LTX-2.5 near-1080p generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list-only", action="store_true", help="Only list models on volume, don't make changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--keep-old", action="store_true", help="Don't destroy the old 24GB endpoint")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    parser.add_argument("--old-endpoint-id", default=OLD_ENDPOINT_ID, help="Old endpoint ID (default: from .env)")
    parser.add_argument("--volume-id", default=VOLUME_ID, help="Network volume ID")
    args = parser.parse_args()

    if not os.environ.get("RUNPOD_API_KEY"):
        log_err("RUNPOD_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    print("=" * 70)
    print(f"{C.BOLD}48GB Serverless Endpoint Setup{C.NC}")
    print(f"Old endpoint: {args.old_endpoint_id}")
    print(f"Volume: {args.volume_id}")
    print(f"New GPU: NVIDIA RTX A6000 (48GB)")
    print(f"COMFYUI_ARGS: (empty — no --lowvram)")
    print("=" * 70)

    # Step 1: List current models
    print()
    log_info(f"{C.BOLD}Step 1: List current models on volume{C.NC}")
    list_models_on_volume(args.old_endpoint_id)

    if args.list_only:
        return

    # Step 2: Purge unnecessary models
    print()
    log_info(f"{C.BOLD}Step 2: Purge unnecessary models{C.NC}")
    if not args.yes:
        confirm = input("Purge unnecessary models? (yes/no): ").strip().lower()
        if confirm != "yes":
            log_info("Skipping purge")
        else:
            purge_models(args.old_endpoint_id, dry_run=args.dry_run)
    else:
        purge_models(args.old_endpoint_id, dry_run=args.dry_run)

    if args.dry_run:
        log_info("Dry run — skipping endpoint creation and model download")
        return

    # Step 3: Create 48GB endpoint
    print()
    log_info(f"{C.BOLD}Step 3: Create 48GB endpoint{C.NC}")
    if not args.yes:
        confirm = input("Create new 48GB endpoint? (yes/no): ").strip().lower()
        if confirm != "yes":
            log_info("Skipping endpoint creation")
            return
    new_endpoint_id = create_48gb_endpoint()
    if not new_endpoint_id:
        log_err("Failed to create endpoint. Aborting.")
        sys.exit(1)

    # Wait for endpoint to be ready
    log_info("Waiting for endpoint to initialize (30s)...")
    time.sleep(30)

    # Step 4: Download models
    print()
    log_info(f"{C.BOLD}Step 4: Download required models{C.NC}")
    # Use the new endpoint for downloads (it has the same volume mounted)
    download_models(new_endpoint_id, DOWNLOAD_MODELS, dry_run=False)

    # Step 5: Test the new endpoint
    print()
    log_info(f"{C.BOLD}Step 5: Test the new endpoint{C.NC}")
    test_ok = test_endpoint(new_endpoint_id)

    if test_ok:
        log_ok(f"New endpoint {new_endpoint_id} is ready!")
        print()
        print(f"  {C.BOLD}Update your .env:{C.NC}")
        print(f"  RUNPOD_ENDPOINT_ID={new_endpoint_id}")
        print()
        print(f"  {C.BOLD}Test with alt_retake:{C.NC}")
        print(f"  uv run python scripts/invoke/alt_retake.py --video rhizome.mp4 \\")
        print(f"      --endpoint-id {new_endpoint_id} \\")
        print(f"      --workflow examples/ltx25_v2v_redetail_comfortable_runpod.json")
    else:
        log_err("Endpoint test failed. Check the output above.")

    # Step 6: Destroy old endpoint
    if not args.keep_old and test_ok:
        print()
        log_info(f"{C.BOLD}Step 6: Destroy old 24GB endpoint{C.NC}")
        if not args.yes:
            confirm = input(f"Destroy old endpoint {args.old_endpoint_id}? (yes/no): ").strip().lower()
            if confirm == "yes":
                destroy_endpoint(args.old_endpoint_id)
            else:
                log_info("Keeping old endpoint")
        else:
            destroy_endpoint(args.old_endpoint_id)
    elif args.keep_old:
        log_info("Keeping old endpoint (--keep-old)")

    print()
    print("=" * 70)
    if test_ok:
        log_ok(f"{C.BOLD}Setup complete!{C.NC}")
        log_info(f"New endpoint: {new_endpoint_id}")
        log_info(f"Old endpoint: {args.old_endpoint_id} ({'destroyed' if not args.keep_old else 'kept'})")
    else:
        log_err("Setup incomplete — endpoint test failed")
    print("=" * 70)


if __name__ == "__main__":
    main()
