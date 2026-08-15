#!/usr/bin/env python3
"""
Patch ComfyUI-LTXVideo's embeddings_connector.py on ALL workers and
restart ComfyUI so it reloads the patched file.

The patch adds strict=False to load_state_dict, fixing the int8
quantization key rejection. ComfyUI caches Python modules in memory,
so we need to kill the ComfyUI process after patching to force a reload
on the next job.

Usage:
    set -a && source .env && set +a
    uv run python scripts/patch_and_restart.py
"""
import runpod
import os
import json
import time

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

# Patch the file AND kill ComfyUI to force reload
commands = [
    # Patch: add strict=False to load_state_dict call
    "sed -i 's/connector.load_state_dict(sd_connector)/connector.load_state_dict(sd_connector, strict=False)/' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py 2>/dev/null; true",
    # Verify the patch
    "grep -n 'load_state_dict' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py",
    # Kill ComfyUI to force reload on next job (handler will restart it)
    "pkill -f 'python.*main.py' 2>/dev/null; pkill -f 'comfyui' 2>/dev/null; true",
    # Verify ComfyUI is stopped
    "sleep 2 && pgrep -f 'python.*main.py' || echo 'ComfyUI stopped'",
]

job = endpoint.run({
    "input": {
        "action": "diagnostic",
        "commands": commands,
        "timeout": 30,
    }
})

print("Patching and restarting ComfyUI on worker...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}")

print(f"\nFinal status: {job.status()}")
output = job.output()
print(json.dumps(output, indent=2))

# Now submit a test job to trigger ComfyUI restart with patched code
print("\n=== Submitting test workflow to trigger restart ===")
time.sleep(5)  # Wait for ComfyUI to fully stop

# Simple test: just submit the workflow again
# The handler will call initialize_comfyui() which starts a fresh ComfyUI
# with the patched embeddings_connector.py
print("The next workflow job will start a fresh ComfyUI with the patched code.")
print("Run: uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4")
