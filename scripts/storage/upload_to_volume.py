#!/usr/bin/env python3
"""
Upload files/folders to the RunPod network volume via S3 — no temp pod needed.

RunPod network volumes are block storage that can only be accessed by pods.
This script avoids creating a temp pod by using a two-phase approach:

  1. Upload phase (local): Upload files to RunPod S3 via the S3 API (boto3)
  2. Sync phase (worker): Use the serverless `diagnostic` action to run a
     Python script on the worker that downloads from S3 to the volume

This is faster, cheaper (no GPU pod), and doesn't depend on GPU availability.

Usage:
    set -a && source .env && set +a

    # Upload a folder to input/swa_aliens/
    uv run python scripts/storage/upload_to_volume.py /path/to/swa_aliens --subfolder swa_aliens

    # Upload a single file
    uv run python scripts/storage/upload_to_volume.py video.mp4

    # Upload to input/ root (no subfolder)
    uv run python scripts/storage/upload_to_volume.py /path/to/clips/

    # Keep S3 copies after sync (default: clean up)
    uv run python scripts/storage/upload_to_volume.py /path/to/clips/ --keep-s3

    # Dry run — show what would be uploaded without doing anything
    uv run python scripts/storage/upload_to_volume.py /path/to/clips/ --dry-run

Prerequisites:
    - RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID set in .env
    - RUNPOD_S3_BUCKET, RUNPOD_S3_ENDPOINT, RUNPOD_S3_REGION set in .env
    - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY set in .env
    - runpod SDK + boto3 installed (uv sync)
"""

import argparse
import base64
import json
import os
import sys
import time
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

try:
    import boto3
    from botocore.config import Config
except ImportError:
    print("ERROR: boto3 not installed. Run: uv sync")
    sys.exit(1)


# ANSI colors
class C:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    NC = "\033[0m"


def log_info(msg): print(f"{C.BLUE}[INFO]{C.NC} {msg}")
def log_ok(msg): print(f"{C.GREEN}[OK]{C.NC} {msg}")
def log_warn(msg): print(f"{C.YELLOW}[WARN]{C.NC} {msg}")
def log_err(msg): print(f"{C.RED}[ERROR]{C.NC} {msg}")


def get_s3_client():
    """Create an S3 client from RUNPOD_S3_* env vars."""
    endpoint = os.environ.get("RUNPOD_S3_ENDPOINT")
    region = os.environ.get("RUNPOD_S3_REGION", "us-ca-2")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not all([endpoint, access_key, secret_key]):
        log_err("Missing S3 config. Need RUNPOD_S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY in .env")
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(retries={"max_attempts": 3}),
    )


def get_bucket():
    bucket = os.environ.get("RUNPOD_S3_BUCKET")
    if not bucket:
        log_err("RUNPOD_S3_BUCKET not set in .env")
        sys.exit(1)
    return bucket


def collect_files(local_path: str) -> list[tuple[str, str]]:
    """Collect (local_path, relative_path) pairs for upload.

    For a directory, returns all files recursively with paths relative to the dir.
    For a single file, returns [(file_path, filename)].
    """
    local_path = os.path.expanduser(local_path)
    if not os.path.exists(local_path):
        log_err(f"Path not found: {local_path}")
        sys.exit(1)

    files = []
    if os.path.isfile(local_path):
        files.append((local_path, os.path.basename(local_path)))
    elif os.path.isdir(local_path):
        base = Path(local_path)
        for f in sorted(base.rglob("*")):
            if f.is_file():
                rel = f.relative_to(base)
                files.append((str(f), str(rel)))
    else:
        log_err(f"Not a file or directory: {local_path}")
        sys.exit(1)

    return files


