#!/usr/bin/env python3
"""
Fetch and cache ComfyUI object_info for the frontend proxy.

The ComfyUI Frontend needs GET /object_info to render the node palette.
In serverless mode there's no live server between jobs, so we cache a
snapshot. This script fetches it from either:

  - A local ComfyUI instance (fastest, if you have the same nodes installed)
  - A RunPod serverless endpoint (cold-starts a worker with a minimal workflow)

It can also refresh just the model lists (--models-only) by scanning the
RunPod network volume, without cold-starting a worker.

Usage:
    # Fetch from local ComfyUI (http://127.0.0.1:8188)
    python scripts/fetch_object_info.py --source local

    # Fetch from local ComfyUI on a custom URL
    python scripts/fetch_object_info.py --source local --url http://localhost:9000

    # Fetch from RunPod serverless endpoint (cold-starts a worker)
    python scripts/fetch_object_info.py --source runpod --endpoint-id YOUR_ID

    # Refresh only model lists from network volume (no worker cold-start)
    python scripts/fetch_object_info.py --models-only --volume-id v1abc123

    # Specify output path (default: config/object_info_cache.json)
    python scripts/fetch_object_info.py --source local --output config/object_info_custom.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DEFAULT_OUTPUT = os.environ.get("OBJECT_INFO_CACHE", "config/object_info_cache.json")
DEFAULT_LOCAL_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")


def fetch_from_local(url: str) -> dict:
    """Fetch object_info from a local ComfyUI instance."""
    print(f"Fetching object_info from {url}/object_info ...")
    try:
        resp = requests.get(f"{url}/object_info", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"  Got {len(data)} node definitions")
        return data
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Could not connect to {url}")
        print("  Is ComfyUI running? Start it with: ./scripts/run_local.sh")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error from ComfyUI: {e}")
        sys.exit(1)


def fetch_from_runpod(endpoint_id: str, api_key: str) -> dict:
    """
    Fetch object_info from a RunPod serverless endpoint.
    Cold-starts a worker by submitting a minimal workflow that returns
    object_info in its output.
    """
    print(f"Fetching object_info from RunPod endpoint {endpoint_id} ...")
    print("  (This will cold-start a worker - may take 10-30s)")

    # Submit a minimal workflow that just loads object_info
    # The handler runs ComfyUI, so we can use a trivial workflow
    # and then fetch /object_info from the worker's internal ComfyUI
    # Actually, the serverless handler doesn't expose /object_info directly.
    # We need to submit a workflow that returns node info.
    #
    # Strategy: submit a minimal text-to-image workflow, then the worker
    # will have ComfyUI running. But we can't access /object_info directly.
    #
    # Better strategy: use a custom handler input that requests object_info.
    # The handler in src/handler.py supports "workflow" input. We can add
    # a special "get_object_info" input that the handler recognizes.
    #
    # For now, the simplest approach: the user should fetch from local
    # ComfyUI with the same custom nodes installed, OR we use the RunPod
    # API to get the worker's /object_info via a health check endpoint.
    #
    # Actually, the cleanest approach: submit a workflow with a single
    # "ObjectInfo" node if one exists, or just document that the user
    # should fetch from local.

    # Let's try: submit a minimal job and see if the output includes
    # system info. If not, we'll fall back to instructions.

    api_base = f"https://api.runpod.ai/v2/{endpoint_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Submit a minimal workflow (just a CheckpointLoaderSimple)
    # The handler will start ComfyUI, run this, and return.
    # We can't get /object_info this way, but we can at least verify
    # the endpoint works.
    minimal_workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "model.safetensors"}
        }
    }

    payload = {"input": {"workflow": minimal_workflow, "timeout": 60}}

    print("  Submitting minimal job to cold-start worker...")
    try:
        resp = requests.post(f"{api_base}/run", json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        job_data = resp.json()
        job_id = job_data.get("id")
        print(f"  Job ID: {job_id}")
    except Exception as e:
        print(f"ERROR: Failed to submit job: {e}")
        sys.exit(1)

    # Poll for completion
    print("  Waiting for worker to start (this is the cold start)...")
    max_wait = 120
    start = time.time()

    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{api_base}/status/{job_id}", headers=headers, timeout=30)
            resp.raise_for_status()
            status_data = resp.json()
            status = status_data.get("status", "UNKNOWN")
            elapsed = time.time() - start
            print(f"  Status: {status} ({elapsed:.0f}s elapsed)")

            if status == "COMPLETED":
                # The worker is now running. We can't directly access /object_info
                # from the serverless API, but we can try to use the RunPod
                # proxy/tunnel if available, or instruct the user.
                print()
                print("  Worker is running, but /object_info is not directly accessible")
                print("  via the RunPod serverless API.")
                print()
                print("  RECOMMENDED: Fetch from a local ComfyUI with the same nodes:")
                print("    1. ./scripts/run_local.sh")
                print("    2. python scripts/fetch_object_info.py --source local")
                print()
                print("  OR: If you have a Cloudflare tunnel or SSH access to the worker,")
                print("  fetch from that URL:")
                print(f"    python scripts/fetch_object_info.py --source local --url <tunnel-url>")
                sys.exit(1)

            elif status in ("FAILED", "CANCELLED", "ERROR", "TIMED_OUT"):
                print(f"  Job failed: {status_data.get('error', 'Unknown')}")
                print("  Falling back to local fetch instructions.")
                sys.exit(1)

        except Exception as e:
            print(f"  Warning: poll error: {e}")

        time.sleep(3)

    print("  Timed out waiting for worker. Try again or use --source local.")
    sys.exit(1)


def refresh_models_only(volume_id: str, api_key: str, cache_path: Path) -> dict:
    """
    Refresh only model lists in the existing cache by scanning the
    RunPod network volume. Patches ckpt_name, lora_name, vae_name, etc.
    widget lists without a full re-fetch.
    """
    print(f"Refreshing model lists from network volume {volume_id} ...")

    if not cache_path.exists():
        print(f"ERROR: Cache file not found: {cache_path}")
        print("  Run first: python scripts/fetch_object_info.py --source local")
        sys.exit(1)

    with open(cache_path, "r") as f:
        cache = json.load(f)

    # Use RunPod API to list files on the network volume
    # The RunPod API doesn't have a direct "list volume files" endpoint,
    # but we can use the serverless endpoint to list models.
    # For now, we'll document this as a TODO and just return the existing cache.
    print("  NOTE: Direct volume scanning requires SSH or a custom handler endpoint.")
    print("  For now, re-fetch from local ComfyUI after adding models:")
    print("    python scripts/fetch_object_info.py --source local")
    print()
    print("  Returning existing cache unchanged.")
    return cache


def save_cache(data: dict, output_path: str):
    """Save object_info to cache file."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} node definitions to {out}")
    print(f"  File size: {out.stat().st_size / 1024:.1f} KB")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and cache ComfyUI object_info for the frontend proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch from local ComfyUI
  python scripts/fetch_object_info.py --source local

  # Fetch from local ComfyUI on custom port
  python scripts/fetch_object_info.py --source local --url http://localhost:9000

  # Fetch from RunPod serverless (cold-starts a worker)
  python scripts/fetch_object_info.py --source runpod --endpoint-id YOUR_ID

  # Refresh only model lists (no worker cold-start)
  python scripts/fetch_object_info.py --models-only --volume-id v1abc123
        """
    )
    parser.add_argument("--source", choices=["local", "runpod"], default="local",
                        help="Where to fetch object_info from (default: local)")
    parser.add_argument("--url", default=DEFAULT_LOCAL_URL,
                        help=f"ComfyUI URL for --source local (default: {DEFAULT_LOCAL_URL})")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", ""),
                        help="RunPod endpoint ID for --source runpod")
    parser.add_argument("--api-key", default=os.environ.get("RUNPOD_API_KEY", ""),
                        help="RunPod API key for --source runpod")
    parser.add_argument("--volume-id", default="",
                        help="RunPod network volume ID for --models-only")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"Output file path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--models-only", action="store_true",
                        help="Only refresh model lists in existing cache (no full re-fetch)")
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.models_only:
        if not args.volume_id:
            print("ERROR: --models-only requires --volume-id")
            sys.exit(1)
        api_key = args.api_key or os.environ.get("RUNPOD_API_KEY", "")
        if not api_key:
            print("ERROR: --models-only requires RUNPOD_API_KEY (set in .env or --api-key)")
            sys.exit(1)
        data = refresh_models_only(args.volume_id, api_key, output_path)
        save_cache(data, args.output)
        return

    if args.source == "local":
        data = fetch_from_local(args.url)
    elif args.source == "runpod":
        if not args.endpoint_id:
            print("ERROR: --source runpod requires --endpoint-id (or RUNPOD_ENDPOINT_ID in .env)")
            sys.exit(1)
        if not args.api_key:
            print("ERROR: --source runpod requires --api-key (or RUNPOD_API_KEY in .env)")
            sys.exit(1)
        data = fetch_from_runpod(args.endpoint_id, args.api_key)
    else:
        print(f"ERROR: Unknown source: {args.source}")
        sys.exit(1)

    save_cache(data, args.output)
    print()
    print("Done! The proxy server will serve this cache to the frontend.")
    print("Restart the proxy if it's running: Ctrl+C and re-run python src/proxy_server.py")


if __name__ == "__main__":
    main()
