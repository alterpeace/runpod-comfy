#!/bin/bash
# =============================================================================
# One-command local GPU setup for Podman/crun environments.
#
# This script automates the entire GPU passthrough workflow that is needed
# because Docker Compose v5.x (external provider) doesn't properly resolve
# CDI device strings when `docker` is actually a Podman shim (crun runtime).
#
# It does three things:
#   1. Patches the CDI spec for Podman 4.9.x compatibility (delegates to
#      fix_local_gpu_cdi.sh — needed after every reboot/driver update).
#   2. Generates a docker-compose.gpu.yml override file that explicitly maps
#      GPU device nodes and NVIDIA userspace libraries into the container
#      (delegates to gen_gpu_compose_override.sh).
#   3. Restarts the container using both compose files so the GPU is available.
#
# The entrypoint.sh setup_nvidia_symlinks() function then creates the
# unversioned .so symlinks (libcuda.so.1, etc.) at container startup.
#
# Usage:
#   ./scripts/setup_local_gpu.sh           # patch + generate + restart
#   ./scripts/setup_local_gpu.sh --no-restart  # patch + generate only
#
# Re-run after: a reboot, an NVIDIA driver update, or an nvidia-container-toolkit
# update. The CDI spec on /var/run/cdi is tmpfs and resets on every reboot.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

RESTART=true
if [ "${1:-}" = "--no-restart" ]; then
    RESTART=false
fi

echo ""
echo "=========================================="
echo "  Local GPU Setup (Podman/crun + Compose)"
echo "=========================================="
echo ""

# Step 1: Patch CDI spec
echo "--- Step 1: Patching CDI spec for Podman 4.9.x ---"
bash "$SCRIPT_DIR/fix_local_gpu_cdi.sh"
echo ""

# Step 2: Generate compose override
echo "--- Step 2: Generating GPU compose override ---"
bash "$SCRIPT_DIR/gen_gpu_compose_override.sh"
echo ""

# Step 3: Restart container
if [ "$RESTART" = true ]; then
    echo "--- Step 3: Restarting container with GPU override ---"
    docker compose -f docker-compose.yml -f docker-compose.gpu.yml down 2>&1
    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d 2>&1
    echo ""

    # Step 4: Verify GPU is visible
    echo "--- Step 4: Verifying GPU inside container ---"
    sleep 3
    if docker exec comfy /comfyui/venv/bin/python -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'Device count: {torch.cuda.device_count()}')
if torch.cuda.is_available():
    print(f'Device 0: {torch.cuda.get_device_name(0)}')
" 2>&1; then
        echo ""
        echo "=========================================="
        echo "  ✅ GPU setup complete!"
        echo "=========================================="
        echo ""
        echo "  ComfyUI: http://localhost:8188"
        echo ""
        echo "  To restart manually next time:"
        echo "    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d"
        echo ""
        echo "  Or add to .env:"
        echo "    COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml"
        echo "  Then just: docker compose up -d"
        echo ""
    else
        echo ""
        echo "=========================================="
        echo "  ⚠️  GPU verification failed - check logs:"
        echo "  docker logs comfy --tail 50"
        echo "=========================================="
        echo ""
        exit 1
    fi
else
    echo "--- Skipping container restart (--no-restart) ---"
    echo ""
    echo "To start the container:"
    echo "  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d"
    echo ""
    echo "Or add to .env and use plain 'docker compose up':"
    echo "  COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml"
    echo ""
fi
