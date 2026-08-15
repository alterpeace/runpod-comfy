#!/usr/bin/env python3
"""
Patch ComfyUI-LTXVideo's embeddings_connector.py to dequantize
comfy_quant weights before loading state_dict.

Usage:
    set -a && source .env && set +a
    uv run python scripts/patch_gemma_dequant.py
"""
import runpod
import os
import json
import time

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

# Write patch script using base64 to avoid all quoting issues
import base64

patch_py = """
import torch

file_path = "/comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the load_state_dict line
patched = False
new_lines = []
for i, line in enumerate(lines):
    if "connector.load_state_dict(sd_connector" in line and not patched:
        indent = len(line) - len(line.lstrip())
        sp = " " * indent
        new_lines.append(sp + "# Dequantize comfy_quant int8 weights to bf16\\n")
        new_lines.append(sp + "import torch as _torch\\n")
        new_lines.append(sp + "_dq = {}\\n")
        new_lines.append(sp + "for _k, _v in sd_connector.items():\\n")
        new_lines.append(sp + "    if _k.endswith('.comfy_quant') or _k.endswith('.weight_scale'):\\n")
        new_lines.append(sp + "        continue\\n")
        new_lines.append(sp + "    if _k.endswith('.weight') and (_k + '_scale') in sd_connector:\\n")
        new_lines.append(sp + "        _s = sd_connector[(_k + '_scale')]\\n")
        new_lines.append(sp + "        if _v.dtype in (_torch.int8, _torch.uint8, _torch.float8_e4m3fn):\\n")
        new_lines.append(sp + "            _v = _v.to(_s.dtype) * _s\\n")
        new_lines.append(sp + "    _dq[_k] = _v\\n")
        new_lines.append(sp + "connector.load_state_dict(_dq, strict=False)\\n")
        patched = True
    else:
        new_lines.append(line)

if not patched:
    print("ERROR: Could not find load_state_dict line")
else:
    with open(file_path, "w") as f:
        f.writelines(new_lines)
    print("PATCHED_SUCCESS")
"""

patch_b64 = base64.b64encode(patch_py.encode()).decode()

job = endpoint.run({
    'input': {
        'action': 'diagnostic',
        'commands': [
            f'echo {patch_b64} | base64 -d > /tmp/patch_dequant.py',
            'python3 /tmp/patch_dequant.py',
            'grep -n "dequant\|load_state_dict\|_dq\|comfy_quant" /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py | head -15',
            'pkill -9 -f "python.*main.py" 2>/dev/null; true',
            'sleep 3',
            'pgrep -f "python.*main.py" || echo ComfyUI stopped',
        ],
        'timeout': 30,
    }
})

print("Patching with dequantization logic...")
while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
    time.sleep(2)
    print(f"  Status: {job.status()}...")

print(f"\nFinal status: {job.status()}")
result = job.output()
print(json.dumps(result, indent=2))
