#!/bin/bash
# Overnight queue mode for the Desktop/input batch:
# launch the 48GB pod -> upload ~/Desktop/input (120 clips) -> QUEUE all of
# them, then exit WITHOUT waiting or tearing down — the pod renders
# autonomously and the PC can go offline.
#
# When back online:
#   ./scripts/skypilot/sync_down.sh status   # pod progress
#   ./scripts/skypilot/sync_down.sh          # pull renders -> ~/Desktop/output
#   ./scripts/skypilot/sync_down.sh down     # same + sky down the pod when complete
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a; source .env; set +a
export SAMPLE_SRC="${SAMPLE_SRC:-$HOME/Desktop/input}"
export OUT_DIR="${OUT_DIR:-$HOME/Desktop/output}"
export WORKFLOW=examples/ltx25_v2v_retake48_loop_runpod.json
export DENOISE="${DENOISE:-0.60}"   # 0.58 default | 0.60 "more life" (this batch) | 1.0 full restyle
export CHUNK="${CHUNK:-5}"
# QONLY also blocks the driver's success-cleanup from sky-downing the pod
# (queue dies with the pod — learned 2026-09-29); --keep-up keeps the tunnel.
QONLY="--queue-only" ./scripts/skypilot/retake_loop_batch.sh --keep-up
echo ""
echo "################################################################"
echo "# ALL QUEUED — PC can go offline now. Pod keeps rendering."
echo "# Pod stays UP (billing) until: sky down -y ltx25"
echo "# Outputs: pod volume /workspace/output (<clip stem>_NNNNN.mp4)"
echo "# Back online: ./scripts/skypilot/sync_down.sh  (sync + verify,"
echo "#              then 'sync_down.sh down' to stop billing)"
echo "################################################################"
