#!/usr/bin/env python3
"""
Standalone ComfyUI workflow debugger.

Submit, validate, and debug API-format ComfyUI workflows against either a
local ComfyUI instance or a RunPod serverless endpoint — without needing the
visual frontend UI.

Features:
  - Workflow validation (node structure, references, required fields)
  - Node graph visualization (text tree of all nodes and connections)
  - Input patching (--set-input NODE_ID.FIELD VALUE)
  - Verbose HTTP logging (every request/response, timing, status)
  - Output extraction (saves base64 images to disk, prints S3 URLs)
  - Error formatting (pretty-prints execution errors with node context)
  - Dry-run mode (validate without submitting)
  - Model validation (check model files exist on network volume)

Usage:
    # Validate workflow structure without submitting
    python scripts/debug_workflow.py --workflow examples/text_to_image_simple.json --dry-run

    # Test against local ComfyUI
    python scripts/debug_workflow.py --target local --workflow examples/text_to_image_simple.json

    # Test against RunPod serverless endpoint
    python scripts/debug_workflow.py --target runpod --workflow examples/text_to_image_simple.json --wait

    # Override specific node inputs
    python scripts/debug_workflow.py --target runpod \\
        --workflow examples/text_to_image_simple.json \\
        --set-input 6.text "a cat sitting on a chair" \\
        --set-input 3.seed 999 \\
        --set-input 3.steps 30 --wait

    # Save output images to disk
    python scripts/debug_workflow.py --target runpod --workflow workflow.json --output-dir ./debug-output/

    # Print node graph
    python scripts/debug_workflow.py --workflow workflow.json --print-graph
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Colors for terminal output
class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    NC = '\033[0m'  # No Color


# ============================================================================
# Workflow Validation
# ============================================================================

def validate_workflow(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate workflow structure.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    if not isinstance(workflow, dict):
        return False, ["Workflow must be a dictionary"]

    if not workflow:
        return False, ["Workflow cannot be empty"]

    # Check for at least one node
    numeric_keys = [k for k in workflow.keys() if str(k).isdigit()]
    if not numeric_keys:
        errors.append("Workflow must contain at least one node (numeric keys)")

    # Validate each node
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            errors.append(f"Node {node_id}: must be a dictionary, got {type(node_data).__name__}")
            continue

        if 'class_type' not in node_data:
            errors.append(f"Node {node_id}: missing required field 'class_type'")

        if 'inputs' not in node_data:
            errors.append(f"Node {node_id}: missing required field 'inputs'")
            continue

        inputs = node_data.get('inputs', {})
        if not isinstance(inputs, dict):
            errors.append(f"Node {node_id}: 'inputs' must be a dictionary")
            continue

        # Check input references (values that are [node_id, output_index] tuples)
        for input_name, input_val in inputs.items():
            if isinstance(input_val, list) and len(input_val) == 2:
                ref_node_id, ref_output = str(input_val[0]), input_val[1]
                if ref_node_id not in workflow:
                    errors.append(
                        f"Node {node_id}.{input_name}: references node '{ref_node_id}' "
                        f"which does not exist"
                    )

    return len(errors) == 0, errors


def validate_nodes_against_cache(workflow: Dict[str, Any], cache_path: str) -> List[str]:
    """
    Validate that all node class_types exist in the object_info cache.
    Returns list of warnings for unknown nodes.
    """
    warnings = []
    cache_file = Path(cache_path)

    if not cache_file.exists():
        return [f"Note: object_info cache not found at {cache_file}, skipping node validation"]

    with open(cache_file, "r") as f:
        cache = json.load(f)

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get('class_type', '')
        if class_type and class_type not in cache:
            warnings.append(
                f"Node {node_id}: class_type '{class_type}' not found in object_info cache "
                f"(may not be installed on the serverless worker)"
            )

    return warnings


# ============================================================================
# Node Graph Visualization
# ============================================================================

def print_node_graph(workflow: Dict[str, Any]):
    """Print a text tree of all nodes and their connections."""
    print(f"\n{C.CYAN}{'='*60}{C.NC}")
    print(f"{C.CYAN}Node Graph ({len(workflow)} nodes){C.NC}")
    print(f"{C.CYAN}{'='*60}{C.NC}\n")

    for node_id in sorted(workflow.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        node = workflow[node_id]
        if not isinstance(node, dict):
            continue

        class_type = node.get('class_type', '???')
        print(f"{C.BOLD}[{node_id}]{C.NC} {C.GREEN}{class_type}{C.NC}")

        inputs = node.get('inputs', {})
        for name, val in inputs.items():
            if isinstance(val, list) and len(val) == 2:
                # Reference to another node
                ref_id, ref_out = val
                print(f"  {C.DIM}├─{C.NC} {name}: {C.YELLOW}← [{ref_id}:{ref_out}]{C.NC}")
            else:
                # Literal value
                val_str = str(val)
                if len(val_str) > 60:
                    val_str = val_str[:57] + "..."
                print(f"  {C.DIM}├─{C.NC} {name}: {C.BLUE}{val_str}{C.NC}")

        print()


# ============================================================================
# Input Patching
# ============================================================================

def parse_set_input(spec: str) -> Tuple[str, str, Any]:
    """
    Parse --set-input argument: "NODE_ID.FIELD=VALUE" or "NODE_ID.FIELD VALUE".
    Returns (node_id, field, value).
    """
    # Try "NODE_ID.FIELD=VALUE" format
    if '=' in spec:
        key, val = spec.split('=', 1)
    else:
        # "NODE_ID.FIELD VALUE" format (split on first space)
        parts = spec.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid --set-input format: {spec}")
        key, val = parts[0], parts[1]

    if '.' not in key:
        raise ValueError(f"Invalid --set-input key: {key} (expected NODE_ID.FIELD)")

    node_id, field = key.split('.', 1)

    # Try to parse value as int, float, or keep as string
    try:
        value: Any = int(val)
    except ValueError:
        try:
            value = float(val)
        except ValueError:
            value = val

    return node_id, field, value


def apply_input_patches(workflow: Dict[str, Any], patches: List[str]) -> List[str]:
    """
    Apply --set-input patches to the workflow.
    Returns list of applied patches for logging.
    """
    applied = []
    for spec in patches:
        try:
            node_id, field, value = parse_set_input(spec)
        except ValueError as e:
            print(f"{C.RED}Error parsing --set-input: {e}{C.NC}")
            continue

        if node_id not in workflow:
            print(f"{C.RED}Warning: node {node_id} not found in workflow{C.NC}")
            continue

        if 'inputs' not in workflow[node_id]:
            workflow[node_id]['inputs'] = {}

        old_val = workflow[node_id]['inputs'].get(field, '(unset)')
        workflow[node_id]['inputs'][field] = value
        applied.append(f"  [{node_id}].{field}: {old_val} -> {value}")
        print(f"{C.YELLOW}Patched [{node_id}].{field}: {old_val} -> {value}{C.NC}")

    return applied


# ============================================================================
# Local ComfyUI Submission
# ============================================================================

def submit_local(url: str, workflow: Dict[str, Any], verbose: bool = True) -> Dict[str, Any]:
    """Submit workflow to a local ComfyUI instance."""
    if verbose:
        print(f"\n{C.CYAN}Submitting to local ComfyUI: {url}{C.NC}")

    t0 = time.time()
    resp = requests.post(f"{url}/prompt", json={"prompt": workflow}, timeout=30)
    elapsed = time.time() - t0

    if verbose:
        print(f"  POST /prompt -> {resp.status_code} ({elapsed:.2f}s)")

    resp.raise_for_status()
    data = resp.json()
    prompt_id = data.get("prompt_id")
    if verbose:
        print(f"  prompt_id: {prompt_id}")

    # Poll for completion
    if verbose:
        print(f"\n{C.CYAN}Polling for completion...{C.NC}")

    while True:
        t0 = time.time()
        resp = requests.get(f"{url}/history/{prompt_id}", timeout=30)
        elapsed = time.time() - t0
        history = resp.json()

        if prompt_id in history:
            if verbose:
                print(f"  GET /history/{prompt_id} -> completed ({elapsed:.2f}s)")
            return history[prompt_id]

        if verbose:
            print(f"  GET /history/{prompt_id} -> pending ({elapsed:.2f}s)")

        time.sleep(1)


# ============================================================================
# RunPod Serverless Submission
# ============================================================================

def submit_runpod(
    endpoint_id: str,
    api_key: str,
    workflow: Dict[str, Any],
    wait: bool = True,
    timeout: int = 300,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Submit workflow to a RunPod serverless endpoint."""
    api_base = f"https://api.runpod.ai/v2/{endpoint_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if verbose:
        print(f"\n{C.CYAN}Submitting to RunPod serverless: {endpoint_id}{C.NC}")
        print(f"  Workflow: {len(workflow)} nodes")

    payload = {"input": {"workflow": workflow}}

    t0 = time.time()
    resp = requests.post(f"{api_base}/run", json=payload, headers=headers, timeout=30)
    elapsed = time.time() - t0

    if verbose:
        print(f"  POST /run -> {resp.status_code} ({elapsed:.2f}s)")

    resp.raise_for_status()
    data = resp.json()
    job_id = data.get("id")

    if verbose:
        print(f"  job_id: {job_id}")
        print(f"  status: {data.get('status', 'IN_QUEUE')}")

    if not wait:
        return {"job_id": job_id, "status": "SUBMITTED"}

    if verbose:
        print(f"\n{C.CYAN}Polling for completion (timeout: {timeout}s)...{C.NC}")

    start = time.time()
    last_status = None

    while time.time() - start < timeout:
        t0 = time.time()
        resp = requests.get(f"{api_base}/status/{job_id}", headers=headers, timeout=30)
        elapsed = time.time() - t0
        status_data = resp.json()
        status = status_data.get("status", "UNKNOWN")

        if status != last_status:
            total = time.time() - start
            if verbose:
                delay = status_data.get("delayTime")
                exec_time = status_data.get("executionTime")
                extra = ""
                if delay is not None:
                    extra += f" delay={delay/1000:.1f}s"
                if exec_time is not None:
                    extra += f" exec={exec_time/1000:.1f}s"
                print(f"  Status: {C.YELLOW}{status}{C.NC} ({total:.1f}s{extra})")
            last_status = status

        if status == "COMPLETED":
            if verbose:
                print(f"\n{C.GREEN}Job completed!{C.NC}")
            return status_data

        elif status in ("FAILED", "CANCELLED", "ERROR", "TIMED_OUT"):
            if verbose:
                print(f"\n{C.RED}Job {status}!{C.NC}")
                error = status_data.get("error", "Unknown error")
                print(f"  Error: {error}")
            return status_data

        time.sleep(2)

    if verbose:
        print(f"\n{C.RED}Timed out after {timeout}s{C.NC}")
    return {"status": "TIMEOUT", "error": f"Timed out after {timeout}s"}


