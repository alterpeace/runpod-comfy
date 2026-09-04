#!/usr/bin/env python3
"""
Re-render specific clips (already on the pod) with a workflow, overwriting
the existing outputs in the batch dir. Queue-safe: can run alongside a
running batch — jobs go into ComfyUI's FIFO queue.

Usage:
    uv run python scripts/invoke/retry_clips.py \
        --clips clip_11-01-26_00013_thm2_prob4.mp4 clip_11-01-26_00027_thm2_prob4.mp4 \
        --workflow examples/ltx25_v2v_redetail_creative_2k_runpod.json
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.comfyui_client import ComfyUIClient  # noqa: E402


def find_output_files(history: dict) -> list:
    files = []
    for node_output in history.get("outputs", {}).values():
        for key in ("gifs", "images", "videos"):
            for entry in node_output.get(key, []):
                files.append((entry.get("filename"), entry.get("subfolder", "")))
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--clips", nargs="+", required=True, help="Clip filenames in sample/")
    p.add_argument("--dir", default="sample")
    p.add_argument("--workflow", type=Path,
                   default=Path("examples/ltx25_v2v_redetail_creative_2k_runpod.json"))
    p.add_argument("--out", type=Path, default=Path("output/redetail_batch"))
    p.add_argument("--url", default="http://localhost:8188")
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--keep-seed", action="store_true", help="Don't randomize seeds")
    args = p.parse_args()

    workflow = json.loads(args.workflow.read_text())
    workflow = {k: v for k, v in workflow.items() if isinstance(v, dict) and "class_type" in v}
    loader = next(n for n, node in workflow.items() if node.get("class_type") == "VHS_LoadVideo")

    client = ComfyUIClient(base_url=args.url, timeout=600)
    if not client.health_check():
        raise SystemExit(f"ERROR: ComfyUI not reachable at {args.url}")
    args.out.mkdir(parents=True, exist_ok=True)

    done = failed = 0
    for i, clip in enumerate(args.clips, 1):
        stem = Path(clip).stem
        print(f"[{i}/{len(args.clips)}] {clip}", flush=True)
        wf = json.loads(json.dumps(workflow))
        wf[loader]["inputs"]["video"] = f"{args.dir}/{clip}"
        if not args.keep_seed:
            seed = random.randint(1, 2**31 - 1)
            for node in wf.values():
                if node.get("class_type") in ("RandomNoise", "SeedVR2VideoUpscaler"):
                    if "noise_seed" in node.get("inputs", {}):
                        node["inputs"]["noise_seed"] = seed
                    elif "seed" in node.get("inputs", {}):
                        node["inputs"]["seed"] = seed
            print(f"  seed {seed}", flush=True)
        try:
            t0 = time.time()
            pid = client.queue_prompt(wf)
            history = client.wait_for_completion(pid, poll_interval=5, max_wait_time=args.timeout)
            files = find_output_files(history)
            if not files:
                raise RuntimeError("no output files in history")
            data = client.get_image(files[0][0], subfolder=files[0][1], folder_type="output")
            dest = args.out / f"{stem}.mp4"
            dest.write_bytes(data)
            print(f"  done {(time.time()-t0)/60:.1f} min -> {dest} ({len(data)/1e6:.1f} MB)", flush=True)
            done += 1
        except Exception as e:  # noqa: BLE001 - keep batch going
            print(f"  FAILED: {e}", flush=True)
            failed += 1
    print(f"\nRetry complete: {done} ok, {failed} failed", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
