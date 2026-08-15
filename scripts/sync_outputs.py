#!/usr/bin/env python3
"""
Sync output files from RunPod S3 volume to a local directory.

Downloads all files from the output/ prefix on the RunPod network volume
to a local folder. Useful for collecting generated videos.

Usage:
    set -a && source .env && set +a
    uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking
    uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking --watch
    uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking --prefix output/
"""
import argparse
import os
import sys
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Sync RunPod S3 outputs to local directory")
    parser.add_argument("dest", help="Local destination directory")
    parser.add_argument("--prefix", default="output/", help="S3 prefix to sync (default: output/)")
    parser.add_argument("--watch", action="store_true", help="Keep running and sync new files every 30s")
    parser.add_argument("--delete", action="store_true", help="Delete local files not on S3 (mirror sync)")
    args = parser.parse_args()

    # Load .env
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
        region_name=os.environ["RUNPOD_S3_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["RUNPOD_S3_BUCKET"]
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    def sync_once():
        """Sync once and return number of files downloaded."""
        downloaded = 0
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if obj["Size"] == 0:
                    continue

                # Calculate local path (strip prefix)
                rel_path = key[len(args.prefix):] if key.startswith(args.prefix) else key
                local_path = dest / rel_path
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # Skip if already exists and same size
                if local_path.exists() and local_path.stat().st_size == obj["Size"]:
                    continue

                # Download
                print(f"  ↓ {key} ({obj['Size']:,} B) → {local_path}")
                s3.download_file(bucket, key, str(local_path))
                downloaded += 1

        return downloaded

    print(f"Syncing s3://{bucket}/{args.prefix} → {dest}")
    count = sync_once()
    print(f"Done: {count} files downloaded")

    if args.watch:
        print("\nWatching for new files (Ctrl+C to stop)...")
        try:
            while True:
                time.sleep(30)
                count = sync_once()
                if count > 0:
                    print(f"  [{time.strftime('%H:%M:%S')}] {count} new files downloaded")
        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    main()
