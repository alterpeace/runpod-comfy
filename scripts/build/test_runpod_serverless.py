#!/usr/bin/env python3
"""
Test RunPod serverless endpoint: dry-run model check, then workflow execution.

Usage:
    uv run python scripts/build/test_runpod_serverless.py --check-models
    uv run python scripts/build/test_runpod_serverless.py --run-workflow text_to_video
    uv run python scripts/build/test_runpod_serverless.py --run-all
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Auto-load .env
def _load_dotenv():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

import requests

# Configuration
ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq")
API_KEY = os.environ.get("RUNPOD_API_KEY", "")
BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Colors
class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    NC = '\033[0m'


def submit_job(job_input: dict, timeout: int = 600) -> dict:
    """Submit a job and poll for completion."""
    print(f"  {C.DIM}Submitting job...{C.NC}")
    resp = requests.post(
        f"{BASE_URL}/run",
        json={"input": job_input},
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  {C.RED}Submit failed: HTTP {resp.status_code}{C.NC}")
        print(f"  {resp.text[:500]}")
        return {"status": "FAILED", "error": f"HTTP {resp.status_code}"}

    data = resp.json()
    job_id = data.get("id")
    print(f"  {C.DIM}Job ID: {job_id}{C.NC}")

    # Poll for completion
    start = time.time()
    last_status = ""
    while time.time() - start < timeout:
        time.sleep(5)
        resp = requests.get(
            f"{BASE_URL}/status/{job_id}",
            headers=HEADERS,
            timeout=30,
        )
        result = resp.json()
        status = result.get("status", "UNKNOWN")

        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"  {C.DIM}  [{elapsed}s] {status}{C.NC}")
            last_status = status

        if status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
            result["_elapsed"] = int(time.time() - start)
            return result

    return {"status": "TIMED_OUT", "_elapsed": timeout}


def check_endpoint_health():
    """Check endpoint health."""
    print(f"\n{C.CYAN}{'='*60}{C.NC}")
    print(f"{C.CYAN}Endpoint Health Check{C.NC}")
    print(f"{C.CYAN}{'='*60}{C.NC}")

    try:
        resp = requests.get(f"{BASE_URL}/health", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            health = resp.json()
            workers = health.get("workers", {})
            jobs = health.get("jobs", {})
            print(f"  {C.GREEN}Healthy{C.NC}")
            print(f"  Workers: idle={workers.get('idle', 0)}, ready={workers.get('ready', 0)}, "
                  f"running={workers.get('running', 0)}, throttled={workers.get('throttled', 0)}")
            print(f"  Jobs: queued={jobs.get('inQueue', 0)}, in_progress={jobs.get('inProgress', 0)}, "
                  f"completed={jobs.get('completed', 0)}, failed={jobs.get('failed', 0)}")
            return True
        else:
            print(f"  {C.RED}HTTP {resp.status_code}: {resp.text[:200]}{C.NC}")
            return False
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.NC}")
        return False


def check_models():
    """Run download_models dry-run to see what's on the volume."""
    print(f"\n{C.CYAN}{'='*60}{C.NC}")
    print(f"{C.CYAN}Model Check (dry-run, mid_vram_24gb profile){C.NC}")
    print(f"{C.CYAN}{'='*60}{C.NC}")

    result = submit_job({
        "action": "download_models",
        "manifest": "ltx-2.5",
        "profile": "mid_vram_24gb",
        "dry_run": True,
        "hf_token": os.environ.get("HF_TOKEN", ""),
    }, timeout=300)

    status = result.get("status")
    if status == "COMPLETED":
        output = result.get("output", {})
        stdout = output.get("output", {}).get("stdout", "")
        print(f"\n  {C.GREEN}Completed in {result.get('_elapsed', '?')}s{C.NC}")
        print(f"  {C.BOLD}Volume model status:{C.NC}")
        for line in stdout.strip().splitlines():
            if "[skip]" in line or "[exists]" in line:
                print(f"    {C.GREEN}✓{C.NC} {line.strip()}")
            elif "[missing]" in line or "[FAIL]" in line:
                print(f"    {C.RED}✗{C.NC} {line.strip()}")
            elif "[dry-run]" in line:
                # dry-run shows what WOULD be downloaded (i.e. not on volume)
                print(f"    {C.YELLOW}⚠{C.NC} {line.strip()}")
            else:
                print(f"    {line.strip()}")
        return output
    else:
        print(f"  {C.RED}Failed: {status}{C.NC}")
        error = result.get("output", result.get("error", ""))
        if error:
            print(f"  {json.dumps(error, indent=2)[:1000]}")
        return None


