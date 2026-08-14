#!/usr/bin/env python3
"""
Fix the /comfyui/input/ → /runpod-volume/input/ linking issue WITHOUT
rebuilding the Docker image.

Exploits the download_models action's inline_manifest feature combined
with the download script's symlink_target field to create symlinks on
the worker's filesystem.

The download script (download_ltx25_models.py) has this logic:
    symlink_target = model.get("symlink_target")
    if symlink_target:
        dest_path = output_dir / model["dest"] / filename
        os.symlink(symlink_target, dest_path)

So if we set output_dir=/comfyui and craft a manifest with:
    dest="input", file="rhizome.mp4", symlink_target="/runpod-volume/input/rhizome.mp4"
    dest="input", file="sample", symlink_target="/runpod-volume/input/sample"

It will create:
    /comfyui/input/rhizome.mp4 -> /runpod-volume/input/rhizome.mp4
    /comfyui/input/sample -> /runpod-volume/input/sample

Usage:
    set -a && source .env && set +a
    uv run python scripts/fix_input_symlink.py            # dry-run first
    uv run python scripts/fix_input_symlink.py --apply     # actually create symlinks
"""
import runpod
import os
import json
import time
import sys

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

# The inline manifest exploits the symlink_target feature
inline_manifest = {
    "models": [
        {
            "id": "link_rhizome",
            "desc": "Symlink rhizome.mp4 from volume to comfyui input",
            "dest": "input",
            "file": "rhizome.mp4",
            "symlink_target": "/runpod-volume/input/rhizome.mp4"
        },
        {
            "id": "link_sample_dir",
            "desc": "Symlink sample/ directory from volume to comfyui input",
            "dest": "input",
            "file": "sample",
            "symlink_target": "/runpod-volume/input/sample"
        }
    ],
    "profiles": {
        "link_input": ["link_rhizome", "link_sample_dir"]
    }
}

apply = "--apply" in sys.argv
dry_run = not apply

job_input = {
    "action": "download_models",
    "inline_manifest": inline_manifest,
    "profile": "link_input",
    "output_dir": "/comfyui",  # So dest_path = /comfyui/input/rhizome.mp4
    "dry_run": dry_run,
    "force": True,  # Overwrite if symlink already exists
}

print(f"Mode: {'APPLY (creating symlinks)' if apply else 'DRY RUN (preview only)'}")
print(f"Sending download_models job with inline manifest...")
print(f"  Target: /comfyui/input/rhizome.mp4 -> /runpod-volume/input/rhizome.mp4")
print(f"  Target: /comfyui/input/sample -> /runpod-volume/input/sample")
print()

job = endpoint.run(job_input)

print("Waiting for job to complete...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}")

print(f"\nFinal status: {job.status()}")
output = job.output()
print(json.dumps(output, indent=2))

if apply and output.get("status") == "success":
    print("\n✅ Symlinks created! The input files should now be visible to ComfyUI.")
    print("   Try running your V2V workflow again.")
elif dry_run and output.get("status") == "success":
    print("\n📋 Dry run successful! Run with --apply to create the symlinks:")
    print("   uv run python scripts/fix_input_symlink.py --apply")
else:
    print("\n❌ Job failed. Check the output above for details.")
