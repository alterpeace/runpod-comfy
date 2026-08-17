# LTX-2.5 Example Workflows

## Overview

These workflows use **LTX-2.5** (Lightricks' latest video diffusion model, 22B
parameters) for text-to-video, video-to-video restyling, and creative
upscaling pipelines. LTX-2.5 brings native audio generation, Gemma 4 text
encoder, spatial + temporal latent upscalers, and a duration head patch.

> **LTX-2.3 workflows** are in the parent directory (`ltx23_*.json`). LTX-2.5
> and 2.3 can coexist — they use different model files and text encoders.

## Prerequisites

- **ComfyUI-LTXVideo** custom node (same as 2.3, updated for 2.5)
- **ComfyUI-GGUF** custom node (only for `*_8gb.json` workflows)
- **ComfyUI-VideoHelperSuite** (VHS) for video load/save nodes
- **LTX-2.5 models** — run `./scripts/models/install_ltx25.sh --profile mid_vram_24gb`
- **HF_TOKEN** — LTX-2.5 is auto-gated on HuggingFace. Visit
  https://huggingface.co/Lightricks/LTX-2.5 and click "Agree and Access".

See [`docs/LTX_2.5_SETUP.md`](../docs/LTX_2.5_SETUP.md) for full setup.

## Workflow Reference

### `ltx25_text_to_video.json` — Text-to-Video (API format)

| Field | Value |
|---|---|
| **Purpose** | Generate video from a text prompt (no input footage) |
| **VRAM** | ~24GB (int8-convrot checkpoint + int8 text encoder) |
| **Resolution** | 768×448, 97 frames (~4s @ 24fps) |
| **Steps** | 8 (distilled LoRA) |
| **Use case** | RunPod serverless / programmatic API calls |
| **Format** | API (flat dict, `input.workflow`) |

**Pipeline:** Text prompt → Gemma 4 encoder → LTX-2.5 int8 checkpoint + distilled LoRA → KSampler (8 steps, euler) → tiled VAE decode → H.264 MP4

---

### `ltx25_v2v_redetail_24gb.json` — V2V Redetail (API, 24GB)

| Field | Value |
|---|---|
| **Purpose** | Re-detail and enhance an input video using IC-LoRA pixel upscaler |
| **VRAM** | ~24GB (int8-convrot checkpoint + int8 text encoder) |
| **Input** | Any video (downscaled to 768×448) |
| **Output** | 768×448 → 1536×896 (2x latent spatial upscale) |
| **Steps** | 8 (first pass) + 4 (refinement pass) |
| **Use case** | RunPod serverless / programmatic API calls |
| **Format** | API (flat dict, `input.workflow`) |

**Pipeline:** Load video → downscale to 768×448 → LTX-2.5 int8 + distilled LoRA + IC-LoRA pixel upscaler → KSampler (8 steps, denoise 1.0) → latent spatial upscale (x2) → refinement KSampler (4 steps) → tiled VAE decode → H.264 MP4

---

### `ltx25_v2v_redetail_8gb.json` — V2V Redetail (API, 8GB GGUF)

| Field | Value |
|---|---|
| **Purpose** | Same as 24GB version but for low-VRAM GPUs using GGUF Q4 quantization |
| **VRAM** | ~8-12GB (GGUF Q4 distilled + int8 text encoder, CPU offload) |
| **Input** | Any video (downscaled to 640×352, 193 frames max) |
| **Output** | 640×352 (no upscale pass — VRAM too tight) |
| **Steps** | 8 (distilled) |
| **Use case** | Local 8GB GPUs, RunPod A4000 |
| **Format** | API (flat dict, `input.workflow`) |

**Pipeline:** Load video → downscale to 640×352 → UnetLoaderGGUF (Q4) + distilled LoRA → KSampler (8 steps) → tiled VAE decode → H.264 MP4

