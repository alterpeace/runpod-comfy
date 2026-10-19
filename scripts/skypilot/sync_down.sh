#!/bin/bash
# =============================================================================
# Sync finished loop-retake renders from the pod back to the local machine.
#
# Companion to the queue-night flow (retake_queue_night.sh): the pod renders
# autonomously while the PC is offline; run this when back online to pull the
# outputs into the local output dir and name them after their source clips.
#
# Pod-side outputs are named <stem>_NNNNN.mp4 (queue-only mode sets
# VHS_VideoCombine's filename_prefix to the source clip's stem), so the
# mapping is a suffix strip — no metadata parsing needed.
#
# Usage:
#   ./scripts/skypilot/sync_down.sh status          # pod queue/history progress
#   ./scripts/skypilot/sync_down.sh                 # sync missing renders down
#   ./scripts/skypilot/sync_down.sh sync            # same as above
#   ./scripts/skypilot/sync_down.sh all             # raw-copy every pod mp4 (no rename)
#   ./scripts/skypilot/sync_down.sh down            # sync, then sky down the pod
#
# Env overrides: CLUSTER=ltx25 POD_DIR=/workspace/output OUT_DIR=~/Desktop/output
#
# The pod keeps billing until `sky down -y ltx25` — run `down` only after the
# count check reports everything synced.
# =============================================================================
set -euo pipefail

CLUSTER="${CLUSTER:-ltx25}"
POD_DIR="${POD_DIR:-/workspace/output}"
OUT_DIR="${OUT_DIR:-$HOME/Desktop/output}"
CMD="${1:-sync}"

if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$CLUSTER" true 2>/dev/null; then
  echo "ERROR: cluster $CLUSTER not reachable (is it up? sky status)"
  exit 1
fi

pod_queue_status() {
  ssh "$CLUSTER" "curl -s --max-time 10 http://127.0.0.1:8188/queue" | python3 -c '
import json, sys
q = json.load(sys.stdin)
running, pending = len(q.get("queue_running", [])), len(q.get("queue_pending", []))
print(f"running: {running}  pending: {pending}")
if running + pending == 0:
    print("queue drained — all submitted jobs have finished")
'
}

pod_done_count() {
  ssh "$CLUSTER" "curl -s --max-time 15 'http://127.0.0.1:8188/history?max_items=1000'" | python3 -c '
import json, sys
h = json.load(sys.stdin)
done = sum(1 for e in h.values()
           if any(k in out for out in (e.get("outputs") or {}).values()
                  for k in ("gifs", "images", "videos")))
print(f"history entries with video output: {done}")
'
}

if [ "$CMD" = "status" ]; then
  echo "=== $CLUSTER queue ==="
  pod_queue_status
  echo "=== $CLUSTER history ==="
  pod_done_count
  n_q=0; [ -d "$OUT_DIR/.workflows" ] && n_q=$(find "$OUT_DIR/.workflows" -name '*.json' | wc -l)
  n_s=$(find "$OUT_DIR" -maxdepth 1 -name '*.mp4' 2>/dev/null | wc -l)
  echo "queued by this batch: $n_q"
  echo "already synced down: $n_s"
  exit 0
fi

mkdir -p "$OUT_DIR"
STAGE="$OUT_DIR/.pod_stage"
mkdir -p "$STAGE"

if [ "$CMD" = "all" ]; then
  echo "=== Raw-syncing every pod mp4 -> $OUT_DIR/raw_pod (no rename) ==="
  rsync -a --info=progress2 --partial \
        -e "ssh -o StrictHostKeyChecking=accept-new" \
        "$CLUSTER:$POD_DIR/" "$OUT_DIR/raw_pod/" --include='*.mp4' --exclude='*'
  echo "Done. Raw copies in $OUT_DIR/raw_pod/"
  exit 0
fi

# --- stem-driven sync (default) -----------------------------------------------
WF_DIR="$OUT_DIR/.workflows"
if [ ! -d "$WF_DIR" ] || [ -z "$(ls "$WF_DIR"/*.json 2>/dev/null)" ]; then
  echo "ERROR: no $WF_DIR/*.json — this sync maps pod outputs by the queued"
  echo "per-clip workflows. If this batch was queued elsewhere, use 'all'."
  exit 1
