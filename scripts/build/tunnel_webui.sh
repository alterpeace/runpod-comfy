#!/bin/bash
# tunnel_webui.sh - Forward a RunPod ComfyUI WebUI to your local machine (Linux/macOS)
#
# POD mode (direct SSH forward) - for Pods, which have public SSH:
#   ./scripts/build/tunnel_webui.sh <POD_PUBLIC_IP> <POD_SSH_PORT>
# Then open http://localhost:8188
# Get IP/port from the pod's "Connect" panel in the RunPod console.
# Pod needs: ENABLE_SSH=true + SSH_PUBLIC_KEY set, TCP 22 exposed.

set -euo pipefail

POD_IP="${1:-}"
POD_PORT="${2:-22}"
LOCAL_PORT="${LOCAL_PORT:-8188}"

usage() {
    sed -n '2,12p' "$0"
    exit 1
}

[ -z "$POD_IP" ] && usage

echo "==> Forwarding pod $POD_IP:$POD_PORT -> http://localhost:$LOCAL_PORT"
echo "==> Ctrl+C to close the tunnel"
# -N: no remote command, ServerAliveInterval keeps NAT/RunPod from idling the conn
ssh -N \
    -L "${LOCAL_PORT}:127.0.0.1:8188" \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    "root@${POD_IP}" -p "$POD_PORT" &
SSH_PID=$!
sleep 2
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:${LOCAL_PORT}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
    open "http://localhost:${LOCAL_PORT}" || true
fi
echo "==> WebUI: http://localhost:${LOCAL_PORT}"
wait $SSH_PID
