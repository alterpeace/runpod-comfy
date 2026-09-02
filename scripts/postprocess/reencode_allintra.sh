#!/bin/bash
# =============================================================================
# Re-encode MP4(s) to all-intra h264 CRF 18 — offline, no GPU needed.
#
# Matches config/video_formats/h264-allintra.json exactly (the format the
# LTX-2.5 workflows now output): keyframe every frame (-g 1), no B-frames
# (-bf 0), CRF 18, preset fast, yuv420p. Audio is stream-copied untouched.
#
# WHY: the old workflows output long-GOP h264 (CRF 19, keyint 250, B-frames)
# which produces pulsing/blocking artifacts during motion. Re-encoding to
# all-intra CRF 18 gives an archival master that won't degrade further.
#
# CAVEAT: re-encoding preserves whatever is already baked into the pixels —
# it removes FUTURE compression damage, not existing generation artifacts.
# For clips with generation-level artifacts, regenerate with
# examples/ltx25_v2v_redetail_seedvr2_runpod.json (SeedVR2 restoration)
# instead of re-encoding.
#
# Usage:
#   ./scripts/postprocess/reencode_allintra.sh video.mp4                # single file -> video_allintra.mp4
#   ./scripts/postprocess/reencode_allintra.sh clips/                   # whole directory
#   ./scripts/postprocess/reencode_allintra.sh clips/ -o out/           # custom output dir
#   ./scripts/postprocess/reencode_allintra.sh video.mp4 --force        # overwrite existing output
#   ./scripts/postprocess/reencode_allintra.sh video.mp4 --crf 16       # custom CRF
# =============================================================================

set -euo pipefail

CRF=18
OUTDIR=""
FORCE=0
TARGETS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --crf)   CRF="$2"; shift 2 ;;
        -o)      OUTDIR="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) head -25 "$0" | tail -12; exit 0 ;;
        *)       TARGETS+=("$1"); shift ;;
    esac
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "Usage: $0 <video.mp4 | directory> [-o outdir] [--crf N] [--force]"
    exit 1
fi

command -v ffmpeg >/dev/null || { echo "[ERROR] ffmpeg not installed"; exit 1; }

# Collect mp4 files (single file or a directory of mp4s)
FILES=()
for t in "${TARGETS[@]}"; do
    if [[ -d "$t" ]]; then
        while IFS= read -r f; do FILES+=("$f"); done < <(find "$t" -maxdepth 1 -name '*.mp4' | sort)
    elif [[ -f "$t" ]]; then
        FILES+=("$t")
    else
        echo "[WARN] skipping missing: $t"
    fi
done

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "[ERROR] no .mp4 files found in: ${TARGETS[*]}"
    exit 1
fi

for f in "${FILES[@]}"; do
    base="$(basename "$f" .mp4)"
    dir="$(dirname "$f")"
    out="${OUTDIR:-$dir}/${base}_allintra.mp4"
    [[ -n "$OUTDIR" ]] && mkdir -p "$OUTDIR"

    if [[ -f "$out" && "$FORCE" != "1" ]]; then
        echo "[SKIP] $out exists (use --force to overwrite)"
        continue
    fi

    before=$(stat -c%s "$f")
    echo "=== $f -> $out (CRF $CRF, all-intra) ==="
    ffmpeg -hide_banner -loglevel error -y -i "$f" \
        -c:v libx264 -crf "$CRF" -preset fast \
        -g 1 -bf 0 -pix_fmt yuv420p \
        -c:a copy \
        -movflags +faststart \
        "$out"
    after=$(stat -c%s "$out")
    echo "  $(numfmt --to=iec "$before") -> $(numfmt --to=iec "$after")"
done

echo "Done."
