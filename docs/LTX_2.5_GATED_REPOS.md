# LTX-2.5 Gated Repositories — Required Access

## The Problem

LTX-2.5 model files are split across **multiple gated repositories** on
HuggingFace. Each repo requires separate "Agree and Access" acceptance.
Missing access on any one repo causes silent download failures — the download
script exits with code 1 and no useful error message.

This has been the primary blocker for serverless deployment: the tokenizer
directory files live in a different repo from the model weights, and that repo
wasn't accepted.

## Required Repositories (you MUST accept access on ALL of these)

### 1. `Lightricks/LTX-2.5` (main weights)

**URL**: https://huggingface.co/Lightricks/LTX-2.5

**Contains**:
- `diffusion_models/ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` (checkpoint)
- `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` (text encoder weights)
- `vae/ltx-2.5-video-vae-bf16.safetensors` (video VAE)
- `vae/ltx-2.5-audio-vae-bf16.safetensors` (audio VAE)
- `loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors` (distilled LoRA)
- `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors`
- `latent_upscale_models/ltx-2.5-latent-temporal-upscaler-x2-bf16-1.0.safetensors`

**Does NOT contain**: tokenizer/config directory files

### 2. `Lightricks/LTX-2.5-Pre-Trained` (tokenizer + config files)

**URL**: https://huggingface.co/Lightricks/LTX-2.5-Pre-Trained

**Contains** (under `ltx-2.5-22b-gemma4-12b/`):
- `config.json` — model architecture config
- `tokenizer_config.json` — tokenizer settings
- `tokenizer.json` (32 MB) — HuggingFace fast tokenizer data
- `chat_template.jinja` — prompt formatting template
- `generation_config.json` — generation parameters
- `processor_config.json` — processor settings
- `model.safetensors` (23.9 GB) — full BF16 weights (NOT needed if using int8)

**CRITICAL**: The `LTXVGemmaCLIPModelLoader` node requires a directory with
`config.json` + `tokenizer.json` to load the text encoder. Without these files,
you get:
```
FileNotFoundError: No config.json found for the selected Gemma model
```

### 3. `Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler` (IC-LoRA)

**URL**: https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler

**Contains**:
- `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors`

### 4. `Comfy-Org/gemma-4` (text enhancer, NOT gated)

**URL**: https://huggingface.co/Comfy-Org/gemma-4

**Contains**:
- `text_encoders/gemma4_e2b_it_bf16.safetensors` (text enhancer/prompt rewriter)

This one is NOT gated — no access acceptance needed.

## How to Accept Access

1. Log in to HuggingFace with the account that owns your `HF_TOKEN`
2. Visit each gated repo URL above
3. Click "Agree and Access" on each one
4. Wait ~1 minute for access to propagate

## Common Failure Modes

### "Value not in list" for gemma_path
```
gemma_path: 'gemma4-12b-ltx-2.5/model.safetensors' not in [...]
```
**Cause**: The `gemma4-12b-ltx-2.5/` directory doesn't exist on the volume.
ComfyUI only sees flat files.

**Fix**: Download the tokenizer files from `LTX-2.5-Pre-Trained` to create the
directory on the volume, then restart the worker so the entrypoint symlinks it.

### "No config.json found for the selected Gemma model"
```
FileNotFoundError: No config.json found for the selected Gemma model
(/comfyui/models/text_encoders). Ensure the model's config, tokenizer and
processor files are present.
```
**Cause**: Same as above — the directory exists but is missing `config.json`
and/or `tokenizer.json`.

**Fix**: Ensure ALL files from `LTX-2.5-Pre-Trained/ltx-2.5-22b-gemma4-12b/`
are downloaded to `text_encoders/gemma4-12b-ltx-2.5/` on the volume.

### Silent download failure (exit code 1, empty stderr)
**Cause**: `huggingface_hub` raises `GatedRepoError` which the download script
catches and prints `[FAIL]` to stdout. But the handler only reports stderr on
failure, making it look silent.

**Fix**: Accept access on the gated repo. Check which repo the failing model
ID belongs to in `config/ltx-2.5-models.json`.

## Directory Layout on RunPod Volume

After all downloads complete, `/runpod-volume/models/text_encoders/` should have:
```
text_encoders/
├── gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors  (15.4 GB)
├── gemma4_e2b_it_bf16.safetensors  (text enhancer)
└── gemma4-12b-ltx-2.5/
    ├── config.json
    ├── tokenizer_config.json
    ├── tokenizer.json  (32 MB)
    ├── chat_template.jinja
    ├── generation_config.json
    ├── processor_config.json
    └── model.safetensors -> ../gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors
```

The `model.safetensors` symlink points back to the int8 weights file so
`LTXVGemmaCLIPModelLoader` can find both the tokenizer AND weights from the
directory path `gemma4-12b-ltx-2.5/model.safetensors`.

## Verifying Access Works

```bash
# Test with HF CLI
huggingface-cli download Lightricks/LTX-2.5-Pre-Trained \
  ltx-2.5-22b-gemma4-12b/config.json --token $HF_TOKEN

# Or via the serverless endpoint (after image rebuild)
curl -X POST "https://api.runpod.ai/v2/$ENDPOINT_ID/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"action": "download_models", "manifest": "ltx-2.5", "ids": ["text_encoder_tokenizer"], "dry_run": true, "hf_token": "'$HF_TOKEN'"}}'
```
