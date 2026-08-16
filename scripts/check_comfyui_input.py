#!/usr/bin/env python3
"""
Check if the symlink at /comfyui/input/rhizome.mp4 exists and is valid.
Also check if the worker that ran the symlink job is the same one that
runs workflows (RunPod serverless may use different workers).

Usage:
    set -a && source .env && set +a
    uv run python scripts/check_comfyui_input.py
"""
import runpod
import os
import json
import time

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint(os.environ.get('RUNPOD_ENDPOINT_ID', 'taea2mhlwbdkuq'))

# Check /comfyui/input/ paths (our symlinks)
inline_manifest = {
    "models": [
        {
            "id": "check_comfyui_rhizome",
            "desc": "Check /comfyui/input/rhizome.mp4 symlink",
            "dest": "input",
            "file": "rhizome.mp4",
            "repo": "nonexistent/bogus-repo",
            "gated": False
        },
        {
            "id": "check_comfyui_sample",
            "desc": "Check /comfyui/input/sample symlink",
            "dest": "input",
            "file": "sample",
            "repo": "nonexistent/bogus-repo-2",
            "gated": False
        }
    ],
    "profiles": {
        "check": ["check_comfyui_rhizome", "check_comfyui_sample"]
    }
}

job_input = {
    "action": "download_models",
    "inline_manifest": inline_manifest,
    "profile": "check",
    "output_dir": "/comfyui",  # Check /comfyui/input/ paths
}

print("Checking /comfyui/input/ symlinks...")
print("  1. /comfyui/input/rhizome.mp4 (should be symlink -> /runpod-volume/input/rhizome.mp4)")
print("  2. /comfyui/input/sample (should be symlink -> /runpod-volume/input/sample)")
print()

job = endpoint.run(job_input)

print("Waiting for job to complete...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}")

print(f"\nFinal status: {job.status()}")
output = job.output()
print(json.dumps(output, indent=2))

stdout = output.get("output", {}).get("stdout", "")
print("\n=== Interpretation ===")
for line in stdout.splitlines():
    if "[skip]" in line and "already exists" in line:
        print(f"  ✅ FILE EXISTS (real file): {line.strip()}")
    elif "[skip]" in line and "symlink" in line:
        print(f"  ✅ SYMLINK EXISTS: {line.strip()}")
    elif "[skip]" in line and "copy_mode" in line:
        print(f"  ⚠️  SYMLINK EXISTS (but copy_mode): {line.strip()}")
    elif "[re-dl]" in line:
        print(f"  ❌ BROKEN SYMLINK (target gone): {line.strip()}")
    elif "[FAIL]" in line:
        print(f"  ❌ NOT FOUND: {line.strip()}")
    elif "[ok]" in line:
        print(f"  ✅ CREATED: {line.strip()}")