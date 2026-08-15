#!/usr/bin/env python3
"""
Alt Retake — Generate 5 creative variations for music visuals.

Designed for VJing at festivals, gigs, and altered-states experiences.
Generates abstract, non-representational visuals with no people.

Each variation uses different seeds, denoise levels (0.3-0.4 range),
LoRA strengths, and style directions from the prompt engineering reference.

Output files include metadata in the filename: _seed123_denoise0.3_lora1.0_
and ffmpeg metadata tags embedded in the video file.

Post-processing mastering chain applied after generation:
- Color grading (contrast +10%, saturation +15%)
- Sharpening (unsharp mask)
- h264 all-intra output (keyframe every frame)

Usage:
    set -a && source .env && set +a
    uv run python scripts/alt_retake.py --video rhizome.mp4
    uv run python scripts/alt_retake.py --video rhizome.mp4 --dry-run
    uv run python scripts/alt_retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4
"""
import argparse
import base64
import json
import os
import subprocess
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

# Negative prompt — no people, no CGI, no cartoon
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

# Common visual elements for all variations
BASE_VISUALS = (
    "chromatic aberration, light leaks, prismatic refraction, "
    "liquid metal, iridescent, holographic, "
    "festival atmosphere, VJ loops, beat-synced motion, "
    "abstract, non-representational, motion blur, depth of field, 4k detail"
)

# 5 creative variations for music visuals
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


def download_from_s3(key: str) -> bytes:
    """Download a file from the RunPod S3 volume."""
    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
        region_name=os.environ["RUNPOD_S3_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["RUNPOD_S3_BUCKET"]
    s3_key = f"input/{key}" if not key.startswith("input/") else key
    resp = s3.get_object(Bucket=bucket, Key=s3_key)
    return resp["Body"].read()


def generate_variation(endpoint, workflow, video_name, video_b64, variation):
    """Generate a single variation."""
    wf = json.loads(json.dumps(workflow))

    # Patch workflow with variation parameters
    wf["7"]["inputs"]["video"] = video_name
    wf["5"]["inputs"]["text"] = variation["prompt"]
    wf["6"]["inputs"]["text"] = NEGATIVE_PROMPT
    wf["13"]["inputs"]["noise_seed"] = variation["seed"]
    wf["11"]["inputs"]["denoise"] = variation["denoise"]
    wf["3"]["inputs"]["strength_model"] = variation["lora_strength"]
    wf["3"]["inputs"]["strength_clip"] = variation["lora_strength"]

    # Set filename prefix with metadata
    prefix = f"altretake_{variation['name']}_seed{variation['seed']}_denoise{variation['denoise']}_lora{variation['lora_strength']}"
    wf["20"]["inputs"]["filename_prefix"] = prefix

    # Submit job
    job = endpoint.run({
        "input": {
            "workflow": wf,
            "input_files": {video_name: video_b64},
            "timeout": 600,
        }
    })

    return job


def apply_mastering_chain(input_path, output_path, variation):
    """Apply post-processing mastering chain with ffmpeg."""
    cmd = [
        "ffmpeg", "-i", str(input_path), "-y",
        # Color grading: contrast +10%, brightness +2%, saturation +15%
        "-vf", "eq=contrast=1.1:brightness=0.02:saturation=1.15,"
               "unsharp=5:5:0.8:3:3:0.4",
        # h264 all-intra (keyframe every frame)
        "-c:v", "libx264",
        "-crf", "16",
        "-preset", "slow",
        "-g", "1",
        "-bf", "0",
        "-pix_fmt", "yuv420p",
        # Metadata
        "-metadata", f"title=Alt Retake - {variation['name']}",
        "-metadata", f"seed={variation['seed']}",
        "-metadata", f"denoise={variation['denoise']}",
        "-metadata", f"lora_strength={variation['lora_strength']}",
        "-metadata", f"style={variation['name']}",
        "-metadata", f"prompt={variation['prompt'][:200]}",
        "-metadata", "mastering=color_grade+sharpen+h264_allintra",
        # No audio
        "-an",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(f"  ✅ Mastered: {output_path}")
            return True
        else:
            print(f"  ⚠️  Mastering failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ⚠️  Mastering error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate 5 alt retake variations for music visuals")
    parser.add_argument("--video", required=True, help="Video filename (e.g. rhizome.mp4)")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", "taea2mhlwbdkuq"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--master", action="store_true", help="Apply mastering chain after generation")
    args = parser.parse_args()

    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    endpoint = runpod.Endpoint(args.endpoint_id)

    # Load workflow
    with open(args.workflow) as f:
        workflow = json.load(f)

    # Download video from S3
    print(f"Downloading {args.video} from S3...")
    video_data = download_from_s3(args.video)
    video_b64 = base64.b64encode(video_data).decode("utf-8")
    print(f"  {len(video_data):,} bytes")

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

        # Generate
        job = generate_variation(endpoint, workflow, args.video, video_b64, var)
        print(f"  Job: {job.job_id}")

        start = time.time()
        while job.status() in ["IN_QUEUE", "IN_PROGRESS"]:
            time.sleep(10)
            elapsed = int(time.time() - start)
            print(f"    [{elapsed}s] {job.status()}...", end="\r")

        status = job.status()
        elapsed = int(time.time() - start)
        print(f"  {status} ({elapsed}s)")

        if status == "COMPLETED" and job.output().get("status") == "success":
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
            meta = job.output().get("metadata", {})
            print(f"  ❌ Error: {meta.get('error_message', 'unknown')[:200]}")
            results.append({
                "variation": var["name"],
                "status": "failed",
                "error": meta.get("error_message", "unknown")[:200],
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

    if args.master and success_count > 0:
        print(f"\nTo apply mastering chain, download outputs first then run:")
        print(f"  ffmpeg -i input.mp4 -vf 'eq=contrast=1.1:brightness=0.02:saturation=1.15,unsharp=5:5:0.8:3:3:0.4' -c:v libx264 -crf 16 -preset slow -g 1 -bf 0 -an output_mastered.mp4")


if __name__ == "__main__":
    main()