def download_missing_models():
    """Download all models for mid_vram_24gb profile."""
    print(f"\n{C.CYAN}{'='*60}{C.NC}")
    print(f"{C.CYAN}Downloading Models (mid_vram_24gb profile){C.NC}")
    print(f"{C.CYAN}{'='*60}{C.NC}")

    result = submit_job({
        "action": "download_models",
        "manifest": "ltx-2.5",
        "profile": "mid_vram_24gb",
        "hf_token": os.environ.get("HF_TOKEN", ""),
    }, timeout=3600)

    status = result.get("status")
    if status == "COMPLETED":
        output = result.get("output", {})
        dl_output = output.get("output", {})
        print(f"\n  {C.GREEN}Completed in {result.get('_elapsed', '?')}s{C.NC}")
        print(f"  Downloaded: {dl_output.get('downloaded', 0)}")
        print(f"  Skipped: {dl_output.get('skipped', 0)}")
        print(f"  Failed: {dl_output.get('failed', 0)}")
        return dl_output.get("failed", 0) == 0
    else:
        print(f"  {C.RED}Failed: {status}{C.NC}")
        return False


def run_workflow(name: str, workflow: dict, timeout: int = 600) -> bool:
    """Submit a workflow for execution."""
    print(f"\n{C.CYAN}{'='*60}{C.NC}")
    print(f"{C.CYAN}Workflow: {name}{C.NC}")
    print(f"{C.CYAN}{'='*60}{C.NC}")

    node_count = len(workflow)
    class_types = set()
    for node in workflow.values():
        if isinstance(node, dict):
            class_types.add(node.get("class_type", ""))
    print(f"  Nodes: {node_count}")
    print(f"  Types: {', '.join(sorted(class_types))}")

    result = submit_job({
        "action": "run_workflow",
        "workflow": workflow,
        "timeout": timeout,
    }, timeout=timeout + 120)  # extra buffer for cold start

    status = result.get("status")
    elapsed = result.get("_elapsed", "?")

    if status == "COMPLETED":
        output = result.get("output", {})
        if isinstance(output, dict) and output.get("status") == "success":
            images = output.get("output", {}).get("images", [])
            metadata = output.get("metadata", {})
            print(f"\n  {C.GREEN}✓ SUCCESS in {elapsed}s{C.NC}")
            print(f"    Execution time: {metadata.get('execution_time', '?')}s")
            print(f"    Outputs: {len(images)} file(s)")
            for img in images:
                print(f"      - {img.get('filename', '?')} ({img.get('type', '?')})")
            return True
        elif isinstance(output, dict) and output.get("status") == "error":
            error = output.get("error", {})
            metadata = output.get("metadata", {})
            print(f"\n  {C.RED}✗ ERROR in {elapsed}s{C.NC}")
            print(f"    Code: {error.get('code', '?')}")
            print(f"    Message: {error.get('message', '?')[:500]}")
            return False
        else:
            print(f"\n  {C.YELLOW}? COMPLETED but unexpected output format{C.NC}")
            print(f"    {json.dumps(output, indent=2, default=str)[:1000]}")
            return False
    else:
        print(f"\n  {C.RED}✗ {status} after {elapsed}s{C.NC}")
        output = result.get("output", "")
        error = result.get("error", "")
        if output:
            print(f"    Output: {json.dumps(output, indent=2, default=str)[:500]}")
        if error:
            print(f"    Error: {error}")
        return False


def load_workflow(path: str) -> dict:
    """Load a workflow JSON file."""
    full_path = PROJECT_ROOT / path
    with open(full_path) as f:
        return json.load(f)


# ============================================================================
# Workflow test definitions (simple -> complex)
# ============================================================================

