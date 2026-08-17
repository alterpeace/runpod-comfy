#!/usr/bin/env python3
"""
List the RunPod S3 volume as a tree with file sizes.

Usage:
    set -a && source .env && set +a
    uv run python scripts/storage/list_s3.py
    uv run python scripts/storage/list_s3.py --prefix models/
    uv run python scripts/storage/list_s3.py --prefix output/
"""
import os
import sys
from pathlib import Path

env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

import boto3

prefix = ""
if len(sys.argv) > 1 and sys.argv[1] == "--prefix":
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
    region_name=os.environ["RUNPOD_S3_REGION"],
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)
bucket = os.environ["RUNPOD_S3_BUCKET"]

def fmt(s):
    if s == 0: return "0 B"
    if s < 1024: return f"{s} B"
    if s < 1048576: return f"{s/1024:.1f} KB"
    if s < 1073741824: return f"{s/1048576:.1f} MB"
    return f"{s/1073741824:.2f} GB"

tree = {}
total = 0
count = 0

for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
    for o in page.get("Contents", []):
        total += o["Size"]
        count += 1
        parts = o["Key"].split("/")
        c = tree
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                c[p] = o["Size"]
            else:
                c = c.setdefault(p, {})

def count_files(n):
    return sum(count_files(v) if isinstance(v, dict) else 1 for v in n.values()) if n else 0

def sum_sizes(n):
    return sum(sum_sizes(v) if isinstance(v, dict) else v for v in n.values()) if n else 0

def pt(node, pre=""):
    items = sorted(node.items())
    for i, (k, v) in enumerate(items):
        last = i == len(items) - 1
        conn = "└── " if last else "├── "
        if isinstance(v, dict):
            n = count_files(v)
            s = sum_sizes(v)
            print(f"{pre}{conn}{k}/ ({n} files, {fmt(s)})")
            pt(v, pre + ("    " if last else "│   "))
        else:
            print(f"{pre}{conn}{k} ({fmt(v)})")

print(f"s3://{bucket}/{prefix}  ({count} files, {fmt(total)} total)")
print("│")
pt(tree)
