#!/usr/bin/env python3
"""
Invoke the LTX-2.5 V2V redetail workflow on RunPod serverless, uploading
the input video via the input_images mechanism.

Works around ComfyUI's path traversal check (is_within_directory uses
os.path.realpath which follows symlinks). Strategy:

1. Replace the existing symlink at /comfyui/input/rhizome.mp4 (which points
   to /runpod-volume/input/rhizome.mp4 — OUTSIDE the input dir) with a
   RELATIVE symlink: rhizome.mp4 -> rhizome_real.mp4 (within /comfyui/input/)
   This is done via the download_models action's symlink_target feature.

2. Upload the video as "rhizome_real.mp4" via input_images. The handler's
   upload_image writes to /comfyui/input/rhizome_real.mp4 (a real file).

3. The workflow references "rhizome.mp4" which is now a relative symlink to
   "rhizome_real.mp4" within the same directory. os.path.realpath resolves
   to /comfyui/input/rhizome_real.mp4 — WITHIN /comfyui/input/ — so the
   path traversal check passes.

Usage:
    set -a && source .env && set +a
    uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4
    uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4 --local-file /path/to/rhizome.mp4
"""
import argparse
import base64
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

DEFAULT_WORKFLOW = Path(__file__).parent.parent / "examples" / "ltx25_v2v_redetail_24gb_runpod.json"


