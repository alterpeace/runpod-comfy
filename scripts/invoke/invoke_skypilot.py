#!/usr/bin/env python3
"""
Invoke a V2V workflow against a SkyPilot-hosted ComfyUI instance.

This is the SkyPilot-style replacement for invoke_v2v_with_upload.py (which
targeted the now-deleted RunPod serverless endpoint). Same UX — upload video,
queue workflow, wait, download output — but against a ComfyUI instance
running on a SkyPilot GPU instance, reached through `sky port-forward`.

Prerequisites:
    ./scripts/skypilot/launch.sh            # boot the instance (once)
    ./scripts/skypilot/launch.sh port-forward   # in another terminal, or --port-forward below

Usage:
    # Process a video with the default (SeedVR2-chained) workflow
    uv run python scripts/invoke/invoke_skypilot.py --video rhizome.mp4

    # Custom workflow / prompt / seed
    uv run python scripts/invoke/invoke_skypilot.py --video clip.mp4 \
        --workflow examples/ltx25_v2v_redetail_entry_runpod.json \
        --prompt "cinematic, moody lighting" --seed 123

    # Different cluster / URL
    uv run python scripts/invoke/invoke_skypilot.py --video clip.mp4 --url http://localhost:8189
"""
import argparse
import json
import sys
import time
from pathlib import Path

# Allow running from repo root or anywhere
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.comfyui_client import ComfyUIClient, ComfyUIWorkflowError  # noqa: E402

DEFAULT_WORKFLOW = Path("examples/ltx25_v2v_redetail_seedvr2_runpod.json")


def find_video_loader_node(workflow: dict) -> str:
    """Find the node id of the VHS_LoadVideo node in an API-format workflow."""
    for node_id, node in workflow.items():
        if node.get("class_type") == "VHS_LoadVideo":
            return node_id
    raise SystemExit("ERROR: workflow has no VHS_LoadVideo node to point at the uploaded video")


def find_output_files(history: dict) -> list:
    """Extract (filename, subfolder) pairs from VHS_VideoCombine outputs."""
    files = []
    for node_output in history.get("outputs", {}).values():
        for key in ("gifs", "images", "videos"):
            for entry in node_output.get(key, []):
                files.append((entry.get("filename"), entry.get("subfolder", "")))
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Upload a video, run a workflow on a SkyPilot ComfyUI instance, download the result.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video", required=True, type=Path, help="Local video file to process")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW, help="Workflow JSON (API format)")
    parser.add_argument("--url", default="http://localhost:8188",
                        help="ComfyUI base URL (default: http://localhost:8188 via sky port-forward)")
    parser.add_argument("--prompt", help="Override positive prompt")
    parser.add_argument("--negative", help="Override negative prompt")
    parser.add_argument("--seed", type=int, help="Override noise seed")
    parser.add_argument("--timeout", type=int, default=1800, help="Max wait in seconds (default: 1800)")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Directory for downloaded results")
    parser.add_argument("--dry-run", action="store_true", help="Show patched workflow without invoking")
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"ERROR: video not found: {args.video}")
    if not args.workflow.exists():
        raise SystemExit(f"ERROR: workflow not found: {args.workflow}")

    workflow = json.loads(args.workflow.read_text())

    # Point the video loader at the file we will upload
    loader_id = find_video_loader_node(workflow)
    workflow[loader_id]["inputs"]["video"] = args.video.name

    # Apply overrides
    for node in workflow.values():
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            if args.prompt and "blurry" not in text:  # heuristic: positive prompt
                node["inputs"]["text"] = args.prompt
            elif args.negative and "blurry" in text:
                node["inputs"]["text"] = args.negative
        if node.get("class_type") == "RandomNoise" and args.seed is not None:
            node["inputs"]["noise_seed"] = args.seed

    if args.dry_run:
        print(json.dumps(workflow, indent=2))
        return

    client = ComfyUIClient(base_url=args.url, timeout=600)

    # 1. Health check
    print(f"Checking ComfyUI at {args.url} ...")
    try:
        if not client.health_check():
            raise RuntimeError("health check returned False")
    except Exception as e:
        raise SystemExit(
            f"ERROR: cannot reach ComfyUI at {args.url} ({e}).\n"
            f"Boot the instance and port-forward first:\n"
            f"  ./scripts/skypilot/launch.sh\n"
            f"  ./scripts/skypilot/launch.sh port-forward"
        )

    # 2. Upload the video
    print(f"Uploading {args.video} ({args.video.stat().st_size / 1e6:.1f} MB) ...")
    with open(args.video, "rb") as f:
        upload = client.upload_file(f.read(), args.video.name, overwrite=True)
    uploaded_name = upload.get("name", args.video.name)
    if uploaded_name != args.video.name:
        workflow[loader_id]["inputs"]["video"] = uploaded_name
        print(f"  stored as: {uploaded_name}")

    # 3. Queue and wait
    print("Queueing workflow ...")
    prompt_id = client.queue_prompt(workflow)
    print(f"  prompt_id: {prompt_id}")
    print(f"Waiting for completion (timeout {args.timeout}s) — this can take 5-15 min for 15s clips ...")
    start = time.time()
    history = client.wait_for_completion(prompt_id, poll_interval=5, max_wait_time=args.timeout)
    elapsed = time.time() - start
    print(f"Completed in {elapsed / 60:.1f} min")

    # 4. Download outputs
    files = find_output_files(history)
    if not files:
        raise SystemExit(f"WARNING: no output files found in history: {json.dumps(history)[:500]}")

    args.out.mkdir(parents=True, exist_ok=True)
    for filename, subfolder in files:
        data = client.get_image(filename, subfolder=subfolder, folder_type="output")
        dest = args.out / filename
        dest.write_bytes(data)
        print(f"  saved: {dest} ({len(data) / 1e6:.1f} MB)")

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except ComfyUIWorkflowError as e:
        raise SystemExit(f"WORKFLOW ERROR: {e}")
    except KeyboardInterrupt:
        raise SystemExit("Interrupted.")
