#!/bin/bash
# =============================================================================
# One-liner resume script for downloading LTX-2.5 models on a RunPod pod.
#
# Run this on EVERY pod boot. It:
#   1. Downloads the latest install script + manifest from GitHub
#   2. Removes broken symlinks from previous runs
#   3. Downloads all models in the mid_vram_24gb profile with --copy --force
#      (copies real files to the network volume, not symlinks)
#   4. Skips models that already exist as real files (resumable)
#
# The serverless endpoint shuts down every 5 min, so you may need to run this
# multiple times. Each run resumes where the last left off.
#
# Usage (paste this entire block into the pod terminal):
#
#   bash <(curl -sL https://raw.githubusercontent.com/alterpeace/runpod-comfy/main/scripts/models/download_ltx25_runpod_resume.sh)
#
# Or if you already have the repo on the pod:
#
#   ./scripts/models/download_ltx25_runpod_resume.sh
#
# Environment:
#   HF_TOKEN     Required — LTX-2.5 is auto-gated on HuggingFace
#   PROFILE      Optional — defaults to "mid_vram_24gb"
#   MODELS_DIR   Optional — defaults to "/runpod-volume/models"
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
PROFILE="${PROFILE:-mid_vram_24gb}"
MODELS_DIR="${MODELS_DIR:-/runpod-volume/models}"
CUSTOM_NODES_DIR="${CUSTOM_NODES_DIR:-/comfyui/custom_nodes}"
HF_TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"

log_info "=== LTX-2.5 Model Download (Resume) ==="
log_info "Profile:      $PROFILE"
log_info "Models dir:   $MODELS_DIR"
log_info "HF token:     $([ -n "$HF_TOKEN" ] && echo 'set' || echo 'NOT SET')"

if [ -z "$HF_TOKEN" ]; then
    log_error "HF_TOKEN not set. LTX-2.5 is auto-gated."
    log_error "Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'."
    log_error "Then: export HF_TOKEN=your_token_here"
    exit 1
fi

# Ensure directories exist
mkdir -p "$MODELS_DIR" /workspace/scripts /workspace/config

# Remove old script + pycache to force fresh download
rm -f /workspace/scripts/models/download_models.py
rm -rf /workspace/scripts/__pycache__

# Always download latest scripts (overwrite old versions)
log_info "Downloading latest download_models.py..."
curl -fsSL https://raw.githubusercontent.com/alterpeace/runpod-comfy/main/scripts/models/download_models.py \
    -o /workspace/scripts/models/download_models.py
chmod +x /workspace/scripts/models/download_models.py

# Verify the downloaded script has --copy support
if ! grep -q '"--copy"' /workspace/scripts/models/download_models.py; then
    log_error "Downloaded script does not have --copy support (GitHub CDN cache?)"
    log_error "File size: $(wc -c < /workspace/scripts/models/download_models.py) bytes"
    log_error "First 5 lines:"
    head -5 /workspace/scripts/models/download_models.py
    exit 1
fi
log_success "Verified: downloaded script has --copy support"

log_info "Downloading latest ltx-2.5-models.json..."
curl -fsSL https://raw.githubusercontent.com/alterpeace/runpod-comfy/main/config/ltx-2.5-models.json \
    -o /workspace/config/ltx-2.5-models.json

# Remove broken symlinks from previous runs (symlinks pointing to deleted HF cache)
log_info "Removing broken symlinks from $MODELS_DIR..."
find "$MODELS_DIR" -type l ! -exec test -e {} \; -print -delete 2>/dev/null || true

# Activate venv for huggingface_hub
if [ -f /comfyui/venv/bin/activate ]; then
    log_info "Activating ComfyUI venv..."
    source /comfyui/venv/bin/activate
fi

# Prevent Python from using cached bytecode
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Download models with --copy (real files, not symlinks) and --force (re-download broken ones)
# The script skips files that already exist as real files (not symlinks), so this is resumable.
log_info "Starting download (copy mode, resumable)..."
python /workspace/scripts/models/download_models.py \
    --manifest /workspace/config/ltx-2.5-models.json \
    --output-dir "$MODELS_DIR" \
    --profile "$PROFILE" \
    --copy \
    --force

log_success "Download complete!"
log_info "Models are at: $MODELS_DIR"
log_info "Verify with: ls -laR $MODELS_DIR"
