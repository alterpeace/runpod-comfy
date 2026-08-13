# LTX-2.5 Setup Guide

## Overview

LTX-2.5 is Lightricks' latest video diffusion model (22B parameters). It
replaces the Gemma 3 text encoder with **Gemma 4**, adds **native audio
generation**, **spatial + temporal latent upscalers**, and a **duration head
patch** for variable-length generation.

This guide covers installing LTX-2.5 alongside (not replacing) LTX-2.3.

## What's New in LTX-2.5 vs LTX-2.3

| Feature | LTX-2.3 | LTX-2.5 |
|---|---|---|
| Text encoder | Gemma 3 12B (fp4 mixed) | Gemma 4 12B (bf16 or int8-convrot) |
| Text enhancer | ❌ None | ✅ Gemma 4 E2B IT (prompt rewriting) |
| Audio | Audio VAE (separate) | Native audio gen (audio VAE + pipeline) |
| Spatial upscaler | x2 (bundled) | x2 (separate file, improved) — **2.3 upscaler also works** |
| Temporal upscaler | ❌ None | ✅ x2 frame interpolation |
| Duration control | Fixed context | Duration head patch (variable) |
| Distilled LoRA | 384-step training | 450-step training |
| Quantization | GGUF Q4/Q8 | int8-convrot, NVFP4, GGUF (community) |
| Gated on HF | No | Yes (auto-gated) |
| IC-LoRAs | Deblur, decompression, etc. | Pixel-Spatial-Upscaler (new) — **2.3 IC-LoRAs also work** |
| Multishot | ❌ Single shot only | ✅ 2-4 connected shots in one generation |
| Frame count rule | Any | Must be 1 + multiple of 8 |

## Prerequisites

### 1. HuggingFace Access (LTX-2.5 is gated)

LTX-2.5 is auto-gated on HuggingFace. You must:

1. Visit https://huggingface.co/Lightricks/LTX-2.5
2. Log in with your HuggingFace account
3. Click **"Agree and Access"**
4. Generate an access token at https://huggingface.co/settings/tokens
5. Set it in your environment:
   ```bash
   export HF_TOKEN=hf_your_token_here
   ```

### 2. ComfyUI Custom Nodes

LTX-2.5 uses the same `ComfyUI-LTXVideo` custom node as 2.3 (updated version).
The install script handles this automatically.

New nodes in LTX-2.5 workflows (from official Lightricks examples):
- `LTXVSetAudioRefTokens` — freezes source audio for V2V (carries through unchanged)
- `LTXVCropGuides` — crops out IC-LoRA guide frames after sampling
- `SaveVideo` / `LoadVideo` — LTX-native video I/O (alternative to VHS)
- `PrimitiveStringMultiline` / `PrimitiveFloat` — input parameter nodes
- `PreviewAny` — preview node

## Installation

### Quick Install (all-in-one)

```bash
# Set your HF token (required — LTX-2.5 is gated)
export HF_TOKEN=hf_your_token_here

# Install custom nodes + models for 24GB GPUs (RTX 4090)
./scripts/install_ltx25.sh --profile mid_vram_24gb

# Or for 8GB GPUs (GGUF quantized)
./scripts/install_ltx25.sh --profile low_vram_8gb

# Or everything (48GB+ GPUs)
./scripts/install_ltx25.sh --profile full
```

### Models Only (skip custom nodes)

```bash
export HF_TOKEN=hf_your_token_here
./scripts/install_ltx25.sh --profile mid_vram_24gb --skip-nodes
```

### List Available Models

```bash
./scripts/install_ltx25.sh --list
# or
python3 scripts/download_ltx25_models.py --list
```

### Dry Run (see what would be downloaded)

```bash
./scripts/install_ltx25.sh --profile mid_vram_24gb --dry-run
```

### Download Specific Models Only

```bash
export HF_TOKEN=hf_your_token_here
./scripts/install_ltx25.sh --ids checkpoint_dev_int8 text_encoder_int8 distilled_lora video_vae
```

## VRAM Profiles

