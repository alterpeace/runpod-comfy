# Session Summary — August 14-15, 2026

Complete record of debugging, fixes, and improvements made during this session.

---

## Issues Diagnosed and Fixed

### 1. Input Video Not Found (comfy_quant realpath issue)
- **Symptom:** `Invalid video file: rhizome.mp4` from VHS_LoadVideo
- **Root cause:** ComfyUI's `is_within_directory()` uses `os.path.realpath()` which follows symlinks. Individual file symlinks from `/runpod-volume/input/` to `/comfyui/input/` resolved outside the input directory, failing the path traversal check.
- **Fix:** Replace `/comfyui/input` entirely with a symlink to `/runpod-volume/input` in [`entrypoint.sh`](../entrypoint.sh). When the directory itself is the symlink, `realpath` resolves both dir and files to the same base.
- **Commit:** `7f0461c`

### 2. Stale Worker Image
- **Symptom:** `Unknown action 'diagnostic'` — worker running old cached image
- **Root cause:** RunPod serverless workers cache images and don't auto-pull new `latest` tags
- **Fix:** Forced endpoint to pull new image by updating image tag in RunPod console
- **Verification:** `diagnostic` action became available after update

### 3. LTXVGemmaCLIPModelLoader comfy_quant Incompatibility
- **Symptom:** `Error(s) in loading state_dict for Embeddings1DConnector: Unexpected key(s): weight_scale, comfy_quant`
- **Root cause:** `LTXVGemmaCLIPModelLoader` uses `transformers`' `Gemma3ForConditionalGeneration.from_pretrained()` which doesn't support ComfyUI's `comfy_quant` int8-convrot format. The `comfy_kitchen` backend that handles this format is only accessible through ComfyUI's model manager, not through `from_pretrained`.
- **Fix:** Replace `LTXVGemmaCLIPModelLoader` with `CLIPLoader` + `type: "ltxv"` in all workflows. `CLIPLoader` goes through ComfyUI's model manager which handles `comfy_quant` properly.
- **Discovery:** Found by comparing our workflows with the official LTXVideo API workflows in `examples/test/` — they use `CLIPLoader`, not `LTXVGemmaCLIPModelLoader`.
- **Commits:** `4bf2db9`, `1ae73cd`

### 4. Missing VAE in int8/GGUF Checkpoints
- **Symptom:** `VAE is invalid: None` from LTXVImgToVideo
- **Root cause:** The int8-convrot and GGUF model files only contain the diffusion transformer, not a VAE. `CheckpointLoaderSimple` returns `None` for VAE output.
- **Fix:** Add explicit `VAELoader` node with `ltx-2.5-video-vae-bf16.safetensors` in all workflows.
- **Commit:** `8680d6b`

### 5. KSampler CUDA OOM with int8-convrot Model
- **Symptom:** ComfyUI crashes during KSampler with `[Errno 32] Broken pipe` after ~80 seconds
- **Root cause:** The int8-convrot transformer (21.5GB) exceeds 24GB VRAM during the forward pass. With `--lowvram`, ComfyUI stages 20.5GB for dynamic VRAM loading but can't fit it all during sampling.
- **Fix:** Use GGUF Q4 model (~6GB) instead of int8-convrot for 24GB GPUs. The Q4 model fits easily with room for latents and computation.
- **Verification:** Workflow completed successfully in 125 seconds, output video saved.
- **Commit:** `3a303de`

