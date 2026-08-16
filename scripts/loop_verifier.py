#!/usr/bin/env python3
"""
Loop Verifier — Automated perfect loop verification for V2V retakes.

Compares original source videos against retake outputs to verify:
1. Frame count matches (output should have same frame count as source)
2. First/last frame similarity (perfect loop = first frame matches last frame)
3. Loop seam quality (how visible the loop point is)

Usage:
    # Verify all retakes against their source clips
    uv run python scripts/loop_verifier.py

    # Verify specific retake against specific source
    uv run python scripts/loop_verifier.py --retake <output_dir>/al7_velour-01_s42d03l10_20260816_220006_00001.mp4 --source <sample_dir>/clip_26-06-11_17-52-52_00007.mp4

    # Verify all retakes in a directory
    uv run python scripts/loop_verifier.py --retake-dir <output_dir> --source-dir <sample_dir>

Requirements:
    - ffmpeg (for frame extraction)
    - Python with PIL/Pillow (for image comparison)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("ERROR: PIL/Pillow and numpy required. Run: uv add pillow numpy")
    sys.exit(1)


def get_video_info(video_path: str) -> dict:
    """Get video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr}
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    fmt = data.get("format", {})
    return {
        "duration": float(fmt.get("duration", 0)),
        "frame_count": int(video_stream.get("nb_frames", 0)),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": eval(video_stream.get("r_frame_rate", "0/1")) if "/" in video_stream.get("r_frame_rate", "0") else 0,
        "codec": video_stream.get("codec_name", "unknown"),
    }


def extract_frame(video_path: str, timestamp: float, output_path: str) -> bool:
    """Extract a single frame from video at given timestamp."""
    cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-f", "image2",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def extract_last_frame(video_path: str, duration: float, output_path: str) -> bool:
    """Extract the last frame from video."""
    # Try multiple timestamps approaching the end
    for offset in [0.04, 0.1, 0.2, 0.5, 1.0]:
        timestamp = max(0, duration - offset)
        if extract_frame(video_path, timestamp, output_path):
            # Verify the file was actually created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
    # Last resort: use ffmpeg to extract the very last frame
    cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-i", video_path,
        "-vf", "select=eq(n\\,0)",
        "-frames:v", "1",
        "-f", "image2",
        output_path,
    ]
    # Actually, let's try reverse: seek from end
    cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-sseof", "-0.1",
        "-i", video_path,
        "-frames:v", "1",
        "-f", "image2",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def compare_images(img1_path: str, img2_path: str) -> dict:
    """Compare two images and return similarity metrics."""
    if not os.path.exists(img1_path) or not os.path.exists(img2_path):
        return {"mae": 1.0, "mse": 1.0, "diff_pct": 1.0, "correlation": 0.0, "match_quality": "error"}

    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    # Resize to match if needed
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.LANCZOS)

    arr1 = np.array(img1)
    arr2 = np.array(img2)

    # Mean Absolute Error
    mae = np.mean(np.abs(arr1.astype(float) - arr2.astype(float)))

    # Mean Squared Error
    mse = np.mean((arr1.astype(float) - arr2.astype(float)) ** 2)

    # Percentage of pixels that are "different" (avg channel diff > 30)
    diff = np.mean(np.abs(arr1.astype(float) - arr2.astype(float)), axis=2)
    diff_pixels = np.sum(diff > 30)
    total_pixels = diff.size
    diff_pct = diff_pixels / total_pixels

    # Structural similarity (simplified — just correlation)
    flat1 = arr1.flatten().astype(float)
    flat2 = arr2.flatten().astype(float)
    correlation = np.corrcoef(flat1, flat2)[0, 1] if np.std(flat1) > 0 and np.std(flat2) > 0 else 0

    return {
        "mae": float(mae),
        "mse": float(mse),
        "diff_pct": float(diff_pct),
        "correlation": float(correlation),
        "match_quality": "perfect" if diff_pct < 0.02 else "good" if diff_pct < 0.05 else "noticeable" if diff_pct < 0.15 else "poor",
    }


