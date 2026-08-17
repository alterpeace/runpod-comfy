#!/bin/bash
# Install everything needed to run LTX V2V / IC-LoRA workflows:
#   1. ComfyUI-LTXVideo custom nodes (IC-LoRA guide/loader nodes)
#   2. ComfyUI-GGUF custom nodes (for low-VRAM quantized checkpoints)
#   3. Models/LoRAs from config/ltx-2.X-models.json, per a VRAM profile
#
# Supports both LTX-2.3 and LTX-2.5. Default is 2.5; pass --version 23 for 2.3.
#
# Usage:
#   ./scripts/models/install_models.sh                          # version=25, profile=mid_vram_24gb
#   ./scripts/models/install_models.sh --version 23             # version=23, profile=mid_vram_12_24gb
#   ./scripts/models/install_models.sh --version 25 --profile low_vram_8gb
#   ./scripts/models/install_models.sh --version 25 --profile full
#   ./scripts/models/install_models.sh --version 25 --ids checkpoint_dev_int8 distilled_lora
#   ./scripts/models/install_models.sh --dry-run
#   ./scripts/models/install_models.sh --skip-nodes             # models only
#   ./scripts/models/install_models.sh --skip-models            # nodes only
#   ./scripts/models/install_models.sh --copy                   # copy instead of symlink (for network volumes)
#
# Environment:
#   HF_TOKEN            Required for gated repos. LTX-2.5 is auto-gated on HuggingFace.
#                        Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access' once.
#                        Get a token at https://huggingface.co/settings/tokens
#   CUSTOM_NODES_DIR     Override custom_nodes location (default: auto-detect)
#   MODELS_DIR           Override models/ location (default: auto-detect)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

VERSION="25"
PROFILE=""
IDS=()
DRY_RUN=false
SKIP_NODES=false
SKIP_MODELS=false
FORCE=false
COPY_MODE=false

usage() {
    sed -n '2,24p' "$0" | sed 's/^# //; s/^#//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"; shift 2 ;;
        --profile)
            PROFILE="$2"; shift 2 ;;
        --ids)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do IDS+=("$1"); shift; done ;;
        --dry-run)
            DRY_RUN=true; shift ;;
        --skip-nodes)
            SKIP_NODES=true; shift ;;
        --skip-models)
            SKIP_MODELS=true; shift ;;
        --force)
            FORCE=true; shift ;;
        --copy)
            COPY_MODE=true; shift ;;
        --list)
            python3 "$SCRIPT_DIR/download_models.py" --version "$VERSION" --list
            exit 0 ;;
        -h|--help)
            usage ;;
        *)
            log_error "Unknown option: $1"; usage ;;
    esac
done

# Set version-specific defaults
MANIFEST_FILE="config/ltx-${VERSION}.0-models.json"
if [ "$VERSION" = "23" ]; then
    MANIFEST_FILE="config/ltx-2.3-models.json"
    : "${PROFILE:=mid_vram_12_24gb}"
else
    MANIFEST_FILE="config/ltx-2.5-models.json"
    : "${PROFILE:=mid_vram_24gb}"
fi

# Auto-detect if we need copy mode: if MODELS_DIR is on a different filesystem
# than the HF cache (default: ~/.cache/huggingface), use --copy so files persist
# on the target volume. This is essential for RunPod network volumes.
if [ "$COPY_MODE" = false ] && [ -n "$MODELS_DIR" ]; then
    HF_CACHE_DIR="${HF_HOME:-$HOME/.cache/huggingface}"
    if [ -d "$MODELS_DIR" ] && [ -d "$(dirname "$HF_CACHE_DIR")" ]; then
        MODELS_DEV=$(stat -c %d "$MODELS_DIR" 2>/dev/null || echo "")
        CACHE_DEV=$(stat -c %d "$(dirname "$HF_CACHE_DIR")" 2>/dev/null || echo "")
        if [ -n "$MODELS_DEV" ] && [ -n "$CACHE_DEV" ] && [ "$MODELS_DEV" != "$CACHE_DEV" ]; then
            log_info "Models dir and HF cache are on different filesystems — using copy mode"
            COPY_MODE=true
        fi
    fi
fi

# ----------------------------------------------------------------------------
# Locate custom_nodes/ and models/ (Docker container vs local dev checkout)
# ----------------------------------------------------------------------------
find_dir() {
    local name="$1"
    local override_var="$2"
    if [ -n "${!override_var}" ] && [ -d "${!override_var}" ]; then
        echo "${!override_var}"; return
    fi
    if [ -d "/comfyui/${name}" ]; then
        echo "/comfyui/${name}"; return
    fi
    if [ -d "$HOME/comfy/${name}" ]; then
        echo "$HOME/comfy/${name}"; return
    fi
    if [ -d "$PROJECT_ROOT/../${name}" ]; then
        echo "$(cd "$PROJECT_ROOT/../${name}" && pwd)"; return
    fi
    if [ -d "$PROJECT_ROOT/${name}" ]; then
        echo "$(cd "$PROJECT_ROOT/${name}" && pwd)"; return
    fi
    echo ""
}

