#!/bin/bash
# =============================================================================
# more_ai_test.sh — "add more AI" ladder: progressively weaken the fidelity
# forces on clip_13-01-26_00034_prob4 (bf16-distilled model, 8 steps).
#
#   R1: no NAG, guiding_strength 0.5   (moderate freedom)
#   R2: no NAG, guiding_strength 0.3, guidance ends step 4  (heavy freedom)
#   R3: no NAG, guiding_strength 0.05, guidance ends step 4  (near-pure AI,
#       anchors kept only via the tiny residual pull)
#
# Resumable per output file. Run from repo root.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "=== staging plain bf16 template to pod ==="
rsync -a --no-owner --no-group /tmp/retake48_nag_bf16test.json \
  ltx25:/workspace/run_variants/examples/nag_bf16test.json

echo "=== building no-NAG variants + submitting renders (server-side) ==="
ssh -o BatchMode=yes ltx25 'bash -s' <<'REMOTE'
set -euo pipefail
cd /workspace/run_variants
mkdir -p out/more_ai

python3 - <<'PY'
import json
base = json.load(open("examples/nag_bf16test.json"))

# R1: no NAG, gs 0.5, full window
w = json.loads(json.dumps(base))
w["14a"]["inputs"]["model"] = ["3", 0]
del w["14b"]
w["15"]["inputs"]["guiding_strength"] = 0.5
w["15"]["inputs"]["guiding_end_step"] = 1000
w["_metadata"]["variant"] = "more-AI R1: no NAG, gs 0.5, full window"
json.dump(w, open("/tmp/moreai_r1.json", "w"), indent=2)

# R2: no NAG, gs 0.3, guidance ends step 4
w = json.loads(json.dumps(base))
w["14a"]["inputs"]["model"] = ["3", 0]
del w["14b"]
w["15"]["inputs"]["guiding_strength"] = 0.3
w["15"]["inputs"]["guiding_end_step"] = 4
w["_metadata"]["variant"] = "more-AI R2: no NAG, gs 0.3, end step 4"
json.dump(w, open("/tmp/moreai_r2.json", "w"), indent=2)

# R3: no NAG, gs 0.05, guidance ends step 4 (anchors only)
w = json.loads(json.dumps(base))
w["14a"]["inputs"]["model"] = ["3", 0]
del w["14b"]
w["15"]["inputs"]["guiding_strength"] = 0.05
w["15"]["inputs"]["guiding_end_step"] = 4
w["_metadata"]["variant"] = "more-AI R3: no NAG, gs 0.05, end step 4"
json.dump(w, open("/tmp/moreai_r3.json", "w"), indent=2)
print("variants built")
PY

for r in r1 r2 r3; do
  out="out/more_ai/$r"
  mkdir -p "$out"
  if [ -f "$out/clip_13-01-26_00034_prob4.mp4" ]; then echo "skip (done): $r"; continue; fi
  echo "=== more-AI $r / clip_13-01-26_00034 ==="
  /opt/venv/bin/python scripts/invoke/invoke_skypilot_batch.py \
    --dir sample \
    --workflow "/tmp/moreai_$r.json" \
    --url http://localhost:8188 \
    --out "$out" \
    --timeout 7200 \
    --no-random-seed clip_13-01-26_00034_prob4.mp4 \
    || echo "FAILED: $r"
done
echo "MORE_AI_DONE"
REMOTE