def verify_loop(video_path: str) -> dict:
    """Verify if a single video is a perfect loop."""
    info = get_video_info(video_path)
    if "error" in info:
        return {"video": video_path, "error": info["error"]}

    duration = info["duration"]
    if duration < 0.1:
        return {"video": video_path, "error": "Video too short", "info": info}

    with tempfile.TemporaryDirectory() as tmpdir:
        first_path = os.path.join(tmpdir, "first.png")
        last_path = os.path.join(tmpdir, "last.png")

        if not extract_frame(video_path, 0, first_path):
            return {"video": video_path, "error": "Failed to extract first frame", "info": info}
        if not extract_last_frame(video_path, duration, last_path):
            return {"video": video_path, "error": "Failed to extract last frame", "info": info}

        comparison = compare_images(first_path, last_path)

    # Check if duration is a clean multiple of common loop lengths
    loop_5s = duration / 5.0
    loop_4s = duration / 4.0
    is_5s_loop = abs(loop_5s - round(loop_5s)) < 0.1
    is_4s_loop = abs(loop_4s - round(loop_4s)) < 0.1

    return {
        "video": os.path.basename(video_path),
        "path": video_path,
        "duration": duration,
        "frame_count": info["frame_count"],
        "fps": info["fps"],
        "resolution": f"{info['width']}x{info['height']}",
        "loop_self_comparison": comparison,
        "is_5s_loop": is_5s_loop,
        "is_4s_loop": is_4s_loop,
        "loop_count_5s": round(loop_5s) if is_5s_loop else None,
        "loop_count_4s": round(loop_4s) if is_4s_loop else None,
        "is_perfect_loop": comparison["diff_pct"] < 0.02,
    }


def compare_videos(source_path: str, retake_path: str) -> dict:
    """Compare source and retake videos for loop compatibility."""
    source_info = get_video_info(source_path)
    retake_info = get_video_info(retake_path)

    if "error" in source_info or "error" in retake_info:
        return {
            "source": source_path,
            "retake": retake_path,
            "error": f"Failed to get video info",
            "source_info": source_info,
            "retake_info": retake_info,
        }

    # Frame count comparison
    source_frames = source_info["frame_count"]
    retake_frames = retake_info["frame_count"]
    frame_diff = retake_frames - source_frames
    frame_match = abs(frame_diff) <= 1  # Allow 1 frame tolerance

    # Duration comparison
    source_dur = source_info["duration"]
    retake_dur = retake_info["duration"]
    dur_diff = retake_dur - source_dur
    dur_match = abs(dur_diff) < 0.2  # Allow 200ms tolerance

    # Resolution comparison
    res_match = (source_info["width"] == retake_info["width"] and
                 source_info["height"] == retake_info["height"])

    # FPS comparison
    fps_match = abs(source_info["fps"] - retake_info["fps"]) < 1.0

    # Extract and compare first frames of both
    with tempfile.TemporaryDirectory() as tmpdir:
        s_first = os.path.join(tmpdir, "source_first.png")
        r_first = os.path.join(tmpdir, "retake_first.png")
        s_last = os.path.join(tmpdir, "source_last.png")
        r_last = os.path.join(tmpdir, "retake_last.png")

        extract_frame(source_path, 0, s_first)
        extract_frame(retake_path, 0, r_first)
        extract_last_frame(source_path, source_dur, s_last)
        extract_last_frame(retake_path, retake_dur, r_last)

        first_comparison = compare_images(s_first, r_first)
        last_comparison = compare_images(s_last, r_last)

    return {
        "source": os.path.basename(source_path),
        "retake": os.path.basename(retake_path),
        "source_path": source_path,
        "retake_path": retake_path,
        "source_duration": source_dur,
        "retake_duration": retake_dur,
        "duration_diff": dur_diff,
        "duration_match": dur_match,
        "source_frames": source_frames,
        "retake_frames": retake_frames,
        "frame_diff": frame_diff,
        "frame_match": frame_match,
        "resolution_match": res_match,
        "fps_match": fps_match,
        "source_fps": source_info["fps"],
        "retake_fps": retake_info["fps"],
        "first_frame_comparison": first_comparison,
        "last_frame_comparison": last_comparison,
        "overall_verdict": "PASS" if (frame_match and dur_match) else "FAIL",
    }