def download_from_s3(key: str) -> bytes:
    """Download a file from the RunPod S3 volume."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
        region_name=os.environ["RUNPOD_S3_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )

    bucket = os.environ["RUNPOD_S3_BUCKET"]
    s3_key = f"input/{key}" if not key.startswith("input/") else key

    print(f"Downloading s3://{bucket}/{s3_key}...")
    response = s3.get_object(Bucket=bucket, Key=s3_key)
    data = response["Body"].read()
    print(f"  Downloaded {len(data):,} bytes")
    return data


def load_workflow(workflow_path: Path) -> dict:
    with open(workflow_path) as f:
        return json.load(f)


def patch_workflow(workflow: dict, video: str, prompt: str = None, negative: str = None, seed: int = None) -> dict:
    if "7" in workflow:
        workflow["7"]["inputs"]["video"] = video
    if prompt and "5" in workflow:
        workflow["5"]["inputs"]["text"] = prompt
    if negative and "6" in workflow:
        workflow["6"]["inputs"]["text"] = negative
    if seed is not None:
        if "22" in workflow:
            workflow["22"]["inputs"]["noise_seed"] = seed
        if "24" in workflow:
            workflow["24"]["inputs"]["noise_seed"] = seed
    return workflow


def create_relative_symlink(endpoint, video_filename: str) -> dict:
    """
    Step 1: Use download_models action to replace the existing symlink with
    a RELATIVE symlink within /comfyui/input/.

    Creates: /comfyui/input/<video_filename> -> <video_filename_stem>_real<ext>
    e.g. /comfyui/input/rhizome.mp4 -> rhizome_real.mp4 (relative)
    """
    stem = Path(video_filename).stem
    ext = Path(video_filename).suffix
    real_name = f"{stem}_real{ext}"

    inline_manifest = {
        "models": [
            {
                "id": "fix_symlink",
                "desc": f"Replace symlink with relative symlink within /comfyui/input/",
                "dest": "input",
                "file": video_filename,
                "symlink_target": real_name  # RELATIVE path — within /comfyui/input/
            }
        ],
        "profiles": {
            "fix": ["fix_symlink"]
        }
    }

    job_input = {
        "action": "download_models",
        "inline_manifest": inline_manifest,
        "profile": "fix",
        "output_dir": "/comfyui",
        "force": True,  # Overwrite existing symlink
    }

    print(f"\n=== Step 1: Creating relative symlink ===")
    print(f"  /comfyui/input/{video_filename} -> {real_name} (relative)")

    job = endpoint.run(job_input)
    while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
        time.sleep(2)

    output = job.output()
    stdout = output.get("output", {}).get("stdout", "")
    print(f"  Status: {job.status()}")
    for line in stdout.splitlines():
        if line.strip():
            print(f"  {line.strip()}")

    return {"real_name": real_name, "status": job.status(), "output": output}


def upload_and_run_workflow(endpoint, workflow: dict, video_filename: str, real_name: str,
                            video_data: bytes, timeout: int, wait: bool) -> dict:
    """
    Step 2: Upload the video as real_name via input_images, then run the workflow.
    The workflow references video_filename which is a relative symlink to real_name.
    """
    video_b64 = base64.b64encode(video_data).decode("utf-8")

    job_input = {
        "workflow": workflow,
        "input_images": {
            real_name: video_b64,  # Upload as the real filename
        },
        "timeout": timeout,
    }

    print(f"\n=== Step 2: Upload video and run workflow ===")
    print(f"  Uploading as: {real_name} ({len(video_data):,} bytes -> {len(video_b64):,} chars b64)")
    print(f"  Workflow video field: {video_filename} (symlink -> {real_name})")

    job = endpoint.run({"input": job_input})
    print(f"  Job ID: {job.job_id}")

    if not wait:
        print(f"\n  Job submitted. Check status later.")
        return {"job_id": job.job_id, "status": "SUBMITTED"}

    print(f"  Waiting for completion (timeout: {timeout}s)...")
    start = time.time()

    while True:
        status = job.status()

        if status == "COMPLETED":
            elapsed = time.time() - start
            result = job.output()
            print(f"\n✅ Completed in {elapsed:.0f}s")
            print(json.dumps(result, indent=2, default=str)[:3000])
            return result

        if status == "FAILED":
            result = job.output()
            print(f"\n❌ Job failed")
            print(json.dumps(result, indent=2, default=str)[:3000])
            return result

        if time.time() - start > timeout:
            print(f"\n⏱️  Timeout after {timeout}s (job still running: {job.job_id})")
            return {"job_id": job.job_id, "status": "TIMEOUT"}

        elapsed = int(time.time() - start)
        print(f"  [{elapsed:>4}s] {status}...", end="\r")
        time.sleep(3)


def main():
    parser = argparse.ArgumentParser(
        description="Invoke V2V workflow with video upload (bypasses symlink limitation)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video", required=True, help="Video filename (e.g. rhizome.mp4)")
    parser.add_argument("--local-file", type=Path, help="Local file to upload (instead of S3)")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW, help="Workflow JSON file")
    parser.add_argument("--prompt", help="Override positive prompt")
    parser.add_argument("--negative", help="Override negative prompt")
    parser.add_argument("--seed", type=int, help="Override noise seed")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and don't wait")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")

    args = parser.parse_args()

    # Get video data
    if args.local_file:
        print(f"Reading local file: {args.local_file}")
        video_data = args.local_file.read_bytes()
    else:
        video_data = download_from_s3(args.video)

    print(f"Video size: {len(video_data):,} bytes")

    # Load and patch workflow
    workflow = load_workflow(args.workflow)
    workflow = patch_workflow(
        workflow,
        video=args.video,
        prompt=args.prompt,
        negative=args.negative,
        seed=args.seed,
    )

    if args.dry_run:
        stem = Path(args.video).stem
        ext = Path(args.video).suffix
        real_name = f"{stem}_real{ext}"
        print(f"\n=== DRY RUN ===")
        print(f"Step 1: Create relative symlink /comfyui/input/{args.video} -> {real_name}")
        print(f"Step 2: Upload {len(video_data):,} bytes as {real_name} via input_images")
        print(f"Step 3: Run workflow with video={args.video}")
        print(json.dumps({"workflow": workflow, "timeout": args.timeout}, indent=2))
        return

    # Setup RunPod
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Step 1: Create relative symlink
    result = create_relative_symlink(endpoint, args.video)
    real_name = result["real_name"]

    if result["status"] != "COMPLETED":
        print(f"\n❌ Step 1 failed. Aborting.")
        print(json.dumps(result["output"], indent=2))
        sys.exit(1)

    # Step 2: Upload video and run workflow
    upload_and_run_workflow(
        endpoint,
        workflow,
        video_filename=args.video,
        real_name=real_name,
        video_data=video_data,
        timeout=args.timeout,
        wait=not args.no_wait,
    )


if __name__ == "__main__":
    main()
