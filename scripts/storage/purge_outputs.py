#!/usr/bin/env python3
"""
Purge all content from the output/ directory on the RunPod network volume.

Usage:
    set -a && source .env && set +a
    uv run python scripts/storage/purge_outputs.py
    uv run python scripts/storage/purge_outputs.py --prefix output/
    uv run python scripts/storage/purge_outputs.py --prefix output/al7/
    uv run python scripts/storage/purge_outputs.py --dry-run
"""
import argparse
import os
import sys
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
    import boto3
except ImportError:
    print("ERROR: boto3 required. Run: uv sync")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Purge output content from RunPod S3 volume")
    parser.add_argument("--prefix", default="output/", help="S3 prefix to purge (default: output/)")
    parser.add_argument("--dry-run", action="store_true", help="List files without deleting")
    args = parser.parse_args()

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
        region_name=os.environ["RUNPOD_S3_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["RUNPOD_S3_BUCKET"]

    # List all objects
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
        for obj in page.get("Contents", []):
            objects.append(obj["Key"])

    if not objects:
        print(f"No objects found under {args.prefix}")
        return

    total_size = sum(
        obj["Size"] for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix)
        for obj in page.get("Contents", [])
    )

    print(f"Found {len(objects)} objects ({total_size / 1024 / 1024:.1f} MB) under {args.prefix}")

    if args.dry_run:
        for key in objects[:20]:
            print(f"  {key}")
        if len(objects) > 20:
            print(f"  ... and {len(objects) - 20} more")
        print(f"\n(dry run — {len(objects)} files would be deleted)")
        return

    # Delete one by one (RunPod S3 doesn't support batch delete)
    deleted = 0
    for key in objects:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            deleted += 1
        except Exception as e:
            print(f"  ERROR deleting {key}: {e}")

    print(f"Deleted {deleted}/{len(objects)} objects from {args.prefix}")


if __name__ == "__main__":
    main()
