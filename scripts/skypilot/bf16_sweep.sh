#!/bin/bash
# =============================================================================
# bf16_sweep.sh — denoise sweep on the NEW bf16-distilled model (resident).
# 2 clips x 0.55/0.60/0.65 = 6 renders, bulk-submitted into ComfyUI's queue.
# Clears pending queue first (running render is left to finish).
# =============================================================================
set -u
cd /workspace/run_variants
LOG=bf16_sweep.log

pkill -f "bulk_[s]weep.sh" 2>/dev/null || true
pkill -f "invoke_[s]kypilot" 2>/dev/null || true
curl -s -X POST http://localhost:8188/queue -H "Content-Type: application/json" -d '{"clear": true}' > /dev/null
echo "queue cleared; submitting bf16 sweep" >> $LOG

CLIPS="clip_26-04-26_12-54-18_00003.mp4 clip_26-09-11_20-02-36_00002.mp4"
for d in 0.55 0.60 0.65; do
  python3 - <<PY
import json
w = json.load(open("examples/nag_bf16test.json"))
w["11"]["inputs"]["denoise"] = $d
json.dump(w, open("/tmp/bf16_d$d.json", "w"), indent=2)
PY
  for clip in $CLIPS; do
    out="out/bf16_sweep/d_$d"
    mkdir -p "$out"
    if [ -f "$out/$clip" ]; then echo "skip (done): d=$d $clip" >> $LOG; continue; fi
    echo "=== bulk submit: bf16 d=$d $clip ===" >> $LOG
    nohup /opt/venv/bin/python scripts/invoke/invoke_skypilot_batch.py \
      --dir sample \
      --workflow "/tmp/bf16_d$d.json" \
      --url http://localhost:8188 \
      --out "$out" \
      --timeout 7200 \
      --no-random-seed "$clip" \
      >> $LOG 2>&1 < /dev/null &
    sleep 2
  done
done
echo "BF16_SWEEP_SUBMITTED" >> $LOG
wait
echo "BF16_SWEEP_DONE" >> $LOG