WORKFLOW_TESTS = [
    {
        "name": "text_to_video (simplest — no input video)",
        "path": "examples/ltx25_text_to_video.json",
        "timeout": 300,
        "description": "Basic T2V: checkpoint + text encoder + KSampler + VAE decode. No IC-LoRA, no upscaler.",
    },
    {
        "name": "v2v_redetail_24gb_runpod (full pipeline)",
        "path": "examples/ltx25_v2v_redetail_24gb_runpod.json",
        "timeout": 600,
        "description": "Full V2V: checkpoint + text encoder + distilled LoRA + IC-LoRA + spatial upscaler + two-pass sampling.",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Test RunPod serverless endpoint")
    parser.add_argument("--check-models", action="store_true", help="Dry-run model check")
    parser.add_argument("--download-models", action="store_true", help="Download missing models")
    parser.add_argument("--run-workflow", type=str, help="Run a specific workflow by name")
    parser.add_argument("--run-all", action="store_true", help="Run all workflow tests (simple -> complex)")
    parser.add_argument("--health", action="store_true", help="Just check endpoint health")
    parser.add_argument("--endpoint-id", type=str, default=ENDPOINT_ID, help="RunPod endpoint ID")
    args = parser.parse_args()

    if args.endpoint_id != ENDPOINT_ID:
        _eid = args.endpoint_id
        # Update module-level references
        globals()["ENDPOINT_ID"] = _eid
        globals()["BASE_URL"] = f"https://api.runpod.ai/v2/{_eid}"

    if not API_KEY:
        print(f"{C.RED}Error: RUNPOD_API_KEY not set{C.NC}")
        sys.exit(1)

    print(f"{C.BOLD}RunPod Serverless Test{C.NC}")
    print(f"  Endpoint: {ENDPOINT_ID}")
    print(f"  URL: {BASE_URL}")

    # Always check health first
    healthy = check_endpoint_health()
    if not healthy:
        print(f"\n{C.RED}Endpoint not healthy — aborting{C.NC}")
        sys.exit(1)

    if args.health:
        sys.exit(0)

    if args.check_models:
        check_models()
        sys.exit(0)

    if args.download_models:
        success = download_missing_models()
        sys.exit(0 if success else 1)

    if args.run_workflow:
        # Find matching workflow
        for wf in WORKFLOW_TESTS:
            if args.run_workflow in wf["name"] or args.run_workflow in wf["path"]:
                workflow = load_workflow(wf["path"])
                success = run_workflow(wf["name"], workflow, wf["timeout"])
                sys.exit(0 if success else 1)
        # Try as a direct path
        try:
            workflow = load_workflow(args.run_workflow)
            success = run_workflow(args.run_workflow, workflow, 600)
            sys.exit(0 if success else 1)
        except FileNotFoundError:
            print(f"{C.RED}Workflow not found: {args.run_workflow}{C.NC}")
            print(f"Available: {[w['name'] for w in WORKFLOW_TESTS]}")
            sys.exit(1)

    if args.run_all:
        results = []
        for wf in WORKFLOW_TESTS:
            workflow = load_workflow(wf["path"])
            print(f"\n  {C.DIM}{wf['description']}{C.NC}")
            success = run_workflow(wf["name"], workflow, wf["timeout"])
            results.append((wf["name"], success))
            if not success:
                print(f"\n  {C.YELLOW}Stopping — fix this before proceeding to more complex workflows{C.NC}")
                break

        # Summary
        print(f"\n{C.BOLD}{'='*60}{C.NC}")
        print(f"{C.BOLD}Results Summary{C.NC}")
        print(f"{C.BOLD}{'='*60}{C.NC}")
        for name, passed in results:
            status = f"{C.GREEN}PASS{C.NC}" if passed else f"{C.RED}FAIL{C.NC}"
            print(f"  [{status}] {name}")

        all_passed = all(p for _, p in results)
        sys.exit(0 if all_passed else 1)

    # Default: check models then run all
    print(f"\n{C.YELLOW}No action specified. Use --check-models, --run-all, etc.{C.NC}")
    parser.print_help()


if __name__ == "__main__":
    main()
