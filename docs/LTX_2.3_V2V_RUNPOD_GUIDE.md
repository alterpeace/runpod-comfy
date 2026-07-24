# LTX-2.3 V2V on RunPod — Complete Setup Guide (with Content Upload)

End-to-end guide for running LTX-2.3 video-to-video (V2V) on RunPod, including
how to upload your own input video content. This consolidates the build, deploy,
model install, content upload, and workflow execution steps into one place.

> **TL;DR:** For V2V where you want to upload your own videos, use **Pods mode**
> (not Serverless). It gives you a persistent ComfyUI WebUI for drag-and-drop
> uploads plus SSH/scp access. Serverless is API-only and requires base64-encoding
> video into the job payload.

---

## Table of Contents

1. [Pick Your GPU / VRAM Tier](#1-pick-your-gpu--vram-tier)
2. [Build & Push the Docker Image](#2-build--push-the-docker-image)
3. [Deploy a Pod (Persistent WebUI)](#3-deploy-a-pod-persistent-webui)
4. [Install LTX-2.3 Models Inside the Pod](#4-install-ltx-23-models-inside-the-pod)
5. [Upload Your Content (Input Videos)](#5-upload-your-content-input-videos)
6. [Load the V2V Workflow & Run](#6-load-the-v2v-workflow--run)
7. [Retrieve Your Output](#7-retrieve-your-output)
8. [Quick Reference: Full Sequence](#8-quick-reference-full-sequence)

---

## 1. Pick Your GPU / VRAM Tier

LTX-2.3 is a 22B-parameter model. Your GPU choice determines which checkpoint
format and example workflow you use:

| VRAM | RunPod GPU | Checkpoint | Workflow File | COMFYUI_ARGS |
|------|-----------|------------|---------------|--------------|
| **8-12GB** | RTX A4000 (16GB), RTX 2060 | GGUF Q4 quantized | [`examples/ltx23_v2v_8gb_gguf.json`](../examples/ltx23_v2v_8gb_gguf.json) | `--lowvram --disable-smart-memory` |
| **24GB** (sweet spot) | RTX 4090, RTX A5000, A30 | fp8 checkpoint | [`examples/ltx23_v2v_runpod_fp8.json`](../examples/ltx23_v2v_runpod_fp8.json) | `--use-sage-attention --lowvram` |
| **32GB+** | A100 80GB, A6000 | bf16 full checkpoint | official LTX-2.3 workflows | (default) |

The fp8 path (24GB) is what the official single-stage distilled V2V IC-LoRA
example uses — it's the recommended target if you can afford it.

For a detailed tier comparison (resolution, frame counts, output sizes), see
[`examples/ltx23_v2v_vram_tiers_README.md`](../examples/ltx23_v2v_vram_tiers_README.md).

---

## 2. Build & Push the Docker Image

The image must be in a registry RunPod can reach (ghcr.io by default):

```bash
# Set your GitHub credentials (token needs write:packages scope)
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=ghp_...

# Build and push (uses scripts/build.sh)
./scripts/build.sh --username $GITHUB_USERNAME --push
```

This tags the image as `ghcr.io/<your-username>/comfyui-serverless:latest`. See
[`scripts/build.sh`](../scripts/build.sh) for details.

> **Note:** The default [`config/runpod-config-pods.json`](../config/runpod-config-pods.json)
> hardcodes `ghcr.io/aaronghent/comfyui-serverless:latest` — update the `image`
> field to your own pushed image before deploying, or pass `--image` to
> `deploy.sh` (which overrides the config file).

---

## 3. Deploy a Pod (Persistent WebUI)

```bash
export RUNPOD_API_KEY=rpa_...

./scripts/deploy.sh --mode pods \
    --name ltx23-v2v \
    --image ghcr.io/$GITHUB_USERNAME/comfyui-serverless:latest \
    --gpu "NVIDIA RTX 4090"   # or "NVIDIA RTX A4000" for the 8GB GGUF path
```

Key options from [`scripts/deploy.sh`](../scripts/deploy.sh):

| Option | Purpose |
|--------|---------|
| `--volume-id <ID>` | Reuse an existing network volume (preserves models between deploys) |
| `--spot` | Cheaper but interruptible (pods only) |
| `--gpu "NVIDIA RTX A4000"` | 16GB — GGUF path |
| `--gpu "NVIDIA RTX 4090"` | 24GB — fp8 path (recommended) |
| `--gpu "NVIDIA A100 80GB PCIe"` | 80GB — bf16 path |

⚠️ **Pods bill continuously while they exist.** Stopping a pod does NOT stop
billing — you must **terminate** it when done:

```bash
runpodctl stop pod <POD_ID> --terminate
```

---

## 4. Install LTX-2.3 Models Inside the Pod

Once the pod is running, get a shell (RunPod console → "Connect" → "Start Web
Terminal", or SSH) and run the install script with the profile matching your VRAM:

```bash
cd /workspace

# For gated Lightricks IC-LoRAs (decompression, colorization, etc.)
export HF_TOKEN=hf_...   # get from https://huggingface.co/settings/tokens

# 24GB GPU (fp8 path):
./scripts/install_ltx23.sh --profile mid_vram_12_24gb

# 8-12GB GPU (GGUF path):
./scripts/install_ltx23.sh --profile low_vram_8gb

# Or install specific models only:
./scripts/install_ltx23.sh --ids checkpoint_fp8 distilled_lora \
    iclora_decompression omninft_rl_lora spatial_upscaler
```

This installs (see [`scripts/install_ltx23.sh`](../scripts/install_ltx23.sh) and
[`config/ltx-2.3-models.json`](../config/ltx-2.3-models.json)):

- **ComfyUI-LTXVideo** custom nodes (IC-LoRA guide/loader nodes)
- **ComfyUI-GGUF** custom nodes (for quantized checkpoints)
- Models into `/runpod-volume/models/` (persists on the network volume)

### Gated Repos

Most official `Lightricks/LTX-2.3-22b-IC-LoRA-*` repos are gated
(instant-approve, but require an explicit click):

1. Visit the repo page on huggingface.co (e.g.
   `https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Decompression`)
2. Click **"Agree and Access"**
3. Generate a token at https://huggingface.co/settings/tokens (read access is enough)
4. Set `HF_TOKEN` before running the install script

Ungated alternatives are included where available (e.g.
`iclora_colorizer_doctordiffusion` instead of the gated official colorization LoRA).

**Restart ComfyUI** after install (or restart the pod) so it picks up the new
custom nodes.

---

## 5. Upload Your Content (Input Videos)

You have several options depending on your workflow and mode:

### Option A: WebUI Upload (Easiest — Pods mode)

1. Open the ComfyUI WebUI via the RunPod proxy URL:
   `https://<pod-id>-8188.proxy.runpod.net`
2. Drag-and-drop your input video into the ComfyUI canvas, or use the
   `VHS_LoadVideo` node's file picker after placing the file in the `input/`
   directory
3. The V2V workflows reference `input_video.mp4` — either name your file that,
   or update the node's `video` field to match your filename

### Option B: SSH / scp (Pods mode with SSH enabled)

Enable SSH in your pod env (`ENABLE_SSH=true`, `SSH_PUBLIC_KEY=ssh-rsa ...`),
then upload directly to the pod's input directory:

```bash
# Upload a video to the pod's input directory
scp -P 2222 my_video.mp4 root@<pod-host>:/runpod-volume/input/input_video.mp4
```

See [`ssh/setup_ssh.sh`](../ssh/setup_ssh.sh) and
[`docs/WEBUI_ACCESS.md`](WEBUI_ACCESS.md) for SSH setup details.

### Option C: Network Volume (Pre-load before deploy)

Upload files to your RunPod network volume via the RunPod console's file
manager, then attach that volume to the pod with `--volume-id`. Files placed in
`/runpod-volume/input/` are immediately available to ComfyUI on startup.

This is the best option if you have many videos to process — upload them once to
the volume, and they persist across pod restarts.

### Option D: Serverless API (base64 — for automation)

If using Serverless mode, embed the video as base64 in the job request (see
[`src/handler.py`](../src/handler.py) `upload_images()`):

```bash
# Base64-encode the video
VIDEO_B64=$(base64 -w0 my_video.mp4)

curl -X POST https://api.runpod.ai/v2/<ENDPOINT_ID>/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"input\": {
      \"workflow\": <workflow JSON>,
      \"input_images\": {
        \"input_video.mp4\": \"$VIDEO_B64\"
      }
    }
  }"
```

> **Note:** The handler's `upload_images()` expects base64 strings. For large
> videos, Options A-C (Pods mode) are far more practical than base64-encoding a
> multi-MB file into a JSON payload.

---

## 6. Load the V2V Workflow & Run

1. Open ComfyUI WebUI (`https://<pod-id>-8188.proxy.runpod.net`)
2. Drag one of these workflow JSON files onto the canvas:
   - **24GB GPU:** [`examples/ltx23_v2v_runpod_fp8.json`](../examples/ltx23_v2v_runpod_fp8.json)
     — fp8 checkpoint + distilled LoRA + decompression IC-LoRA + OmniNFT RL LoRA,
     960×544, 257 frames
   - **8GB GPU:** [`examples/ltx23_v2v_8gb_gguf.json`](../examples/ltx23_v2v_8gb_gguf.json)
     — GGUF Q4 quantized, 512×320, 73 frames
3. Verify the `VHS_LoadVideo` node points to your uploaded video (e.g.
   `input_video.mp4`)
4. Adjust prompts in the `CLIPTextEncode` nodes
5. Click **Queue Prompt**

### Workflow Structure (what's happening)

Both V2V workflows follow the same pipeline (see
[`examples/ltx23_v2v_runpod_fp8.json`](../examples/ltx23_v2v_runpod_fp8.json)):

1. `CheckpointLoaderSimple` / `UnetLoaderGGUF` → load the model
2. `LoraLoader` → distilled speed LoRA (enables 8-step sampling)
3. `LTXICLoRALoaderModelOnly` → stack IC-LoRAs (decompression, OmniNFT, etc.)
4. `VHS_LoadVideo` → your input video
5. `LTXVImgToVideoConditionOnly` + `LTXAddVideoICLoRAGuide` → condition on input frames
6. Two-pass sampling: low-res → `LTXVLatentUpsampler` → high-res refine
7. `LTXVTiledVAEDecode` → tiled decode (prevents edge artifacts)
8. `VHS_VideoCombine` → output MP4

### Swapping IC-LoRAs

Replace the `lora_name` in the `LTXICLoRALoaderModelOnly` nodes with any from
the catalog in [`docs/LTX_2.3_V2V_ICLORA_SETUP.md`](LTX_2.3_V2V_ICLORA_SETUP.md)
— e.g. `iclora_colorization`, `iclora_day_to_night`, `iclora_deblur`,
`iclora_water_simulation`, etc. Download them first with:

```bash
./scripts/install_ltx23.sh --ids <model_id>
```

### Disabling Audio (saves VRAM)

LTX-2.3 generates video and audio jointly by default. If you only need video
output, disabling the audio branch saves ~2-3GB VRAM. This is workflow-level
(not a CLI flag) — bypass `LTXVAudioVAELoader` and downstream audio nodes. See
[`docs/LTX_2.3_V2V_ICLORA_SETUP.md`](LTX_2.3_V2V_ICLORA_SETUP.md) for details.

---

## 7. Retrieve Your Output

- **Pods mode:** Output MP4s are saved to `/runpod-volume/output/` (or
  ComfyUI's `output/` dir). Download via WebUI, SSH/scp, or RunPod console file
  manager.
- **Serverless mode:** Output is returned in the job response (base64) or saved
  to S3/volume depending on `STORAGE_TYPE` (see
  [`src/handler.py`](../src/handler.py) `process_outputs()`).

### Getting 1080p Output

The two-pass fp8 workflow outputs ~1920×1088. For true 1080p or higher, add a
super-resolution pass — see
[`examples/ltx23_v2v_music_visuals_patch_README.md`](../examples/ltx23_v2v_music_visuals_patch_README.md)
for FlashVSR / USDU options.

---

## 8. Quick Reference: Full Sequence

```bash
# 1. Build & push image
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=ghp_...
./scripts/build.sh --username $GITHUB_USERNAME --push

# 2. Deploy pod
export RUNPOD_API_KEY=rpa_...
./scripts/deploy.sh --mode pods --name ltx23-v2v \
    --image ghcr.io/$GITHUB_USERNAME/comfyui-serverless:latest \
    --gpu "NVIDIA RTX 4090"

# 3. SSH in (or use RunPod web terminal), install models
cd /workspace
export HF_TOKEN=hf_...
./scripts/install_ltx23.sh --profile mid_vram_12_24gb

# 4. Upload your video (via WebUI drag-drop, scp, or network volume)

# 5. Open WebUI, load examples/ltx23_v2v_runpod_fp8.json, queue

# 6. When done — TERMINATE the pod (stopping doesn't stop billing!)
runpodctl stop pod <POD_ID> --terminate
```

---

## Related Documentation

- [`docs/LTX_2.3_V2V_ICLORA_SETUP.md`](LTX_2.3_V2V_ICLORA_SETUP.md) — full
  IC-LoRA catalog, VRAM tiers, audio disabling
- [`docs/LTX_2.3_LOCAL_AND_RUNPOD_TESTING.md`](LTX_2.3_LOCAL_AND_RUNPOD_TESTING.md)
  — local→RunPod testing checklist
- [`docs/WEBUI_ACCESS.md`](WEBUI_ACCESS.md) — WebUI access methods in all modes
- [`examples/ltx23_v2v_music_visuals_patch_README.md`](../examples/ltx23_v2v_music_visuals_patch_README.md)
  — parameter guide for the music-visuals V2V variant
- [`examples/ltx23_v2v_vram_tiers_README.md`](../examples/ltx23_v2v_vram_tiers_README.md)
  — detailed 8GB vs 24GB tier comparison
- [`docs/LTX_2.3_WORKFLOW_ENHANCEMENTS.md`](LTX_2.3_WORKFLOW_ENHANCEMENTS.md) —
  scheduler tuning, sampler benchmarks, segment chaining, beat detection
