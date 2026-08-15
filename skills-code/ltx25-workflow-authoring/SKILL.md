---
name: ltx25-workflow-authoring
description: >
  Rules and patterns for building, debugging, and deploying LTX-2.5 ComfyUI
  workflows on this project's RunPod serverless infrastructure. Covers model
  loader selection (CLIPLoader vs LTXVGemmaCLIPModelLoader), VAE loading,
  VRAM constraints (int8-convrot vs GGUF Q4), COMFYUI_ARGS, and API-format
  workflow JSON structure. Activate when creating, editing, or debugging
  ComfyUI workflow JSON files or when troubleshooting model loading errors.
---

# LTX-2.5 Workflow Authoring Skill

## When to Use This Skill

- Creating or editing ComfyUI workflow JSON files (in [`examples/`](../../../examples/))
- Debugging model loading errors (e.g., `comfy_quant`, `weight_scale` errors)
- Troubleshooting VAE errors (e.g., `VAE is invalid: None`)
- Selecting models based on GPU VRAM constraints
- Converting UI-format workflows to API format for serverless deployment

## Critical Rules

### 1. Model Loader: `CLIPLoader` with `type: "ltxv"`

**NEVER use `LTXVGemmaCLIPModelLoader`.** It uses `transformers`'
`from_pretrained()` which doesn't support `comfy_quant` int8-convrot format.

```json
{
  "class_type": "CLIPLoader",
  "inputs": {
    "clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "type": "ltxv",
    "device": "default"
  }
}
```

### 2. Always Add Explicit `VAELoader`

int8-convrot and GGUF models don't contain a VAE. `CheckpointLoaderSimple`
returns `None` for VAE output with these models.

```json
{
  "class_type": "VAELoader",
  "inputs": { "vae_name": "ltx-2.5-video-vae-bf16.safetensors" }
}
```

### 3. VRAM-Based Model Selection

| GPU VRAM | Transformer Loader | Model File |
|---|---|---|
| 24GB (RTX 4090, etc.) | `UnetLoaderGGUF` | `LTX-2.5-Distilled-Q4_K_M.gguf` (~6GB) |
| 48GB+ (A6000, A100) | `CheckpointLoaderSimple` | `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` (21.5GB) |

Text encoder (`gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`, 15GB)
fits all GPUs with `--lowvram` — it's offloaded after text encoding.

### 4. COMFYUI_ARGS

```bash
COMFYUI_ARGS=--lowvram
```

Do NOT add `--use-sage-attention` — crashes with `comfy_quant` models
(`comfy_kitchen` CUDA backend needs cu130, we have cu129).

### 5. Workflow JSON Must Be API Format

All workflows for serverless deployment must be in **API format**:
a dict of `node_id → {class_type, inputs}`. UI format (with `nodes` array,
`links`, `widgets_values`) doesn't work with the serverless handler.

Convert UI workflows using ComfyUI's "Save (API Format)" in the WebUI.

## Workflow Structure Template

A minimal LTX-2.5 v2v workflow in API format:

```json
{
  "1": {
    "class_type": "CLIPLoader",
    "inputs": {
      "clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
      "type": "ltxv",
      "device": "default"
    }
  },
  "2": {
    "class_type": "UnetLoaderGGUF",
    "inputs": {
      "unet_name": "LTX-2.5-Distilled-Q4_K_M.gguf"
    }
  },
  "3": {
    "class_type": "VAELoader",
    "inputs": {
      "vae_name": "ltx-2.5-video-vae-bf16.safetensors"
    }
  }
}
```

## Example Workflows

See [`examples/`](../../../examples/) for complete workflow JSON files:

- [`ltx25_v2v_redetail_entry.json`](../../../examples/ltx25_v2v_redetail_entry.json) — Entry-level v2v redetail (GGUF Q4, 24GB)
- [`ltx25_v2v_redetail_comfortable.json`](../../../examples/ltx25_v2v_redetail_comfortable.json) — Higher quality v2v redetail
- [`ltx25_t2v_entry.json`](../../../examples/ltx25_t2v_entry.json) — Text-to-video entry level
- [`examples/ltx25_README.md`](../../../examples/ltx25_README.md) — Full workflow catalog

## Debugging Model Loading Errors

| Error | Cause | Fix |
|---|---|---|
| `Unexpected key(s): weight_scale, comfy_quant` | Using `LTXVGemmaCLIPModelLoader` with int8-convrot model | Switch to `CLIPLoader` with `type: "ltxv"` |
| `VAE is invalid: None` | No explicit `VAELoader`, relying on `CheckpointLoaderSimple` VAE output | Add `VAELoader` node |
| CUDA OOM during KSampler | int8-convrot transformer (21.5GB) on 24GB GPU | Switch to GGUF Q4 model with `UnetLoaderGGUF` |
| `[Errno 32] Broken pipe` | ComfyUI process crashed (likely OOM) | Check VRAM, use smaller model |
| `Invalid video file: <name>` | Individual file symlink instead of directory symlink | Use entire-directory symlink for `/comfyui/input` |

## Further Reading

- [`.kilocode/rules/model-loading.md`](../../../.kilocode/rules/model-loading.md) — Detailed model loading rules
- [`docs/COMFYUI_WORKFLOW_STEERING.md`](../../../docs/COMFYUI_WORKFLOW_STEERING.md) — Full workflow building guide
- [`docs/SESSION_SUMMARY_2026_08_14_15.md`](../../../docs/SESSION_SUMMARY_2026_08_14_15.md) — Debugging session with error history
- [`docs/WORKFLOW_CATALOG.md`](../../../docs/WORKFLOW_CATALOG.md) — Available workflow examples
