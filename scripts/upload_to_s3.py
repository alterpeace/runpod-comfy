#!/usr/bin/env python3
"""
Upload a single file to S3 / S3-compatible storage.

Reuses the S3StorageClient from src/storage_s3.py and supports both the
general S3 env vars (S3_BUCKET, AWS_ACCESS_KEY_ID, …) and the RunPod
S3 env vars (RUNPOD_S3_BUCKET, …) used by scripts/sync_to_runpod_s3.sh.

Usage
-----
    # Upload a file, auto-generating the object key under the prefix:
    python scripts/upload_to_s3.py path/to/video.mp4

    # Specify an explicit S3 key (path inside the bucket):
    python scripts/upload_to_s3.py video.mp4 --key outputs/2026/my-video.mp4

    # Use the RunPod S3 backend instead of the general S3 env vars:
    python scripts/upload_to_s3.py video.mp4 --runpod

    # Make the object publicly readable and print a public URL:
    python scripts/upload_to_s3.py image.png --public

    # Generate a presigned download URL after uploading (private objects):
    python scripts/upload_to_s3.py video.mp4 --presign 3600

    # Override the bucket/prefix from the command line:
    python scripts/upload_to_s3.py video.mp4 --bucket my-bucket --prefix uploads

Environment (set in .env or export)
-----------------------------------
    General S3:
        S3_BUCKET              Bucket name
        S3_REGION              AWS region (default: us-east-1)
        S3_ENDPOINT_URL        Custom endpoint for R2 / MinIO / RunPod / …
        S3_PREFIX              Object key prefix (default: comfyui-outputs)
        AWS_ACCESS_KEY_ID      Access key
        AWS_SECRET_ACCESS_KEY  Secret key

    RunPod S3 (used with --runpod):
        RUNPOD_S3_BUCKET       Bucket name
        RUNPOD_S3_REGION       Region (default: us-ca-2)
        RUNPOD_S3_ENDPOINT     Endpoint URL
        AWS_ACCESS_KEY_ID      Access key (shared)
        AWS_SECRET_ACCESS_KEY  Secret key (shared)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make src/ importable when run as a standalone script.
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.storage_s3 import S3StorageClient, S3StorageError  # noqa: E402


def load_dotenv(path: Path) -> None:
    """Minimal .env loader that does not require python-dotenv."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def build_client(args: argparse.Namespace) -> S3StorageClient:
    """Build an S3StorageClient from env vars / CLI flags."""
    if args.runpod:
        bucket = args.bucket or os.environ.get("RUNPOD_S3_BUCKET")
        region = os.environ.get("RUNPOD_S3_REGION", "us-ca-2")
        endpoint_url = os.environ.get("RUNPOD_S3_ENDPOINT")
        prefix = args.prefix or "models"
    else:
        bucket = args.bucket or os.environ.get("S3_BUCKET")
        region = os.environ.get("S3_REGION", "us-east-1")
        endpoint_url = os.environ.get("S3_ENDPOINT_URL")
        prefix = args.prefix or os.environ.get("S3_PREFIX", "comfyui-outputs")

    if not bucket:
        raise SystemExit(
            "No bucket configured. Set S3_BUCKET (or RUNPOD_S3_BUCKET with "
            "--runpod) in .env, or pass --bucket."
        )

    return S3StorageClient(
        bucket=bucket,
        region=region,
        endpoint_url=endpoint_url,
        prefix=prefix,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload a single file to S3 / S3-compatible storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", type=Path, help="Path to the file to upload.")
    parser.add_argument(
        "--key",
        type=str,
        default=None,
        help="Explicit S3 object key (path inside the bucket). "
        "Defaults to <prefix>/<filename>.",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=None,
        help="Override the S3 bucket name.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="Override the object key prefix (folder). "
        "Default: comfyui-outputs (or models with --runpod).",
    )
    parser.add_argument(
        "--runpod",
        action="store_true",
        help="Use RunPod S3 env vars (RUNPOD_S3_*).",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Make the uploaded object publicly readable.",
    )
    parser.add_argument(
        "--presign",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Generate a presigned download URL valid for this many seconds.",
    )
    parser.add_argument(
        "--metadata",
        type=str,
        default=None,
        help="Optional metadata as key=value pairs separated by commas, "
        "e.g. --metadata 'author=me,project=test'.",
    )
    args = parser.parse_args()

    # Load .env from the project root.
    load_dotenv(PROJECT_DIR / ".env")

    file_path: Path = args.file
    if not file_path.is_file():
        raise SystemExit(f"File not found: {file_path}")

    # Parse optional metadata.
    metadata = None
    if args.metadata:
        metadata = {}
        for pair in args.metadata.split(","):
            if "=" not in pair:
                raise SystemExit(f"Invalid metadata pair: {pair!r}")
            k, _, v = pair.partition("=")
            metadata[k.strip()] = v.strip()

    # Build the client.
    try:
        client = build_client(args)
    except S3StorageError as exc:
        raise SystemExit(f"Failed to initialise S3 client: {exc}")

    # Read the file.
    data = file_path.read_bytes()
    filename = file_path.name

    # Upload.
    try:
        if args.key:
            # When an explicit key is given, bypass _generate_object_key by
            # uploading directly and building the result dict ourselves.
            content_type = client._get_content_type(filename)
            extra_args: dict = {"ContentType": content_type}
            if metadata:
                extra_args["Metadata"] = {
                    k.lower(): str(v) for k, v in metadata.items()
                }
            if args.public:
                extra_args["ACL"] = "public-read"

            client.s3_client.put_object(
                Bucket=client.bucket,
                Key=args.key,
                Body=data,
                **extra_args,
            )

            if args.public and client.endpoint_url:
                url = f"{client.endpoint_url.rstrip('/')}/{client.bucket}/{args.key}"
            elif args.public:
                url = f"https://{client.bucket}.s3.{client.region}.amazonaws.com/{args.key}"
            else:
                url = f"s3://{client.bucket}/{args.key}"

            result = {
                "key": args.key,
                "url": url,
                "bucket": client.bucket,
                "size": len(data),
                "content_type": content_type,
            }
        else:
            result = client.upload_file(
                file_data=data,
                filename=filename,
                metadata=metadata,
                public=args.public,
            )
    except S3StorageError as exc:
        raise SystemExit(f"Upload failed: {exc}")

    # Report.
    print("✅ Upload complete")
    print(f"   Bucket: {result['bucket']}")
    print(f"   Key:    {result['key']}")
    print(f"   Size:   {result['size']:,} bytes")
    print(f"   Type:   {result['content_type']}")
    print(f"   URL:    {result['url']}")

    if args.presign is not None:
        try:
            presigned = client.generate_presigned_url(
                result["key"], expiration=args.presign
            )
            print(f"   Presigned URL ({args.presign}s): {presigned}")
        except S3StorageError as exc:
            print(f"   ⚠️  Presigned URL generation failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
