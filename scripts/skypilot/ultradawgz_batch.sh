#!/bin/bash
# Full ultradawgz batch, pipelined: CHUNK=5 uploads overlap with rendering.
# Sources = pre-resized pass-1 copies (quality-neutral; uplink ~150kB/s).
set -euo pipefail
cd /home/chiral/source/runpod-comfy
set -a; source .env; set +a
export SAMPLE_SRC=/media/chiral/data/visuals/clips/al7/ultradawgz_pass1
export OUT_DIR=output/ultradawgz_batch
export WORKFLOW=examples/ltx25_v2v_retake48_loop_runpod.json
export CHUNK=5
./scripts/skypilot/retake_loop_batch.sh