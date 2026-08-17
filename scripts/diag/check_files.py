#!/usr/bin/env python3
"""
Check if input files exist on the worker by exploiting the download_models
action's inline_manifest feature.

The download script checks if dest_path exists before downloading.
If the file exists, it prints [skip]. If not, it tries to download
from HF and prints [FAIL] (since we use a bogus repo).

Modes:
  input  — Check /comfyui/input/ paths (symlinks)
  volume — Check /runpod-volume/input/ paths (real files on FUSE mount)

Usage:
    set -a && source .env && set +a
    uv run python scripts/diag/check_files.py               # default: volume
    uv run python scripts/diag/check_files.py --mode input   # check /comfyui/input/
    uv run python scripts/diag/check_files.py --mode volume  # check /runpod-volume/input/
"""
import argparse
import json
import os
import sys
import time

import runpod

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint(os.environ.get('RUNPOD_ENDPOINT_ID', 'taea2mhlwbdkuq'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["input", "volume"], default="volume",
                        help="input: check /comfyui/input/ symlinks; volume: check /runpod-volume/input/ files")
    args = parser.parse_args()

    # Inline manifest with bogus repo — if file exists, [skip]; if not, [FAIL]
    inline_manifest = {
        "models": [
            {
                "id": "check_rhizome",
                "desc": "Check if rhizome.mp4 exists",
                "dest": "input",
                "file": "rhizome.mp4",
                "repo": "nonexistent/bogus-repo",
                "gated": False
            },
            {
                "id": "check_sample_clip",
                "desc": "Check if sample clip exists",
                "dest": "input/sample",
                "file": "clip_26-06-11_17-52-54_00002.mp4",
                "repo": "nonexistent/bogus-repo",
                "gated": False
            },
            {
                "id": "check_comfyui_input_rhizome",
                "desc": "Check if rhizome.mp4 symlink exists in /comfyui/input/",
                "dest": "input",
                "file": "rhizome.mp4",
                "repo": "nonexistent/bogus-repo-2",
                "gated": False
            }
        ],
        "profiles": {
            "check": ["check_rhizome", "check_sample_clip", "check_comfyui_input_rhizome"]
        }
    }

    if args.mode == "input":
        output_dir = "/comfyui"
        print("Checking /comfyui/input/ symlinks...")
        print("  1. /comfyui/input/rhizome.mp4 (should be symlink -> /runpod-volume/input/rhizome.mp4)")
        print("  2. /comfyui/input/sample (should be symlink -> /runpod-volume/input/sample)")
    else:
        output_dir = "/runpod-volume"
        print("Checking if input files exist on the worker...")
        print("  1. /runpod-volume/input/rhizome.mp4")
        print("  2. /runpod-volume/input/sample/clip_26-06-11_17-52-54_00002.mp4")
        print("  3. /comfyui/input/rhizome.mp4 (our symlink)")
    print()

    job_input = {
        "action": "download_models",
        "inline_manifest": inline_manifest,
        "profile": "check",
        "output_dir": output_dir,
    }

    job = endpoint.run(job_input)

    print("Waiting for job to complete...")
    while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
        time.sleep(2)
        print(f"  Status: {job.status()}")

    print(f"\nFinal status: {job.status()}")
    output = job.output()
    print(json.dumps(output, indent=2))

    # Parse the stdout to interpret results
    stdout = output.get("output", {}).get("stdout", "")
    print("\n=== Interpretation ===")
    for line in stdout.splitlines():
        if "[skip]" in line and "already exists" in line:
            print(f"  ✅ FILE EXISTS (real file): {line.strip()}")
        elif "[skip]" in line and "symlink" in line:
            print(f"  ✅ SYMLINK EXISTS: {line.strip()}")
        elif "[skip]" in line and "copy_mode" in line:
            print(f"  ⚠️  SYMLINK EXISTS (but copy_mode): {line.strip()}")
        elif "[skip]" in line:
            print(f"  ✅ EXISTS: {line.strip()}")
        elif "[re-dl]" in line:
            print(f"  ❌ BROKEN SYMLINK (target gone): {line.strip()}")
        elif "[FAIL]" in line:
            print(f"  ❌ NOT FOUND: {line.strip()}")
        elif "[ok]" in line:
            print(f"  ✅ CREATED: {line.strip()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
