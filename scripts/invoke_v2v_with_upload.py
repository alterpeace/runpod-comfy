#!/usr/bin/env python3
"""
Invoke the LTX-2.5 V2V redetail workflow on RunPod serverless, uploading
the input video via the input_files mechanism.

With the content type fix in comfyui_client.py (derives MIME type from
filename extension instead of hardcoded image/png), we can now upload
video files directly — no symlink workaround needed. The handler uploads
the file to ComfyUI's /upload/image endpoint, which saves it as a real
file in /comfyui/input/. Real files pass ComfyUI's is_within_directory
realpath check automatically.

Usage:
    set -a && source .env && set +a
    uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4
    uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4 --local-file /path/to/rhizome.mp4
    uv run python scripts/invoke_v2v_with_upload.py --video sample/clip_001.mp4 --prompt "cinematic"
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


def main():
    parser = argparse.ArgumentParser(
        description="Invoke V2V workflow with video upload via input_files",
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
    parser.add_argument("--dry-run", action="store_true", help="Show payload without invoking")

    args = parser.parse_args()

    # Get video data
    if args.local_file:
        print(f"Reading local file: {args.local_file}")
        video_data = args.local_file.read_bytes()
    else:
        video_data = download_from_s3(args.video)

    print(f"Video size: {len(video_data):,} bytes")

    # Base64 encode
    video_b64 = base64.b64encode(video_data).decode("utf-8")
    print(f"Base64 encoded: {len(video_b64):,} chars")

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
        print("\n=== DRY RUN ===")
        print(f"Upload: {args.video} ({len(video_data):,} bytes)")
        print(json.dumps({"workflow": workflow, "timeout": args.timeout}, indent=2))
        return

    # Submit job — use input_files (new name) which the handler accepts
    # alongside the legacy input_images key
    job_input = {
        "workflow": workflow,
        "input_files": {
            args.video: video_b64,
        },
        "timeout": args.timeout,
    }

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    print(f"\nInvoking endpoint: {args.endpoint_id}")
    print(f"Video: {args.video} (uploaded via input_files, {len(video_data):,} bytes)")
    print(f"Workflow: {args.workflow}")

    job = endpoint.run({"input": job_input})
    print(f"Job ID: {job.job_id}")

    if args.no_wait:
        print(f"\nJob submitted. Check status later.")
        return

    print(f"\nWaiting for completion (timeout: {args.timeout}s)...")
    start = time.time()

    while True:
        status = job.status()

        if status == "COMPLETED":
            elapsed = time.time() - start
            result = job.output()
            print(f"\n✅ Completed in {elapsed:.0f}s")
            print(json.dumps(result, indent=2, default=str)[:3000])
            return

        if status == "FAILED":
            result = job.output()
            print(f"\n❌ Job failed")
            print(json.dumps(result, indent=2, default=str)[:3000])
            return

        if time.time() - start > args.timeout:
            print(f"\n⏱️  Timeout after {args.timeout}s (job still running: {job.job_id})")
            return

        elapsed = int(time.time() - start)
        print(f"  [{elapsed:>4}s] {status}...", end="\r")
        time.sleep(3)


if __name__ == "__main__":
    main()
