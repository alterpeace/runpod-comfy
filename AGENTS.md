# AGENTS.md — Project-Level Context for AI Coding Assistants

This file is auto-loaded at the start of every Kilo Code session. It provides
the minimum context needed to avoid common mistakes. Detailed rules live in
[`docs/`](docs/) and [`.kilocode/rules/`](.kilocode/rules/).

---

## Project Overview

**runpod-comfy** — A ComfyUI serverless deployment on RunPod for LTX-2.5
video generation. The project packages ComfyUI + custom nodes into a Docker
image, deploys it as a RunPod serverless endpoint, and provides lifecycle
scripts, workflow examples, and storage integration (S3/B2).

---

## Critical Rules (read these first)

### 1. Package Management — `uv` only, never `pip`

The container has NO `pip` binary. The venv at `/comfyui/venv/` was created
by `uv` and doesn't include `pip`.

```bash
# CORRECT
uv pip install --python /comfyui/venv/bin/python <package>
uv sync
uv run python scripts/<script>.py

# WRONG — pip doesn't exist
pip install <package>
```

See: [`.kilocode/rules/package-management.md`](.kilocode/rules/package-management.md)

### 2. Container Layout — `/workspace` ≠ `/comfyui`

```
/workspace     ← project code (handler.py, entrypoint.sh, scripts/)
/comfyui       ← ComfyUI installation (main.py, venv, custom_nodes, models/)
/comfyui/venv  ← Python venv (created by uv, no pip)
/comfyui/input  → /runpod-volume/input   (symlink — entire dir, not individual files)
/comfyui/output → /runpod-volume/output  (symlink — persists across worker restarts)
/comfyui/models → /runpod-volume/models  (symlink)
```

See: [`.kilocode/rules/container-layout.md`](.kilocode/rules/container-layout.md)

### 3. Model Loading — `CLIPLoader` with `type: "ltxv"`, NOT `LTXVGemmaCLIPModelLoader`

`LTXVGemmaCLIPModelLoader` uses `transformers`' `from_pretrained()` which
doesn't support ComfyUI's `comfy_quant` int8-convrot format. `CLIPLoader`
goes through ComfyUI's model manager which handles it properly.

Always add an explicit `VAELoader` — int8-convrot and GGUF models don't
contain a VAE.

See: [`.kilocode/rules/model-loading.md`](.kilocode/rules/model-loading.md)

### 4. VRAM Constraints

| Model | Size | Fits 24GB? |
|---|---|---|
| dev int8-convrot transformer | 21.5 GB | ❌ OOM (at 768×448 two-pass) |
| distilled int8-convrot transformer | 21.5 GB | ⚠️ UNTESTED (official ComfyUI standard) |
| GGUF Q4_K_M | 15.7 GB | ✅ with `--lowvram` |
| GGUF Q3_K_S | 12.6 GB | ✅ with `--lowvram` (8GB GPUs, slow) |
| gemma4-12b int8-convrot (text encoder) | 15 GB | ✅ with `--lowvram` (offloaded after encoding) |

For 8GB GPUs: use `UnetLoaderGGUF` with Q3_K_S.
For 24GB GPUs: use `UnetLoaderGGUF` with Q4_K_M, or try distilled int8-convrot (untested).
For 48GB+ GPUs: use `CheckpointLoaderSimple` with the dev int8 model.

### 5. COMFYUI_ARGS — `--lowvram` only

Do NOT add `--use-sage-attention`. It crashes with `comfy_quant` models
because `comfy_kitchen` CUDA backend is disabled (needs cu130, we have cu129).

### 6. Git Workflow

```bash
git add -A
git commit -m "fix: <what and why>"
git push github main   # remote is 'github', not 'origin'
```

Commit and push after each fix. Don't accumulate changes.

---

## Key Directories

| Path | Purpose |
|---|---|
| [`src/handler.py`](src/handler.py) | RunPod serverless handler (main entry point) |
| [`src/proxy_server.py`](src/proxy_server.py) | HTTP proxy for ComfyUI API |
| [`entrypoint.sh`](entrypoint.sh) | Container boot script (symlinks, patches, ComfyUI launch) |
| [`lifecycle/`](lifecycle/) | RunPod pod/serverless lifecycle management scripts |
| [`scripts/`](scripts/) | Build, deploy, test, and utility scripts |
| [`examples/`](examples/) | ComfyUI workflow JSON files (API format) |
| [`config/`](config/) | Model configs, RunPod configs |
| [`docs/`](docs/) | Full documentation |
| [`.kilocode/rules/`](.kilocode/rules/) | Auto-loaded project rules (this file's companions) |

---

## Common Commands

```bash
# Build the Docker image
./scripts/build/build.sh

# Deploy to RunPod serverless
./scripts/build/deploy.sh

# Run locally for testing
./scripts/build/run_local.sh --logs

# Test a v2v workflow on serverless
set -a && source .env && set +a
uv run python scripts/invoke/invoke_v2v_with_upload.py --video rhizome.mp4

# Enter the running container
docker exec -it comfy bash
```

---

## Testing Order

1. Test locally first: `./scripts/build/run_local.sh --logs` → WebUI at `http://localhost:8188`
2. If local works, test on serverless: `uv run python scripts/invoke/invoke_v2v_with_upload.py`
3. If serverless fails but local works, check:
   - Worker image is up to date (is `diagnostic` action available?)
   - Model files exist on the volume
   - `COMFYUI_ARGS` doesn't have `--use-sage-attention`
   - GPU VRAM is sufficient for the model size

---

## Further Reading

- [`.kilocode/rules/`](.kilocode/rules/) — Auto-loaded detailed rules
- [`docs/STEERING_RULES.md`](docs/STEERING_RULES.md) — Full steering rules (12 sections)
- [`docs/SESSION_SUMMARY_2026_08_14_15.md`](docs/SESSION_SUMMARY_2026_08_14_15.md) — Recent debugging session (error history)
- [`docs/RUNPOD_STEERING.md`](docs/RUNPOD_STEERING.md) — RunPod CLI and infrastructure guidance
- [`docs/COMFYUI_WORKFLOW_STEERING.md`](docs/COMFYUI_WORKFLOW_STEERING.md) — Workflow building patterns
- [`docs/WORKFLOW_CATALOG.md`](docs/WORKFLOW_CATALOG.md) — Available workflow examples