fi

mapfile -t STEMS < <(for f in "$WF_DIR"/*.json; do basename "$f" .json; done | sort -u)
expected=${#STEMS[@]}

# Files already synced down (skip: resumable)
already=0
for stem in "${STEMS[@]}"; do
  [ -f "$OUT_DIR/$stem.mp4" ] && already=$((already + 1))
done
todo=$((expected - already))
echo "=== $expected queued, $already already synced, $todo to fetch ==="
[ "$todo" -eq 0 ] && { echo "Nothing to do."; exit 0; }

# Build the pod-side file list for the missing stems. rsync --files-from
# does NOT glob, so list the pod's actual output files over ssh and match
# <stem>_NNNNN.mp4 against the missing stems locally.
LIST="$(mktemp)"
MISSING_LIST="$(mktemp)"
for stem in "${STEMS[@]}"; do
  [ -f "$OUT_DIR/$stem.mp4" ] || echo "$stem"
done > "$MISSING_LIST"
ssh -o StrictHostKeyChecking=accept-new "$CLUSTER" \
  "ls -1 '$POD_DIR' 2>/dev/null | grep -E '\.mp4$'" > "$LIST" || true
FILTERED="$(mktemp)"
while IFS= read -r podfile; do
  [ -z "$podfile" ] && continue
  stem="${podfile%_*}"   # strip the _NNNNN counter suffix
  grep -qxF "$stem" "$MISSING_LIST" && echo "$podfile" >> "$FILTERED"
done < "$LIST"
wc -l < "$FILTERED" | xargs -I{} echo "=== {} pod files match missing stems ==="
: > "$LIST"; cat "$FILTERED" > "$LIST"; rm -f "$FILTERED" "$MISSING_LIST"

echo "=== rsync from $CLUSTER:$POD_DIR (missing stems only) ==="
rsync -a --info=progress2 --partial --files-from="$LIST" \
      -e "ssh -o StrictHostKeyChecking=accept-new" \
      "$CLUSTER:$POD_DIR/" "$STAGE/" || true
rm -f "$LIST"

# Rename <stem>_NNNNN.mp4 -> <stem>.mp4 (suffix strip; keep highest NNNNN on clash)
echo "=== Renaming into $OUT_DIR ==="
synced=0
for stage_file in "$STAGE"/*.mp4; do
  [ -f "$stage_file" ] || continue
  base="$(basename "$stage_file" .mp4)"
  stem="${base%_*}"            # strip _NNNNN
  if [ -f "$OUT_DIR/$stem.mp4" ]; then continue; fi
  mv "$stage_file" "$OUT_DIR/$stem.mp4"
  synced=$((synced + 1))
done

# --- verify ---------------------------------------------------------------------
missing=()
for stem in "${STEMS[@]}"; do
  [ -f "$OUT_DIR/$stem.mp4" ] || missing+=("$stem")
done
echo ""
echo "=== Sync complete: $((already + synced))/$expected present in $OUT_DIR ==="
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Missing ${#missing[@]} (still rendering, failed on the pod, or not yet queued):"
  printf '  %s\n' "${missing[@]}" | head -20
  [ "${#missing[@]}" -gt 20 ] && echo "  ... and $(( ${#missing[@]} - 20 )) more"
  echo "Check progress with: $0 status"
  echo "Do NOT sky down yet if the queue is not drained."
else
  echo "All renders present. Validate loops (tools/loop-checker.html), then tear down:"
  echo "  sky down -y $CLUSTER"
fi

# Tidy the stage dir
find "$STAGE" -type f -delete 2>/dev/null || true
rmdir "$STAGE" 2>/dev/null || true

[ "$CMD" = "down" ] && [ "${#missing[@]}" -eq 0 ] && {
  echo "=== Terminating cluster (volume + models survive) ==="
  sky down -y "$CLUSTER"
}
exit 0
