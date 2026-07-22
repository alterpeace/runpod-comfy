# LTX-2.3 V2V / IC-LoRA Setup Guide

## Overview

LTX-2.3 is Lightricks' 22B-parameter audio-video DiT model. It's natively
supported in ComfyUI core (v0.16.1+), so no custom nodes are required for
basic text/image-to-video. IC-LoRA (in-context LoRA) workflows — video-to-video
style transfer, colorization, detailing, relighting, etc. — need the
`ComfyUI-LTXVideo` node pack on top.

This repo bumps `COMFYUI_VERSION` to a current release and adds an install
script (`scripts/install_ltx23.sh`) that handles both the custom nodes and
the model downloads.

## Quick Start

```bash
# Inside the container, or locally with venv activated:
./scripts/install_ltx23.sh --profile mid_vram_12_24gb
```

Then restart ComfyUI and load one of the example workflows from
[ComfyUI-LTXVideo/example_workflows/2.3](https://github.com/Lightricks/ComfyUI-LTXVideo/tree/master/example_workflows/2.3),
e.g. `LTX-2.3_V2V_ICLoRA_Single_Stage_Distilled.json`.

## What Gets Installed

### Custom nodes (`custom_nodes/`)
- **ComfyUI-LTXVideo** (Lightricks) — IC-LoRA guide/loader nodes
  (`LTXAddVideoICLoRAGuide`, `LTXICLoRALoaderModelOnly`,
  `LTXVImgToVideoConditionOnly`, `LTXVTiledVAEDecode`, etc.)
- **ComfyUI-GGUF** (city96) — lets low-VRAM cards load quantized `.gguf`
  checkpoints via the "Unet Loader (GGUF)" node

### Models (`models/`)
Defined in `config/ltx-2.3-models.json`, selected by `--profile` or `--ids`.
See `./scripts/install_ltx23.sh --list` for the full catalog with
descriptions.

| Profile | Use case | Approx VRAM |
|---|---|---|
| `low_vram_8gb` | GGUF quantized dev+distilled checkpoints | ~8-12GB |
| `mid_vram_12_24gb` (default) | fp8 checkpoint + distilled speed LoRA | ~12-24GB |
| `minimal` | text encoder + fp8 checkpoint + distilled LoRA only | ~24GB |
| `full` | everything in the manifest (all IC-LoRAs, upscalers, GGUFs) | n/a (disk-bound) |

## VRAM Tiers in Detail

- **8GB and under**: use `gguf_distilled_q4` (`ltx-2.3-22b-distilled-1.1-Q4_K_M.gguf`)
  with the GGUF Unet Loader node, low resolution (e.g. 512x512), short clips
  (~2-3s), and `COMFYUI_ARGS=--lowvram --disable-smart-memory`. Expect to trade
  quality for headroom — this is genuinely tight for a 22B model.
- **12GB**: `gguf_dev_q4` or `gguf_distilled_q4` GGUF quants are the
  realistic path. fp8 checkpoints (~24GB VRAM target) will likely OOM without
  aggressive offloading.
- **24GB (RTX 4090/3090)**: `checkpoint_fp8` (`ltx-2.3-22b-dev-fp8.safetensors`)
  + `distilled_lora` is the sweet spot — this is exactly what the official
  single-stage distilled V2V IC-LoRA example workflow uses.
- **32GB+**: `checkpoint_bf16` for full quality, or stack multiple IC-LoRAs
  at once without VRAM pressure.

## Gated IC-LoRA Repos

Most of the official `Lightricks/LTX-2.3-22b-IC-LoRA-*` repos are gated
(instant-approve, but still require an explicit click):

1. Visit the repo page on huggingface.co (e.g.
   `https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Colorization`) and
   click **"Agree and Access"**.
2. Generate a token at https://huggingface.co/settings/tokens (read access is
   enough).
3. Set `HF_TOKEN` in your `.env` or shell environment before running the
   install script.

Ungated alternatives are included where available (e.g.
`iclora_colorizer_doctordiffusion` instead of the gated official
colorization LoRA).

## Available IC-LoRAs / Effect LoRAs

