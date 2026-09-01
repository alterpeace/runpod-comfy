# SkyPilot — Multi-DC LTX-2.5 GPU Instances, Ordered CLI Guide

SkyPilot boots the full LTX-2.5 + SeedVR2 stack on the **cheapest available
48GB GPU across all your configured clouds and datacenters** (RunPod, Lambda
Labs, Vast.ai — SkyPilot picks automatically, or you pin one). Two modes:

| Mode | Command | Behavior |
|---|---|---|
| **Single instance** | `sky launch` | One GPU, WebUI via port-forward, you manage start/stop |
| **Autoscaled endpoint** | `sky serve up` | Load-balanced replicas, scale-to-zero — SkyPilot's serverless mode |

Both use the same task file: [`scripts/skypilot/ltx25-48gb.yaml`](../scripts/skypilot/ltx25-48gb.yaml).

---

## Step 0 — One-time prerequisites (local machine)

```bash
# Install SkyPilot
pip install skypilot

# Verify which clouds SkyPilot can reach (enables multi-DC picking)
sky check
```

Add API keys to `.env` in the project root (launch.sh loads it automatically):

```bash
# .env
HF_TOKEN=hf_...            # REQUIRED — LTX-2.5 repos are gated
RUNPOD_API_KEY=rpa_...     # for RunPod DCs
LAMBDA_CLOUD_API_KEY=...   # for Lambda DCs (optional)
VAST_API_KEY=...           # for Vast.ai DCs (optional)
```

Get the HF token at <https://huggingface.co/Lightricks/LTX-2.5> →
"Agree and Access and get token".

### Enabling additional providers (multi-cloud cheapest-first)

SkyPilot only considers **enabled** clouds. `sky status` showed
`Enabled Infra: runpod` — that's why every candidate was RunPod. To add more:

```bash
# 1. Put each provider's credentials where SkyPilot expects them
#    Lambda Labs (cloud.lambda.ai → API keys):
export LAMBDA_CLOUD_API_KEY=...
#    Vast.ai (console.vast.ai → API keys):
export VAST_API_KEY=...
#    AWS (any region with GPU capacity):
aws configure
#    GCP: gcloud auth application-default login  (or a service account)
#    Azure: az login

# 2. Re-scan — SkyPilot enables every cloud it finds credentials for
sky check

# 3. Confirm
sky status          # "Enabled Infra" should now list all of them
sky gpus L40S --all # browse L40S prices/availability across ALL enabled clouds
```

Once two or more clouds are enabled, `./scripts/skypilot/launch.sh` (no
`--cloud` flag) automatically considers **every enabled cloud and every
region** and provisions the cheapest GPU that's actually in stock — the
14-region sweep you saw was RunPod-only; with Lambda/Vast enabled the same
sweep covers their DCs too. Pin one with `--cloud lambda` / `--cloud vast`
when you want to force it.

Notes per provider:

| Provider | 48GB GPUs | Setup notes |
|---|---|---|
| RunPod | L40S, RTX 6000 Ada, A6000, A40 | Secure Cloud only via SkyPilot; keys in `.env` |
| Lambda | L40S, A100, H100 | Simple API key; on-demand only |
| Vast.ai | L40S, RTX 6000 Ada, A6000, 4090... | Usually cheapest; interruptible pricing |
| AWS | A10G, L4, A100, H100 | No 48GB single-die GPU except A100 80GB (pricier) |
| GCP | L4, A100 | Same as AWS |
| Azure | A100, NC-series | Same as AWS |

The task yaml is cloud-agnostic (no pinned image, driver installed by
SkyPilot), so nothing else changes — the same setup script runs on any of
them.

---

## Step 1 — Boot (multi-DC)

```bash
# SkyPilot picks the CHEAPEST available 48GB GPU across ALL configured clouds
./scripts/skypilot/launch.sh

# Or pin a specific cloud / DC
./scripts/skypilot/launch.sh --cloud runpod
./scripts/skypilot/launch.sh --cloud lambda
./scripts/skypilot/launch.sh --cloud vast      # usually cheapest

# Pin a GPU type (default L40S:1)
./scripts/skypilot/launch.sh --gpu A6000:1

# 24GB fallback (RTX 4090, adds --lowvram automatically)
./scripts/skypilot/launch.sh --24gb
```

First launch: **~20–40 min** (installs ComfyUI + custom nodes via `uv`,
downloads ~90GB of models). Later launches reuse the disk: **~2 min**.

What gets installed: ComfyUI core, ComfyUI-LTXVideo, ComfyUI-GGUF,
VideoHelperSuite, ComfyUI-SeedVR2_VideoUpscaler, the `h264-allintra` video
format, all LTX-2.5 int8-convrot models, the Q5_K_M GGUF, and SeedVR2 3B + VAE.