def upload_to_s3(s3_client, bucket, files, s3_prefix):
    """Upload files to S3 under the given prefix.

    Args:
        files: List of (local_path, relative_path) tuples
        s3_prefix: S3 key prefix (e.g. "input/swa_aliens/")

    Returns:
        List of (s3_key, relative_path) tuples for uploaded files
    """
    uploaded = []
    total = len(files)
    for i, (local_path, rel_path) in enumerate(files, 1):
        s3_key = f"{s3_prefix}{rel_path}"
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        log_info(f"[{i}/{total}] Uploading {rel_path} ({size_mb:.1f} MB) -> s3://{bucket}/{s3_key}")

        try:
            s3_client.upload_file(local_path, bucket, s3_key)
            uploaded.append((s3_key, rel_path))
            log_ok(f"  Uploaded")
        except Exception as e:
            log_err(f"  Failed: {e}")

    return uploaded


def sync_to_volume_via_diagnostic(s3_prefix, target_dir, timeout=120):
    """Use the serverless diagnostic action to download files from S3 to the volume.

    Runs a Python script on the worker that:
    1. Connects to S3 using the provided credentials
    2. Lists objects under the prefix
    3. Downloads each to the target directory on the volume
    """
    endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq")
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(endpoint_id)

    bucket = get_bucket()
    s3_endpoint = os.environ["RUNPOD_S3_ENDPOINT"]
    s3_region = os.environ.get("RUNPOD_S3_REGION", "us-ca-2")
    access_key = os.environ["AWS_ACCESS_KEY_ID"]
    secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]

    # Build the Python sync script that will run on the worker
    # We use base64 encoding to avoid shell escaping issues
    sync_script = f"""import boto3, os, sys
from botocore.config import Config

BUCKET = "{bucket}"
ENDPOINT = "{s3_endpoint}"
REGION = "{s3_region}"
ACCESS_KEY = "{access_key}"
SECRET_KEY = "{secret_key}"
PREFIX = "{s3_prefix}"
TARGET_DIR = "{target_dir}"

os.makedirs(TARGET_DIR, exist_ok=True)

s3 = boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION,
                  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                  config=Config(retries={{"max_attempts": 3}}))

paginator = s3.get_paginator("list_objects_v2")
count = 0
for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if key.endswith("/"):
            continue
        rel_path = key[len(PREFIX):]
        local_path = os.path.join(TARGET_DIR, rel_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        size_mb = obj["Size"] / (1024 * 1024)
        print(f"Downloading {{rel_path}} ({{size_mb:.1f}} MB)...", flush=True)
        s3.download_file(BUCKET, key, local_path)
        count += 1
        print(f"  OK", flush=True)

print(f"Total downloaded: {{count}} files", flush=True)
"""

    script_b64 = base64.b64encode(sync_script.encode()).decode()
    command = f"echo '{script_b64}' | base64 -d > /tmp/s3_sync.py && python3 /tmp/s3_sync.py"

    log_info(f"Triggering sync on worker (endpoint: {endpoint_id})...")
    log_info(f"  S3 prefix: s3://{bucket}/{s3_prefix}")
    log_info(f"  Target: {target_dir}/")

    job = endpoint.run({
        "input": {
            "action": "diagnostic",
            "commands": [command],
            "timeout": timeout,
        }
    })

    log_info(f"  Job: {job.job_id}")

    # Wait for completion
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
        log_err(f"Job {status} with no output (timeout or worker error)")
        return False

    if output.get("status") != "success":
        error = output.get("error") or output.get("error_message") or str(output)[:500]
        log_err(f"Diagnostic failed: {error}")
        return False

    # Print the sync output
    results = output.get("output", {}).get("results", [])
    for r in results:
        if r.get("stdout"):
            print(r["stdout"], end="")
        if r.get("stderr"):
            log_warn(f"stderr: {r['stderr'][:500]}")
        if r.get("returncode", 0) != 0:
            log_err(f"Command exited with code {r['returncode']}")
            return False

    return True


