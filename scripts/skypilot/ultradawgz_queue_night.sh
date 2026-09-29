#!/bin/bash
# Overnight queue mode: upload (delta) + QUEUE all pending clips on the pod,
# then exit WITHOUT waiting or tearing down — the pod renders autonomously.
# Requires the cluster to already be up (or launch it first with
#   sky launch -c ltx25 -y -d --retry-until-up scripts/skypilot/ltx25-48gb.yaml).
# The pod MUST stay up until rendering finishes; `sky down -y ltx25` when done.
set -euo pipefail
cd /home/chiral/source/runpod-comfy
set -a; source .env; set +a
export SAMPLE_SRC=/media/chiral/data/visuals/clips/al7/ultradawgz_pass1
export OUT_DIR=output/ultradawgz_batch
export WORKFLOW=examples/ltx25_v2v_retake48_loop_runpod.json
export CHUNK=5
# QONLY also blocks the driver's success-cleanup from sky-downing the pod
# (queue dies with the pod — learned 2026-09-29); --keep-up keeps the tunnel.
QONLY="--queue-only" ./scripts/skypilot/retake_loop_batch.sh --keep-up
echo ""
echo "################################################################"
echo "# ALL QUEUED — PC can go offline now. Pod keeps rendering."
echo "# Pod stays UP (billing ~\$1.09/h) until: sky down -y ltx25"
echo "# Outputs: pod volume /workspace/output (ultradawgz_batch)"
echo "# Tomorrow: sync down + verify count, then sky down the pod"
echo "################################################################"