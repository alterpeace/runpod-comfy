#!/usr/bin/env python3
"""
Patch ComfyUI-LTXVideo's embeddings_connector.py on the worker to fix
comfy_quant int8 weight loading issues.

Modes:
  int8    — Simple sed patch: add strict=False to load_state_dict (quick fix)
  dequant — Full dequantization: dequantize comfy_quant weights before
            load_state_dict (more thorough, always restarts ComfyUI)
  restart — Same as int8 but also kills ComfyUI to force reload

Usage:
    set -a && source .env && set +a

    # Simple strict=False patch (no restart)
    uv run python scripts/diag/patch_gemma.py --mode int8

    # Simple patch + restart ComfyUI to reload patched file
    uv run python scripts/diag/patch_gemma.py --mode int8 --restart

    # Full dequantization patch (always restarts)
    uv run python scripts/diag/patch_gemma.py --mode dequant
"""
import argparse
import base64
import json
import os
import sys
import time

import runpod

runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint(os.environ.get('RUNPOD_ENDPOINT_ID', 'taea2mhlwbdkuq'))

# Dequantization patch (written in Python, sent as base64 to avoid quoting issues)
DEQUANT_PATCH_PY = """
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


def run_diagnostic(commands: list[str], label: str) -> None:
    """Run diagnostic commands on the worker and print results."""
    job = endpoint.run({
        "input": {
            "action": "diagnostic",
            "commands": commands,
            "timeout": 30,
        }
    })

    print(f"{label}...")
    while job.status() in ['IN_QUEUE', 'IN_PROGRESS']:
        time.sleep(2)
        print(f"  Status: {job.status()}...")

    print(f"\nFinal status: {job.status()}")
    result = job.output()
    print(json.dumps(result, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["int8", "dequant", "restart"], default="int8",
                        help="Patch mode: int8 (strict=False), dequant (full dequantization), restart (int8 + restart)")
    parser.add_argument("--restart", action="store_true",
                        help="Restart ComfyUI after patching (kill process to force reload)")
    args = parser.parse_args()

    # restart mode = int8 patch + restart
    do_restart = args.restart or args.mode == "restart" or args.mode == "dequant"

    if args.mode == "dequant":
        # Full dequantization patch
        patch_b64 = base64.b64encode(DEQUANT_PATCH_PY.encode()).decode()
        commands = [
            f'echo {patch_b64} | base64 -d > /tmp/patch_dequant.py',
            'python3 /tmp/patch_dequant.py',
            'grep -n "dequant\\|load_state_dict\\|_dq\\|comfy_quant" /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py | head -15',
        ]
        label = "Patching with dequantization logic"
    else:
        # Simple int8/restart patch: sed strict=False
        commands = [
            "sed -i 's/connector.load_state_dict(sd_connector)/connector.load_state_dict(sd_connector, strict=False)/' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py 2>/dev/null; true",
            "grep -n 'load_state_dict' /comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py",
        ]
        label = "Patching embeddings_connector.py (strict=False)"

    # Add restart commands if needed
    if do_restart:
        commands.extend([
            "pkill -f 'python.*main.py' 2>/dev/null; pkill -f 'comfyui' 2>/dev/null; true",
            "sleep 2 && pgrep -f 'python.*main.py' || echo 'ComfyUI stopped'",
        ])

    # Also check for other load_state_dict calls that might need patching
    commands.append(
        "grep -rn 'load_state_dict' /comfyui/custom_nodes/ComfyUI-LTXVideo/*.py | grep -v strict=False | grep -v '.pyc' || true"
    )

    run_diagnostic(commands, label)

    if do_restart:
        print("\nThe next workflow job will start a fresh ComfyUI with the patched code.")
        print("Run: uv run python scripts/invoke/invoke_v2v_with_upload.py --video rhizome.mp4")

    return 0


if __name__ == "__main__":
    sys.exit(main())
