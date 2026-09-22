#!/bin/bash
# =============================================================================
# bulk_sweep.sh — submit ALL remaining (denoise, clip) renders into ComfyUI's
# queue at once (depth-N queue instead of one-at-a-time). Resumes per output
# file, so it is safe to run repeatedly; pairs with an already-running render.
# =============================================================================
set -u
cd /workspace/run_variants

CLIPS="clip_26-09-18_19-36-48_00001.mp4 clip_26-09-18_19-37-30_00001.mp4"
VALS="0.5 0.55 0.60 0.65"

for d in $VALS; do
  python3 - <<PY
import json
w = json.load(open("examples/ltx25_v2v_retake48_loop_nag.json"))
w["11"]["inputs"]["denoise"] = $d
json.dump(w, open("/tmp/nag_d$d.json", "w"), indent=2)
PY
  for clip in $CLIPS; do
    out="out/denoise_test/d_$d"
    mkdir -p "$out"
    if [ -f "$out/$clip" ]; then echo "skip (done): d=$d $clip" >> bulk_sweep.log; continue; fi
    echo "=== bulk submit: d=$d $clip ===" >> bulk_sweep.log
    nohup /opt/venv/bin/python scripts/invoke/invoke_skypilot_batch.py \
      --dir sample \
      --workflow "/tmp/nag_d$d.json" \
      --url http://localhost:8188 \
      --out "$out" \
      --timeout 7200 \
      --no-random-seed "$clip" \
      >> bulk_sweep.log 2>&1 < /dev/null &
    sleep 2   # stagger so queue order matches the ladder
  done
done
echo "BULK_SUBMITTED" >> bulk_sweep.log
wait
echo "BULK_SWEEP_DONE" >> bulk_sweep.log