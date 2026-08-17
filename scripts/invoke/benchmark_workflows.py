#!/usr/bin/env python3
"""
Benchmark all LTX-2.5 V2V workflows and generate a cost analysis.

Tests each workflow on a sample video, measures generation time, and
calculates the total cost to process a full directory of videos.

Usage:
    set -a && source .env && set +a

    # Benchmark all workflows on a sample video
    uv run python scripts/invoke/benchmark_workflows.py --video swa_aliens/clip_001.mp4

    # Benchmark with a specific directory size for cost projection
    uv run python scripts/invoke/benchmark_workflows.py --video swa_aliens/clip_001.mp4 \\
        --total-videos 156 --avg-duration 15

    # Skip workflows that require more VRAM than available
    uv run python scripts/invoke/benchmark_workflows.py --video swa_aliens/clip_001.mp4 \\
        --max-vram 24

    # Dry run (show what would be tested without running)
    uv run python scripts/invoke/benchmark_workflows.py --video swa_aliens/clip_001.mp4 --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent.parent / ".env"
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

# ---------------------------------------------------------------------------
# Workflow definitions
# ---------------------------------------------------------------------------
WORKFLOWS = [
    {
        "name": "entry_q4",
        "file": "examples/ltx25_v2v_redetail_entry_runpod.json",
        "model": "GGUF Q4 (~6 GB)",
        "resolution": "640x352",
        "vram_required": 10,
        "gpu_tier": "24GB+",
        "passes": "single (8 steps)",
    },
    {
        "name": "entry_fp8",
        "file": "examples/ltx25_v2v_redetail_entry_fp8.json",
        "model": "FP8 (~19 GB)",
        "resolution": "640x352",
        "vram_required": 22,
        "gpu_tier": "24GB+",
        "passes": "single (8 steps)",
    },
    {
        "name": "comfortable_int8",
        "file": "examples/ltx25_v2v_redetail_comfortable_runpod.json",
        "model": "int8-convrot (21.5 GB)",
        "resolution": "768x448 -> 1536x896",
        "vram_required": 48,
        "gpu_tier": "48GB+",
        "passes": "two-pass (8 + 3 steps)",
    },
]

# RunPod serverless pricing (USD per hour, approximate)
# Source: https://www.runpod.io/pricing
GPU_PRICING = {
    "NVIDIA RTX A4000": {"vram": 16, "price": 0.16},
    "NVIDIA RTX A5000": {"vram": 24, "price": 0.23},
    "NVIDIA RTX A6000": {"vram": 48, "price": 0.45},
    "NVIDIA RTX 4090": {"vram": 24, "price": 0.34},
    "NVIDIA L4": {"vram": 24, "price": 0.26},
    "NVIDIA L40S": {"vram": 48, "price": 0.55},
    "NVIDIA RTX 6000 Ada": {"vram": 48, "price": 0.60},
    "NVIDIA A100 80GB": {"vram": 80, "price": 1.10},
    "NVIDIA H100 80GB": {"vram": 80, "price": 2.49},
}


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


def load_workflow(workflow_path: str) -> dict:
    """Load a workflow JSON file."""
    full_path = Path(__file__).parent.parent.parent / workflow_path
    with open(full_path) as f:
        return json.load(f)


def run_benchmark(endpoint, workflow: dict, video_path: str, timeout: int = 600) -> dict:
    """Run a single benchmark and return timing results.

    Returns:
        dict with keys: status, time_seconds, error
    """
    wf = json.loads(json.dumps(workflow))

    # Strip _metadata key — the handler rejects it as a node
    wf.pop("_metadata", None)

    # Patch the workflow with the test video
    for node_id, node in wf.items():
        if node.get("class_type") == "VHS_LoadVideo":
            wf[node_id]["inputs"]["video"] = video_path
            wf[node_id]["inputs"]["force_rate"] = 24
            wf[node_id]["inputs"]["frame_load_cap"] = 48  # 2 seconds at 24fps
            break

    # Set a generic filename prefix
    for node_id, node in wf.items():
        if node_id == "_metadata":
            continue
        if node.get("class_type") == "VHS_VideoCombine":
            wf[node_id]["inputs"]["filename_prefix"] = f"benchmark/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            break

    start_time = time.time()

    job = endpoint.run({
        "input": {
            "workflow": wf,
            "timeout": timeout,
        }
    })

    # Wait for completion
    while job.status() in ["IN_QUEUE", "IN_PROGRESS"]:
        time.sleep(5)
        elapsed = int(time.time() - start_time)
        print(f"  [{elapsed}s] {job.status()}...", end="\r")

    status = job.status()
    elapsed = time.time() - start_time
    print(f"  {status} ({elapsed:.1f}s)")

    output = job.output()

    if output is None:
        return {
            "status": "failed",
            "time_seconds": elapsed,
            "error": f"Job {status} with no output (timeout or worker error)",
        }

    if output.get("status") == "success":
        return {
            "status": "success",
            "time_seconds": elapsed,
            "error": None,
        }

    error_msg = (
        output.get("error")
        or output.get("error_message")
        or output.get("metadata", {}).get("error_message")
        or str(output)[:500]
    )
    return {
        "status": "failed",
        "time_seconds": elapsed,
        "error": str(error_msg)[:500],
    }


def calculate_cost(time_per_video: float, total_videos: int, gpu_price_per_hr: float) -> dict:
    """Calculate total cost for processing a directory of videos."""
    total_seconds = time_per_video * total_videos
    total_hours = total_seconds / 3600
    total_cost = total_hours * gpu_price_per_hr
    return {
        "time_per_video": time_per_video,
        "total_videos": total_videos,
        "total_seconds": total_seconds,
        "total_hours": total_hours,
        "total_cost": total_cost,
        "gpu_price_per_hr": gpu_price_per_hr,
    }


def print_report(results: list, total_videos: int, avg_duration: float):
    """Print a formatted benchmark + cost analysis report."""
    print()
    print("=" * 80)
    print(f"{C.BOLD}BENCHMARK & COST ANALYSIS REPORT{C.NC}")
    print(f"Directory: {total_videos} videos, ~{avg_duration}s each")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Per-workflow results
    print()
    print(f"{C.BOLD}PER-WORKFLOW RESULTS{C.NC}")
    print("-" * 80)
    print(f"{'Workflow':<20} {'Model':<25} {'Resolution':<22} {'VRAM':<8} {'Time/Video':<12} {'Status'}")
    print("-" * 80)

    for r in results:
        wf = r["workflow"]
        time_str = f"{r['time_seconds']:.1f}s" if r["status"] == "success" else "N/A"
        status_str = f"{C.GREEN}OK{C.NC}" if r["status"] == "success" else f"{C.RED}FAILED{C.NC}"
        print(f"{wf['name']:<20} {wf['model']:<25} {wf['resolution']:<22} {wf['vram_required']}GB{'':<4} {time_str:<12} {status_str}")
        if r["status"] == "failed" and r.get("error"):
            print(f"  {C.RED}Error: {r['error'][:200]}{C.NC}")

    # Cost analysis
    print()
    print(f"{C.BOLD}COST ANALYSIS -- {total_videos} videos{C.NC}")
    print("-" * 80)

    for r in results:
        if r["status"] != "success":
            continue

        wf = r["workflow"]
        time_per_video = r["time_seconds"]

        print()
        print(f"  {C.BOLD}{wf['name']}{C.NC} ({wf['model']}, {wf['resolution']})")
        print(f"  Time per video: {time_per_video:.1f}s")
        print(f"  {'GPU':<25} {'VRAM':<8} {'$/hr':<8} {'Total Time':<18} {'Total Cost':<12} {'Fits?'}")
        print(f"  {'-'*78}")

        for gpu_name, gpu_info in sorted(GPU_PRICING.items(), key=lambda x: x[1]["price"]):
            fits = gpu_info["vram"] >= wf["vram_required"]
            if not fits:
                continue

            cost = calculate_cost(time_per_video, total_videos, gpu_info["price"])
            total_time_str = f"{cost['total_hours']:.1f}h ({cost['total_seconds']/60:.0f}min)"
            cost_str = f"${cost['total_cost']:.2f}"
            fits_str = f"{C.GREEN}yes{C.NC}" if fits else f"{C.RED}no{C.NC}"
            print(f"  {gpu_name:<25} {gpu_info['vram']}GB{'':<4} ${gpu_info['price']:<7.2f} {total_time_str:<18} {cost_str:<12} {fits_str}")

    # Summary
    print()
    print(f"{C.BOLD}SUMMARY{C.NC}")
    print("-" * 80)

    successful = [r for r in results if r["status"] == "success"]
    if not successful:
        print(f"  {C.RED}No workflows completed successfully.{C.NC}")
        return

    cheapest = None
    for r in successful:
        wf = r["workflow"]
        time_per_video = r["time_seconds"]
        for gpu_name, gpu_info in GPU_PRICING.items():
            if gpu_info["vram"] < wf["vram_required"]:
                continue
            cost = calculate_cost(time_per_video, total_videos, gpu_info["price"])
            if cheapest is None or cost["total_cost"] < cheapest["total_cost"]:
                cheapest = {
                    "workflow": wf["name"],
                    "gpu": gpu_name,
                    "total_cost": cost["total_cost"],
                    "total_hours": cost["total_hours"],
                    "resolution": wf["resolution"],
                }

    if cheapest:
        print(f"  Cheapest option: {C.GREEN}{cheapest['workflow']}{C.NC} on {C.GREEN}{cheapest['gpu']}{C.NC}")
        print(f"  Total cost: {C.GREEN}${cheapest['total_cost']:.2f}{C.NC} ({cheapest['total_hours']:.1f}h)")
        print(f"  Resolution: {cheapest['resolution']}")

    best_quality = max(successful, key=lambda r: r["workflow"]["vram_required"])
    print(f"  Best quality: {C.GREEN}{best_quality['workflow']}{C.NC} ({best_quality['workflow']['resolution']})")

    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark LTX-2.5 V2V workflows and generate cost analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video", required=True, help="Sample video path on the volume (e.g. swa_aliens/clip_001.mp4)")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per benchmark in seconds (default: 600)")
    parser.add_argument("--total-videos", type=int, default=156, help="Total videos in directory for cost projection (default: 156)")
    parser.add_argument("--avg-duration", type=float, default=15, help="Average video duration in seconds (default: 15)")
    parser.add_argument("--max-vram", type=int, default=0, help="Skip workflows requiring more than this VRAM (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be tested without running")
    parser.add_argument("--output", type=str, default=None, help="Save report to file (JSON)")
    args = parser.parse_args()

    if not os.environ.get("RUNPOD_API_KEY"):
        log_err("RUNPOD_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Filter workflows by VRAM limit
    workflows_to_test = WORKFLOWS
    if args.max_vram > 0:
        workflows_to_test = [w for w in WORKFLOWS if w["vram_required"] <= args.max_vram]
        skipped = [w for w in WORKFLOWS if w["vram_required"] > args.max_vram]
        for w in skipped:
            log_warn(f"Skipping {w['name']} (requires {w['vram_required']}GB, max is {args.max_vram}GB)")

    print("=" * 80)
    print(f"{C.BOLD}LTX-2.5 V2V Workflow Benchmark{C.NC}")
    print(f"Sample video: {args.video}")
    print(f"Endpoint: {args.endpoint_id}")
    print(f"Directory: {args.total_videos} videos, ~{args.avg_duration}s each")
    print(f"Workflows to test: {len(workflows_to_test)}")
    print("=" * 80)

    if args.dry_run:
        log_warn("DRY RUN -- no benchmarks will run")
        for w in workflows_to_test:
            print(f"  {w['name']}: {w['file']} ({w['model']}, {w['resolution']}, {w['vram_required']}GB)")
        return

    results = []
    for wf_def in workflows_to_test:
        print()
        log_info(f"Benchmarking: {wf_def['name']} ({wf_def['model']}, {wf_def['resolution']})")

        try:
            workflow = load_workflow(wf_def["file"])
        except FileNotFoundError:
            log_err(f"Workflow file not found: {wf_def['file']}")
            results.append({
                "workflow": wf_def,
                "status": "failed",
                "time_seconds": 0,
                "error": f"File not found: {wf_def['file']}",
            })
            continue

        result = run_benchmark(endpoint, workflow, args.video, timeout=args.timeout)
        result["workflow"] = wf_def
        results.append(result)

        if result["status"] == "success":
            log_ok(f"Completed in {result['time_seconds']:.1f}s")
        else:
            log_err(f"Failed: {result.get('error', 'unknown')[:200]}")

    # Print report
    print_report(results, args.total_videos, args.avg_duration)

    # Save JSON output if requested
    if args.output:
        report_data = {
            "generated": datetime.now().isoformat(),
            "sample_video": args.video,
            "endpoint_id": args.endpoint_id,
            "total_videos": args.total_videos,
            "avg_duration": args.avg_duration,
            "results": [
                {
                    "workflow": r["workflow"],
                    "status": r["status"],
                    "time_seconds": r["time_seconds"],
                    "error": r.get("error"),
                }
                for r in results
            ],
            "gpu_pricing": GPU_PRICING,
        }
        with open(args.output, "w") as f:
            json.dump(report_data, f, indent=2)
        log_ok(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()