# Model Loading — CLIPLoader, VAELoader, and VRAM Constraints

## Rule 1: Use `CLIPLoader` with `type: "ltxv"`, NOT `LTXVGemmaCLIPModelLoader`

**LTX-2.5 workflows MUST use `CLIPLoader` with `type: "ltxv"`.**

```json
// CORRECT — uses ComfyUI's model manager (handles comfy_quant)
{
  "class_type": "CLIPLoader",
  "inputs": {
    "clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "type": "ltxv",
    "device": "default"
  }
}

// WRONG — uses transformers' from_pretrained (doesn't handle comfy_quant)
{
  "class_type": "LTXVGemmaCLIPModelLoader",
  "inputs": {
    "gemma_path": "gemma4-12b-ltx-2.5/model.safetensors",
    "ltxv_path": "...",
    "max_length": 1024
  }
}
```

**Why:** `LTXVGemmaCLIPModelLoader` uses `transformers`'
`Gemma3ForConditionalGeneration.from_pretrained()` which doesn't support
ComfyUI's `comfy_quant` int8-convrot format. The `comfy_kitchen` backend that
handles this format is only accessible through ComfyUI's model manager, not
through `from_pretrained`.

Discovered in Aug 14-15 session, issue #3. See
[`docs/SESSION_SUMMARY_2026_08_14_15.md`](../../docs/SESSION_SUMMARY_2026_08_14_15.md).

## Rule 2: Always Add Explicit `VAELoader`

**The int8-convrot and GGUF models don't contain a VAE. Always add a
`VAELoader` node.**

```json
// CORRECT — explicit VAE loader
{
  "class_type": "VAELoader",
  "inputs": { "vae_name": "ltx-2.5-video-vae-bf16.safetensors" }
}

// WRONG — VAE from CheckpointLoaderSimple (returns None for int8/GGUF models)
"vae": ["1", 2]  // CheckpointLoaderSimple output 2 = VAE (None for these models)
```

Discovered in Aug 14-15 session, issue #4.

## Rule 3: VRAM Constraints — Model Size vs GPU Memory

**The int8-convrot transformer (21.5GB) is TOO LARGE for 24GB VRAM.**

| Model | Size | Fits 24GB? | Use |
|---|---|---|---|
| `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` | 21.5 GB | ❌ OOM | 48GB+ GPUs only |
| `LTX-2.5-Distilled-Q4_K_M.gguf` | ~6 GB | ✅ | 24GB and 8GB GPUs |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | 15 GB | ✅ with --lowvram | All GPUs (text encoder, offloaded after encoding) |

For 24GB GPUs: use `UnetLoaderGGUF` with the Q4 model.
For 48GB+ GPUs: use `CheckpointLoaderSimple` with the int8 model for better quality.

Discovered in Aug 14-15 session, issue #5.

## Rule 4: COMFYUI_ARGS — `--lowvram` only

**Do NOT add `--use-sage-attention`.**

```bash
# CORRECT
COMFYUI_ARGS=--lowvram

# WRONG — crashes with int8-convrot models
COMFYUI_ARGS=--use-sage-attention --lowvram
```

**Why:** `--use-sage-attention` crashes during KSampler with `comfy_quant`
models. The `comfy_kitchen` CUDA backend is disabled (needs cu130, we have
cu129), so sage attention can't handle the quantized weights.

Discovered in Aug 14-15 session, issue #6.

## Rule 5: Don't Modify ComfyUI-LTXVideo Code on the Worker

Patches to `embeddings_connector.py` or `gemma_encoder.py` on the worker
are ephemeral — they're lost when the worker restarts.

If a code fix is needed in ComfyUI-LTXVideo:
1. Add it to [`entrypoint.sh`](../../entrypoint.sh) as a `sed` patch that runs at boot
2. Or file a bug/PR with the upstream repo
3. Or fork the repo and point `update_custom_nodes` to the fork
