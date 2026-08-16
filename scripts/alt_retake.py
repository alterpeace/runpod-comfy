#!/usr/bin/env python3
"""
Alt Retake — Generate 5 creative variations for music visuals.

Uses direct path references (no base64 upload) so it works with ANY file size.
Videos must already be on the RunPod volume at /runpod-volume/input/<path>.

Designed for VJing at festivals, gigs, and altered-states experiences.
Generates abstract, non-representational visuals with no people.

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

BASE_VISUALS = (
    "chromatic aberration, light leaks, prismatic refraction, "
    "liquid metal, iridescent, holographic, "
    "festival atmosphere, VJ loops, beat-synced motion, "
    "abstract, non-representational, motion blur, depth of field, 4k detail"
)

VARIATIONS = [
    {
        "name": "golden_cinematic",
        "seed": 42,
        "denoise": 0.3,
        "lora_strength": 1.0,
        "prompt": (
            f"cinematic, film noir, golden hour lighting, natural sunlight, "
            f"dramatic shadows, film grain, anamorphic lens flare, shallow depth of field, "
            f"smooth metal textures, vibrant color palette, expansive scale, "
            f"pushes in slowly, lingering shot, professional cinematography, {BASE_VISUALS}"
        ),
    },
    {
        "name": "neon_psychedelic",
        "seed": 1337,
        "denoise": 0.4,
        "lora_strength": 0.5,
        "prompt": (
            f"psychedelic, fractal patterns, morphing geometry, kaleidoscopic, "
            f"neon glow, dramatic shadows, high contrast, "
            f"rain, fog, smoke, particles, glossy surfaces, iridescent, "
            f"claustrophobic scale, handheld movement, circles around, "
            f"hypnotic, trance-inducing, flowing organic shapes, {BASE_VISUALS}"
        ),
    },
    {
        "name": "sacred_geometry",
        "seed": 8080,
        "denoise": 0.3,
        "lora_strength": 1.0,
        "prompt": (
            f"sacred geometry, mandala, infinite zoom, "
            f"experimental film, arthouse, volumetric fog, "
            f"dust, particles, natural sunlight, worn fabric textures, "
            f"muted color palette, epic scale, wide establishing shot, "
            f"tracks slowly, static frame, particle systems, {BASE_VISUALS}"
        ),
    },
    {
        "name": "festival_energy",
        "seed": 2718,
        "denoise": 0.4,
        "lora_strength": 1.0,
        "prompt": (
            f"stage lighting, laser beams, strobe effects, projection mapping, "
            f"LED wall content, high energy, dynamic, pulsing, rhythmic, "
            f"vibrant color palette, high contrast, neon glow, "
            f"smooth metal textures, glossy surfaces, expansive scale, "
            f"overhead view, tilts upward, pushes in, {BASE_VISUALS}"
        ),
    },
    {
        "name": "liquid_dreams",
        "seed": 31415,
        "denoise": 0.3,
        "lora_strength": 0.5,
        "prompt": (
            f"liquid metal, iridescent, holographic, prismatic refraction, "
            f"chromatic aberration, light leaks, "
            f"flowing organic shapes, morphing, hypnotic, "
            f"natural sunlight, dramatic shadows, worn fabric, "
            f"muted color palette, intimate scale, over-the-shoulder, "
            f"follows, handheld movement, film grain, {BASE_VISUALS}"
        ),
    },
]


def generate_variation(endpoint, workflow, video_path, variation):
    """Generate a single variation using direct path reference (no upload)."""
    wf = json.loads(json.dumps(workflow))

    # Patch workflow with variation parameters
    wf["7"]["inputs"]["video"] = video_path
    wf["5"]["inputs"]["text"] = variation["prompt"]
    wf["6"]["inputs"]["text"] = NEGATIVE_PROMPT
    wf["13"]["inputs"]["noise_seed"] = variation["seed"]
    wf["11"]["inputs"]["denoise"] = variation["denoise"]
    wf["3"]["inputs"]["strength_model"] = variation["lora_strength"]
    wf["3"]["inputs"]["strength_clip"] = variation["lora_strength"]

    # Set filename prefix with metadata
    prefix = f"altretake_{variation['name']}_seed{variation['seed']}_denoise{variation['denoise']}_lora{variation['lora_strength']}"
    wf["20"]["inputs"]["filename_prefix"] = prefix

    # Submit job — NO input_files, just the workflow with path reference
    job = endpoint.run({
        "input": {
            "workflow": wf,
            "timeout": 600,
        }
    })

    return job


def main():
    parser = argparse.ArgumentParser(description="Generate 5 alt retake variations for music visuals")
    parser.add_argument("--video", required=True, help="Video path on volume (e.g. rhizome.mp4 or sample/clip_001.mp4)")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Load workflow
    with open(args.workflow) as f:
        workflow = json.load(f)

    print(f"Video: {args.video}")
    print(f"Workflow: {args.workflow}")
    print(f"Endpoint: {args.endpoint_id}")
    print(f"\nGenerating {len(VARIATIONS)} alt retake variations...\n")

    results = []
    for i, var in enumerate(VARIATIONS):
        print(f"[{i+1}/{len(VARIATIONS)}] {var['name']}")
        print(f"  Seed: {var['seed']}, Denoise: {var['denoise']}, LoRA: {var['lora_strength']}")
        print(f"  Prompt: {var['prompt'][:100]}...")

        if args.dry_run:
            print("  (dry run — skipping generation)")
            results.append({"variation": var["name"], "status": "dry_run"})
            continue

        # Generate — direct path reference, no upload
        job = generate_variation(endpoint, workflow, args.video, var)
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
                "status": "failed",
                "error": error_msg,
                "elapsed": elapsed,
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
                "status": "success",
                "elapsed": elapsed,
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
                "status": "failed",
                "error": str(error_msg)[:500],
                "elapsed": elapsed,
            })

        print()

    # Summary
    print("=" * 60)
    print("ALT RETAKE SUMMARY")
    print("=" * 60)
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {status_icon} {r['variation']:25s} seed={r.get('seed', '?'):>5}  denoise={r.get('denoise', '?')}  lora={r.get('lora_strength', '?')}")

    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"\n{success_count}/{len(VARIATIONS)} variations generated successfully")
    print(f"\nDownload outputs:")
    print(f"  uv run python scripts/sync_outputs.py /media/chiral/data/comfy/output/sofaking")
    print(f"\nList outputs:")
    print(f"  uv run python scripts/list_s3.py --prefix output/")


if __name__ == "__main__":
    main()