def cleanup_s3(s3_client, bucket, s3_prefix):
    """Delete all objects under the S3 prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            keys.append({"Key": obj["Key"]})

    if not keys:
        return

    # Delete in batches of 1000 (S3 limit)
    for i in range(0, len(keys), 1000):
        batch = keys[i:i + 1000]
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": batch})

    log_ok(f"Cleaned up {len(keys)} objects from s3://{bucket}/{s3_prefix}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload files/folders to RunPod network volume via S3 (no temp pod needed)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a folder to input/swa_aliens/
  %(prog)s /path/to/swa_aliens --subfolder swa_aliens

  # Upload a single file
  %(prog)s video.mp4

  # Upload to input/ root
  %(prog)s /path/to/clips/

  # Dry run
  %(prog)s /path/to/clips/ --dry-run
        """,
    )
    parser.add_argument("path", help="File or directory to upload")
    parser.add_argument("--subfolder", default="", help="Subfolder under /runpod-volume/input/ (default: upload to input/ root)")
    parser.add_argument("--keep-s3", action="store_true", help="Keep S3 copies after sync (default: clean up)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without doing anything")
    parser.add_argument("--sync-timeout", type=int, default=120, help="Timeout for the worker sync phase in seconds (default: 120)")
    args = parser.parse_args()

    # Check prerequisites
    if not os.environ.get("RUNPOD_API_KEY"):
        log_err("RUNPOD_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    # Collect files
    files = collect_files(args.path)
    if not files:
        log_err("No files found to upload")
        sys.exit(1)

    # Determine paths
    if os.path.isdir(os.path.expanduser(args.path)):
        source_desc = f"directory: {args.path}"
    else:
        source_desc = f"file: {args.path}"

    if args.subfolder:
        s3_prefix = f"input/{args.subfolder}/"
        target_dir = f"/runpod-volume/input/{args.subfolder}"
    else:
        s3_prefix = "input/"
        target_dir = "/runpod-volume/input"

    total_size = sum(os.path.getsize(f[0]) for f in files) / (1024 * 1024)

    print("=" * 60)
    log_info(f"Source: {source_desc}")
    log_info(f"Files: {len(files)} ({total_size:.1f} MB total)")
    log_info(f"S3 prefix: s3://{get_bucket()}/{s3_prefix}")
    log_info(f"Volume target: {target_dir}/")
    print("=" * 60)

    if args.dry_run:
        log_warn("DRY RUN -- no uploads or sync will occur")
        for local_path, rel_path in files:
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            print(f"  {rel_path} ({size_mb:.1f} MB)")
        return

    # Phase 1: Upload to S3
    print()
    log_info("Phase 1: Uploading to S3...")
    s3_client = get_s3_client()
    bucket = get_bucket()
    uploaded = upload_to_s3(s3_client, bucket, files, s3_prefix)

    if len(uploaded) != len(files):
        log_err(f"Only {len(uploaded)}/{len(files)} files uploaded to S3. Aborting.")
        sys.exit(1)

    log_ok(f"All {len(uploaded)} files uploaded to S3")

    # Phase 2: Sync to volume via diagnostic action
    print()
    log_info("Phase 2: Syncing S3 -> volume via serverless worker...")
    success = sync_to_volume_via_diagnostic(s3_prefix, target_dir, timeout=args.sync_timeout)

    if not success:
        log_err("Sync failed. Files are still in S3 -- you can retry with:")
        log_err(f"  uv run python scripts/storage/upload_to_volume.py {args.path} --subfolder {args.subfolder}")
        sys.exit(1)

    log_ok(f"Sync complete! {len(uploaded)} files are now on the volume at {target_dir}/")

    # Phase 3: Cleanup S3 (optional)
    if not args.keep_s3:
        print()
        log_info("Phase 3: Cleaning up S3...")
        cleanup_s3(s3_client, bucket, s3_prefix)
    else:
        log_info("Keeping S3 copies (--keep-s3)")

    # Print usage hint
    print()
    print("=" * 60)
    log_ok("Done! Files are ready on the volume.")
    print("=" * 60)
    if args.subfolder:
        print(f"\nUse in alt_retake.py:")
        print(f"  uv run python scripts/invoke/alt_retake.py --video {args.subfolder}/<filename>.mp4")
    else:
        print(f"\nUse in alt_retake.py:")
        print(f"  uv run python scripts/invoke/alt_retake.py --video <filename>.mp4")


if __name__ == "__main__":
    main()