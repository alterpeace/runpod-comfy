#!/bin/bash
# Install everything needed to run LTX-2.5 V2V / IC-LoRA / audio workflows:
#   1. ComfyUI-LTXVideo custom nodes (IC-LoRA guide/loader nodes, 2.5-compatible)
#   2. ComfyUI-GGUF custom nodes (for low-VRAM quantized checkpoints)
#   3. Models/LoRAs from config/ltx-2.5-models.json, per a VRAM profile
#
# Usage:
#   ./scripts/install_ltx25.sh                     # profile=mid_vram_24gb (default)
#   ./scripts/install_ltx25.sh --profile low_vram_8gb
#   ./scripts/install_ltx25.sh --profile full
#   ./scripts/install_ltx25.sh --ids checkpoint_dev_int8 distilled_lora
#   ./scripts/install_ltx25.sh --dry-run
#   ./scripts/install_ltx25.sh --skip-nodes         # models only
#   ./scripts/install_ltx25.sh --skip-models        # nodes only
#
# Environment:
#   HF_TOKEN            Required — LTX-2.5 is auto-gated on HuggingFace.
#                        Visit https://huggingface.co/Lightricks/LTX-2.5
#                        and click "Agree and Access" once.
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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PROFILE="mid_vram_24gb"
IDS=()
DRY_RUN=false
SKIP_NODES=false
SKIP_MODELS=false
FORCE=false

usage() {
    sed -n '2,20p' "$0" | sed 's/^# //; s/^#//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
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
        --list)
            python3 "$SCRIPT_DIR/download_ltx25_models.py" --manifest "$PROJECT_ROOT/config/ltx-2.5-models.json" --list
            exit 0 ;;
        -h|--help)
            usage ;;
        *)
            log_error "Unknown option: $1"; usage ;;
    esac
done

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
    log_info "=== Downloading LTX-2.5 models (profile: $PROFILE) ==="

    if [ -z "$HF_TOKEN" ] && [ -z "$HUGGING_FACE_HUB_TOKEN" ]; then
        log_warning "HF_TOKEN not set — LTX-2.5 is auto-gated and ALL official model files will be skipped."
        log_warning "Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'."
        log_warning "Get a token at https://huggingface.co/settings/tokens"
    fi

    PY_ARGS=(--manifest "$PROJECT_ROOT/config/ltx-2.5-models.json" --output-dir "$MODELS_DIR")
    if [ ${#IDS[@]} -gt 0 ]; then
        PY_ARGS+=(--ids "${IDS[@]}")
    else
        PY_ARGS+=(--profile "$PROFILE")
    fi
    [ "$DRY_RUN" = true ] && PY_ARGS+=(--dry-run)
    [ "$FORCE" = true ] && PY_ARGS+=(--force)

    python3 "$SCRIPT_DIR/download_ltx25_models.py" "${PY_ARGS[@]}"
fi

log_success "LTX-2.5 install complete."
log_info "Restart ComfyUI to pick up the new custom nodes."
log_info "Example workflows: see examples/ltx25_*.json in this repo."
log_info "LTX-2.5 ComfyUI node docs: https://github.com/Lightricks/ComfyUI-LTXVideo"
