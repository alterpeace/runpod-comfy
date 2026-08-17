#!/usr/bin/env python3
"""
Alt Retake — Generate creative variations for music visuals.

Uses direct path references (no base64 upload) so it works with ANY file size.
Videos must already be on the RunPod volume at /runpod-volume/input/<path>.

## Output Naming Convention

Outputs use a structured, token-based filename:

    al7/al7_<variation>_<params>_<version>.mp4

Where:
  - al7              = project code (alterpeace LTX 2.5)
  - <variation>      = variation name (e.g. "velour", "obsidian")
  - <params>          = compact parameter encoding (see below)
  - <version>        = timestamp-based version ID (YYYYMMDD_hhmmss)

### Compact Parameter Encoding (short_hand_params)

Parameters are encoded as a single alphanumeric token:

    s<seed>d<denoise>l<lora>

Where denoise and lora are encoded as 2-digit integers (value × 10):
  - denoise 0.3 → d03
  - denoise 0.4 → d04
  - lora 0.5    → l05
  - lora 1.0    → l10

Example: s42d03l05 = seed 42, denoise 0.3, lora 0.5

Usage:
    set -a && source .env && set +a
    uv run python scripts/invoke/alt_retake.py --video rhizome.mp4
    uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-52_00007.mp4
    uv run python scripts/invoke/alt_retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4 --dry-run

    # Parameter sweep — test denoise and lora_strength combinations
    uv run python scripts/invoke/alt_retake.py --video rhizome.mp4 \\
        --denoise-sweep 0.2,0.3,0.5 --lora-sweep 0.3,0.5,0.7
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Run: uv sync")
    sys.exit(1)

DEFAULT_WORKFLOW = Path(__file__).parent.parent.parent / "examples" / "ltx25_v2v_redetail_entry_runpod.json"

# ---------------------------------------------------------------------------
# Negative Prompt — comprehensive exclusion list
# ---------------------------------------------------------------------------
NEGATIVE_PROMPT = (
    "people, faces, humans, characters, portraits, figures, persons, "
    "crowd, audience, hands, body, skin, "
    "cgi, render, cartoon, "
    "dots, speckles, halftone, stippling, grain, noise, static, "
    "glossy skin, plastic skin, worst quality, low quality, "
    "deformed, distorted, blurry, jpeg artifacts, ugly, duplicate, "
    "mutated hands, poorly drawn hands, poorly drawn face, bad anatomy, "
    "extra limbs, extra fingers, fused fingers, missing limbs, long neck, "
    "text, watermark, signature, low resolution, "
    "cropped, shaking, jittery, oversharpened, banding, scan lines"
)

# ---------------------------------------------------------------------------
# Base visual vocabulary — appended to all prompts for consistency
# ---------------------------------------------------------------------------
# For V2V redetail: the source video already defines camera movement, pacing,
# and scale. The prompt should focus on texture, lighting, color, and
# atmosphere — NOT camera language or pacing, which would conflict with
# the source footage's motion. The model re-renders the existing motion
# with new visual style; it doesn't create new camera moves.
#
# This BASE_VISUALS is the signature style for al7. It's designed based on
# what's working in the AI VJ art community:
# - Volumetric depth (fog, particles, light shafts) for projection-friendly layering
# - Material richness (liquid metal, glass, crystalline) for tangible surfaces
# - Optical effects (chromatic aberration, light leaks) for the VJ aesthetic
# - Luminosity (glowing, radiant) for self-luminous elements on big screens
# - Quality markers (ultra detailed, sharp focus) for clean renders
BASE_VISUALS = (
    "volumetric fog, atmospheric haze, light shafts, "
    "floating particles, dust motes, "
    "liquid metal, iridescent, holographic, "
    "glass refraction, crystalline, "
    "chromatic aberration, light leaks, prismatic, "
    "glowing, radiant, luminous, "
    "ultra detailed, sharp focus, clean render"
)
# ---------------------------------------------------------------------------

VARIATIONS = [
    {
        "name": "obsidian",
        "seed": 1337,
        "denoise": 0.3,
        "lora_strength": 0.5,
        "prompt": (
            f"high contrast, neon glow, dramatic shadows, "
            f"glossy black surfaces, reflective, "
            f"dark tones with electric highlights, "
            f"sharp edges, geometric, {BASE_VISUALS}"
        ),
    },
    {
        "name": "mirage",
        "seed": 36963,
        "denoise": 0.3,
        "lora_strength": 0.5,
        "prompt": (
            f"liquid metal, iridescent, holographic, prismatic refraction, "
            f"chromatic aberration, light leaks, "
            f"flowing organic shapes, morphing, hypnotic, "
            f"natural sunlight, dramatic shadows, worn fabric, "
            f"muted color palette, film grain, {BASE_VISUALS}"
        ),
    },
]


def encode_params(seed: int, denoise: float, lora: float) -> str:
    """Encode generation parameters as a compact token.

    Format: s<seed>d<DD>l<LL>
    Where DD = denoise × 10 (2 digits), LL = lora × 10 (2 digits)

    Example: s42d03l05 = seed 42, denoise 0.3, lora 0.5
    """
    d = int(denoise * 10)
    l = int(lora * 10)
    return f"s{seed}d{d:02d}l{l:02d}"


def generate_version_id() -> str:
    """Generate a timestamp-based version identifier.

    Format: YYYYMMDD_hhmmss
    This acts as a unique version number per generation request.
    If you regenerate with the same parameters, you get a new version
    with a different timestamp, enabling version tracking without Git.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_source_frame_count(video_path: str) -> int | None:
    """Get the total frame count of a video using ffprobe.

    The video path is on the RunPod worker, so we can't probe it locally.
    Instead, we use the diagnostic action to run ffprobe on the worker.
    But since alt_retake.py runs locally and the video is on the worker,
    we need to probe a LOCAL copy if available, or use --frame-count to
    specify manually.

    For local files (when testing), we can probe directly.
    For remote files (on the worker), the user should use --frame-count.
    """
    # Try to probe locally (works if the file exists on this machine)
    # Check common local paths
    local_paths = [
        video_path,
        os.path.expanduser(f"~/Desktop/sample/{os.path.basename(video_path)}"),
    ]

    for path in local_paths:
        if os.path.exists(path):
            cmd = [
                "ffprobe", "-v", "quiet", "-select_streams", "v:0",
                "-count_packets", "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0", path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                count = int(result.stdout.strip())
                if count > 0:
                    return count

    return None


def build_filename_prefix(variation: dict, subdir: str = "qtrtime") -> str:
    """Build the VFX-style filename prefix for ComfyUI output.

    Format: al7/<subdir>/al7_<name>_<params>_<version>

    The MP4 goes to: al7/qtrtime/al7_velour_s42d03l05_20260816_192200_00001.mp4
    The PNG goes to: al7/qtrtime/images/al7_velour_s42d03l05_20260816_192200_00001.png

    ComfyUI's VHS_VideoCombine will append _00001.mp4 etc. to this prefix.
    Directories are created automatically by ComfyUI if they don't exist.
    """
    name = variation["name"]
    params = encode_params(
        variation["seed"],
        variation["denoise"],
        variation["lora_strength"],
    )
    version = generate_version_id()
    return f"al7/{subdir}/al7_{name}_{params}_{version}"


def generate_variation(endpoint, workflow, video_path, variation,
                       frame_count=0, fps=24):
    """Generate a single variation using direct path reference (no upload).

    Args:
        frame_count: Number of frames to load from source (0 = load all)
        fps: Frame rate for both input loading and output encoding
    """
    wf = json.loads(json.dumps(workflow))

    # Patch workflow with variation parameters
    wf["7"]["inputs"]["video"] = video_path
    wf["7"]["inputs"]["force_rate"] = fps
    # frame_load_cap: 0 means load all frames; otherwise load exactly N
    wf["7"]["inputs"]["frame_load_cap"] = frame_count
    wf["5"]["inputs"]["text"] = variation["prompt"]
    wf["6"]["inputs"]["text"] = NEGATIVE_PROMPT
    wf["13"]["inputs"]["noise_seed"] = variation["seed"]
    wf["11"]["inputs"]["denoise"] = variation["denoise"]
    wf["3"]["inputs"]["strength_model"] = variation["lora_strength"]
    wf["3"]["inputs"]["strength_clip"] = variation["lora_strength"]

    # Set output frame rate to match
    wf["20"]["inputs"]["frame_rate"] = fps

    # Set VFX-style filename prefix for video
    prefix = build_filename_prefix(variation)
    wf["20"]["inputs"]["filename_prefix"] = prefix
    # Use custom h264-al7 format with embedded artist metadata
    wf["20"]["inputs"]["format"] = "video/h264-al7"

    # Submit job — NO input_files, just the workflow with path reference
    job = endpoint.run({
        "input": {
            "workflow": wf,
            "timeout": 600,
        }
    })

    return job, prefix


def main():
    parser = argparse.ArgumentParser(
        description="Generate creative variations for music visuals with VFX-style naming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Filename format:
  al7/al7_<name>_<params>_<version>.mp4

  Example: al7/al7_velour_s42d03l05_20260816_192200_00001.mp4

  Params: s42d03l05 = seed 42, denoise 0.3, lora 0.5

Communities for LTX prompt engineering:
  - ComfyUI Discord (#ltx-video)
  - r/comfyui, r/StableDiffusion
  - Civitai.com (LTX models + prompts)
  - Hugging Face (Lightricks/LTX-2.5)
  - X/Twitter: #LTX #ComfyUI
        """,
    )
    parser.add_argument("--video", required=True, help="Video path on volume (e.g. rhizome.mp4 or sample/clip_001.mp4)")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--match-frames", action="store_true", default=True,
        help="Auto-detect source video frame count and match it (default)",
    )
    parser.add_argument(
        "--frame-count", type=int, default=0,
        help="Manually set frame_load_cap (0 = load all frames from source)",
    )
    parser.add_argument(
        "--fps", type=int, default=24,
        help="Frame rate for input loading and output encoding (default: 24)",
    )
    parser.add_argument(
        "--random-seeds", action="store_true",
        help="Use random seeds instead of the fixed defaults (latent space exploration)",
    )
    parser.add_argument(
        "--seed-sweep", type=int, default=0,
        help="Test N seeds per variation (e.g. --seed-sweep 3 = 3 random seeds × 5 variations = 15 jobs)",
    )
    parser.add_argument(
        "--seed-min", type=int, default=1,
        help="Minimum seed value for random generation (default: 1)",
    )
    parser.add_argument(
        "--seed-max", type=int, default=999999,
        help="Maximum seed value for random generation (default: 999999)",
    )
    parser.add_argument(
        "--denoise-sweep", type=str, default=None,
        help="Comma-separated denoise values to sweep (e.g. --denoise-sweep 0.2,0.3,0.5). "
             "Creates a cartesian product with variations and --lora-sweep if set.",
    )
    parser.add_argument(
        "--lora-sweep", type=str, default=None,
        help="Comma-separated lora_strength values to sweep (e.g. --lora-sweep 0.3,0.5,0.7). "
             "Creates a cartesian product with variations and --denoise-sweep if set.",
    )
    args = parser.parse_args()

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Load workflow
    with open(args.workflow) as f:
        workflow = json.load(f)

    # Auto-detect source frame count
    frame_count = args.frame_count
    if args.match_frames and frame_count == 0:
        detected = get_source_frame_count(args.video)
        if detected:
            frame_count = detected
            print(f"Source: {args.video} ({frame_count} frames detected)")
        else:
            print(f"Source: {args.video} (frame count unknown — will load all frames)")
            frame_count = 0  # 0 = load all
    elif frame_count > 0:
        print(f"Source: {args.video} (using --frame-count {frame_count})")
    else:
        print(f"Source: {args.video} (will load all frames)")

    duration_est = frame_count / args.fps if frame_count > 0 else 0
    print(f"Workflow: {args.workflow}")
    print(f"Endpoint: {args.endpoint_id}")
    if frame_count > 0:
        print(f"Frames: {frame_count} (~{duration_est:.1f}s @ {args.fps}fps)")
    else:
        print(f"Frames: all (frame_load_cap=0)")
    print(f"Naming: al7/qtrtime/al7_<name>_<params>_<timestamp>.mp4")

    # Parse parameter sweep values
    denoise_values = None
    lora_values = None
    if args.denoise_sweep:
        denoise_values = [float(x.strip()) for x in args.denoise_sweep.split(",")]
    if args.lora_sweep:
        lora_values = [float(x.strip()) for x in args.lora_sweep.split(",")]

    # Build the job list
    # Default: 1 job per variation (fixed seed, fixed denoise/lora from VARIATIONS)
    # --random-seeds: 1 random seed per variation
    # --seed-sweep N: N random seeds per variation
    # --denoise-sweep / --lora-sweep: cartesian product of (variation × denoise × lora)
    #   If only one sweep is set, the other uses the variation's default value
    jobs_list = []
    sweep_count = args.seed_sweep if args.seed_sweep > 0 else 1
    use_random = args.random_seeds or args.seed_sweep > 0

    for var in VARIATIONS:
        # Determine the parameter grid for this variation
        d_values = denoise_values if denoise_values else [var["denoise"]]
        l_values = lora_values if lora_values else [var["lora_strength"]]

        for d in d_values:
            for l in l_values:
                if use_random:
                    for _ in range(sweep_count):
                        seed = random.randint(args.seed_min, args.seed_max)
                        v = dict(var)
                        v["seed"] = seed
                        v["denoise"] = d
                        v["lora_strength"] = l
                        jobs_list.append(v)
                else:
                    v = dict(var)
                    v["denoise"] = d
                    v["lora_strength"] = l
                    jobs_list.append(v)

    total_jobs = len(jobs_list)
    # Build mode description
    mode_parts = []
    if args.seed_sweep > 0:
        mode_parts.append(f"seed sweep ×{sweep_count}")
    elif use_random:
        mode_parts.append("random seeds")
    else:
        mode_parts.append("fixed seeds")
    if denoise_values:
        mode_parts.append(f"denoise sweep {denoise_values}")
    if lora_values:
        mode_parts.append(f"lora sweep {lora_values}")
    mode = " + ".join(mode_parts)
    print(f"Mode: {mode} ({total_jobs} jobs total)")
    print(f"\nGenerating {total_jobs} alt retake variations...\n")

    results = []
    for idx, var in enumerate(jobs_list):
        params_token = encode_params(var["seed"], var["denoise"], var["lora_strength"])
        prefix_preview = build_filename_prefix(var)

        print(f"[{idx+1}/{total_jobs}] {var['name']} (seed={var['seed']})")
        print(f"  Params: {params_token} (seed={var['seed']}, denoise={var['denoise']}, lora={var['lora_strength']})")
        print(f"  Output: {prefix_preview}_00001.mp4")
        print(f"  Prompt: {var['prompt'][:100]}...")

        if args.dry_run:
            print("  (dry run — skipping generation)")
            results.append({"variation": var["name"], "status": "dry_run", "prefix": prefix_preview, "params": params_token})
            continue

        # Generate — direct path reference, no upload
        job, prefix = generate_variation(
            endpoint, workflow, args.video, var,
            frame_count=frame_count, fps=args.fps,
        )
        print(f"  Job: {job.job_id}")

        start = time.time()
        while job.status() in ["IN_QUEUE", "IN_PROGRESS"]:
            time.sleep(10)
            elapsed = int(time.time() - start)
            print(f"    [{elapsed}s] {job.status()}...", end="\r")

        status = job.status()
        elapsed = int(time.time() - start)
        print(f"  {status} ({elapsed}s)")

        output = job.output()

        # Handle None output (FAILED status, timeout, etc.)
        if output is None:
            error_msg = f"Job {status} with no output (likely timeout or worker error)"
            print(f"  ❌ Error: {error_msg}")
            results.append({
                "variation": var["name"],
                "seed": var["seed"],
                "denoise": var["denoise"],
                "lora_strength": var["lora_strength"],
                "params": params_token,
                "status": "failed",
                "error": error_msg,
                "elapsed": elapsed,
                "prefix": prefix,
            })
            print()
            continue

        # Check if the job succeeded
        if output.get("status") == "success":
            print(f"  ✅ Success!")
            results.append({
                "variation": var["name"],
                "seed": var["seed"],
                "denoise": var["denoise"],
                "lora_strength": var["lora_strength"],
                "params": params_token,
                "status": "success",
                "elapsed": elapsed,
                "prefix": prefix,
            })
        else:
            # Extract error message from multiple possible locations
            error_msg = (
                output.get("error")
                or output.get("error_message")
                or output.get("metadata", {}).get("error_message")
                or str(output)[:500]
            )
            print(f"  ❌ Error: {str(error_msg)[:500]}")
            results.append({
                "variation": var["name"],
                "seed": var["seed"],
                "denoise": var["denoise"],
                "lora_strength": var["lora_strength"],
                "params": params_token,
                "status": "failed",
                "error": str(error_msg)[:500],
                "elapsed": elapsed,
                "prefix": prefix,
            })

        print()

    # Summary
    print("=" * 70)
    print("ALT RETAKE SUMMARY")
    print("=" * 70)
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {status_icon} {r['variation']:12s} {r.get('params', '?'):12s}  {r.get('prefix', '?')}")

    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"\n{success_count}/{total_jobs} variations generated successfully")
    print(f"\nDownload outputs:")
    print(f"  uv run python scripts/storage/sync_outputs.py <local_output_dir>")
    print(f"\nList outputs:")
    print(f"  uv run python scripts/storage/list_s3.py --prefix output/al7/qtrtime/")


if __name__ == "__main__":
    main()
