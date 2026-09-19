#!/bin/bash
# =============================================================================
# ensure_models.sh — idempotent model sync for the ltx25 48GB build.
#
# Runs ON THE POD (ssh ltx25 'bash -s' < scripts/skypilot/ensure_models.sh).
# Called automatically by scripts/skypilot/retake_loop_batch.sh after SSH is
# up; safe to re-run any time — present files are skipped, partials resume.
#
# Model list = scripts/skypilot/ltx25-48gb.yaml setup (dev int8 build) PLUS
# the retake48_loop additions the launch yaml deliberately skips:
#   - ltx-2.5-22b-distilled-transformer-comfy-int8-convrot (checkpoints)
#   - ltx-2.5-audio-vae-bf16                               (vae)
#   - gemma4_e2b_it_int8_convrot (Comfy-Org/gemma-4)       (text_encoders)
#
# Flat-path guard: hf --local-dir nests repo subfolders under the target dir
# (text_encoders/text_encoders/...). The volume keeps FLAT files — a nested
# 15GB duplicate of the 12B encoder once blew the 100GB volume quota
# ("Disk quota exceeded", 2026-09-19). So: only fetch when the flat
# destination is missing, then flatten nested safetensors.
# =============================================================================
set -euo pipefail

MODELS="${COMFYUI_MODELS:-/opt/ComfyUI/models}"

# Guard: models dir MUST be the network-volume symlink, never container disk
# (container disk is capped at 40GB — a 22GB download there is lost on `sky down`).
if [ "$(readlink -f "$MODELS")" != "/workspace/models" ]; then
  echo "ERROR: $MODELS does not resolve to /workspace/models (setup not finished? volume not mounted?)"
  exit 1
fi

: "${HF_TOKEN:?"HF_TOKEN required (gated Lightricks/LTX-2.5)"}"
export HF_XET_HIGH_PERFORMANCE=1   # hf_transfer is deprecated/unused in huggingface_hub >= 1.x

# Non-interactive ssh has no venv on PATH — activate ComfyUI's venv explicitly
# shellcheck disable=SC1091
source /opt/venv/bin/activate

ensure() {  # ensure <repo> <repo_file> <category_dir>
  local dest="$3/$(basename "$2")"
  if [ -f "$dest" ]; then
    echo "present: $dest"
    return 0
  fi
  hf download "$1" "$2" --local-dir "$3"
  find "$3" -mindepth 2 -type f -name "*.safetensors" -exec mv -n {} "$3/" \;
}

mkdir -p "$MODELS"/{checkpoints,text_encoders,vae,loras,latent_upscale_models,SEEDVR2}

# --- 48GB redetail build (from scripts/skypilot/ltx25-48gb.yaml setup) -------
ensure Lightricks/LTX-2.5 \
  text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors \
  "$MODELS/text_encoders"

# --- Text encoder tokenizer files (nested dir is INTENTIONAL for CLIPLoader /
#     LTXVGemmaCLIPModelLoader directory format — not flattened) ---
if [ ! -f "$MODELS/text_encoders/gemma4-12b-ltx-2.5/tokenizer.json" ]; then
  hf download Lightricks/LTX-2.5-Pre-Trained \
    ltx-2.5-22b-gemma4-12b/config.json \
    ltx-2.5-22b-gemma4-12b/tokenizer_config.json \
    ltx-2.5-22b-gemma4-12b/tokenizer.json \
    ltx-2.5-22b-gemma4-12b/chat_template.jinja \
    ltx-2.5-22b-gemma4-12b/generation_config.json \
    ltx-2.5-22b-gemma4-12b/processor_config.json \
    --local-dir "$MODELS/text_encoders/gemma4-12b-ltx-2.5"
  ln -sf ../gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors \
    "$MODELS/text_encoders/gemma4-12b-ltx-2.5/model.safetensors"
else
  echo "present: text_encoders/gemma4-12b-ltx-2.5/ (tokenizer set)"
fi

ensure Lightricks/LTX-2.5 \
  diffusion_models/ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors \
  "$MODELS/checkpoints"

ensure Lightricks/LTX-2.5 \
  vae/ltx-2.5-video-vae-bf16.safetensors \
  "$MODELS/vae"

ensure Lightricks/LTX-2.5 \
  loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors \
  "$MODELS/loras"

ensure Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler \
  ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors \
  "$MODELS/loras"

ensure Lightricks/LTX-2.5 \
  latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors \
  "$MODELS/latent_upscale_models"

ensure numz/SeedVR2_comfyUI \
  seedvr2_ema_3b_fp16.safetensors \
  "$MODELS/SEEDVR2"
ensure numz/SeedVR2_comfyUI \
  ema_vae_fp16.safetensors \
  "$MODELS/SEEDVR2"

# --- retake48_loop additions (ltx25_v2v_retake48_loop_runpod.json) -----------
ensure Lightricks/LTX-2.5 \
  diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors \
  "$MODELS/checkpoints"

ensure Lightricks/LTX-2.5 \
  vae/ltx-2.5-audio-vae-bf16.safetensors \
  "$MODELS/vae"

ensure Comfy-Org/gemma-4 \
  text_encoders/gemma4_e2b_it_int8_convrot.safetensors \
  "$MODELS/text_encoders"

echo "=== Model set complete ==="
df -h /workspace | tail -1