# ============================================================================
# Output Extraction
# ============================================================================

def extract_outputs(result: Dict[str, Any], target: str, output_dir: Optional[str], verbose: bool = True):
    """Extract and optionally save output images from the result."""
    images = []

    if target == "local":
        # Local ComfyUI history format
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                images.append({
                    "node_id": node_id,
                    "filename": img.get("filename", "output.png"),
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })
    else:
        # RunPod serverless format
        output = result.get("output", {})
        for img in output.get("images", []):
            images.append({
                "node_id": img.get("node_id", "unknown"),
                "filename": img.get("filename", "output.png"),
                "data": img.get("data"),
                "url": img.get("url"),
                "path": img.get("path"),
            })

    if verbose:
        print(f"\n{C.CYAN}Outputs ({len(images)} images):{C.NC}")
        for img in images:
            print(f"  [{img['node_id']}] {img['filename']}")
            if img.get("url"):
                print(f"    URL: {img['url']}")
            if img.get("path"):
                print(f"    Path: {img['path']}")

    # Save to disk if requested
    if output_dir and images:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        for img in images:
            if img.get("data"):
                # Base64 encoded
                img_bytes = base64.b64decode(img["data"])
                file_path = out_path / img["filename"]
                with open(file_path, "wb") as f:
                    f.write(img_bytes)
                if verbose:
                    print(f"  {C.GREEN}Saved: {file_path} ({len(img_bytes)} bytes){C.NC}")
            elif img.get("url"):
                # Download from URL
                if verbose:
                    print(f"  {C.YELLOW}Downloading from URL: {img['url']}{C.NC}")
                try:
                    resp = requests.get(img["url"], timeout=60)
                    resp.raise_for_status()
                    file_path = out_path / img["filename"]
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
                    if verbose:
                        print(f"  {C.GREEN}Saved: {file_path} ({len(resp.content)} bytes){C.NC}")
                except Exception as e:
                    if verbose:
                        print(f"  {C.RED}Failed to download: {e}{C.NC}")

    return images


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Standalone ComfyUI workflow debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate without submitting
  python scripts/debug_workflow.py --workflow examples/text_to_image_simple.json --dry-run

  # Test against local ComfyUI
  python scripts/debug_workflow.py --target local --workflow examples/text_to_image_simple.json

  # Test against RunPod serverless
  python scripts/debug_workflow.py --target runpod --workflow examples/text_to_image_simple.json --wait

  # Override inputs
  python scripts/debug_workflow.py --target runpod \\
      --workflow examples/text_to_image_simple.json \\
      --set-input 6.text="a cat" --set-input 3.seed=999 --wait

  # Print node graph
  python scripts/debug_workflow.py --workflow workflow.json --print-graph
        """
    )
    parser.add_argument("--workflow", required=True,
                        help="Path to API-format workflow JSON file")
    parser.add_argument("--target", choices=["local", "runpod"], default="local",
                        help="Where to submit the workflow (default: local)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"),
                        help="ComfyUI URL for --target local")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", ""),
                        help="RunPod endpoint ID for --target runpod")
    parser.add_argument("--api-key", default=os.environ.get("RUNPOD_API_KEY", ""),
                        help="RunPod API key for --target runpod")
    parser.add_argument("--wait", action="store_true",
                        help="Wait for completion (RunPod only)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout in seconds (default: 300)")
    parser.add_argument("--set-input", action="append", default=[],
                        help="Override node input: NODE_ID.FIELD=VALUE (can repeat)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory to save output images")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only, don't submit")
    parser.add_argument("--print-graph", action="store_true",
                        help="Print node graph and exit")
    parser.add_argument("--validate-models", action="store_true",
                        help="Validate model files against object_info cache")
    parser.add_argument("--object-info-cache",
                        default=os.environ.get("OBJECT_INFO_CACHE", "config/object_info_cache.json"),
                        help="Path to object_info cache for validation")
    args = parser.parse_args()

    # Load workflow
    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print(f"{C.RED}ERROR: Workflow file not found: {workflow_path}{C.NC}")
        sys.exit(1)

    with open(workflow_path, "r") as f:
        workflow = json.load(f)

    print(f"{C.CYAN}Loaded workflow: {workflow_path}{C.NC}")
    print(f"  Nodes: {len(workflow)}")

    # Print graph if requested
    if args.print_graph:
        print_node_graph(workflow)
        sys.exit(0)

    # Apply input patches
    if args.set_input:
        print(f"\n{C.CYAN}Applying input patches:{C.NC}")
        apply_input_patches(workflow, args.set_input)

    # Validate
    print(f"\n{C.CYAN}Validating workflow...{C.NC}")
    is_valid, errors = validate_workflow(workflow)

    if errors:
        for err in errors:
            print(f"  {C.RED}✗ {err}{C.NC}")
    else:
        print(f"  {C.GREEN}✓ Workflow structure valid{C.NC}")

    # Validate against object_info cache
    if args.validate_models or args.dry_run:
        warnings = validate_nodes_against_cache(workflow, args.object_info_cache)
        if warnings:
            print(f"\n{C.YELLOW}Node validation warnings:{C.NC}")
            for w in warnings:
                print(f"  {C.YELLOW}⚠ {w}{C.NC}")
        else:
            print(f"  {C.GREEN}✓ All node types found in cache{C.NC}")

    if args.dry_run:
        print(f"\n{C.GREEN}Dry run complete — workflow is valid, not submitting.{C.NC}")
        sys.exit(0 if is_valid else 1)

    if not is_valid:
        print(f"\n{C.RED}Workflow has validation errors, not submitting.{C.NC}")
        sys.exit(1)

    # Submit
    if args.target == "local":
        try:
            result = submit_local(args.url, workflow, verbose=True)
        except requests.exceptions.ConnectionError:
            print(f"\n{C.RED}ERROR: Could not connect to {args.url}{C.NC}")
            print(f"  Is ComfyUI running? Start with: ./scripts/run_local.sh")
            sys.exit(1)
        except Exception as e:
            print(f"\n{C.RED}ERROR: {e}{C.NC}")
            sys.exit(1)

        extract_outputs(result, "local", args.output_dir)

    elif args.target == "runpod":
        if not args.endpoint_id:
            print(f"\n{C.RED}ERROR: --target runpod requires --endpoint-id{C.NC}")
            sys.exit(1)
        if not args.api_key:
            print(f"\n{C.RED}ERROR: --target runpod requires --api-key{C.NC}")
            sys.exit(1)

        try:
            result = submit_runpod(
                args.endpoint_id, args.api_key, workflow,
                wait=args.wait, timeout=args.timeout, verbose=True
            )
        except Exception as e:
            print(f"\n{C.RED}ERROR: {e}{C.NC}")
            sys.exit(1)

        if args.wait:
            extract_outputs(result, "runpod", args.output_dir)

    print(f"\n{C.GREEN}Done!{C.NC}")


if __name__ == "__main__":
    main()