| Profile | VRAM | Checkpoint | Text Encoder | Includes |
|---|---|---|---|---|
| `minimal` | 24GB | int8-convrot dev | int8-convrot | checkpoint + text encoder + distilled LoRA |
| `low_vram_8gb` | 8-12GB | GGUF Q4 distilled | int8-convrot | + video VAE + audio VAE + distilled LoRA |
| `mid_vram_24gb` | 24GB | int8-convrot dev | int8-convrot | + spatial upscaler + temporal upscaler + IC-LoRA pixel upscaler |
| `full` | 48GB+ | All variants | All variants | Everything |

## Model Files

### Checkpoints (pick one per workflow)

| File | Size | VRAM | Notes |
|---|---|---|---|
| `ltx-2.5-22b-dev-transformer-bf16.safetensors` | ~44GB | 48GB+ | Full precision, highest quality |
| `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` | ~22GB | 24GB | **Recommended for RTX 4090** |
| `ltx-2.5-22b-distilled-transformer-bf16.safetensors` | ~44GB | 48GB+ | Distilled (fewer steps) |
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | ~22GB | 24GB | Distilled + quantized |
| `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` | ~11GB | 16GB+ | **Blackwell only** (sm_120+) |
| `ltx-2.5-22b-distilled-Q4_K_M.gguf` | ~11GB | 8-12GB | Community GGUF, needs ComfyUI-GGUF |

### Text Encoders (pick one)

| File | Size | Notes |
|---|---|---|
| `gemma4-12b-with-proj-ltx-2.5-bf16.safetensors` | ~24GB | Full precision |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | ~12GB | **Recommended** |

### VAEs

| File | Purpose |
|---|---|
| `ltx-2.5-video-vae-bf16.safetensors` | Video VAE (decode latents to frames) |
| `ltx-2.5-video-vae-conv-bf16.safetensors` | Conv variant (alternative architecture) |
| `ltx-2.5-audio-vae-bf16.safetensors` | Audio VAE (for native audio generation) |

### Upscalers

| File | Purpose |
|---|---|
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | 2x spatial (resolution doubling) |
| `ltx-2.5-latent-temporal-upscaler-x2-bf16-1.0.safetensors` | 2x temporal (frame interpolation) |

### LoRAs & Patches

| File | Purpose |
|---|---|
| `ltx-2.5-22b-distilled-lora-450-bf16.safetensors` | Speed-up LoRA (8-step sampling) |
| `ltx-2.5-duration-head-bf16.safetensors` | Variable duration control patch |
| `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler.safetensors` | IC-LoRA for guided upscaling |

## GPU Recommendations

| GPU | VRAM | Profile | Checkpoint | Notes |
|---|---|---|---|---|
| RTX 2060/3050 | 6-8GB | `low_vram_8gb` | GGUF Q4 | CPU offload, tiled VAE, 640×352 |
| RTX 3060/4060 | 8-12GB | `low_vram_8gb` | GGUF Q4 or Q8 | Can push to 768×448 with Q4 |
| RTX 4070 Ti/4080 | 12-16GB | `low_vram_8gb` | GGUF Q8 | Higher quality quant |
| RTX 4090/3090 | 24GB | `mid_vram_24gb` | int8-convrot | **Sweet spot** — full pipeline + upscalers |
| A100 80GB | 80GB | `full` | BF16 | Max quality, can run BF16 + audio |
| L40/L40S | 48GB | `mid_vram_24gb` or `full` | int8 or BF16 | Ada arch, FP8-native |
| B100/B200 | 80GB+ | `full` | NVFP4 or BF16 | Blackwell — NVFP4 available |

> **⚠️ SageAttention:** The hosted image compiles SageAttention with
> `TORCH_CUDA_ARCH_LIST=8.9` (Ada only). On Ampere GPUs (A6000, A40, A100),
> drop `--use-sage-attention` from `COMFYUI_ARGS`. See
> [`docs/SERVERLESS_DEPLOY.md`](SERVERLESS_DEPLOY.md) for details.

## RunPod Serverless Deployment

### Seed the Volume

```bash
# Create a spot pod for seeding
uv run python lifecycle/runpod_pods.py create \
  --name ltx25-seed \
  --gpu "RTX 4090" --spot \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --volume-id <YOUR_VOLUME_ID> \
  --env MODE=pods --env ENABLE_SSH=true

# SSH in and install
docker exec -it <pod> bash
cd /workspace
export HF_TOKEN=hf_...   # required — LTX-2.5 is gated
./scripts/install_ltx25.sh --profile mid_vram_24gb

# Terminate the seed pod
uv run python lifecycle/runpod_pods.py terminate --pod-id <seed_pod_id>
```

