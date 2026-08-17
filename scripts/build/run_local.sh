#!/bin/bash
# =============================================================================
# Start ComfyUI locally with GPU passthrough.
#
# This is the one-command entry point for local development. It:
#   1. Ensures the CDI spec is patched for Podman 4.9.x (re-runs only if needed)
#   2. Ensures docker-compose.gpu.yml exists (regenerates if missing/stale)
#   3. Starts the container with GPU access via both compose files
#
# Usage:
#   ./scripts/build/run_local.sh          # start (detached)
#   ./scripts/build/run_local.sh --build  # rebuild image first
#   ./scripts/build/run_local.sh --logs   # start + follow logs
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

BUILD=false
FOLLOW_LOGS=false
for arg in "$@"; do
    case "$arg" in
        --build) BUILD=true ;;
        --logs)  FOLLOW_LOGS=true ;;
    esac
done

GPU_OVERRIDE="docker-compose.gpu.yml"

# Step 1: Ensure CDI spec is patched (idempotent — re-patches if stale)
# Check if /var/run/cdi/nvidia.yaml has the unsupported 0.7.0 version
NEEDS_PATCH=false
if [ ! -f /var/run/cdi/nvidia.yaml ]; then
    NEEDS_PATCH=true
elif grep -q "cdiVersion: 0.7.0" /var/run/cdi/nvidia.yaml 2>/dev/null; then
    NEEDS_PATCH=true
elif grep -q "additionalGids" /var/run/cdi/nvidia.yaml 2>/dev/null; then
    NEEDS_PATCH=true
fi

if [ "$NEEDS_PATCH" = true ]; then
    echo "[run_local] CDI spec needs patching — running fix_local_gpu_cdi.sh..."
    bash "$SCRIPT_DIR/../gpu/fix_local_gpu_cdi.sh" >/dev/null 2>&1 || true
fi

# Step 2: Ensure GPU compose override exists
if [ ! -f "$GPU_OVERRIDE" ]; then
    echo "[run_local] Generating GPU compose override..."
    bash "$SCRIPT_DIR/../gpu/gen_gpu_compose_override.sh" >/dev/null 2>&1
fi

# Step 3: Build if requested
if [ "$BUILD" = true ]; then
    echo "[run_local] Building image..."
    docker compose -f docker-compose.yml -f "$GPU_OVERRIDE" build 2>&1
fi

# Step 4: Start the container
echo "[run_local] Starting ComfyUI..."
docker compose -f docker-compose.yml -f "$GPU_OVERRIDE" down 2>&1 || true
docker compose -f docker-compose.yml -f "$GPU_OVERRIDE" up -d 2>&1

# Step 5: Quick GPU verification
sleep 3
if docker exec comfy /comfyui/venv/bin/python -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available'
print(f'GPU: {torch.cuda.get_device_name(0)}')
" 2>&1; then
    echo "[run_local] ✅ GPU detected — ComfyUI starting at http://localhost:8188"
else
    echo "[run_local] ⚠️  GPU not detected — try: ./scripts/gpu/setup_local_gpu.sh"
fi

# Step 6: Follow logs if requested
if [ "$FOLLOW_LOGS" = true ]; then
    echo "[run_local] Following logs (Ctrl+C to stop)..."
    docker logs -f comfy 2>&1
fi