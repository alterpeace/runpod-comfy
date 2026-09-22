#!/bin/bash
# =============================================================================
# sweep_status.sh — live status for the pod-side denoise sweep.
#
#   ./scripts/skypilot/sweep_status.sh             # one snapshot
#   ./scripts/skypilot/sweep_status.sh --watch     # refresh every 15s
#   ./scripts/skypilot/sweep_status.sh --watch 5   # custom interval (s)
#
# Or through watch:  watch -c -n 10 ./scripts/skypilot/sweep_status.sh
# =============================================================================
set -u
WATCH=0
INTERVAL=15
[ "${1:-}" = "--watch" ] && { WATCH=1; INTERVAL="${2:-15}"; }

CLUSTER="${CLUSTER:-ltx25}"
TOTAL="${SWEEP_TOTAL:-6}"   # 2 clips x 4 denoise values

snapshot() {
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$CLUSTER" "SWEEP_TOTAL=$TOTAL /opt/venv/bin/python3 -" <<'PY' 2>/dev/null
import glob, json, os, re, urllib.request

log_path = "/workspace/run_variants/bf16_sweep.log"
bulk_path = "/workspace/run_variants/bulk_sweep.log"
log = open(log_path).read() if os.path.exists(log_path) else ""
blog = open(bulk_path).read() if os.path.exists(bulk_path) else ""
log = log + "\n" + blog if blog else log
total = int(os.environ.get("SWEEP_TOTAL", "8"))
started = len(re.findall(r"^=== ", log, re.M))
failed = len(re.findall(r"^FAILED", log, re.M))
finished = len(glob.glob("/workspace/run_variants/out/bf16_sweep/*/*.mp4"))
times = [float(x) for x in re.findall(r"done in ([\d.]+) min", log)]
cur_m = re.findall(r"^=== (.+)$", log, re.M)
current = cur_m[-1] if cur_m else "-"
sweep_done = "SWEEP_DONE" in log
try:
    q = json.loads(__import__("urllib.request", fromlist=["urlopen"])
                   .urlopen("http://localhost:8188/queue", timeout=5).read())
    running, pending = len(q["queue_running"]), len(q["queue_pending"])
except Exception:
    running, pending = -1, -1
avg = times[-1] if times else 0.0
print(f"{total}|{finished}|{failed}|{running}|{pending}|{avg:.1f}|{int(sweep_done)}|{current}")
PY
}

render() {
  local data; data=$(snapshot)
  if [ -z "$data" ]; then echo "pod unreachable"; return; fi
  IFS='|' read -r total finished failed running pending avg sweepdone current <<< "$data"
  now=$(date -u +%H:%M:%SZ)
  echo "──────────────────────────────────────────────────────────"
  echo " denoise sweep @ $now"
  echo "──────────────────────────────────────────────────────────"
  printf " total:      %s   (2 clips x 3 denoise values)\n" "$total"
  printf " finished:   %s\n" "$finished"
  printf " failed:     %s\n" "$failed"
  printf " running:    %s (comfyui queue)   pending: %s (comfyui)\n" "$running" "$pending"
  printf " current:    %s\n" "$current"
  left=$(( total - finished ))
  if [ "$avg" != "0.0" ] && [ "$left" -gt 0 ]; then
    printf " avg/render: %s min   remaining: %s ≈ %s min (%.1fh)\n" "$avg" "$left" "$(( left * ${avg%.*} ))" "$(echo "$left * $avg / 60" | bc -l 2>/dev/null || echo 0)"
  fi
  [ "$sweepdone" = "1" ] && echo " ✔ SWEEP_DONE"
  echo "──────────────────────────────────────────────────────────"
}

if [ "$WATCH" = "1" ]; then
  while true; do clear; render; sleep "$INTERVAL"; done
else
  render
fi