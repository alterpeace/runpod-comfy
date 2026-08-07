#!/bin/bash
# tunnel_webui.sh - Forward a RunPod ComfyUI WebUI to your local machine (Linux/macOS)
#
# TWO MODES:
#
#   1) POD mode (direct SSH forward) - for Pods, which have public SSH:
#        ./scripts/tunnel_webui.sh pod <POD_PUBLIC_IP> <POD_SSH_PORT>
#      Then open http://localhost:8188
#      Get IP/port from the pod's "Connect" panel in the RunPod console.
#      Pod needs: ENABLE_SSH=true + SSH_PUBLIC_KEY set, TCP 22 exposed.
#
#   2) ZITI mode (sanctuary overlay) - for SERVERLESS workers (no inbound SSH):
#        ./scripts/tunnel_webui.sh ziti
#      Requires: worker joined to your OpenZiti network (see docs/WEBUI_ACCESS.md)
#      and a local ziti tunneler running (Ziti Desktop Edge / ziti-edge-tunnel).
#      Then open http://comfyui-http.ziti (or your OPENZITI_SERVICE_HTTP name).
#
# Serverless workers are OUTBOUND-ONLY - you cannot ssh INTO them. Ziti works
# because the worker dials OUT to your controller. To put a worker on sanctuary:
#   - drop ziti-identity.json at /runpod-volume/ziti-identity.json (via seed pod)
#   - drop a .env on the volume containing:
#       OPENZITI_IDENTITY=/runpod-volume/ziti-identity.json
#       OPENZITI_SERVICE_HTTP=comfyui-http
#       OPENZITI_SERVICE_SSH=comfyui-ssh
#   entrypoint.sh sources /runpod-volume/.env automatically at every worker boot.
#   (Alternative: set OPENZITI_IDENTITY_JSON as a Secret env var on the endpoint.)

set -euo pipefail

MODE="${1:-}"
LOCAL_PORT="${LOCAL_PORT:-8188}"

usage() {
    sed -n '2,30p' "$0"
    exit 1
}

[ -z "$MODE" ] && usage

case "$MODE" in
    pod)
        POD_IP="${2:-}"
        POD_PORT="${3:-22}"
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
        ;;
    ziti)
        SERVICE="${OPENZITI_SERVICE_HTTP:-comfyui-http}"
        echo "==> Ziti mode: expecting a local tunneler with the '${SERVICE}' service"
        if command -v ziti-edge-tunnel >/dev/null 2>&1; then
            echo "==> ziti-edge-tunnel found - service status:"
            ziti-edge-tunnel service_control --help >/dev/null 2>&1 || true
        else
            echo "!! ziti-edge-tunnel not found. Install Ziti Desktop Edge:"
            echo "   https://openziti.io/docs/downloads"
            echo "   Then enroll YOUR client identity and dial the '${SERVICE}' service."
        fi
        echo "==> WebUI: http://${SERVICE}.ziti  (once the worker is enrolled and running)"
        ;;
    *)
        usage
        ;;
esac
