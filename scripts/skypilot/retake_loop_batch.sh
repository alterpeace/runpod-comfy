#!/bin/bash
# =============================================================================
# Looping-retake batch driver — SkyPilot 48GB -> ltx25_v2v_retake48_loop.
#
# End to end: ensure network volume -> launch cluster -> wait for ComfyUI ->
# upload ~/Desktop/sample -> batch V2V with the looping retake workflow ->
# outputs land in output/retake_loop_batch -> terminate cluster.
#
# Models live on the ltx25-vol network volume and survive `sky down`, so the
# next run only re-provisions the container disk (~15 min) instead of
# re-downloading ~42GB of weights.
#
# Usage (run from a normal terminal — needs network):
#   ./scripts/skypilot/retake_loop_batch.sh
#   ./scripts/skypilot/retake_loop_batch.sh clip_11-01-26_00013_thm2_prob4.mp4   # subset first
#   ./scripts/skypilot/retake_loop_batch.sh --keep-up                            # keep cluster up after
#
# Validate outputs with tools/loop-checker.html (Start/End match + Loop diff).
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

CLUSTER="ltx25"
VOL="ltx25-vol"
VOL_INFRA="runpod/NL/EU-NL-1"
VOL_SIZE="${VOL_SIZE:-100}"   # GB; export VOL_SIZE=200 for more headroom
SAMPLE_SRC="${SAMPLE_SRC:-$HOME/Desktop/sample}"
OUT_DIR="output/retake_loop_batch"
PER_CLIP_TIMEOUT="${PER_CLIP_TIMEOUT:-3600}"

KEEP_UP=0
RANDOM_SEEDS=0
CLIPS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-up)      KEEP_UP=1; shift ;;
    --random-seeds) RANDOM_SEEDS=1; shift ;;
    *)              CLIPS+=("$1"); shift ;;
  esac
done

[ -f .env ] || { echo "ERROR: .env with HF_TOKEN / RUNPOD_API_KEY required"; exit 1; }
set -a; source .env; set +a
[ -n "${HF_TOKEN:-}" ] || { echo "ERROR: HF_TOKEN missing (gated LTX-2.5)"; exit 1; }
[ -n "${RUNPOD_API_KEY:-}" ] || { echo "ERROR: RUNPOD_API_KEY missing"; exit 1; }
[ -d "$SAMPLE_SRC" ] || { echo "ERROR: $SAMPLE_SRC not found"; exit 1; }
command -v sky >/dev/null || { echo "ERROR: skypilot not installed (pipx install skypilot)"; exit 1; }
command -v uv   >/dev/null || { echo "ERROR: uv not installed"; exit 1; }

