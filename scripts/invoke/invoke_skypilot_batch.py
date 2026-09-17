#!/usr/bin/env python3
"""
Batch V2V processing of clips already on the SkyPilot pod's input dir.

Unlike invoke_skypilot.py (which HTTP-uploads each video), this script
points the workflow's VHS_LoadVideo node at files already under
/workspace/input/<dir>/ on the pod — no per-clip upload. Resumable: clips
whose output file already exists are skipped.

Usage:
    uv run python scripts/invoke/invoke_skypilot_batch.py \
        --dir sample --workflow examples/ltx25_v2v_redetail_comfortable_runpod.json \
        --out output/redetail_batch
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.comfyui_client import ComfyUIClient, ComfyUIWorkflowError  # noqa: E402


def find_video_loader_node(workflow: dict) -> str:
    for node_id, node in workflow.items():
        if node.get("class_type") == "VHS_LoadVideo":
            return node_id
    raise SystemExit("ERROR: workflow has no VHS_LoadVideo node")


def find_output_files(history: dict) -> list:
    files = []
    for node_output in history.get("outputs", {}).values():
        for key in ("gifs", "images", "videos"):
            for entry in node_output.get(key, []):
                files.append((entry.get("filename"), entry.get("subfolder", "")))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default="sample", help="Subdir of pod input dir holding the clips")
    parser.add_argument("--workflow", type=Path,
                        default=Path("examples/ltx25_v2v_redetail_comfortable_runpod.json"))
    parser.add_argument("--url", default="http://localhost:8188")
    parser.add_argument("--out", type=Path, default=Path("output/redetail_batch"))
    parser.add_argument("--timeout", type=int, default=1800, help="Per-clip wait in seconds")
    parser.add_argument("--no-random-seed", action="store_true",
                        help="Keep the workflow's fixed seed instead of randomizing per clip")
    parser.add_argument("--dry-run", action="store_true", help="List clips and exit")
    parser.add_argument("clips", nargs="*", help="Optional: specific clip filenames (default: all in --dir)")
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text())
    workflow = {k: v for k, v in workflow.items() if isinstance(v, dict) and "class_type" in v}
    loader_id = find_video_loader_node(workflow)

    clips = sorted(Path("sample").glob("*.mp4"))
    if not clips:
        raise SystemExit("ERROR: no clips found under sample/")
    if args.clips:
        wanted = {Path(c).name for c in args.clips}
        clips = [c for c in clips if c.name in wanted]
        missing = wanted - {c.name for c in clips}
        if missing:
            print(f"WARNING: not found in {args.dir}/: {sorted(missing)}")
    pending = [c for c in clips if not (args.out / f"{c.stem}.mp4").exists()]
    print(f"{len(clips)} clips total, {len(clips) - len(pending)} already done, {len(pending)} to process")
    if args.dry_run:
        for c in pending:
            print("  queued-plan:", c.name)
        return
    if not pending:
        print("Nothing to do.")
        return

    client = ComfyUIClient(base_url=args.url, timeout=600)
    if not client.health_check():
        raise SystemExit(f"ERROR: ComfyUI not reachable at {args.url}")

    args.out.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    t_all = time.time()
    for i, clip in enumerate(pending, 1):
        print(f"\n=== [{i}/{len(pending)}] {clip.name} ({clip.stat().st_size / 1e6:.0f} MB) ===")
        wf = json.loads(json.dumps(workflow))  # deep copy
        wf[loader_id]["inputs"]["video"] = f"{args.dir}/{clip.name}"
        if not args.no_random_seed:
            import random
            seed = random.randint(1, 2**31 - 1)
            for node in wf.values():
                if node.get("class_type") == "RandomNoise":
                    node["inputs"]["noise_seed"] = seed
            if "SeedVR2VideoUpscaler" in [n.get("class_type") for n in wf.values()]:
                for node in wf.values():
                    if node.get("class_type") == "SeedVR2VideoUpscaler":
                        node["inputs"]["seed"] = seed
            print(f"  seed: {seed}")
        try:
            t0 = time.time()
            prompt_id = client.queue_prompt(wf)
            history = client.wait_for_completion(prompt_id, poll_interval=5,
                                                 max_wait_time=args.timeout)
            files = find_output_files(history)
            if not files:
                raise RuntimeError(f"no output files in history: {json.dumps(history)[:300]}")
            data = client.get_image(files[0][0], subfolder=files[0][1], folder_type="output")
            dest = args.out / f"{clip.stem}.mp4"
            dest.write_bytes(data)
            print(f"  done in {(time.time() - t0) / 60:.1f} min -> {dest} ({len(data) / 1e6:.1f} MB)")
            done += 1
        except (ComfyUIWorkflowError, RuntimeError, Exception) as e:  # noqa: B014 - keep batch going
            print(f"  FAILED: {e}")
            failed += 1

    total_min = (time.time() - t_all) / 60
    print(f"\nBatch complete: {done} ok, {failed} failed, {total_min:.0f} min total")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Interrupted.")
