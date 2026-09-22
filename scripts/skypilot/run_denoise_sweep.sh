#!/bin/bash
# Waits for the freshly launched ltx25 pod, then stages + launches the
# denoise sweep server-side. Run via background_process from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

echo "=== Waiting for SSH + /workspace symlink (provision ~15 min) ==="
until ssh -o ConnectTimeout=10 -o BatchMode=yes ltx25 \
      '[ -d /workspace/models ] && [ "$(readlink -f /opt/ComfyUI/models)" = /workspace/models ]' 2>/dev/null; do
  sleep 30
done
echo "=== Pod ready (volume mounted) ==="

echo "=== Ensuring the 3 sweep clips are on the volume ==="
ssh ltx25 'mkdir -p /workspace/input/sample'
rsync -a --no-owner --no-group \
  "$HOME/Desktop/sample/clip_26-09-11_20-03-51_00001.mp4" \
  "$HOME/Desktop/sample/clip_26-09-18_19-36-48_00001.mp4" \
  "$HOME/Desktop/sample/clip_26-09-18_19-37-30_00001.mp4" \
  ltx25:/workspace/input/sample/
ssh ltx25 'ln -sfn /workspace/input/sample /workspace/run_variants/sample'

echo "=== Waiting for ComfyUI /queue ==="
until ssh ltx25 'curl -s -o /dev/null -w %{http_code} --max-time 5 http://localhost:8188/queue' 2>/dev/null | grep -q 200; do
  sleep 30
done
echo "=== ComfyUI healthy — launching denoise sweep ==="
rsync -a --no-owner --no-group scripts/skypilot/denoise_sweep.sh ltx25:/workspace/run_variants/
ssh ltx25 'chmod +x /workspace/run_variants/denoise_sweep.sh; \
  nohup /workspace/run_variants/denoise_sweep.sh < /dev/null >> /workspace/run_variants/denoise_sweep.log 2>&1 & \
  echo "sweep launched pid $!"'