### Invoke with a Workflow

```bash
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id <ENDPOINT_ID> \
  --workflow examples/ltx25_animatediff_restyle_upscale_24gb.json \
  --wait --timeout 600
```

## Coexistence with LTX-2.3

LTX-2.5 and LTX-2.3 can coexist on the same volume — they use different model
files and different text encoders:

| Component | LTX-2.3 | LTX-2.5 |
|---|---|---|
| Config | `config/ltx-2.3-models.json` | `config/ltx-2.5-models.json` |
| Install script | `scripts/install_ltx23.sh` | `scripts/install_ltx25.sh` |
| Download script | `scripts/download_ltx23_models.py` | `scripts/download_ltx25_models.py` |
| Example workflows | `examples/ltx23_*.json` | `examples/ltx25_*.json` |
| Setup doc | `docs/LTX_2.3_V2V_ICLORA_SETUP.md` | `docs/LTX_2.5_SETUP.md` |
| Text encoder | `gemma_3_12B_it_fp4_mixed.safetensors` | `gemma4-12b-with-proj-ltx-2.5-*.safetensors` |
| Custom node | ComfyUI-LTXVideo (same) | ComfyUI-LTXVideo (same, updated) |

Both share the same `ComfyUI-LTXVideo` custom node — just keep it updated to
the latest version for 2.5 support.

## Troubleshooting

### "access denied for gated repo"

LTX-2.5 is auto-gated. You must:
1. Visit https://huggingface.co/Lightricks/LTX-2.5
2. Click "Agree and Access" with the account matching your HF_TOKEN
3. Retry the install

### "huggingface_hub not installed"

```bash
uv pip install 'huggingface_hub[cli,hf_transfer]'
```

### GGUF models not loading

Ensure `ComfyUI-GGUF` custom node is installed:
```bash
./scripts/install_ltx25.sh --skip-models  # nodes only
```

### Out of memory on 24GB GPU

- Use `low_vram_8gb` profile (GGUF Q4) instead of `mid_vram_24gb`
- Add `--lowvram` to `COMFYUI_ARGS`
- Reduce frame count (`frame_load_cap` in the workflow)
- Disable the spatial/temporal upscale passes

### IC-LoRA not applying

- Verify the IC-LoRA file exists in `models/loras/`
- Check `LTXICLoRALoaderModelOnly` node references the correct filename
- **LTX-2.3 IC-LoRAs ARE compatible with LTX-2.5** — confirmed by official
  Lightricks V2V workflow which uses `ltx-2.3-22b-ic-lora-instant-shave-0.9.safetensors`.
  You can reuse 2.3 IC-LoRAs (deblur, decompression, colorization, etc.) with 2.5.

## Cross-References

This implementation was cross-referenced with:

- **Official Lightricks workflows**: https://github.com/Lightricks/ComfyUI-LTXVideo/tree/master/example_workflows/2.5
  - 9 official workflows: T2V/I2V (single + two-stage), V2V IC-LoRA, T2A (text-to-audio),
    IC-LoRA ingredients/inpaint/outpaint/motion-track/union-control
  - Confirms 2.3 IC-LoRAs + spatial upscaler work with 2.5
  - Reveals text enhancer model (`gemma4_e2b_it_bf16.safetensors`)
  - Frame count must be 1 + multiple of 8
- **Kijai's model repos**: https://huggingface.co/Kijai/LTX2.3_comfy
  - Transformer-only checkpoints (fp8, int8-convrot, mxfp8, bf16)
  - VAEs, tiny VAE, OmniNFT RL LoRA
  - Kijai has not yet published LTX-2.5-specific repos (as of Aug 2026)
- **Benji's LTX-2.5 Agent Prompt Skill**: https://github.com/benjiyaya/LTX-2.5-Agent-Prompt-Skill
  - Reveals LTX-2.5 native multishot (2-4 connected shots in one generation)
  - 6-part prompt structure: shot → scene → action → character → camera → audio
  - Prompting is pure natural language (no JSON/tags)
- **Community GGUF quants**: https://huggingface.co/Abiray/LTX-2.5-Distilled-GGUF
  - Q4_K_M and Q8_0 for low-VRAM GPUs
