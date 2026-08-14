#!/usr/bin/env python3
"""
Patch ComfyUI-LTXVideo's embeddings_connector.py on the worker to use
strict=False when loading state_dict, fixing the int8 quantization key
rejection error.

Usage:
    set -a && source .env && set +a
    uv run python scripts/patch_gemma_int8.py
"""
import runpod
import os
import json
import time

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

job = endpoint.run({
    "input": {
        "action": "diagnostic",
        "commands": [
            # Patch: add strict=False to load_state_dict call
            "sed -i 's/connector.load_state_dict(sd_connector)/connector.load_state_dict(sd_connector, strict=False)/' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py",
            # Verify the patch
            "grep -n 'load_state_dict' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py",
            # Also check if there are other load_state_dict calls that need patching
            "grep -rn 'load_state_dict' /comfyui/custom_nodes/ComfyUI-LTXVideo/*.py | grep -v strict=False | grep -v '.pyc'",
        ],
        "timeout": 15,
    }
})

print("Patching embeddings_connector.py on worker...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}")

print(f"\nFinal status: {job.status()}")
output = job.output()
print(json.dumps(output, indent=2))