---

## Step 2 — Interact

### Option A: single instance (WebUI)

```bash
./scripts/skypilot/launch.sh port-forward   # WebUI at http://localhost:8188
./scripts/skypilot/launch.sh ssh            # shell into the machine
```

Then in the WebUI: upload your source video, load a workflow from
[`examples/`](../examples/), queue it, download the output.

### Option B: autoscaled endpoint (serverless-like)

Uncomment the `service:` block in
[`scripts/skypilot/ltx25-48gb.yaml`](../scripts/skypilot/ltx25-48gb.yaml), then:

```bash
sky serve up ltx25-service scripts/skypilot/ltx25-48gb.yaml
sky serve status ltx25-service              # endpoint URL + replica health
```

Submit jobs to the printed endpoint URL with ComfyUI's HTTP API:

```bash
# Queue a workflow (API format) against the served endpoint
curl -X POST http://<endpoint>:30001/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": <workflow-json>}'

# Poll history for results
curl http://<endpoint>:30001/history
```

Replicas scale 0→2 with load (`min_replicas: 0` = scale to zero = pay only
when processing), across DCs if multiple clouds are configured.

### Processing video (the old serverless flow, SkyPilot style)

The old RunPod flow was: upload to S3 → invoke endpoint → poll → download
from S3. The SkyPilot equivalent is one script that does upload → queue →
wait → download over the port-forwarded API:

```bash
# Terminal 1: boot + forward (leave running)
./scripts/skypilot/launch.sh
./scripts/skypilot/launch.sh port-forward

# Terminal 2: process videos — same UX as the old invoke_v2v_with_upload.py
uv run python scripts/invoke/invoke_skypilot.py --video rhizome.mp4

# Options: custom workflow, prompt, seed, output dir
uv run python scripts/invoke/invoke_skypilot.py --video clip.mp4 \
    --workflow examples/ltx25_v2v_redetail_entry_runpod.json \
    --prompt "cinematic, moody lighting" --seed 123 --out output/
```

The script ([`scripts/invoke/invoke_skypilot.py`](../scripts/invoke/invoke_skypilot.py))
uploads the video to ComfyUI's input, patches the workflow's `VHS_LoadVideo`
node, queues it, polls until done, and downloads the resulting MP4(s) to
`output/`. Default workflow: the SeedVR2-chained 1080p all-intra pipeline.

Batch processing = loop it:

```bash
for f in clips/*.mp4; do
  uv run python scripts/invoke/invoke_skypilot.py --video "$f"
done
./scripts/skypilot/launch.sh stop    # stop billing when the batch is done
```

Manual alternative: the WebUI (Step 2, Option A) — upload via the input
panel, load a workflow from [`examples/`](../examples/), queue, download
from the gallery.

---

## Step 3 — Cost control (ALWAYS do this)

```bash
./scripts/skypilot/launch.sh status         # what's running, where
./scripts/skypilot/launch.sh stop           # STOP billing, keep disk + models
./scripts/skypilot/launch.sh start          # resume later (~2 min)
./scripts/skypilot/launch.sh down           # TERMINATE — destroys disk + models
```

An idle L40S costs ~$0.55/hr. **`stop` whenever you walk away.** The
`sky serve` mode with `min_replicas: 0` handles this automatically (scales to
zero when idle).

---

## Cost reference (48GB tier)

| GPU | ~$/hr | Notes |
|---|---|---|
| L40S | 0.55 | Best Ada option for LTX-2.5 (default) |
| RTX 6000 Ada | 0.60 | Workstation Ada |
| A6000 | 0.45 | Ampere, slower but cheap |
| Vast.ai L40S | ~0.40–0.50 | Often cheapest; SkyPilot picks it if configured |

A 15s clip through the SeedVR2-chained workflow ≈ 6–10 min warm on L40S →
**~$0.06–0.10/clip**. A 156-clip batch ≈ $10–16 of GPU time.

---

## SkyPilot vs RunPod serverless

| | SkyPilot (`sky launch` / `sky serve`) | RunPod serverless |
|---|---|---|
| Multi-DC | ✅ any SkyPilot cloud, cheapest-first | RunPod DCs only |
| Billing | Per second while running | Per request execution |
| Scale to zero | `sky serve` with `min_replicas: 0`, or `stop` | Automatic |
| Cold start | One-time setup (~30 min), then ~2 min | ~1–4 min per cold worker |
| Best for | Interactive work, multi-cloud redundancy | High-volume batch via API |

For unattended high-volume batch on RunPod specifically, see
[`SERVERLESS_DEPLOY.md`](SERVERLESS_DEPLOY.md) and
[`scripts/build/setup_48gb_endpoint.py`](../scripts/build/setup_48gb_endpoint.py).