cleanup() {
  local code=$?
  local kill_tunnel=1
  if [ "$code" -eq 0 ] && [ "$KEEP_UP" -eq 1 ]; then
    kill_tunnel=0
  fi
  if [ "$kill_tunnel" -eq 1 ] && [ -n "${TUNNEL_PID:-}" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
  if [ "$code" -eq 0 ] && [ "$KEEP_UP" -eq 0 ]; then
    echo "=== Terminating cluster (volume + models survive) ==="
    sky down -y "$CLUSTER" 2>/dev/null || true
  fi
  if [ "$code" -eq 0 ] && [ "$KEEP_UP" -eq 1 ]; then
    echo "=== Cluster left UP (still billing). Tunnel live at http://localhost:8188."
    echo "    Iterate directly:  uv run python scripts/invoke/invoke_skypilot_batch.py \\"
    echo "      --dir sample --workflow examples/ltx25_v2v_retake48_loop_runpod.json \\"
    echo "      --out $OUT_DIR <clip.mp4 ...>"
    echo "    When done testing:  sky down -y $CLUSTER"
  fi
  exit "$code"
}
trap cleanup EXIT

# --- 1. Network volume (models, input, output) --------------------------------
if ! sky volumes ls 2>/dev/null | grep -q "$VOL"; then
  echo "=== Creating 200GB network volume $VOL ($VOL_INFRA) ==="
  sky volumes apply -n "$VOL" --infra "$VOL_INFRA" --type runpod-network-volume --size "$VOL_SIZE"
else
  echo "=== Volume $VOL exists ==="
fi

# --- 2. Launch cluster (detached: provisioning + ~42GB model setup) ----------
# Skip when the cluster is already reachable (e.g. a previous --keep-up run):
# re-launching re-runs setup and its `run:` phase, whose ComfyUI would collide
# with the one already listening on 8188.
if ssh -o ConnectTimeout=10 -o BatchMode=yes "$CLUSTER" true 2>/dev/null; then
  echo "=== Cluster $CLUSTER already reachable — skipping launch/setup ==="
else
  echo "=== Launching $CLUSTER (48GB, detached) ==="
  ./scripts/skypilot/launch.sh -d -y
fi

# --- 3. Wait for the pod to accept SSH ----------------------------------------
echo "=== Waiting for SSH (first boot: image + ~42GB model download) ==="
SSH_OK=0
for i in $(seq 1 180); do   # up to ~90 min
  if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
         -o BatchMode=yes "$CLUSTER" true 2>/dev/null; then
    SSH_OK=1; break
  fi
  sleep 30
  if ! sky status 2>/dev/null | grep -q "$CLUSTER"; then
    echo "ERROR: cluster vanished from sky status"; exit 1
  fi
done
[ "$SSH_OK" -eq 1 ] || { echo "ERROR: SSH never came up after 90 min"; exit 1; }

# --- 3.5 Sync model set to the network volume (idempotent; includes the
#         retake48 extras the launch yaml skips: distilled int8 transformer,
#         audio VAE, gemma4_e2b int8 enhancer) --------------------------------
echo "=== Syncing models (ensure_models.sh — idempotent) ==="
ssh -o StrictHostKeyChecking=accept-new "$CLUSTER" \
  "export HF_TOKEN='$HF_TOKEN'; bash -s" < "$ROOT/scripts/skypilot/ensure_models.sh"

# --- 4. SSH tunnel + wait for ComfyUI health ----------------------------------
TUNNEL_PIDFILE="/tmp/ltx25-tunnel.pid"
if [ -f "$TUNNEL_PIDFILE" ] && kill -0 "$(cat "$TUNNEL_PIDFILE")" 2>/dev/null; then
  kill "$(cat "$TUNNEL_PIDFILE")" 2>/dev/null || true
fi
ssh -f -N -L 8188:localhost:8188 \
    -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    "$CLUSTER" > /dev/null 2>&1 || true   # non-fatal: a stale tunnel may hold the port; health loop decides
TUNNEL_PID=$(pgrep -f "ssh -f -N -L 8188:localhost:8188.*$CLUSTER" | head -1 || true)
[ -n "$TUNNEL_PID" ] && echo "$TUNNEL_PID" > "$TUNNEL_PIDFILE"

echo "=== Waiting for ComfyUI (/queue) — first boot includes ~50GB model downloads ==="
HEALTH=0
for i in $(seq 1 240); do   # 40 min: cold start = setup + full model download
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8188/queue || true)
  [ "$code" = "200" ] && { HEALTH=1; break; }
  if [ $((i % 6)) -eq 0 ]; then
    echo "  ...still waiting ($((i * 10 / 60)) min elapsed)"
  fi
  sleep 10
done
[ "$HEALTH" -eq 1 ] || { echo "ERROR: ComfyUI not healthy at localhost:8188"; exit 1; }

# --- 5. Upload clips (resumable) ----------------------------------------------
echo "=== Uploading $SAMPLE_SRC -> pod:/workspace/input/sample ==="
ssh -o StrictHostKeyChecking=accept-new "$CLUSTER" 'mkdir -p /workspace/input/sample'
rsync -a --no-owner --no-group --info=progress2 --partial \
      -e "ssh -o StrictHostKeyChecking=accept-new" \
      "$SAMPLE_SRC/" "$CLUSTER:/workspace/input/sample/"

# --- 6. Batch V2V ---------------------------------------------------------------
# The batch script plans against a local sample/ dir; symlink the source in.
ln -sfn "$SAMPLE_SRC" sample
mkdir -p "$OUT_DIR"
echo "=== Running looping-retake batch (outputs -> $OUT_DIR) ==="
SEED_ARGS=""
[ "$RANDOM_SEEDS" -eq 0 ] && SEED_ARGS="--no-random-seed"
uv run python scripts/invoke/invoke_skypilot_batch.py \
  --dir sample \
  --workflow examples/ltx25_v2v_retake48_loop_runpod.json \
  --out "$OUT_DIR" \
  --timeout "$PER_CLIP_TIMEOUT" \
  $SEED_ARGS \
  ${CLIPS+"${CLIPS[@]}"}

echo "=== Done. Check loops: open tools/loop-checker.html, drop original + $OUT_DIR/*.mp4 ==="
echo "    Pass requires: Start match <5%, End match <15%, retake Loop diff <5%, same frame count."
