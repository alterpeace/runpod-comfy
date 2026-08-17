#!/usr/bin/env python3
"""
Invoke the LTX-2.5 V2V redetail workflow on RunPod serverless.

Loads .env automatically, patches the workflow's input video path,
and invokes the endpoint.

Usage:
  # Single video
  uv run python scripts/invoke/invoke_v2v.py --video rhizome.mp4

  # Video in a subfolder (relative to /runpod-volume/input/)
  uv run python scripts/invoke/invoke_v2v.py --video sample/clip_001.mp4

  # Batch all mp4s in a directory on the volume
  uv run python scripts/invoke/invoke_v2v.py --video-dir sample/

  # Custom prompt
  uv run python scripts/invoke/invoke_v2v.py --video rhizome.mp4 \
    --prompt "cinematic, warm tones, shallow depth of field"

  # Override endpoint
  uv run python scripts/invoke/invoke_v2v.py --video rhizome.mp4 --endpoint-id abc123
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List

# Load .env
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            # Strip surrounding quotes
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Run: uv sync")
    sys.exit(1)


# Default workflow
DEFAULT_WORKFLOW = Path(__file__).parent.parent.parent / "examples" / "ltx25_v2v_redetail_24gb_runpod.json"


def list_remote_videos(prefix: str) -> List[str]:
    """List .mp4 files on the RunPod S3 volume under input/<prefix>."""
    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 not installed. Run: uv add boto3")
        sys.exit(1)

    endpoint = os.environ.get("RUNPOD_S3_ENDPOINT")
    region = os.environ.get("RUNPOD_S3_REGION")
    bucket = os.environ.get("RUNPOD_S3_BUCKET")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not all([endpoint, region, bucket, access_key, secret_key]):
        print("ERROR: RunPod S3 credentials not set in .env")
        print("Need: RUNPOD_S3_ENDPOINT, RUNPOD_S3_REGION, RUNPOD_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    # Normalize prefix: input/sample/ or input/sample
    s3_prefix = f"input/{prefix.strip('/')}/"
    videos = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".mp4"):
                # Return path relative to input/ (what VHS_LoadVideo expects)
                rel = key[len("input/"):]
                videos.append(rel)

    return sorted(videos)


def load_workflow(workflow_path: Path) -> dict:
    """Load and return the workflow JSON."""
    with open(workflow_path) as f:
        return json.load(f)


def patch_workflow(workflow: dict, video: str, prompt: str = None, negative: str = None, seed: int = None) -> dict:
    """Patch the workflow with the given video path and optional overrides."""
    # Patch video input (node 7 = VHS_LoadVideo)
    if "7" in workflow:
        workflow["7"]["inputs"]["video"] = video

    # Patch positive prompt (node 5 = CLIPTextEncode positive)
    if prompt and "5" in workflow:
        workflow["5"]["inputs"]["text"] = prompt

    # Patch negative prompt (node 6 = CLIPTextEncode negative)
    if negative and "6" in workflow:
        workflow["6"]["inputs"]["text"] = negative

    # Patch seed if specified
    if seed is not None:
        if "22" in workflow:
            workflow["22"]["inputs"]["noise_seed"] = seed
        if "24" in workflow:
            workflow["24"]["inputs"]["noise_seed"] = seed

    return workflow


def invoke(endpoint_id: str, workflow: dict, timeout: int = 600, wait: bool = True) -> dict:
    """Submit workflow to RunPod and optionally wait for completion."""
    runpod.api_key = os.environ.get("RUNPOD_API_KEY")
    if not runpod.api_key:
        print("ERROR: RUNPOD_API_KEY not set in .env or environment")
        sys.exit(1)

    endpoint = runpod.Endpoint(endpoint_id)

    print(f"Invoking endpoint: {endpoint_id}")
    print(f"Video: {workflow.get('7', {}).get('inputs', {}).get('video', '?')}")

    job = endpoint.run({"input": {"workflow": workflow, "timeout": timeout}})
    print(f"Job ID: {job.job_id}")

    if not wait:
        print(f"Job submitted. Check status with:")
        print(f"  uv run python lifecycle/runpod_serverless.py status --endpoint-id {endpoint_id} --job-id {job.job_id}")
        return {"job_id": job.job_id, "status": "SUBMITTED"}

    print(f"Waiting for completion (timeout: {timeout}s)...")
    start = time.time()

    while True:
        status = job.status()

        if status == "COMPLETED":
            elapsed = time.time() - start
            result = job.output()
            print(f"\n✅ Completed in {elapsed:.0f}s")
            print(json.dumps(result, indent=2, default=str)[:2000])
            return result

        if status == "FAILED":
            result = job.output()
            print(f"\n❌ Job failed")
            print(json.dumps(result, indent=2, default=str)[:2000])
            return result

        if time.time() - start > timeout:
            print(f"\n⏱️  Timeout after {timeout}s (job still running: {job.job_id})")
            return {"job_id": job.job_id, "status": "TIMEOUT"}

        elapsed = int(time.time() - start)
        print(f"  [{elapsed:>4}s] {status}...", end="\r")
        time.sleep(3)


def main():
    parser = argparse.ArgumentParser(
        description="Invoke LTX-2.5 V2V redetail on RunPod",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video", help="Video filename relative to /runpod-volume/input/")
    parser.add_argument("--video-dir", help="Process all .mp4 files in this dir (relative to input/)")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW, help="Workflow JSON file")
    parser.add_argument("--prompt", help="Override positive prompt")
    parser.add_argument("--negative", help="Override negative prompt")
    parser.add_argument("--seed", type=int, help="Override noise seed")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and don't wait for completion")
    parser.add_argument("--dry-run", action="store_true", help="Show patched workflow without invoking")

    args = parser.parse_args()

    if not args.video and not args.video_dir:
        parser.error("Specify --video or --video-dir")

    # Build list of videos to process
    videos = []
    if args.video:
        videos.append(args.video)
    elif args.video_dir:
        videos = list_remote_videos(args.video_dir)
        if not videos:
            print(f"No .mp4 files found on volume at input/{args.video_dir}")
            print(f"Upload with: uv run python scripts/storage/upload_to_runpod.py /path/to/videos --subfolder {args.video_dir}")
            sys.exit(1)
        print(f"Found {len(videos)} video(s) on volume:")
        for v in videos:
            print(f"  • {v}")
        print()

    for video in videos:
        print(f"\n{'='*60}")
        print(f"  Processing: {video}")
        print(f"{'='*60}\n")

        workflow = load_workflow(args.workflow)
        workflow = patch_workflow(
            workflow,
            video=video,
            prompt=args.prompt,
            negative=args.negative,
            seed=args.seed,
        )

        if args.dry_run:
            print(json.dumps(workflow, indent=2))
            continue

        invoke(
            endpoint_id=args.endpoint_id,
            workflow=workflow,
            timeout=args.timeout,
            wait=not args.no_wait,
        )


if __name__ == "__main__":
    main()
