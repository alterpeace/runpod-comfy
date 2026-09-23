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


def find_cond_nodes(workflow: dict) -> tuple[str, str]:
    """Node ids of the positive / negative CLIPTextEncode via the CFGGuider."""
    def to_text_node(ref: list) -> str:
        # Walk up through conditioning pass-throughs (e.g. LTXVConditioning,
        # whose outputs 0/1 = positive/negative) to the CLIPTextEncode.
        nid, slot = ref[0], ref[1]
        for _ in range(10):
            node = workflow[nid]
            if node.get("class_type") == "CLIPTextEncode":
                return nid
            key = "negative" if slot == 1 else "positive"
            nid, slot = node["inputs"][key][0], node["inputs"][key][1]
        raise SystemExit(f"ERROR: no CLIPTextEncode upstream of {ref}")

    for node_id, node in workflow.items():
        if node.get("class_type") == "CFGGuider":
            return (to_text_node(node["inputs"]["positive"]),
                    to_text_node(node["inputs"]["negative"]))
    raise SystemExit("ERROR: workflow has no CFGGuider to locate prompt nodes")


def find_output_files(history: dict) -> list:
    files = []
    for node_output in history.get("outputs", {}).values():
        for key in ("gifs", "images", "videos"):
            for entry in node_output.get(key, []):
                files.append((entry.get("filename"), entry.get("subfolder", "")))
    return files


MAX_FRAMES = 385  # documented LTX-2.5 max at 1536x896; 385 = 8*48+1


def probe_frames(clip: Path) -> int:
    """Frame count the pod-side VHS_LoadVideo will deliver at force_rate=24."""
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames,avg_frame_rate,duration",
         "-of", "json", str(clip)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    num, _, den = st.get("avg_frame_rate", "24/1").partition("/")
    fps = float(num) / float(den or 1)
    if st.get("nb_frames"):
        return round(int(st["nb_frames"]) * 24 / fps)
    return round(float(st["duration"]) * 24)


def probe_size(clip: Path) -> tuple[int, int]:
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(clip)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return int(st["width"]), int(st["height"])


def pass1_size(w: int, h: int, area: int = 960 * 544) -> tuple[int, int]:
    """Multiple-of-32 size near `area` pixels with the source's aspect ratio."""
    ar = w / h
    pw = max(32, round((area * ar) ** 0.5 / 32) * 32)
    ph = max(32, round(pw / ar / 32) * 32)
    return pw, ph


def match_size_nodes(wf: dict, roles: dict, w: int, h: int) -> tuple[int, int]:
    """Aspect-matched sampling size for the loop_wrap pass-1 resize nodes."""
    pw, ph = pass1_size(w, h)
    for nid in roles.get("pass1_resize", []):
        wf[nid]["inputs"]["width"], wf[nid]["inputs"]["height"] = pw, ph
    return pw, ph


def match_length_nodes(wf: dict, loader_id: str, n: int) -> tuple[int, int]:
    """Rewrite loader cap + pad/trim nodes so output frames == n.

    LTX needs frames ≡ 1 (mod 8). n is first reduced to the largest such
    value (dropping tail frames when the pad would exceed 2), then the
    tail-pad repeat (nodes feeding an ImageBatch) and post-decode trim
    (ImageFromBatch feeding the video combine) are rewritten per clip.
    """
    pad = (8 - ((n - 1) % 8)) % 8
    if pad > 1:  # ImageFromBatch clamps at the batch edge: only a 1-frame pad is safe
        n -= (8 - pad)
        pad = 0
    wf[loader_id]["inputs"]["frame_load_cap"] = n

    consumers: dict[str, list[tuple[str, str]]] = {}
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        for key, v in node.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                consumers.setdefault(v[0], []).append((nid, key))

    def cls(nid: str) -> str:
        return wf[nid].get("class_type", "")

    pad_src = pad_batch = trim = None
    for nid, node in wf.items():
        if not isinstance(node, dict) or cls(nid) != "ImageFromBatch":
            continue
        outs = consumers.get(nid, [])
        if any(cls(c) == "ImageBatch" for c, _ in outs):
            pad_src = nid
        else:
            trim = nid
    for nid, node in wf.items():
        if isinstance(node, dict) and cls(nid) == "ImageBatch":
            pad_batch = nid
    if not (pad_src and pad_batch and trim):
        raise SystemExit("ERROR: workflow lacks the pad/trim nodes needed for --length-match")
    resize = next(nid for nid, node in wf.items()
                  if isinstance(node, dict)
                  and any(v == [pad_batch, 0] for v in node.get("inputs", {}).values()))

    if pad == 0:
        wf[resize]["inputs"]["image"] = [loader_id, 0]
    else:
        wf[pad_src]["inputs"]["batch_index"] = n - 1
        wf[pad_src]["inputs"]["length"] = pad
        wf[resize]["inputs"]["image"] = [pad_batch, 0]
    wf[trim]["inputs"]["length"] = n
    return n, pad


LOOP_MAX_FRAMES = 384  # N + wrap <= 385 keeps both passes in one temporal tile