| id | Effect |
|---|---|
| `iclora_ingredients` | Character/prop consistency from a reference sheet |
| `iclora_colorization` / `iclora_colorizer_doctordiffusion` | Colorize B&W video |
| `iclora_day_to_night` | Relight daytime → night |
| `iclora_decompression` | Remove compression artifacts |
| `iclora_deblur` | Sharpen out-of-focus video |
| `iclora_water_simulation` | Add water VFX |
| `iclora_in_outpainting` | Video inpainting/outpainting |
| `iclora_hdr` | 16-bit HDR generation / SDR→HDR |
| `audio_reactive` | Beat-synced / music-visualizer generation (fal.ai) |
| `id_lora_celebvhq` / `id_lora_talkvid` | Talking-head identity consistency |
| `omninft_rl_lora` | General quality boost (AV sync, audio quality, prompt adherence) from RL fine-tuning — **use LoRA strength 2.0**, not 1.0, to match the training config (alpha=64/rank=32). Source license is "research use only" — check it fits your use case before commercial deployment. |
| `editanything_multitask` | **Experimental**: prompt-only video editing — Add/Remove/Replace/Style (300+ style names). Standalone LoRA, strict per-task caption shape required (see workflow enhancements doc). |
| `editanything_motion_transfer` | **Experimental**: swap a guide video's first frame, copy its motion onto the new subject. Fails on hard scene cuts and fast motion. |
| `editanything_refv2v_standard` + `editanything_refv2v_module` | **Experimental**: reference-image-driven add/replace. Needs both halves loaded together plus the `ComfyUI-BFSNodes` node pack (`LTXVEditAnythingModuleLoader` + Looping Sampler). |
| `detailer_experimental` | **Unverified**: general detail enhancer trained on LTX-2 19b (not 2.3) — test before relying on it |

## Manual Usage

```bash
# List everything available
python scripts/download_ltx23_models.py --list

# Download specific models into a custom location
python scripts/download_ltx23_models.py --ids checkpoint_fp8 distilled_lora \
    --output-dir /path/to/models

# Dry run to see what would be fetched
python scripts/download_ltx23_models.py --profile full --dry-run

# Nodes only (no model downloads)
./scripts/install_ltx23.sh --skip-models

# Models only (nodes already installed)
./scripts/install_ltx23.sh --skip-nodes --profile low_vram_8gb
```

## Disabling Audio Generation (video-only, saves VRAM)

LTX-2.3 generates video and audio jointly by default. If you only need
video output, disabling the audio branch saves VRAM (skips loading the
~audio VAE and the extra audio latent tokens) and shortens sampling
slightly, since the model doesn't have to attend across A/V cross-attention
for a stream you're discarding.

In the official example workflows (e.g. `LTX-2.3_V2V_ICLoRA_Single_Stage_Distilled.json`),
this is workflow-level, not a command-line flag:

- Set the `LTXVAudioVAELoader` node's mode to **Bypass** (right-click node →
  Mode → Bypass, or `mode: 4` in the raw JSON) if nothing downstream needs
  audio.
- Skip/bypass `LTXVEmptyLatentAudio`, `LTXVSetAudioRefTokens`,
  `VAEEncodeAudio`, and `LTXVAudioVAEDecode` — these only exist to produce
  or condition on the audio latent.
- Remove `LTXVConcatAVLatent` from the sampling chain (it merges video +
  audio latents before sampling) and feed the video latent straight to the
  sampler, then use `LTXVSeparateAVLatent` is unnecessary too since there's
  nothing to separate.
- `CreateVideo`'s `audio` input is optional (`shape: 7` = optional slot in
  the node JSON) — leave it disconnected for a silent video output.

There's no single ComfyUI startup flag for this (e.g. no
`--disable-audio`) — it's controlled per-workflow by which nodes are wired
and active. If you're building workflows programmatically (via the RunPod
handler), the simplest approach is to keep two workflow JSON variants —
one with the audio branch, one without — and select based on a request
parameter, rather than trying to toggle node `mode` values at submission
time.

## Running on Constrained Hardware (8-24GB) and Across Providers

The image built by this repo's Dockerfile is a standard Docker image — it
runs the same way locally (via `docker-compose.yml`), on RunPod Pods,
RunPod Serverless, or any other GPU host that can run Docker + NVIDIA
Container Toolkit. There's nothing RunPod-specific baked into the ComfyUI
process itself, only the optional handler/entrypoint mode switching
(`MODE=local|pods|serverless`).

For low-VRAM cards, stack these:
- Use a GGUF-quantized checkpoint (`gguf_distilled_q4` at minimum) via
  ComfyUI-GGUF.
- Set `COMFYUI_ARGS=--lowvram --disable-smart-memory` (already the
  docker-compose.yml default).
- ComfyUI's built-in **Dynamic VRAM** system (`comfy-aimdo`, bundled since
  ComfyUI ~v0.24) automatically offloads model weights between VRAM/RAM
  under pressure — it's on by default on Nvidia + Linux/Windows and generally
  helps here, but some users report it being overly aggressive on certain
  cards (see [Comfy-Org/ComfyUI#14447](https://github.com/Comfy-Org/ComfyUI/issues/14447)).
  If you see unexpected slowdowns or instability, try `--disable-dynamic-vram`
  and fall back to manual `--lowvram`/GGUF tuning instead.
- Reduce resolution/frame count first — LTX-2.3 V2V IC-LoRA quality degrades
  more gracefully at lower res than a 22B model degrades at low quantization.

No code changes are needed to move between local Docker Compose and RunPod —
just re-point the same image at a different host with a GPU that meets the
VRAM tier you're targeting.