def find_matching_source(retake_name: str, source_dir: str) -> str | None:
    """Try to find the source video that matches a retake.

    Retake filenames contain the variation name and params but not the source name.
    We match by comparing frame counts or duration.
    """
    # This is a heuristic — in practice, the user should specify the source
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Automated perfect loop verification for V2V retakes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a single retake's self-loop quality
  uv run python scripts/loop_verifier.py --retake output/al7_velour-01_s42d03l10_20260816_220006_00001.mp4

  # Compare retake against original source
  uv run python scripts/loop_verifier.py --retake output/al7_velour-01_s42d03l10_20260816_220006_00001.mp4 --source <sample_dir>/clip_26-06-11_17-52-52_00007.mp4

  # Verify all retakes in a directory (self-loop check)
  uv run python scripts/loop_verifier.py --retake-dir <output_dir>

  # Compare all retakes against all sources
  uv run python scripts/loop_verifier.py --retake-dir <output_dir> --source-dir <sample_dir>
        """,
    )
    parser.add_argument("--retake", help="Path to retake video to verify")
    parser.add_argument("--source", help="Path to original source video to compare against")
    parser.add_argument("--retake-dir", help="Directory of retake videos to verify")
    parser.add_argument("--source-dir", help="Directory of source videos to compare against")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    results = []

    # Single retake self-loop check
    if args.retake and not args.source:
        print(f"Verifying self-loop: {args.retake}")
        result = verify_loop(args.retake)
        results.append(result)
        if not args.json:
            print_result(result)

    # Single retake vs source comparison
    elif args.retake and args.source:
        print(f"Comparing: {args.source} → {args.retake}")
        result = compare_videos(args.source, args.retake)
        results.append(result)
        if not args.json:
            print_comparison(result)

    # Directory of retakes (self-loop check)
    elif args.retake_dir and not args.source_dir:
        retake_dir = Path(args.retake_dir)
        if not retake_dir.exists():
            print(f"ERROR: Directory not found: {retake_dir}")
            sys.exit(1)

        videos = sorted(list(retake_dir.glob("*.mp4")) + list(retake_dir.glob("*.webm")) + list(retake_dir.glob("*.mov")))
        # Also check subdirectories (al7/ etc.)
        for subdir in retake_dir.iterdir():
            if subdir.is_dir():
                videos.extend(sorted(subdir.glob("*.mp4")))

        print(f"Found {len(videos)} videos in {retake_dir}")
        for v in videos:
            print(f"\nVerifying: {v.name}")
            result = verify_loop(str(v))
            results.append(result)
            if not args.json:
                print_result(result)

    # Directory of retakes vs directory of sources
    elif args.retake_dir and args.source_dir:
        retake_dir = Path(args.retake_dir)
        source_dir = Path(args.source_dir)

        if not retake_dir.exists():
            print(f"ERROR: Retake directory not found: {retake_dir}")
            sys.exit(1)
        if not source_dir.exists():
            print(f"ERROR: Source directory not found: {source_dir}")
            sys.exit(1)

        # Find all retake videos (including subdirs)
        retake_videos = sorted(list(retake_dir.glob("*.mp4")) + list(retake_dir.glob("*.webm")))
        for subdir in retake_dir.iterdir():
            if subdir.is_dir():
                retake_videos.extend(sorted(subdir.glob("*.mp4")))

        source_videos = sorted(list(source_dir.glob("*.mp4")) + list(source_dir.glob("*.webm")) + list(source_dir.glob("*.mov")))

        print(f"Found {len(retake_videos)} retakes and {len(source_videos)} sources")

        # For each retake, compare against all sources to find best match
        for retake in retake_videos:
            retake_info = get_video_info(str(retake))
            if "error" in retake_info:
                continue

            best_match = None
            best_score = float("inf")

            for source in source_videos:
                source_info = get_video_info(str(source))
                if "error" in source_info:
                    continue

                # Score by frame count difference
                frame_diff = abs(retake_info.get("frame_count", 0) - source_info.get("frame_count", 0))
                dur_diff = abs(retake_info.get("duration", 0) - source_info.get("duration", 0))
                score = frame_diff + dur_diff * 10

                if score < best_score:
                    best_score = score
                    best_match = source

            if best_match:
                print(f"\nComparing: {best_match.name} → {retake.name}")
                result = compare_videos(str(best_match), str(retake))
                results.append(result)
                if not args.json:
                    print_comparison(result)

    else:
        parser.print_help()
        sys.exit(1)

    # Summary
    if not args.json:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

    if results and "overall_verdict" in results[0]:
        # Comparison results
        passed = sum(1 for r in results if r.get("overall_verdict") == "PASS")
        failed = sum(1 for r in results if r.get("overall_verdict") == "FAIL")
        if not args.json:
            print(f"  {passed} passed, {failed} failed out of {len(results)} comparisons")
            for r in results:
                verdict = r.get("overall_verdict", "?")
                icon = "✅" if verdict == "PASS" else "❌"
                frame_info = f"frames: {r.get('source_frames', '?')}→{r.get('retake_frames', '?')} (diff={r.get('frame_diff', '?')})"
                dur_info = f"duration: {r.get('source_duration', 0):.1f}s→{r.get('retake_duration', 0):.1f}s"
                print(f"  {icon} {r.get('retake', '?'):50s} {frame_info}  {dur_info}")
    elif results:
        # Self-loop results
        perfect = sum(1 for r in results if r.get("is_perfect_loop"))
        if not args.json:
            print(f"  {perfect}/{len(results)} videos are perfect loops")
            for r in results:
                loop = "✅" if r.get("is_perfect_loop") else "❌"
                diff = r.get("loop_self_comparison", {}).get("diff_pct", 0)
                quality = r.get("loop_self_comparison", {}).get("match_quality", "?")
                dur = r.get("duration", 0)
                print(f"  {loop} {r.get('video', '?'):50s} diff={diff:.1%} ({quality}) {dur:.1f}s")

    if args.json:
        print(json.dumps(results, indent=2))


def print_result(r: dict):
    """Print a single self-loop verification result."""
    if "error" in r:
        print(f"  ❌ Error: {r['error']}")
        return

    loop = "✅" if r.get("is_perfect_loop") else "❌"
    comp = r.get("loop_self_comparison", {})
    print(f"  {loop} Duration: {r.get('duration', 0):.3f}s ({r.get('frame_count', '?')} frames @ {r.get('fps', 0):.1f}fps)")
    print(f"     First/last frame diff: {comp.get('diff_pct', 0):.1%} ({comp.get('match_quality', '?')})")
    print(f"     Correlation: {comp.get('correlation', 0):.4f}")
    if r.get("is_5s_loop"):
        print(f"     ✓ {r.get('loop_count_5s')}x 5s loop")
    elif r.get("is_4s_loop"):
        print(f"     ✓ {r.get('loop_count_4s')}x 4s loop")


def print_comparison(r: dict):
    """Print a comparison result."""
    if "error" in r:
        print(f"  ❌ Error: {r['error']}")
        return

    verdict = r.get("overall_verdict", "?")
    icon = "✅" if verdict == "PASS" else "❌"
    print(f"  {icon} Verdict: {verdict}")
    print(f"     Source: {r.get('source', '?')} ({r.get('source_duration', 0):.3f}s, {r.get('source_frames', '?')} frames)")
    print(f"     Retake: {r.get('retake', '?')} ({r.get('retake_duration', 0):.3f}s, {r.get('retake_frames', '?')} frames)")
    print(f"     Frame diff: {r.get('frame_diff', 0)} ({'match' if r.get('frame_match') else 'MISMATCH'})")
    print(f"     Duration diff: {r.get('duration_diff', 0):.3f}s ({'match' if r.get('duration_match') else 'MISMATCH'})")
    print(f"     Resolution: {'match' if r.get('resolution_match') else 'MISMATCH'}")
    print(f"     FPS: {'match' if r.get('fps_match') else 'MISMATCH'} ({r.get('source_fps', 0):.1f} → {r.get('retake_fps', 0):.1f})")

    fc = r.get("first_frame_comparison", {})
    lc = r.get("last_frame_comparison", {})
    print(f"     First frame comparison: {fc.get('diff_pct', 0):.1%} diff ({fc.get('match_quality', '?')})")
    print(f"     Last frame comparison: {lc.get('diff_pct', 0):.1%} diff ({lc.get('match_quality', '?')})")


if __name__ == "__main__":
    main()