### 6. --use-sage-attention Crash
- **Symptom:** ComfyUI crashes during KSampler (initially thought to be sage attention)
- **Root cause:** Initially suspected `--use-sage-attention` but after removing it, the crash persisted. The real cause was CUDA OOM (issue #5 above). However, `--use-sage-attention` was still removed as a precaution since `comfy_kitchen` CUDA backend is disabled (needs cu130, we have cu129).
- **Fix:** Changed `COMFYUI_ARGS` default from `--use-sage-attention --lowvram` to `--lowvram` in handler.py and RunPod console.
- **Commit:** (handler.py change)

### 7. Output Files Lost on Worker Restart
- **Symptom:** Output videos saved to `/comfyui/output/` (ephemeral container disk) were lost when workers scaled down
- **Root cause:** `/comfyui/output` was a real directory (created by Dockerfile), not symlinked to the network volume
- **Fix:** Replace `/comfyui/output` with a symlink to `/runpod-volume/output` in entrypoint.sh (same approach as the input fix)
- **Verification:** Output video appeared in S3 at `output/ltx25_v2v_entry_00001.mp4`
- **Commit:** `3541fbb`

### 8. Content Type for Video Uploads
- **Symptom:** Video files uploaded via `input_images` might not work correctly
- **Root cause:** `comfyui_client.py` hardcoded content type as `image/png` for all uploads
- **Fix:** Renamed `upload_image` to `upload_file`, derive content type from filename extension via `mimetypes.guess_type()`
- **Commit:** `7f0461c`

### 9. Disk Space Exhaustion
- **Symptom:** `OSError: [Errno 122] Disk quota exceeded` when downloading BF16 model
- **Root cause:** 94GB volume was 100% full with duplicate HF caches (28GB), unused models, and incomplete downloads
- **Fix:** Deleted 28GB of HF caches, deleted int8 and BF16 models (not needed for 24GB), deleted zero-byte files
- **Result:** Freed 56GB, volume now at 40% usage

### 10. .env File Corruption
- **Symptom:** `RUNPOD_ENDPOINT_ID=taea2mhlwbdkuqAUTO_INSTALL_CUSTOM_NODE_DEPS=false` — endpoint ID corrupted
- **Root cause:** `echo "AUTO_INSTALL_CUSTOM_NODE_DEPS=false" >> .env` appended to a line without trailing newline
- **Fix:** `sed -i` to separate the lines
- **Commit:** `1618380`

---

## Code Changes Summary

### entrypoint.sh
- Input directory: Replace `/comfyui/input` with symlink to `/runpod-volume/input`
- Output directory: Replace `/comfyui/output` with symlink to `/runpod-volume/output`
- Gemma tokenizer: Prefer int8-convrot over BF16 (BF16 causes OOM on 24GB)
- int8 patch: `patch_ltxv_int8` function adds `strict=False` to `embeddings_connector.py`
- Custom node updates: `update_custom_nodes` clones latest ComfyUI-LTXVideo

### src/handler.py
- `COMFYUI_ARGS` default changed from `--use-sage-attention --lowvram` to `--lowvram`
- `upload_images` renamed to `upload_files` (backward-compatible alias preserved)
- `input_files` added as alias for `input_images` in job input
- `run_diagnostic` action for remote shell command execution
- `download_models` action with `inline_manifest` support

### src/comfyui_client.py
- `upload_image` renamed to `upload_file`
- Content type derived from filename extension via `mimetypes.guess_type()`
- Backward-compatible `upload_image` alias preserved

### docker-compose.yml
- `AUTO_INSTALL_CUSTOM_NODE_DEPS` env var passed through to container

### Workflows (all updated to use CLIPLoader + VAELoader)
- `ltx25_v2v_redetail_entry_runpod.json` — GGUF Q4, single-pass, 24GB
- `ltx25_v2v_redetail_entry.json` — GGUF Q4, single-pass, 24GB
- `ltx25_v2v_redetail_comfortable_runpod.json` — int8, two-pass, 48GB
- `ltx25_v2v_redetail_comfortable.json` — int8, two-pass, 48GB
- `ltx25_v2v_redetail_recommended_runpod.json` — BF16, two-pass, 80GB+
- `ltx25_t2v_entry.json` — T2V, GGUF Q4, 24GB
- `ltx25_animatediff_restyle_comfortable.json` — AnimateDiff restyle, 48GB

### Scripts Created
- `scripts/diag/diagnose_worker.py` — Send diagnostic commands to worker
- `scripts/invoke/invoke_v2v_with_upload.py` — V2V with video upload via input_files
- `scripts/invoke/invoke_v2v.py` — V2V workflow invocation
- `scripts/diag/fix_input_symlink.py` — Create input symlinks via download_models
- `scripts/diag/check_volume_files.py` — Verify files on worker FUSE mount
- `scripts/diag/check_comfyui_input.py` — Verify symlinks in /comfyui/input/
- `scripts/diag/patch_gemma_int8.py` — Patch embeddings_connector.py (strict=False)
- `scripts/diag/patch_gemma_dequant.py` — Patch with dequantization logic
- `scripts/diag/patch_and_restart.py` — Patch and restart ComfyUI
- `scripts/storage/sync_outputs.py` — Sync S3 outputs to local directory
- `scripts/storage/list_s3.py` — List S3 volume as tree with sizes

### Documentation Created
- `docs/STEERING_RULES.md` — 12 project rules for AI agents
- `docs/RUNPOD_STEERING.md` — RunPod CLI, MCP, handler reference
- `docs/COMFYUI_WORKFLOW_STEERING.md` — Workflow patterns and debugging
- `docs/PROMPT_ENGINEERING_REFERENCE.md` — Prompt terms for video generation
- `docs/WORKFLOW_CATALOG.md` — Workflow comparison and style consistency
- `docs/LTX2_OFFICIAL_VS_RUNPOD.md` — (planned, not yet created)

### Cleanup
- Removed all LTX-2.3 example workflows (12 files, 3,750 lines)
- Removed PUSA_V1 examples and docs (3 files)
- Removed 8 docs (LTX-2.3 cruft, overlaps, niche features)
- Renamed workflows from GB-based to tier-based naming

---

## Models on Volume (Final State)

| Model | Size | Purpose |
|---|---|---|
| `LTX-2.5-Distilled-Q4_K_M.gguf` | 14.6 GB | Entry-tier diffusion model (GGUF Q4) |
| `ltx-2.5-fp8.safetensors` | 19.0 GB | Entry-tier diffusion model (FP8, better quality) |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | 15.4 GB | Text encoder (int8-convrot) |
| `ltx-2.5-22b-distilled-lora-450-bf16.safetensors` | 8.9 GB | Distilled LoRA (speed) |
| `ltx-2.5-video-vae-bf16.safetensors` | 1.5 GB | Video VAE |
| `ltx-2.5-audio-vae-bf16.safetensors` | 0.4 GB | Audio VAE |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | 1.0 GB | Latent upscaler |
| `ltx-2.5-latent-temporal-upscaler-x2-bf16-1.0.safetensors` | 0.3 GB | Temporal upscaler |
| `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors` | 0.3 GB | IC-LoRA pixel upscaler |
| Tokenizer files | 0.04 GB | Gemma 4 tokenizer/config |

**Total:** ~61 GB on 94GB volume (65% used, 33GB free)

---

## Confirmed Working

- ✅ V2V redetail workflow (GGUF Q4, single-pass, 24GB) — 122s, output saved to S3
- ✅ CLIPLoader with `type: "ltxv"` loads `comfy_quant` int8-convrot models
- ✅ Text encoding with int8 Gemma model-
- ✅ KSampler with GGUF Q4 model
- ✅ VAE decode and video output
- ✅ Output persistence to S3 volume
- ✅ Output download via `sync_outputs.py`
- ✅ `diagnostic` action for remote debugging
- ✅ `download_models` action with `inline_manifest`

---

## Next 5 Steps

1. **Create and test FP8 workflow** — `ltx25_v2v_redetail_entry_fp8.json` using `UNETLoader` with the FP8 model (19GB, better quality than Q4)

2. **Download and integrate turbo LoRA** — `TheDivergentAI/ltx25-turbo-distill-lora` (r128 variant) for faster generation (4 steps instead of 8)

3. **Rebuild and push Docker image** — All fixes are in code but the deployed image is stale. Rebuild with `./scripts/build/build.sh --username alterpeace --push` to bake in all entrypoint/handler changes permanently.

4. **Create keyframe interpolation workflow** — Using `LTXVImgToVideoConditionOnly` to interpolate between keyframes for slow-motion effects

5. **Create retake workflow** — Same input video, different seed/prompt for creative variations. Useful for generating multiple style options from the same footage.