**Differences from 24GB:**
- Uses `UnetLoaderGGUF` instead of `CheckpointLoaderSimple`
- Separate `VAELoader` (GGUF checkpoints don't bundle the VAE)
- No spatial/temporal upscale (VRAM constraint)
- Fewer frames (193 vs 385) and smaller resolution (640×352 vs 768×448)

---

### `ltx25_animatediff_restyle_upscale_24gb.json` — Creative Restyle + Upscale (API, 24GB)

| Field | Value |
|---|---|
| **Purpose** | Take any input video, creatively restyle it with LTX-2.5, then spatially AND temporally upscale |
| **VRAM** | ~24GB (int8-convrot checkpoint + int8 text encoder) |
| **Input** | Any video (downscaled to 768×448, 385 frames / ~16s @ 24fps) |
| **Output** | 1536×896 @ 48fps (2x spatial + 2x temporal = 770 frames) |
| **Steps** | 8 (restyle) + 4 (spatial refine) + 3 (temporal refine) |
| **Use case** | Creative video restyling, AnimateDiff enhancement, music video post-production |
| **Format** | API (flat dict, `input.workflow`) |

**Pipeline (3-pass):**

1. **Restyle pass** — Load video → downscale to 768×448 → LTX-2.5 int8 + distilled LoRA + IC-LoRA pixel upscaler → KSampler (8 steps, denoise 0.85 for creative restyling — not full denoise, preserves some original structure)

2. **Spatial upscale pass** — LTX-2.5 latent spatial upscaler (x2: 768×448 → 1536×896) → refinement KSampler (4 steps with manual sigmas to sharpen upscaled details)

3. **Temporal upscale pass** — LTX-2.5 latent temporal upscaler (x2: 385 frames → 770 frames, 24fps → 48fps) → final refinement KSampler (3 steps to smooth interpolated frames)

**Key settings:**
- `denoise: 0.85` in the first pass — lower than 1.0 to preserve the original video's motion/structure while still allowing creative restyling. Increase to 1.0 for more aggressive restyling, decrease to 0.6 for subtle enhancement.
- `strength: 0.75` on `LTXAddVideoICLoRAGuide` — controls how much the IC-LoRA influences the output vs. the input video
- `strength: 0.6` on `LTXICLoRALoaderModelOnly` — IC-LoRA model strength
- `frame_rate: 48` on output — doubled because of temporal upscale

**When to use this vs. `ltx25_v2v_redetail_24gb.json`:**
- Use **restyle+upscale** when you want to creatively transform the look of a video AND get higher resolution + framerate
- Use **redetail** when you just want to clean up / enhance detail without changing the artistic style, and don't need temporal upscale

## VRAM Profile Guide

| GPU | VRAM | Recommended workflow | Checkpoint |
|---|---|---|---|
| RTX 2060/3050/3060 | 6-8GB | `ltx25_v2v_redetail_8gb.json` | GGUF Q4 |
| RTX 4060 Ti/4070 | 12-16GB | `ltx25_v2v_redetail_8gb.json` | GGUF Q4 or Q8 |
| RTX 4090/3090 | 24GB | `ltx25_v2v_redetail_24gb.json` or `ltx25_animatediff_restyle_upscale_24gb.json` | int8-convrot |
| A100/L40/L40S | 48GB+ | Same 24GB workflows (or use BF16 checkpoint for max quality) | int8-convrot or BF16 |

## Running on RunPod Serverless

```bash
# Invoke the endpoint with a workflow
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id <ENDPOINT_ID> \
  --workflow examples/ltx25_animatediff_restyle_upscale_24gb.json \
  --wait --timeout 600
```

The handler ([`src/handler.py`](../src/handler.py:1)) accepts the workflow JSON
under `input.workflow` and returns output URLs (to the volume or S3).

## Customizing Workflows

### Change the restyle prompt
Edit node `"5"` (positive) and `"6"` (negative) in any V2V workflow:
```json
"5": {
  "inputs": {
    "text": "your custom restyle prompt here",
    "clip": ["3", 1]
  },
  "class_type": "CLIPTextEncode"
}
```

### Adjust restyle intensity
- **More aggressive restyle:** Increase `denoise` in node `"12"` (BasicScheduler) toward 1.0
- **Subtle enhancement:** Decrease `denoise` to 0.6-0.7
- **More IC-LoRA influence:** Increase `strength` in node `"10"` (LTXAddVideoICLoRAGuide) toward 1.0

### Change output resolution
Edit nodes `"8"` (ImageScale) and `"9"` (LTXVImgToVideoConditionOnly):
- `width` and `height` must be multiples of 32
- Common: 768×448 (720p-ish), 1024×576 (576p), 1280×704 (720p)

### Disable temporal upscale (for faster rendering)
Remove nodes `"20"`-`"24"` and connect node `"19"` directly to `"25"` (VAEDecode).
Set `frame_rate` in node `"26"` back to 24.
