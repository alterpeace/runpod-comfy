#!/bin/bash
# =============================================================================
# Deploy/manage ComfyUI on RunPod (serverless or pods mode).
#
# This is the one-command entry point for RunPod deployments. It handles both
# serverless endpoints and GPU pods via the lifecycle scripts.
#
# Usage:
#   ./scripts/run_runpod.sh serverless deploy          # deploy serverless endpoint
#   ./scripts/run_runpod.sh serverless status          # check endpoint status
#   ./scripts/run_runpod.sh serverless logs            # tail handler logs
#   ./scripts/run_runpod.sh pods create --gpu "RTX 4090" --name "comfy-prod"
#   ./scripts/run_runpod.sh pods list                   # list active pods
#   ./scripts/run_runpod.sh pods terminate <pod-id>    # terminate a pod
#
# Prerequisites:
#   - RUNPOD_API_KEY set in .env or environment
#   - Python with requests installed (or run inside the project venv)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Load .env if it exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Check for API key
if [ -z "${RUNPOD_API_KEY:-}" ]; then
    echo "[run_runpod] ERROR: RUNPOD_API_KEY not set."
    echo "  Add it to .env:  RUNPOD_API_KEY=your_key_here"
    exit 1
fi

# Use the project venv if available (runpod SDK is installed there, not system Python)
if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python"
fi

MODE="${1:-}"
shift || true

case "$MODE" in
    serverless)
        ACTION="${1:-deploy}"
        case "$ACTION" in
            deploy)
                echo "[run_runpod] Deploying serverless endpoint..."
                "$PYTHON" lifecycle/runpod_serverless.py create "${@:2}"
                ;;
            status)
                echo "[run_runpod] Checking serverless endpoint status..."
                "$PYTHON" lifecycle/runpod_serverless.py status "${@:2}"
                ;;
            list)
                echo "[run_runpod] Listing serverless endpoints..."
                "$PYTHON" lifecycle/runpod_serverless.py list "${@:2}"
                ;;
            invoke)
                echo "[run_runpod] Invoking serverless endpoint..."
                "$PYTHON" lifecycle/runpod_serverless.py invoke "${@:2}"
                ;;
            logs)
                echo "[run_runpod] Tailing serverless logs..."
                "$PYTHON" lifecycle/runpod_serverless.py logs "${@:2}"
                ;;
            *)
                echo "[run_runpod] Unknown serverless action: $ACTION"
                echo "  Usage: $0 serverless [deploy|status|list|invoke|logs]"
                exit 1
                ;;
        esac
        ;;
    pods)
        ACTION="${1:-list}"
        case "$ACTION" in
            create)
                echo "[run_runpod] Creating GPU pod..."
                "$PYTHON" lifecycle/runpod_pods.py create "${@:2}"
                ;;
            list)
                echo "[run_runpod] Listing active pods..."
                "$PYTHON" lifecycle/runpod_pods.py list "${@:2}"
                ;;
            terminate)
                POD_ID="${2:-}"
                if [ -z "$POD_ID" ]; then
                    echo "[run_runpod] ERROR: pod ID required"
                    echo "  Usage: $0 pods terminate <pod-id>"
                    exit 1
                fi
                echo "[run_runpod] Terminating pod $POD_ID..."
                "$PYTHON" lifecycle/runpod_pods.py terminate "$POD_ID"
                ;;
            *)
                echo "[run_runpod] Unknown pods action: $ACTION"
                echo "  Usage: $0 pods [create|list|terminate]"
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Usage: $0 <serverless|pods> [action] [args...]"
        echo ""
        echo "Serverless:"
        echo "  $0 serverless deploy          Deploy serverless endpoint"
        echo "  $0 serverless status          Check endpoint status"
        echo "  $0 serverless logs            Tail handler logs"
        echo ""
        echo "Pods:"
        echo "  $0 pods create --gpu 'RTX 4090' --name 'comfy-prod'"
        echo "  $0 pods list                   List active pods"
        echo "  $0 pods terminate <pod-id>     Terminate a pod"
        exit 1
        ;;
esac