#!/bin/bash
# =============================================================================
# denoise_sweep.sh — denoise ladder test, server-side (runs ON THE POD).
#
# 3 clips x 4 denoise values (0.50/0.55/0.60/0.65), NAG workflow.
# Each render -> out/denoise_test/d_<value>/<clip>.mp4 (folder-per-value).
# Resumable: skips renders whose output file already exists.
# =============================================================================
set -u
cd /workspace/run_variants

CLIPS="clip_26-09-18_19-36-48_00001.mp4 clip_26-09-18_19-37-30_00001.mp4"

for d in 0.5 0.55 0.60 0.65; do
  python3 - <<PY
import json
w = json.load(open("examples/ltx25_v2v_retake48_loop_nag.json"))
w["11"]["inputs"]["denoise"] = $d
json.dump(w, open("/tmp/nag_d$d.json", "w"), indent=2)
PY
  for clip in $CLIPS; do
    out="out/denoise_test/d_$d"
    mkdir -p "$out"
    if [ -f "$out/$clip" ]; then echo "skip (done): d=$d $clip"; continue; fi
    echo "=== denoise $d / $clip ==="
    /opt/venv/bin/python scripts/invoke/invoke_skypilot_batch.py \
      --dir sample \
      --workflow "/tmp/nag_d$d.json" \
      --url http://localhost:8188 \
      --out "$out" \
      --timeout 3600 \
      --no-random-seed "$clip" \
      || echo "FAILED: d=$d $clip"
  done
done
echo "SWEEP_DONE"