def match_loop_wrap_nodes(wf: dict, loader_id: str, n: int, roles: dict) -> tuple[int, int, str]:
    """Exact-length seam pinning for sources that already loop.

    Loads all N source frames, appends source frames 0..p-1 (the loop's own
    continuation) so N+p ≡ 1 (mod 8), pins output 0 -> source 0, a -> source
    N-1, b -> source 0 (wrap copy), and trims to N. The output's N-1 -> 0 wrap
    is then the source's own seam. With guiding latents a pin at 8k+1 raises
    in LTXVInContextSampler, so a shifts to N-2 or b to N+1 (wrap frame 1).
    Roles (node ids) come from the workflow's _metadata.length_match.
    """
    n = min(n, LOOP_MAX_FRAMES)
    p = (1 - n) % 8 or 8
    a, b = n - 1, n
    if a % 8 == 1:
        a = n - 2
    if b % 8 == 1:
        b = n + 1  # p == 8 here, so wrap frame 1 exists
    wf[loader_id]["inputs"]["frame_load_cap"] = n
    wf[roles["wrap"]]["inputs"]["batch_index"] = 0
    wf[roles["wrap"]]["inputs"]["length"] = p
    if roles.get("kf_a") and roles.get("kf_b"):
        # Legacy per-seam-frame pins (source frames N-1 / wrap copy).
        wf[roles["kf_a"]]["inputs"]["batch_index"] = a
        wf[roles["kf_b"]]["inputs"]["batch_index"] = b
    # else: single-anchor mode -- all three pins are one image repeated 3x
    # (source frame 0 by default, or --anchor-image), no per-pin indices.
    for sid in roles["samplers"]:
        wf[sid]["inputs"]["optional_cond_image_indices"] = f"0, {a}, {b}"
    wf[roles["trim"]]["inputs"]["batch_index"] = 0
    wf[roles["trim"]]["inputs"]["length"] = n
    return n, p, f"0, {a}, {b}"


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
    parser.add_argument("--no-length-match", action="store_true",
                        help="Disable per-clip frame-count matching (default: match via ffprobe)")
    parser.add_argument("--prompt", default=None,
                        help="Override the workflow's positive prompt (node via CFGGuider)")
    parser.add_argument("--negative", default=None,
                        help="Override the workflow's negative prompt")
    parser.add_argument("--denoise", type=float, default=None,
                        help="loop_wrap workflows: BasicScheduler denoise (0.4 polish, 0.55 default, 0.7 more life, 1.0 full restyle)")
    parser.add_argument("--anchor-image", default=None,
                        help="loop_wrap workflows: pod input filename of a still to pin instead of source frame 0 "
                             "(only coherent at --denoise 1.0; lower denoise snaps)")
    parser.add_argument("--shuffle", action="store_true", help="Process clips in random order")
    parser.add_argument("--dry-run", action="store_true", help="List clips and exit")
    parser.add_argument("clips", nargs="*", help="Optional: specific clip filenames (default: all in --dir)")
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text())
    loop_roles = workflow.get("_metadata", {}).get("length_match")
    if not (isinstance(loop_roles, dict) and loop_roles.get("mode") == "loop_wrap"):
        loop_roles = None
    workflow = {k: v for k, v in workflow.items() if isinstance(v, dict) and "class_type" in v}
    loader_id = find_video_loader_node(workflow)
    pos_id, neg_id = find_cond_nodes(workflow)

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
    if args.shuffle:
        import random
        random.shuffle(pending)
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
        if args.prompt:
            wf[pos_id]["inputs"]["text"] = args.prompt
        if args.negative:
            wf[neg_id]["inputs"]["text"] = args.negative
        if loop_roles and args.denoise is not None and loop_roles.get("denoise"):
            wf[loop_roles["denoise"]]["inputs"]["denoise"] = args.denoise
        if loop_roles and args.anchor_image and loop_roles.get("anchor_kf"):
            wf["9001"] = {"inputs": {"image": args.anchor_image}, "class_type": "LoadImage",
                          "_meta": {"title": "Anchor still (--anchor-image)"}}
            wf["9002"] = {"inputs": {"image": ["9001", 0], "upscale_method": "lanczos",
                                     "width": 960, "height": 544, "crop": "disabled"},
                          "class_type": "ImageScale", "_meta": {"title": "Anchor @ pass-1 res"}}
            wf[loop_roles["anchor_kf"]]["inputs"]["image"] = ["9002", 0]
            wf.pop(loop_roles.get("anchor_src", ""), None)
        if not args.no_length_match:
            n24 = probe_frames(clip)
            if loop_roles:
                if n24 > LOOP_MAX_FRAMES:
                    print(f"  WARNING: {n24} frames > {LOOP_MAX_FRAMES}: truncating breaks the source loop")
                n, p, pins = match_loop_wrap_nodes(wf, loader_id, n24, loop_roles)
                sw, sh = probe_size(clip)
                pw, ph = match_size_nodes(wf, loop_roles, sw, sh)
                if "9002" in wf:
                    wf["9002"]["inputs"]["width"], wf["9002"]["inputs"]["height"] = pw, ph
                note = f"exact, +{p} wrap frames, pins {pins}; sample/out {pw}x{ph} (source {sw}x{sh})"
            else:
                n, pad = match_length_nodes(wf, loader_id, min(n24, MAX_FRAMES))
                note = f"pad {pad}" if pad else f"dropped {min(n24, MAX_FRAMES) - n}"
            print(f"  length: {n24} frames @24fps -> {n} ({note})")
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