CUSTOM_NODES_DIR="$(find_dir custom_nodes CUSTOM_NODES_DIR)"
MODELS_DIR="$(find_dir models MODELS_DIR)"

if [ -z "$CUSTOM_NODES_DIR" ] && [ "$SKIP_NODES" = false ]; then
    log_error "Could not find custom_nodes directory. Set CUSTOM_NODES_DIR=/path/to/custom_nodes"
    exit 1
fi
if [ -z "$MODELS_DIR" ] && [ "$SKIP_MODELS" = false ]; then
    log_error "Could not find models directory. Set MODELS_DIR=/path/to/models"
    exit 1
fi

log_info "LTX version:      $VERSION"
log_info "Profile:          $PROFILE"
log_info "Custom nodes dir: ${CUSTOM_NODES_DIR:-<skipped>}"
log_info "Models dir:       ${MODELS_DIR:-<skipped>}"
[ "$DRY_RUN" = true ] && log_warning "DRY RUN - nothing will actually be installed/downloaded"

# ----------------------------------------------------------------------------
# 1. Custom nodes
# ----------------------------------------------------------------------------
if [ "$SKIP_NODES" = false ]; then
    log_info "=== Installing custom nodes ==="

    VENV_ACTIVATE=""
    if [ -f "/comfyui/venv/bin/activate" ]; then
        VENV_ACTIVATE="/comfyui/venv/bin/activate"
    elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
        VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"
    fi
    if [ -n "$VENV_ACTIVATE" ]; then
        log_info "Activating venv: $VENV_ACTIVATE"
        # shellcheck disable=SC1090
        source "$VENV_ACTIVATE"
    else
        log_warning "No venv found - installing requirements.txt into current Python environment"
    fi

    declare -A NODE_REPOS=(
        ["ComfyUI-LTXVideo"]="https://github.com/Lightricks/ComfyUI-LTXVideo.git"
        ["ComfyUI-GGUF"]="https://github.com/city96/ComfyUI-GGUF.git"
    )

    for name in "${!NODE_REPOS[@]}"; do
        repo="${NODE_REPOS[$name]}"
        target="${CUSTOM_NODES_DIR}/${name}"

        if [ "$DRY_RUN" = true ]; then
            log_info "[dry-run] would clone/update ${name} at ${target}"
            continue
        fi

        if [ -d "$target/.git" ]; then
            log_info "${name} already present, pulling latest..."
            git -C "$target" pull --ff-only || log_warning "${name}: pull failed, leaving as-is"
        else
            log_info "Cloning ${name}..."
            git clone --depth 1 "$repo" "$target"
        fi

        if [ -f "${target}/requirements.txt" ]; then
            log_info "Installing requirements for ${name}..."
            if command -v uv &>/dev/null; then
                uv pip install -r "${target}/requirements.txt"
            else
                pip install -r "${target}/requirements.txt"
            fi
        fi
        log_success "${name} ready"
    done
fi

# ----------------------------------------------------------------------------
# 2. Models
# ----------------------------------------------------------------------------
if [ "$SKIP_MODELS" = false ]; then
    log_info "=== Downloading LTX-${VERSION} models (profile: $PROFILE) ==="

    if [ -z "$HF_TOKEN" ] && [ -z "$HUGGING_FACE_HUB_TOKEN" ]; then
        if [ "$VERSION" = "25" ]; then
            log_warning "HF_TOKEN not set — LTX-2.5 is auto-gated and ALL official model files will be skipped."
            log_warning "Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'."
            log_warning "Get a token at https://huggingface.co/settings/tokens"
        else
            log_warning "HF_TOKEN not set - gated IC-LoRA repos (most Lightricks IC-LoRAs) will be skipped."
            log_warning "Get a token at https://huggingface.co/settings/tokens and 'Agree and Access' each gated repo first."
        fi
    fi

    PY_ARGS=(--manifest "$PROJECT_ROOT/$MANIFEST_FILE" --output-dir "$MODELS_DIR")
    if [ ${#IDS[@]} -gt 0 ]; then
        PY_ARGS+=(--ids "${IDS[@]}")
    else
        PY_ARGS+=(--profile "$PROFILE")
    fi
    [ "$DRY_RUN" = true ] && PY_ARGS+=(--dry-run)
    [ "$FORCE" = true ] && PY_ARGS+=(--force)
    [ "$COPY_MODE" = true ] && PY_ARGS+=(--copy)

    python3 "$SCRIPT_DIR/download_models.py" "${PY_ARGS[@]}"
fi

log_success "LTX-${VERSION} install complete."
log_info "Restart ComfyUI to pick up the new custom nodes."
if [ "$VERSION" = "25" ]; then
    log_info "Example workflows: see examples/ltx25_*.json in this repo."
    log_info "LTX-2.5 ComfyUI node docs: https://github.com/Lightricks/ComfyUI-LTXVideo"
else
    log_info "Example workflows: https://github.com/Lightricks/ComfyUI-LTXVideo/tree/master/example_workflows/2.3"
fi
