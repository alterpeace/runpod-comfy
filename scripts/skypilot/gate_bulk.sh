#!/bin/bash
# Gate: stop the one-at-a-time sweep loop (its in-flight render completes as an
# orphan), wait for that output, then bulk-submit the remaining ladder into
# ComfyUI's queue.
set -u
cd /workspace/run_variants

pkill -f "denoise_[s]weep.sh" 2>/dev/null || true
echo "sweep loop stopped (in-flight render continues server-side)" >> bulk_sweep.log

echo "waiting for in-flight render to finish..." >> bulk_sweep.log
until [ -f out/denoise_test/d_0.5/clip_26-09-18_19-36-48_00001.mp4 ]; do sleep 20; done
echo "in-flight render done" >> bulk_sweep.log

bash bulk_sweep.sh