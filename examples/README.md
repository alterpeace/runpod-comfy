# Example ComfyUI Workflows

This directory contains sample ComfyUI workflow JSON files for testing the RunPod serverless handler.

## Available Workflows

### text_to_image_simple.json

A basic text-to-image workflow using Stable Diffusion XL.

**Features:**
- Simple KSampler workflow
- 512x512 output resolution
- 20 steps with euler sampler
- Positive and negative prompts

**Usage:**
```python
import json

with open('examples/text_to_image_simple.json') as f:
    workflow = json.load(f)

job_input = {
    'workflow': workflow
}
```

### image_to_image.json

An image-to-image transformation workflow.

**Features:**
- Loads an input image
- Applies style transfer with 75% denoise
- Uses VAE encoding/decoding
- Requires input image upload

**Usage:**
```python
import json
import base64

with open('examples/image_to_image.json') as f:
    workflow = json.load(f)

# Load and encode input image
with open('input.png', 'rb') as img:
    image_data = base64.b64encode(img.read()).decode('utf-8')

job_input = {
    'workflow': workflow,
    'input_images': {
        'input_image.png': image_data
    }
}
```

## Customizing Workflows

You can modify these workflows to:
- Change model checkpoints (`ckpt_name`)
- Adjust generation parameters (steps, cfg, seed)
- Modify prompts (positive/negative text)
- Change output resolution (width/height)
- Adjust denoise strength for img2img

## Testing Locally

Use these workflows with the test scripts:

```bash
# Test with local container
./test_local.sh examples/text_to_image_simple.json

# Test with RunPod endpoint
python test_runpod.py --workflow examples/text_to_image_simple.json
```

### ltx23_v2v_music_visuals_patch.json / ltx23_v2v_music_visuals_patch_ui.json

An LTX-2.3 video-to-video workflow for fixing bad AnimateDiff renders and
adding style to music video footage. Designed for abstract/music visual
content (no lip-sync or characters).

**Features:**
- Two-pass V2V pipeline: 640×352 → 1280×720 (8-step + 3-step)
- IC-LoRA stack: `distilled_lora` + `iclora_decompression` + `omninft_rl_lora`
- `euler` sampler with `linear_quadratic` scheduler (fast tier)
- Tiled VAE decode to prevent edge artifacts
- API format for RunPod serverless, UI format for ComfyUI web interface

**Usage:**
```bash
# Download required models
python scripts/download_ltx23_models.py --ids \
  checkpoint_fp8 distilled_lora \
  iclora_decompression omninft_rl_lora \
  spatial_upscaler

# Test locally
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh \
  examples/ltx23_v2v_music_visuals_patch.json
```

See [`ltx23_v2v_music_visuals_patch_README.md`](ltx23_v2v_music_visuals_patch_README.md)
for full parameter guide, LoRA swap table, and troubleshooting.

### ltx23_v2v_iclora_detail_{8gb,24gb}.json

Two V2V IC-LoRA detailer workflows for re-detailing and upscaling video using
LTX-2.3 IC-LoRA conditioning. The 24GB variant adds a spatial latent upscale
pass for higher resolution output.

**Features:**
- IC-LoRA stack: `distilled_lora` (speed, 24GB only) +
  `iclora_decompression` (artifact removal, 24GB only) +
  `omninft_rl_lora` (quality boost, strength 2.0)
- Two-pass pipeline (24GB): 768×432 → 1536×864 via `LTXVLatentUpsampler` ×2
  with `ManualSigmas` `0.85, 0.725, 0.4219, 0.0` (official Lightricks Pass 2)
- Single-pass (8GB): 512×288 GGUF Q4, CPU text encoder offload, 2×2 tiled VAE
- `euler` sampler with `linear_quadratic` scheduler, 8 steps, cfg 1.0
- Tiled VAE decode to manage VRAM (1×1 on 24GB, 2×2 on 8GB)
- API format for RunPod serverless / programmatic use

| Workflow | GPU | Loader | Base res | Frames | Pass 2 | Output |
|---|---|---|---|---|---|---|
| `ltx23_v2v_iclora_detail_8gb.json` | 8GB local | `UnetLoaderGGUF` Q4 | 512×288 | 97 (~4s) | No | 512×288 |
| `ltx23_v2v_iclora_detail_upscale_24gb.json` | 24GB cloud | `CheckpointLoaderSimple` | 768×432 | 193 (~8s) | Yes | 1536×864 |

**Usage:**
```bash
# Download required models (8GB)
python scripts/download_ltx23_models.py --ids \
  gguf_distilled_q4 text_encoder video_vae \
  omninft_rl_lora

# Download required models (24GB)
python scripts/download_ltx23_models.py --ids \
  checkpoint_fp8 distilled_lora \
  iclora_decompression omninft_rl_lora \
  spatial_upscaler

# Test locally
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh \
  examples/ltx23_v2v_iclora_detail_8gb.json
```

### ltx23_v2v_animatediff_cleanup_{8gb,24gb}.json / _ui.json

V2V cleanup workflows for re-detailing ~15-second AnimateDiff renders
(24fps, 1080p source): remove undescribable detail, fix blur, smooth
jittery motion. Every post-LTX stage is **bypassable** for testing at
any output resolution.

**Features:**
- IC-LoRA stack: `iclora_deblur` (blur fix) + `iclora_decompression`
  (24GB only, artifact removal) + `omninft_rl_lora` (quality boost)
- Two-pass pipeline (24GB): 768×432 → 1536×864 via `LTXVLatentUpsampler`
- Single-pass (8GB): 512×288 GGUF Q4, CPU text encoder offload
- SeedVR2 (ByteDance) diffusion-based video super-resolution with built-in
  color correction (`lab` mode) and temporal overlap blending
- Bypassable stages: SeedVR2 upscale, Pass 2 latent upscale (24GB)
- Output modes: preview / default / 1080p / 4K (24GB) — all @ 24fps
- API format for RunPod serverless, UI format for ComfyUI web interface

**Also includes:**
- [`ltx23_v2v_animatediff_retake_24gb.json`](ltx23_v2v_animatediff_retake_24gb.json) —
  Section-repair workflow using KJNodes' `LTXVAudioVideoMask` to regenerate
  specific frame ranges while leaving the rest untouched

**Usage:**
```bash
# Download required models (8GB)
python scripts/download_ltx23_models.py --ids \
  gguf_distilled_q4 text_encoder video_vae \
  iclora_deblur omninft_rl_lora

# Download required models (24GB)
python scripts/download_ltx23_models.py --ids \
  checkpoint_fp8 distilled_lora \
  iclora_deblur iclora_decompression omninft_rl_lora \
  spatial_upscaler

# Test locally
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh \
  examples/ltx23_v2v_animatediff_cleanup_8gb.json
```

See [`ltx23_v2v_animatediff_cleanup_README.md`](ltx23_v2v_animatediff_cleanup_README.md)
for full mode tables, stage-toggle JSON patches, HF gating steps, VRAM
fallbacks, SeedVR2 color correction guide, ReTake section-repair guide,
and cost estimates.

## Creating Custom Workflows

1. Design your workflow in ComfyUI WebUI
2. Export the workflow as JSON (Save API Format)
3. Place the JSON file in this directory
4. Test with the provided scripts

**Note:** Make sure any referenced models or custom nodes are available in your deployment.
