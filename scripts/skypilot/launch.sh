#!/bin/bash
# =============================================================================
# SkyPilot LTX-2.5 launcher — wraps sky commands with .env loading.
#
# Usage:
#   ./scripts/skypilot/launch.sh                # launch on cheapest available
#   ./scripts/skypilot/launch.sh --cloud runpod  # launch on RunPod
#   ./scripts/skypilot/launch.sh --cloud lambda  # launch on Lambda Labs
#   ./scripts/skypilot/launch.sh --cloud vast    # launch on Vast.ai
#   ./scripts/skypilot/launch.sh --24gb          # use 24GB config (--lowvram)
#   ./scripts/skypilot/launch.sh status           # check status
#   ./scripts/skypilot/launch.sh ssh             # SSH into the machine
#   ./scripts/skypilot/launch.sh port-forward     # forward ComfyUI WebUI
#   ./scripts/skypilot/launch.sh stop             # stop (saves cost, keeps disk)
#   ./scripts/skypilot/launch.sh start            # resume from stop
#   ./scripts/skypilot/launch.sh down             # terminate (destroys disk)
#
# Environment:
#   HF_TOKEN          HuggingFace token (required, from .env)
#   RUNPOD_API_KEY    RunPod API key (for RunPod)
#   LAMBDA_CLOUD_API_KEY  Lambda Labs API key (for Lambda)
#   VAST_API_KEY      Vast.ai API key (for Vast.ai)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="ltx25"

# Load .env
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Check HF_TOKEN
if [ -z "${HF_TOKEN:-}" ]; then
    echo "[ERROR] HF_TOKEN not set. Add it to .env or export it."
    echo "        Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'."
    exit 1
fi

# Check if sky is installed
if ! command -v sky &>/dev/null; then
    echo "[ERROR] SkyPilot not installed. Run: pip install skypilot"
    exit 1
fi

# Parse arguments
ACTION="launch"
CLOUD_ARG=""
GPU_TYPE="L40S:1"
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        status)        ACTION="status"; shift ;;
        ssh)           ACTION="ssh"; shift ;;
        port-forward)  ACTION="port-forward"; shift ;;
        stop)          ACTION="stop"; shift ;;
        start)         ACTION="start"; shift ;;
        down)          ACTION="down"; shift ;;
        --cloud)       CLOUD_ARG="--cloud $2"; shift 2 ;;
        --24gb)        GPU_TYPE="RTX4090:1"; EXTRA_ARGS="--env COMFYUI_ARGS=--lowvram"; shift ;;
        --gpu)         GPU_TYPE="$2"; shift 2 ;;
        --name)        CLUSTER_NAME="$2"; shift 2 ;;
        *)             EXTRA_ARGS="$EXTRA_ARGS $1"; shift ;;
    esac
done

TASK_FILE="$SCRIPT_DIR/ltx25-48gb.yaml"

case "$ACTION" in
    launch)
        echo "=== Launching SkyPilot LTX-2.5 ($GPU_TYPE) ==="
        echo "  Cluster: $CLUSTER_NAME"
        echo "  GPU: $GPU_TYPE"
        echo "  HF Token: set"
        ${CLOUD_ARG:+echo "  Cloud: $CLOUD_ARG"}
        echo ""
        sky launch -c "$CLUSTER_NAME" "$TASK_FILE" \
            --gpus "$GPU_TYPE" \
            --env HF_TOKEN="$HF_TOKEN" \
            $CLOUD_ARG $EXTRA_ARGS
        ;;
    status)
        sky status
        ;;
    ssh)
        sky ssh "$CLUSTER_NAME"
        ;;
    port-forward)
        echo "Port-forwarding ComfyUI WebUI at http://localhost:8188"
        sky port-forward "$CLUSTER_NAME" 8188
        ;;
    stop)
        echo "Stopping $CLUSTER_NAME (disk is preserved)..."
        sky stop "$CLUSTER_NAME"
        ;;
    start)
        echo "Resuming $CLUSTER_NAME..."
        sky start "$CLUSTER_NAME"
        ;;
    down)
        echo "WARNING: This will destroy the disk and all downloaded models."
        read -p "Are you sure? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            sky down "$CLUSTER_NAME"
        else
            echo "Cancelled."
        fi
        ;;
esac
