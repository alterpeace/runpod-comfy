#!/bin/bash
# =============================================================================
# Test-matrix runner: recover setup, render baseline + 3 upgrade variants,
# summarize outputs per subfolder.
#
#   ./scripts/skypilot/run_test_matrix.sh
#
# Idempotent end to end: setup verify-skips volume models, rsync skips
# uploaded clips, batch skips already-rendered clips. Safe to re-run.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

set -a; source .env; set +a

CLIPS=(
  clip_26-09-11_20-02-36_00002.mp4
  clip_26-09-11_20-02-53_00002.mp4
  clip_26-09-11_20-03-51_00001.mp4
  clip_26-08-19_20-15-27_00001.mp4
  clip_26-08-19_20-15-35_00001.mp4
  clip_26-08-19_20-15-35_00003.mp4
)
PAIRS=(clip_26-09-11_20-02-36_00002.mp4 clip_26-08-19_20-15-35_00003.mp4)

command -v sky   >/dev/null || { echo "ERROR: sky not installed"; exit 1; }
command -v uv    >/dev/null || { echo "ERROR: uv not installed";   exit 1; }
[ -d sample ] || ln -sfn "$HOME/Desktop/sample" sample

echo "=== [1/5] Setup (detached — job runs server-side, never blocks) ==="
sky launch -c ltx25 -y -d scripts/skypilot/ltx25-48gb.yaml --env HF_TOKEN="$HF_TOKEN" || {
  echo "ERROR: launch failed — check sky logs ltx25"; exit 1; }

echo "=== [2/5] Tunnel ==="
pkill -f "ssh -f -N -L 8188" 2>/dev/null || true
sleep 1
ssh -f -N -L 8188:localhost:8188 \
    -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new ltx25

echo "=== [3/5] Health (first boot may include model loads) ==="
HEALTH=0
for i in $(seq 1 240); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8188/system_stats || true)
  [ "$code" = "200" ] && { HEALTH=1; break; }
  [ $((i % 12)) -eq 0 ] && echo "  ...waiting ($((i * 10 / 60)) min)"
  sleep 10
done
[ "$HEALTH" -eq 1 ] || { echo "ERROR: ComfyUI never became healthy"; exit 1; }

echo "=== [4/5] Sync clips (incremental) ==="
ssh -o StrictHostKeyChecking=accept-new ltx25 'mkdir -p /workspace/input/sample'
rsync -a --no-owner --no-group -e "ssh -o StrictHostKeyChecking=accept-new" \
  sample/ ltx25:/workspace/input/sample/

echo "=== [5/5] Render matrix ==="
FAILED=()
run_batch() {
  local wf=$1 out=$2; shift 2
  echo "--- $out"
  uv run python scripts/invoke/invoke_skypilot_batch.py \
    --dir sample --workflow "$wf" --out "$out" --no-random-seed "$@" \
    || FAILED+=("$out")
}

run_batch examples/ltx25_v2v_retake48_loop_runpod.json output/retake_loop_batch "${CLIPS[@]}"
run_batch examples/ltx25_v2v_retake48_loop_nag.json     output/retake_nag       "${PAIRS[@]}"
run_batch examples/ltx25_v2v_retake48_loop_iclora.json  output/retake_iclora    "${PAIRS[@]}"
run_batch examples/ltx25_v2v_retake48_loop_both.json    output/retake_nag_ic    "${PAIRS[@]}"

echo
echo "=================== REPORT ==================="
for d in output/retake_loop_batch output/retake_nag output/retake_iclora output/retake_nag_ic; do
  echo "--- $d ($(ls "$d" 2>/dev/null | wc -l) files)"
  ls -la "$d" 2>/dev/null | awk 'NR>3 {printf "    %-60s %10.1f MB\n", $NF, $5/1e6}'
done
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "FAILED batches: ${FAILED[*]}"
  exit 1
fi
echo "All batches complete. Validate in tools/loop-checker.html: Loop diff <5%, Start match <5%."
