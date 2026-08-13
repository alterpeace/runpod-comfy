# RunPod Serverless Guide

Complete guide for deploying, managing, and using ComfyUI on RunPod Serverless.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Deploying the Serverless Endpoint](#deploying-the-serverless-endpoint)
- [Installing Models on the Network Volume](#installing-models-on-the-network-volume)
- [Uploading Videos and Files](#uploading-videos-and-files)
- [Caching Strategy](#caching-strategy)
- [Running Workflows via API](#running-workflows-via-api)
- [SeedVR2 Video Upscaling](#seedvr2-video-upscaling)
- [LTX-2.5 Video Generation](#ltx-25-video-generation)
- [Managing the Endpoint](#managing-the-endpoint)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Set your API key
cp .env.example .env
# Edit .env: set RUNPOD_API_KEY, HF_TOKEN, GITHUB_USERNAME

# 2. Deploy serverless endpoint
./scripts/run_runpod.sh serverless deploy

# 3. Install LTX-2.5 models on the network volume (via SSH)
# See: Installing Models on the Network Volume

# 4. Upload videos to upscale
.venv/bin/python scripts/upload_to_runpod.py video.mp4 --subfolder upscale_test

# 5. Run a workflow via API
# See: Running Workflows via API
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 RunPod Serverless                     │
│                                                       │
│  ┌──────────┐    ┌──────────────────────────────┐   │
│  │  API     │───▶│  Worker Pod (RTX A4000/4090) │   │
│  │  Gateway │    │  ┌────────────────────────┐  │   │
│  │          │    │  │  ComfyUI + Handler     │  │   │
│  │          │    │  │  (ghcr.io/alterpeace/   │  │   │
│  │          │    │  │   runpod-comfy:latest)  │  │   │
│  │          │    │  └───────────┬────────────┘  │   │
│  │          │    │              │               │   │
│  │          │    │  ┌───────────▼────────────┐  │   │
│  │          │    │  │  /runpod-volume/       │  │   │
│  │          │    │  │  ├── models/           │  │   │
│  │          │    │  │  ├── custom_nodes/     │  │   │
│  │          │    │  │  ├── input/            │  │   │
│  │          │    │  │  ├── output/           │  │   │
│  │          │    │  │  ├── hf-cache/         │  │   │
│  │          │    │  │  └── .env              │  │   │
│  │          │    │  │  (Network Volume —     │  │   │
│  │          │    │  │   persists across      │  │   │
│  │          │    │  │   pod restarts)        │  │   │
│  │          │    │  └────────────────────────┘  │   │
│  └──────────┘    └──────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Key points:**
- Workers scale to zero when idle (no cost when not processing jobs)
- The network volume persists across pod restarts — models, custom nodes, and uploaded files survive
- Container storage (`/workspace`, `~/.cache`) is ephemeral — lost on pod restart
- The handler (`src/handler.py`) receives jobs, uploads input images, runs the ComfyUI workflow, and returns outputs

---

## Deploying the Serverless Endpoint

### Prerequisites

- `RUNPOD_API_KEY` set in `.env`
- Docker image pushed to GHCR: `ghcr.io/alterpeace/runpod-comfy:latest`
- Network volume created in RunPod dashboard (100GB+ recommended)

### Deploy

```bash
# Deploy using the lifecycle script
./scripts/run_runpod.sh serverless deploy \
  --name comfyui-serverless \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --gpu "NVIDIA RTX A4000" \
  --volume-id <your-volume-id>

# Or use the deploy script directly
./scripts/deploy.sh --mode serverless \
  --name comfyui-api \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --gpu "NVIDIA RTX A4000"
```

### Check status

```bash
./scripts/run_runpod.sh serverless status
```

### GPU types

| GPU | VRAM | Cost/hr | Best for |
|-----|------|---------|----------|
| NVIDIA RTX A4000 | 16GB | ~$0.35 | LTX-2.5, SeedVR2 3B |
| NVIDIA RTX A5000 | 24GB | ~$0.45 | SeedVR2 7B, LTX-2.5 full |
| NVIDIA RTX 4090 | 24GB | ~$0.50 | Fastest inference |
| ADA_24 (RTX 6000 Ada) | 48GB | ~$0.80 | Large batch sizes |

---

## Installing Models on the Network Volume

Models must be installed on the network volume so they persist across pod restarts. There are two methods:

### Method 1: SSH into a worker pod (recommended)

```bash
# SSH into the serverless worker pod
ssh <pod-id>-<worker-id>@ssh.runpod.io -i ~/.ssh/id_ed25519

# Inside the SSH session:
git clone https://github.com/alterpeace/runpod-comfy.git /tmp/runpod-comfy
cd /tmp/runpod-comfy

# Set environment variables
export HF_TOKEN=hf_your_token_here
export CUSTOM_NODES_DIR=/runpod-volume/custom_nodes
export MODELS_DIR=/runpod-volume/models
export HF_HOME=/runpod-volume/hf-cache  # Cache HF downloads on volume

# Install LTX-2.5 models
./scripts/install_ltx25.sh --profile mid_vram_24gb

# Or install LTX-2.3 models
./scripts/install_ltx23.sh --profile low_vram_8gb
```

### Method 2: Use the download_models API action

```bash
# Submit a download_models job via the RunPod API
curl -X POST https://api.runpod.ai/v2/<endpoint-id>/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "action": "download_models",
      "profile": "mid_vram_24gb",
      "manifest": "ltx25"
    }
  }'
```

### VRAM profiles

| Profile | Models included | Total size | Min VRAM |
|---------|----------------|------------|----------|
| `low_vram_8gb` | Quantized checkpoints, essential LoRAs | ~8GB | 8GB |
| `mid_vram_24gb` | FP8 checkpoints, all LoRAs, VAE | ~20GB | 16GB |
| `full` | FP16 checkpoints, everything | ~40GB | 24GB |

---

## Uploading Videos and Files

Use the upload script to transfer files to the network volume:

```bash
# Upload a single video
.venv/bin/python scripts/upload_to_runpod.py video.mp4

# Upload to a subfolder under input/
.venv/bin/python scripts/upload_to_runpod.py video.mp4 --subfolder upscale_test

# Upload an entire directory (recursive)
.venv/bin/python scripts/upload_to_runpod.py /path/to/clips --subfolder montked

# List files on the volume
.venv/bin/python scripts/upload_to_runpod.py --list

# Keep the temp pod running for SSH access
.venv/bin/python scripts/upload_to_runpod.py video.mp4 --keep-pod
```

The script:
1. Creates a temporary RunPod pod with the network volume mounted
2. Creates the folder structure (`input/`, `output/`, `models/`, etc.)
3. Uploads files via SCP
4. Terminates the temp pod

### Folder structure on the volume

```
/runpod-volume/
├── input/              # Uploaded videos/images
│   ├── montked/        # Subfolder example
│   │   ├── clip_001.mp4
│   │   └── clip_002.mp4
│   └── upscale_test/
│       └── video.mp4
├── output/             # Generated outputs
├── models/             # AI models
│   ├── checkpoints/
│   ├── loras/
│   ├── vae/
│   └── SEEDVR2/
├── custom_nodes/       # ComfyUI custom nodes
├── user/               # ComfyUI user data
├── hf-cache/           # HuggingFace download cache (if HF_HOME set)
└── .env                # Configuration file (optional)
```

### Referencing uploaded files in workflows

In ComfyUI workflows, reference files relative to the input directory:

```
VHS_LoadVideo video: input/montked/clip_001.mp4
```

This resolves to `/runpod-volume/input/montked/clip_001.mp4` on the worker.

---

## Caching Strategy

### What persists on the network volume

| Path | Persists? | Purpose |
|------|-----------|---------|
| `/runpod-volume/models/` | ✅ Yes | AI model files (checkpoints, LoRAs, VAEs) |
| `/runpod-volume/custom_nodes/` | ✅ Yes | ComfyUI custom node packages |
| `/runpod-volume/input/` | ✅ Yes | Uploaded input files |
| `/runpod-volume/output/` | ✅ Yes | Generated output files |
| `/runpod-volume/hf-cache/` | ✅ Yes (if `HF_HOME` set) | HuggingFace download cache |
| `/runpod-volume/.env` | ✅ Yes | Configuration file |

### What is ephemeral (lost on pod restart)

| Path | Purpose | Impact |
|------|---------|--------|
| `~/.cache/huggingface/` | Default HF cache | Re-download if `HF_HOME` not set |
| `/cache/uv/` | pip/uv package cache | Slower custom node dep install on boot |
| `/workspace/` | Handler scripts | Baked into image, no impact |
| `/comfyui/` | ComfyUI core | Baked into image, no impact |

### Recommended: Cache HF downloads on the volume

Set `HF_HOME=/runpod-volume/hf-cache` when installing models:

```bash
export HF_HOME=/runpod-volume/hf-cache
./scripts/install_ltx25.sh --profile mid_vram_24gb
```

**Benefits:**
- HuggingFace downloads cached on the volume (no re-downloads on pod restart)
- Subsequent `install_ltx25.sh` runs are instant (cache hits)
- Models copied from cache to `models/` directory

**Trade-off:**
- Uses ~2x disk space (HF cache + model copies)
- 100GB volume recommended for `mid_vram_24gb` profile with cache

### How the install script handles symlinks vs copies

The install script at `scripts/install_ltx25.sh` auto-detects:
- **Same filesystem** (local dev): Creates symlinks from `models/` → HF cache (saves space)
- **Different filesystem** (RunPod volume): Copies files to `models/` (persists independently)

This is controlled by comparing device IDs (`stat -c %d`) of the models directory and HF cache.

---

## Running Workflows via API

### Submit a workflow job

```bash
curl -X POST https://api.runpod.ai/v2/<endpoint-id>/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "workflow": { ... },
      "timeout": 3600
    }
  }'
```

### Job input format

```json
{
  "input": {
    "action": "run_workflow",
    "workflow": { "1": {"class_type": "LoadImage", "inputs": {...}}, ... },
    "input_images": {
      "image1.png": "base64_encoded_data..."
    },
    "timeout": 3600,
    "clear_cache": true
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `workflow` | Yes | ComfyUI workflow in API format (not UI format) |
| `input_images` | No | Dict of `{filename: base64_data}` for image inputs |
| `timeout` | No | Custom timeout in seconds (default: 300) |
| `clear_cache` | No | Clear latent cache before execution (default: true) |
| `action` | No | `run_workflow` (default) or `download_models` |

### Check job status

```bash
curl https://api.runpod.ai/v2/<endpoint-id>/status/<job-id> \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

### Converting UI workflows to API format

1. Open ComfyUI at http://localhost:8188
2. Load the workflow JSON (drag into UI)
3. Configure nodes (set video paths, model selections, etc.)
4. Click **Settings → Save (API Format)**
5. Submit the saved JSON via the API

### Python helper

```python
import requests, os, json

api_key = os.environ["RUNPOD_API_KEY"]
endpoint_id = "taea2mhlwbdkuq"  # your endpoint ID

# Submit job
workflow = json.load(open("workflow_api.json"))
r = requests.post(
    f"https://api.runpod.ai/v2/{endpoint_id}/run",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={"input": {"workflow": workflow, "timeout": 3600}}
)
job_id = r.json()["id"]

# Poll for completion
import time
while True:
    r = requests.get(
        f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    status = r.json()["status"]
    if status in ["COMPLETED", "FAILED", "CANCELLED"]:
        print(r.json())
        break
    time.sleep(10)
```

---

## SeedVR2 Video Upscaling

### Available models

| Model | Size | VRAM (min) | Quality | Speed |
|-------|------|------------|---------|-------|
| `seedvr2_ema_3b-Q4_K_M.gguf` | ~2GB | 8GB | Acceptable | Fast |
| `seedvr2_ema_3b-Q8_0.gguf` | ~3.5GB | 8GB | Good | Fast |
| `seedvr2_ema_3b_fp8_e4m3fn.safetensors` | ~3.5GB | 12GB | Good | Fast |
| `seedvr2_ema_3b_fp16.safetensors` | ~6GB | 16GB | Best (3B) | Medium |
| `seedvr2_ema_7b_fp8_e4m3fn_mixed_block35_fp16.safetensors` | ~7GB | 16GB | Good | Medium |
| `seedvr2_ema_7b_fp16.safetensors` | ~14GB | 24GB | Best (7B) | Slow |
| `seedvr2_ema_7b_sharp_fp16.safetensors` | ~14GB | 24GB | Best + Sharp | Slow |

### Cloud Burst workflow

The workflow at `examples/seedvr2_cloud_burst_comparison.json` compares 4 configurations:

1. **Local 3B GGUF Q4 → 1080p** (8GB VRAM: BlockSwap 32, VAE tiled 512px)
2. **Cloud 7B FP16 → 1080p** (24GB VRAM: batch_size=21, temporal_overlap=4)
3. **Cloud 7B FP16 → 4K/2160p** (24GB VRAM: 10-bit H265 output)
4. **Local 3B GGUF Q4 → 720p** (quick preview)

### Batch size formula

SeedVR2 requires `batch_size` to follow the **4n+1 formula**: 1, 5, 9, 13, 17, 21, 25, ...

Higher batch sizes = better temporal consistency but more VRAM.

### Low VRAM settings (8GB)

```
DiT Model: seedvr2_ema_3b-Q4_K_M.gguf
  blocks_to_swap: 32
  swap_io_components: true
  offload_device: cpu
VAE:
  encode_tiled: true, tile_size: 512
  decode_tiled: true, tile_size: 512
Upscaler:
  batch_size: 5
  resolution: 720
```

### High VRAM settings (24GB)

```
DiT Model: seedvr2_ema_7b_fp16.safetensors
  blocks_to_swap: 0
  offload_device: none
VAE:
  encode_tiled: false
  decode_tiled: false
Upscaler:
  batch_size: 21
  resolution: 1080 (or 2160 for 4K)
  temporal_overlap: 4
  prepend_frames: 4
```

---

## LTX-2.5 Video Generation

See [`docs/LTX_2.5_SETUP.md`](LTX_2.5_SETUP.md) for detailed LTX-2.5 setup instructions.

### Quick install

```bash
# On the RunPod pod via SSH:
export HF_TOKEN=hf_your_token
export CUSTOM_NODES_DIR=/runpod-volume/custom_nodes
export MODELS_DIR=/runpod-volume/models
export HF_HOME=/runpod-volume/hf-cache
./scripts/install_ltx25.sh --profile mid_vram_24gb
```

### VRAM profiles

| Profile | Checkpoint | LoRAs | VAE | Total |
|---------|-----------|-------|-----|-------|
| `low_vram_8gb` | Dev INT8 (quantized) | Distilled LoRA | FP8 | ~8GB |
| `mid_vram_24gb` | Dev FP8 | All LoRAs | FP16 | ~20GB |
| `full` | Dev FP16 + Distilled FP16 | All LoRAs | FP16 | ~40GB |

---

## Managing the Endpoint

### List endpoints

```bash
./scripts/run_runpod.sh serverless status
```

### View logs

```bash
./scripts/run_runpod.sh serverless logs
```

### Terminate endpoint

```bash
./scripts/run_runpod.sh serverless delete <endpoint-id>
```

### Update the Docker image

```bash
# Build and push new image
./scripts/build.sh --username alterpeace --push

# RunPod auto-pulls the latest image on next worker start
# (no need to restart the endpoint)
```

### Environment variables

Set these in `.env` and upload to the volume, or set in the RunPod dashboard:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | auto-detected | `serverless` (auto-detected on RunPod) |
| `COMFYUI_PORT` | 8188 | ComfyUI server port |
| `COMFYUI_ARGS` | `--use-sage-attention --lowvram` | ComfyUI startup args |
| `STORAGE_TYPE` | `response` | `response`, `volume`, or `s3` |
| `STORAGE_BACKEND` | `network-volume` | `network-volume`, `b2-mount`, or `b2-sync` |
| `HF_TOKEN` | (none) | HuggingFace token for gated models |
| `HF_HOME` | `~/.cache/huggingface` | HF cache directory (set to `/runpod-volume/hf-cache` for persistence) |

---

## Troubleshooting

### Worker won't start

```bash
# Check endpoint status
./scripts/run_runpod.sh serverless status

# Common issues:
# - Image not found: ensure ghcr.io/alterpeace/runpod-comfy:latest is pushed
# - Volume not attached: check volume_id in endpoint config
# - GPU unavailable: try a different GPU type
```

### Models not found

```bash
# SSH into the pod and check
ssh <pod-id>@ssh.runpod.io -i ~/.ssh/id_ed25519
ls /runpod-volume/models/
ls /runpod-volume/models/SEEDVR2/

# Re-install if missing
cd /tmp/runpod-comfy
export CUSTOM_NODES_DIR=/runpod-volume/custom_nodes
export MODELS_DIR=/runpod-volume/models
export HF_HOME=/runpod-volume/hf-cache
./scripts/install_ltx25.sh --profile mid_vram_24gb
```

### Job timeout

```bash
# Increase timeout in the job payload
curl -X POST https://api.runpod.ai/v2/<endpoint-id>/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -d '{"input": {"workflow": {...}, "timeout": 3600}}'
```

### Custom node import failures

```bash
# Check worker logs
./scripts/run_runpod.sh serverless logs

# SSH in and check
ssh <pod-id>@ssh.runpod.io -i ~/.ssh/id_ed25519
docker logs $(docker ps -q) 2>&1 | grep "IMPORT FAILED"
```

### Out of memory (OOM)

- Use a smaller model (3B instead of 7B)
- Enable BlockSwap (`blocks_to_swap: 32`)
- Enable VAE tiling (`encode_tiled: true`, `decode_tiled: true`)
- Reduce `batch_size` (must follow 4n+1: 5, 9, 13...)
- Reduce `resolution`
- Use GGUF quantized models (`Q4_K_M` or `Q8_0`)
