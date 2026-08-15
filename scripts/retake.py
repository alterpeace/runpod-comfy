#!/usr/bin/env python3
"""
Retake Workflow — Generate 5 creative variations of an input video.

Each variation uses different seeds, denoise levels, LoRA strengths, and
style directions assembled from the prompt engineering reference categories.

Output files include metadata in the filename: _seed123_denoise0.5_lora1.0_
and ffmpeg metadata tags embedded in the video file.

Usage:
    set -a && source .env && set +a
    uv run python scripts/retake.py --video rhizome.mp4
    uv run python scripts/retake.py --video sample/clip_26-06-11_17-52-54_00002.mp4
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

NEGATIVE_PROMPT = (
    "(dots, speckles, halftone, stippling:1.5), (grain, noise, static:1.4), "
    "(glossy skin, plastic skin:1.3), (worst quality, low quality:1.4), "
    "(deformed, distorted:1.3), blurry, jpeg artifacts, ugly, duplicate, "
    "mutated hands, poorly drawn hands, poorly drawn face, bad anatomy, "
    "extra limbs, extra fingers, fused fingers, missing limbs, long neck, "
    "(text, watermark, signature), low resolution, (cgi, 3d, render, cartoon, anime), "
    "cropped, (shaking, jittery:1.2), (oversharpened:1.3), (banding, scan lines:1.4)"
)

# 5 creative variations using categories from PROMPT_ENGINEERING_REFERENCE.md
VARIATIONS = [
    {
        "name": "cinematic_golden",
        "seed": 42,
        "denoise": 0.2,
        "lora_strength": 1.0,
        "prompt": (
            "cinematic, film noir, golden hour lighting, natural sunlight, "
            "dramatic shadows, film grain, anamorphic lens flare, shallow depth of field, "
            "smooth metal textures, vibrant color palette, expansive scale, "
            "pushes in slowly, lingering shot, professional cinematography, 4k detail"
        ),
    },
    {
        "name": "neon_noir",
        "seed": 1337,
        "denoise": 0.5,
        "lora_strength": 0.5,
        "prompt": (
            "cinematic, film noir, neon glow, dramatic shadows, high contrast, "
            "rain, fog, smoke, particles, glossy surfaces, rough stone textures, "
            "claustrophobic scale, handheld movement, circles around, "
            "motion blur, depth of field, blade runner aesthetic, 4k detail"
        ),
    },
    {
        "name": "fantasy_atmospheric",
        "seed": 8080,
        "denoise": 0.3,
        "lora_strength": 1.0,
        "prompt": (
            "cinematic, fantasy, experimental film, arthouse, volumetric fog, "
            "dust, particles, natural sunlight, worn fabric textures, "
            "muted color palette, epic scale, wide establishing shot, "
            "tracks slowly, static frame, particle systems, motion blur, 4k detail"
        ),
    },
    {
        "name": "stylized_vibrant",
        "seed": 2718,
        "denoise": 0.5,
        "lora_strength": 1.0,
        "prompt": (
            "stylized, comic book, vibrant color palette, high contrast, "
            "neon glow, dramatic shadows, smooth metal textures, glossy surfaces, "
            "expansive scale, overhead view, tilts upward, pushes in, "
            "particle systems, depth of field, 4k detail"
        ),
    },
    {
        "name": "intimate_documentary",
        "seed": 31415,
        "denoise": 0.2,
        "lora_strength": 0.5,
        "prompt": (
            "cinematic, documentary, arthouse, natural sunlight, "
            "dramatic shadows, worn fabric textures, rough stone, "
            "muted color palette, intimate scale, over-the-shoulder, "
            "follows, handheld movement, film grain, motion blur, 4k detail"
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
    prefix = f"retake_{variation['name']}_seed{variation['seed']}_denoise{variation['denoise']}_lora{variation['lora_strength']}"
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


def add_ffmpeg_metadata(video_path, variation):
    """Add metadata tags to the video file using ffmpeg."""
    metadata = {
        "title": f"Retake - {variation['name']}",
        "seed": str(variation["seed"]),
        "denoise": str(variation["denoise"]),
        "lora_strength": str(variation["lora_strength"]),
        "prompt": variation["prompt"][:200],
        "negative_prompt": "standard_negative",
        "style": variation["name"],
    }

    cmd = ["ffmpeg", "-i", str(video_path), "-y"]
    for k, v in metadata.items():
        cmd.extend(["-metadata", f"{k}={v}"])
    cmd.extend(["-c", "copy", str(video_path) + ".tmp"])

    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        os.replace(str(video_path) + ".tmp", str(video_path))
        print(f"  ✅ Metadata embedded")
    except Exception as e:
        print(f"  ⚠️  Metadata embedding failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate 5 creative retake variations")
    parser.add_argument("--video", required=True, help="Video filename (e.g. rhizome.mp4)")
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

    # Download video from S3
    print(f"Downloading {args.video} from S3...")
    video_data = download_from_s3(args.video)
    video_b64 = base64.b64encode(video_data).decode("utf-8")
    print(f"  {len(video_data):,} bytes")

    print(f"\nGenerating {len(VARIATIONS)} creative variations...\n")

    results = []
    for i, var in enumerate(VARIATIONS):
        print(f"[{i+1}/{len(VARIATIONS)}] {var['name']}")
        print(f"  Seed: {var['seed']}, Denoise: {var['denoise']}, LoRA: {var['lora_strength']}")
        print(f"  Prompt: {var['prompt'][:80]}...")

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
    print("RETAKE SUMMARY")
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
