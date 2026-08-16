#!/usr/bin/env python3
"""
Alt Retake — Generate creative variations for music visuals.

Uses direct path references (no base64 upload) so it works with ANY file size.
Videos must already be on the RunPod volume at /runpod-volume/input/<path>.

## Output Naming Convention

Outputs use a structured, token-based filename:

    al7/al7_<variation>-<prompt_num>_<params>_<version>.mp4

Where:
  - al7              = project code (alterpeace LTX 2.5)
  - <variation>      = variation name (e.g. "velour", "obsidian")
  - <prompt_num>     = 2-digit prompt variant number (01-99)
  - <params>          = compact parameter encoding (see below)
  - <version>        = timestamp-based version ID (YYYYMMDD_hhmmss)

### Compact Parameter Encoding (short_hand_params)

Parameters are encoded as a single alphanumeric token:

    s<seed>d<denoise>l<lora>

Where denoise and lora are encoded as 2-digit integers (value × 10):
  - denoise 0.3 → d03
  - denoise 0.4 → d04
  - lora 1.0    → l10
  - lora 0.5    → l05

Example: s42d03l10 = seed 42, denoise 0.3, lora 1.0

Usage:
    set -a && source .env && set +a
    uv run python scripts/alt_retake.py --video rhizome.mp4
    uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-52_00007.mp4
    uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4 --dry-run
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent / ".env"
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

DEFAULT_WORKFLOW = Path(__file__).parent.parent / "examples" / "ltx25_v2v_redetail_entry_runpod.json"

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
BASE_VISUALS = (
    "chromatic aberration, light leaks, prismatic refraction, "
    "liquid metal, iridescent, holographic, "
    "high quality render, sharp focus, clean detail, "
    "motion blur, depth of field, 4k detail"
)
# ---------------------------------------------------------------------------

VARIATIONS = [
    {
        "name": "velour",
        "seed": 42,
        "denoise": 0.3,
        "lora_strength": 1.0,
        "prompt": (
            f"cinematic, film noir, golden hour lighting, natural sunlight, "
            f"dramatic shadows, film grain, anamorphic lens flare, shallow depth of field, "
            f"smooth metal textures, vibrant color palette, "
            f"professional cinematography, {BASE_VISUALS}"
        ),
    },
    {
        "name": "obsidian",
        "seed": 1337,
        "denoise": 0.4,
        "lora_strength": 0.5,
        "prompt": (
            f"psychedelic, fractal patterns, morphing geometry, kaleidoscopic, "
            f"neon glow, dramatic shadows, high contrast, "
            f"rain, fog, smoke, particles, glossy surfaces, iridescent, "
            f"hypnotic, flowing organic shapes, {BASE_VISUALS}"
        ),
    },
    {
        "name": "halcyon",
        "seed": 8080,
        "denoise": 0.3,
        "lora_strength": 1.0,
        "prompt": (
            f"sacred geometry, mandala, infinite zoom, "
            f"experimental film, arthouse, volumetric fog, "
            f"dust, particles, natural sunlight, worn fabric textures, "
            f"muted color palette, particle systems, {BASE_VISUALS}"
        ),
    },
    {
        "name": "nebula",
        "seed": 2718,
        "denoise": 0.4,
        "lora_strength": 1.0,
        "prompt": (
            f"nebula clouds, cosmic dust, gravitational lensing, "
            f"deep space colors, ultraviolet, infrared, "
            f"star fields, light trails, wormhole, "
            f"dark background, glowing particles, volumetric light, "
            f"fluid dynamics, swirling, {BASE_VISUALS}"
        ),
    },
    {
        "name": "mirage",
        "seed": 31415,
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

    Example: s42d03l10 = seed 42, denoise 0.3, lora 1.0
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


def build_filename_prefix(variation: dict, prompt_num: int = 1) -> str:
    """Build the VFX-style filename prefix for ComfyUI output.

    Format: al7/al7_<name>-<NN>_<params>_<version>

    ComfyUI's VHS_VideoCombine will append _00001.mp4 etc. to this prefix.
    The directory (al7/) is created automatically by ComfyUI if it doesn't exist.
    """
    name = variation["name"]
    params = encode_params(
        variation["seed"],
        variation["denoise"],
        variation["lora_strength"],
    )
    version = generate_version_id()
    return f"al7/al7_{name}-{prompt_num:02d}_{params}_{version}"


def generate_variation(endpoint, workflow, video_path, variation, prompt_num=1,
                       duration=15, fps=24):
    """Generate a single variation using direct path reference (no upload).

    Args:
        duration: Target output duration in seconds (controls frame_load_cap)
        fps: Frame rate for both input loading and output encoding
    """
    wf = json.loads(json.dumps(workflow))

    # Calculate frame count from desired duration
    frame_count = int(duration * fps)

    # Patch workflow with variation parameters
    wf["7"]["inputs"]["video"] = video_path
    wf["7"]["inputs"]["force_rate"] = fps
    wf["7"]["inputs"]["frame_load_cap"] = frame_count
    wf["5"]["inputs"]["text"] = variation["prompt"]
    wf["6"]["inputs"]["text"] = NEGATIVE_PROMPT
    wf["13"]["inputs"]["noise_seed"] = variation["seed"]
    wf["11"]["inputs"]["denoise"] = variation["denoise"]
    wf["3"]["inputs"]["strength_model"] = variation["lora_strength"]
    wf["3"]["inputs"]["strength_clip"] = variation["lora_strength"]

    # Set output frame rate to match
    wf["20"]["inputs"]["frame_rate"] = fps

    # Set VFX-style filename prefix
    prefix = build_filename_prefix(variation, prompt_num)
    wf["20"]["inputs"]["filename_prefix"] = prefix

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
  al7/al7_<name>-<NN>_<params>_<version>.mp4

  Example: al7/al7_velour-01_s42d03l10_20260816_192200_00001.mp4

  Params: s42d03l10 = seed 42, denoise 0.3, lora 1.0

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
        "--duration", type=float, default=15.0,
        help="Target output duration in seconds (default: 15 = 5s loop x 3)",
    )
    parser.add_argument(
        "--fps", type=int, default=24,
        help="Frame rate for input loading and output encoding (default: 24)",
    )
    args = parser.parse_args()

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Load workflow
    with open(args.workflow) as f:
        workflow = json.load(f)

    print(f"Video: {args.video}")
    print(f"Workflow: {args.workflow}")
    print(f"Endpoint: {args.endpoint_id}")
    print(f"Duration: {args.duration}s ({int(args.duration * args.fps)} frames @ {args.fps}fps)")
    print(f"Naming: al7/al7_<name>-<NN>_<params>_<timestamp>.mp4")
    print(f"\nGenerating {len(VARIATIONS)} alt retake variations...\n")

    results = []
    for i, var in enumerate(VARIATIONS):
        prompt_num = i + 1
        params_token = encode_params(var["seed"], var["denoise"], var["lora_strength"])
        prefix_preview = build_filename_prefix(var, prompt_num)

        print(f"[{i+1}/{len(VARIATIONS)}] {var['name']}")
        print(f"  Params: {params_token} (seed={var['seed']}, denoise={var['denoise']}, lora={var['lora_strength']})")
        print(f"  Output: {prefix_preview}_00001.mp4")
        print(f"  Prompt: {var['prompt'][:100]}...")

        if args.dry_run:
            print("  (dry run — skipping generation)")
            results.append({"variation": var["name"], "status": "dry_run", "prefix": prefix_preview, "params": params_token})
            continue

        # Generate — direct path reference, no upload
        job, prefix = generate_variation(
            endpoint, workflow, args.video, var, prompt_num,
            duration=args.duration, fps=args.fps,
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
    print(f"\n{success_count}/{len(VARIATIONS)} variations generated successfully")
    print(f"\nDownload outputs:")
    print(f"  uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking")
    print(f"\nList outputs:")
    print(f"  uv run python scripts/list_s3.py --prefix output/al7/")


if __name__ == "__main__":
    main()
