#!/usr/bin/env python3
"""Beat/onset detection for music-video work: exports NLE timeline markers
(Premiere/Resolve-compatible CSV) and a JSON file mapping beats to frame
indices at a target fps, for driving LTX-2.3 generation parameters
(guide-image placement, IC-LoRA strength keyframing, effect timing, etc.)
instead of just even/uniform spacing.

Usage:
    python scripts/analyze_beats.py song.wav --fps 24 --output-dir ./beats

Outputs (in --output-dir):
    <name>_markers.csv   - "Timecode In","Name","Comment" columns.
                            Import via https://editingtools.io/marker
                            (CSV -> DaVinci Resolve EDL, or CSV -> Premiere XML)
    <name>_beats.json     - full beat/downbeat/onset data with both seconds
                            and frame-index (at --fps), for scripting.

Notes:
    - "Downbeats" here are approximated as every Nth beat (--beats-per-bar,
      default 4) starting from the first detected beat, NOT true bar-line
      detection. Verify against the track manually if bar alignment matters -
      librosa's beat tracker has no concept of meter, this is a heuristic.
    - Onset detection (finer-grained than beats - hi-hats, transients) is
      included separately and is much noisier; use for effect timing, not
      as a marker substitute for beats.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def seconds_to_timecode(seconds: float, fps: float) -> str:
    """HH:MM:SS:FF timecode, the format editingtools.io's CSV->marker
    converter (and most NLE marker importers) expect for 'Timecode In'."""
    total_frames = round(seconds * fps)
    frames = int(total_frames % round(fps))
    total_seconds = int(total_frames // round(fps))
    secs = total_seconds % 60
    mins = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"


def analyze(audio_path: Path, fps: float, beats_per_bar: int, detect_onsets: bool) -> dict:
    import librosa

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # librosa >=0.10 returns tempo as a 0-d numpy array in some versions.
    try:
        bpm = float(tempo)
    except TypeError:
        bpm = float(tempo[0])

    beats = []
    for i, t in enumerate(beat_times):
        beats.append({
            "index": i,
            "time_sec": round(float(t), 4),
            "frame_index": round(float(t) * fps),
            "is_downbeat": (i % beats_per_bar == 0),
        })

    result = {
        "audio_file": str(audio_path),
        "sample_rate": sr,
        "fps": fps,
        "estimated_bpm": round(bpm, 2),
        "beats_per_bar_assumed": beats_per_bar,
        "beat_count": len(beats),
        "beats": beats,
    }

    if detect_onsets:
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        result["onsets"] = [
            {"time_sec": round(float(t), 4), "frame_index": round(float(t) * fps)}
            for t in onset_times
        ]
        result["onset_count"] = len(result["onsets"])

    return result


def write_csv(result: dict, csv_path: Path, fps: float, downbeats_only: bool) -> None:
    import csv

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timecode In", "Name", "Comment"])
        for b in result["beats"]:
            if downbeats_only and not b["is_downbeat"]:
                continue
            tc = seconds_to_timecode(b["time_sec"], fps)
            label = "Downbeat" if b["is_downbeat"] else "Beat"
            writer.writerow([
                tc,
                f"{label} {b['index']}",
                f"frame {b['frame_index']} | ~{result['estimated_bpm']} BPM",
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path, help="Path to the audio file (wav/mp3/flac/etc.)")
    parser.add_argument("--fps", type=float, default=24.0, help="Project/generation fps for frame-index mapping (default: 24)")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Where to write outputs")
    parser.add_argument("--beats-per-bar", type=int, default=4, help="Assumed beats per bar for downbeat heuristic (default: 4)")
    parser.add_argument("--onsets", action="store_true", help="Also detect finer-grained onsets (noisier, for effect timing)")
    parser.add_argument("--downbeats-only-csv", action="store_true", help="Only write downbeats to the marker CSV (less clutter in NLE)")
    args = parser.parse_args()

    if not args.audio.exists():
        print(f"Audio file not found: {args.audio}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.audio.stem

    print(f"Analyzing {args.audio} ...")
    result = analyze(args.audio, args.fps, args.beats_per_bar, args.onsets)
    print(f"  Estimated BPM: {result['estimated_bpm']}")
    print(f"  Beats detected: {result['beat_count']}")
    if args.onsets:
        print(f"  Onsets detected: {result['onset_count']}")

    json_path = args.output_dir / f"{stem}_beats.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"  Wrote {json_path}")

    csv_path = args.output_dir / f"{stem}_markers.csv"
    write_csv(result, csv_path, args.fps, args.downbeats_only_csv)
    print(f"  Wrote {csv_path}")
    print(
        "\nImport the CSV as NLE markers via https://editingtools.io/marker "
        "(CSV -> DaVinci Resolve EDL, or CSV -> Adobe Premiere Pro XML)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
