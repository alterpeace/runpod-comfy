# Plan: LTX-2.5 Side-by-Side with LTX-2.3

## Goal

Add LTX-2.5 support alongside the existing LTX-2.3 setup — new config, scripts,
example workflows, and docs — without modifying any existing 2.3 files.

## LTX-2.5 vs LTX-2.3 — Key Differences

| Feature | LTX-2.3 | LTX-2.5 |
|---|---|---|
| Architecture | 22B DiT | 22B DiT (revised) |
| Text encoder | Gemma 3 12B (fp4 mixed) | Gemma 4 12B (bf16 or int8-convrot) |
| Audio | Audio VAE (separate) | Native audio gen (audio VAE + audio pipeline) |
| Upscalers | Spatial x2 only | Spatial x2 + Temporal x2 |
| Duration control | Fixed | Duration head patch (model_patches/) |
| Quantization | GGUF Q4/Q8 (unsloth) | int8-convrot, nvfp4, GGUF (community) |
| Distilled LoRA | 384 steps | 450 steps |
| Gated | No | Yes (auto-gated on HF) |
| IC-LoRAs | Deblur, decompression, etc. | Pixel-Spatial-Upscaler (new), 2.3 IC-LoRAs may not be compatible |

## LTX-2.5 Model Files (from HuggingFace `Lightricks/LTX-2.5`)

### Diffusion models (pick one)
- `diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors` — full BF16 (~44GB)
- `diffusion_models/ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` — int8 (~22GB)
- `diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors` — distilled BF16
- `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` — distilled int8
- `diffusion_models/ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` — NVFP4 (Blackwell only)

### Text encoder (pick one)
- `text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors` — full BF16
- `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` — int8

### VAEs
- `vae/ltx-2.5-video-vae-bf16.safetensors` — video VAE
- `vae/ltx-2.5-video-vae-conv-bf16.safetensors` — conv variant
- `vae/ltx-2.5-audio-vae-bf16.safetensors` — audio VAE

### Upscalers
- `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors`
- `latent_upscale_models/ltx-2.5-latent-temporal-upscaler-x2-bf16-1.0.safetensors`

### LoRAs
- `loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors`

### Patches
- `model_patches/ltx-2.5-duration-head-bf16.safetensors`

### IC-LoRA (separate repo)
- `Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler` — pixel spatial upscaler IC-LoRA

### Community GGUF
- `Abiray/LTX-2.5-Distilled-GGUF` — distilled GGUF
- `realrebelai/LTX-2.5_GGUFs` — various GGUF quants

## VRAM Profiles

| Profile | VRAM | Checkpoint | Text Encoder | Notes |
|---|---|---|---|---|
| `low_vram_8gb` | 8-12GB | GGUF Q4 (community) | int8-convrot | CPU offload, tiled VAE |
| `mid_vram_24gb` | 24GB | int8-convrot | int8-convrot | RTX 4090 sweet spot |
| `full` | 48GB+ | BF16 | BF16 | A100/L40, full quality |

## Files to Create

### 1. `config/ltx-2.5-models.json`
Model manifest with all LTX-2.5 files, VRAM profiles, gated flags.

### 2. `scripts/download_ltx25_models.py`
Copy of `download_ltx23_models.py` pointing at `ltx-2.5-models.json`.

### 3. `scripts/install_ltx25.sh`
Copy of `install_ltx23.sh` calling `download_ltx25_models.py`.
Installs ComfyUI-LTXVideo (same custom node, updated for 2.5).

### 4. Example workflows
Based on existing 2.3 examples, adapted for 2.5 node names and model files:
- `examples/ltx25_text_to_video.json` — simple T2V (API format)
- `examples/ltx25_text_to_video_ui.json` — same, UI graph format
- `examples/ltx25_v2v_redetail_24gb.json` — V2V with IC-LoRA (24GB, API)
- `examples/ltx25_v2v_redetail_24gb_ui.json` — same, UI format
- `examples/ltx25_v2v_redetail_8gb.json` — V2V with GGUF (8GB, API)
- `examples/ltx25_v2v_redetail_8gb_ui.json` — same, UI format
- `examples/ltx25_music_visuals_24gb.json` — music visuals with audio-reactive
- `examples/ltx25_README.md` — workflow descriptions

### 5. `docs/LTX_2.5_SETUP.md`
Setup guide: model download, VRAM profiles, ComfyUI node requirements,
gated repo access, differences from 2.3.

### 6. Doc updates (additive only)
- `examples/README.md` — add LTX-2.5 section
- `docs/SERVERLESS_DEPLOY.md` — mention LTX-2.5 as an option in the GPU table

## ComfyUI Node Compatibility

LTX-2.5 uses the same `ComfyUI-LTXVideo` custom node as 2.3 (updated version).
Key node changes:
- `CheckpointLoaderSimple` → loads `.safetensors` from `diffusion_models/`
- `CLIPLoader` with `type: "ltx"` → loads Gemma 4 text encoder
- `LTXICLoRALoaderModelOnly` → same node, new 2.5 IC-LoRAs
- New: duration head patch loader
- New: temporal upscaler node
- New: audio pipeline nodes (audio VAE, audio sampler)

## Gated Access

`Lightricks/LTX-2.5` is auto-gated. Users must:
1. Visit https://huggingface.co/Lightricks/LTX-2.5
2. Click "Agree and Access"
3. Set `HF_TOKEN` in environment

## Execution Order

1. Create `config/ltx-2.5-models.json`
2. Create `scripts/download_ltx25_models.py`
3. Create `scripts/install_ltx25.sh`
4. Create example workflows (start with T2V, then V2V, then music visuals)
5. Create `docs/LTX_2.5_SETUP.md`
6. Update `examples/README.md` and `docs/SERVERLESS_DEPLOY.md`
7. Test syntax of all JSON/Python/Bash files
8. Git commit and push
