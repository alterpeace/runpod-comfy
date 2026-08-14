#!/usr/bin/env python3
"""
Diagnostic script: check the worker's filesystem state via the RunPod
serverless endpoint's 'diagnostic' action.

Usage:
    set -a && source .env && set +a
    uv run python scripts/diagnose_worker.py
"""
import runpod
import os
import json
import time
import sys

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

job = endpoint.run({
    "action": "diagnostic",
    "commands": [
        "ls -la /runpod-volume/input/ 2>&1",
        "ls -la /comfyui/input/ 2>&1",
        "readlink -f /comfyui/input 2>&1",
        "ls -la /comfyui/input/rhizome.mp4 2>&1",
        "find /runpod-volume/input -type f 2>&1 | head -20",
        "find /comfyui/input -type f 2>&1 | head -20",
    ],
    "timeout": 15
})

print("Waiting for job to complete...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}")

print(f"\nFinal status: {job.status()}")
output = job.output()
print(json.dumps(output, indent=2))
