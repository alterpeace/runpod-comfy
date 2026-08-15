# Project Steering Rules

Rules for AI agents working on this project. Follow these to avoid repeating
mistakes and stay on the correct path.

---

## 1. Package Management

**ALWAYS use `uv`, never `pip` directly.**

```bash
# CORRECT — install into ComfyUI's venv
uv pip install --python /comfyui/venv/bin/python <package>

# CORRECT — install project deps
uv sync

# CORRECT — run Python scripts
uv run python scripts/<script>.py

# WRONG — pip doesn't exist in the container
pip install <package>
/comfyui/venv/bin/pip install <package>
```

The container has NO `pip` binary. The venv at `/comfyui/venv/` was created
by `uv` and doesn't include `pip`. All package management goes through `uv`.

---

## 2. Container Access

**The container shell is at `/workspace`, not `/comfyui`.**

```bash
# Enter the container
docker exec -it comfy bash

# You're now in /workspace (this project's code)
# ComfyUI is at /comfyui (separate directory)
# ComfyUI's venv is at /comfyui/venv
# Custom nodes are at /comfyui/custom_nodes
# Models are at /comfyui/models (symlinked from /runpod-volume/models)
```

Don't confuse `/workspace` (project code: handler.py, entrypoint.sh, scripts/)
with `/comfyui` (ComfyUI installation: main.py, venv, custom_nodes, models/).

---

## 3. Model Loading — Use CLIPLoader, NOT LTXVGemmaCLIPModelLoader

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

`LTXVGemmaCLIPModelLoader` uses `transformers`' `from_pretrained()` which
doesn't support ComfyUI's `comfy_quant` int8-convrot format. `CLIPLoader`
with `type: "ltxv"` goes through ComfyUI's model manager which handles it.

---

## 4. VAE Loading — Always Use Explicit VAELoader

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

---

## 5. Model Size vs VRAM

**The int8-convrot transformer (21.5GB) is TOO LARGE for 24GB VRAM.**

| Model | Size | Fits 24GB? | Use |
|---|---|---|---|
| `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` | 21.5 GB | ❌ OOM | 48GB+ GPUs only |
| `LTX-2.5-Distilled-Q4_K_M.gguf` | ~6 GB | ✅ | 24GB and 8GB GPUs |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | 15 GB | ✅ with --lowvram | All GPUs (text encoder, offloaded after encoding) |

For 24GB GPUs: use `UnetLoaderGGUF` with the Q4 model.
For 48GB+ GPUs: use `CheckpointLoaderSimple` with the int8 model for better quality.

---

## 6. COMFYUI_ARGS

**Default is `--lowvram`. Do NOT add `--use-sage-attention`.**

```bash
# CORRECT
COMFYUI_ARGS=--lowvram

# WRONG — crashes with int8-convrot models
COMFYUI_ARGS=--use-sage-attention --lowvram
```

`--use-sage-attention` crashes during KSampler with `comfy_quant` models.
The `comfy_kitchen` CUDA backend is disabled (needs cu130, we have cu129),
so sage attention can't handle the quantized weights.

---

## 7. Input File Paths

**VHS_LoadVideo paths are relative to `/comfyui/input/`.**

The entrypoint replaces `/comfyui/input` with a symlink to
`/runpod-volume/input`. This makes `os.path.realpath()` resolve correctly,
passing ComfyUI's `is_within_directory` check.

Do NOT symlink individual files from the volume to `/comfyui/input/` —
this fails the realpath check. The entire directory must be a symlink.

---

## 8. Serverless Debugging

**Use the `diagnostic` action for remote debugging.**

```python
job = endpoint.run({
    "input": {
        "action": "diagnostic",
        "commands": ["ls -la /comfyui/models/", "nvidia-smi"],
        "timeout": 15,
    }
})
```

The `diagnostic` action runs shell commands on the worker and returns
stdout/stderr. Use it to:
- Check file existence and paths
- Inspect GPU memory usage
- Patch files on the worker (ephemeral — lost on restart)
- Kill/restart ComfyUI process

---

## 9. Workflow JSON Format

**All workflows must be in API format (dict of node_id → {class_type, inputs}).**

UI format (with `nodes` array, `links`, `widgets_values`) doesn't work with
the serverless handler. Convert UI workflows to API format using ComfyUI's
"Save (API Format)" in the WebUI.

---

## 10. Git Workflow

**Commit and push after each fix. Don't accumulate changes.**

```bash
git add -A
git commit -m "fix: <description of what and why>"
git push github main
```

The remote is `github` (not `origin`). Use descriptive commit messages
that explain WHY the change was made, not just WHAT changed.

---

## 11. Don't Modify ComfyUI-LTXVideo Code on the Worker

**Patches to `embeddings_connector.py` or `gemma_encoder.py` on the worker
are ephemeral — they're lost when the worker restarts.**

If a code fix is needed in ComfyUI-LTXVideo:
1. Add it to `entrypoint.sh` as a `sed` patch that runs at boot
2. Or file a bug/PR with the upstream repo
3. Or fork the repo and point `update_custom_nodes` to the fork

---

## 12. Testing Order

**Test locally first, then on serverless.**

1. Start local ComfyUI: `AUTO_INSTALL_CUSTOM_NODE_DEPS=false ./scripts/run_local.sh --logs`
2. Test workflow via WebUI at http://localhost:8188
3. If it works locally, test on serverless:
   ```bash
   set -a && source .env && set +a
   uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4
   ```
4. If it fails on serverless but works locally, check:
   - Worker image is up to date (diagnostic action available?)
   - Model files exist on the volume
   - COMFYUI_ARGS doesn't have `--use-sage-attention`
   - GPU VRAM is sufficient for the model size
