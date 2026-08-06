# Booting ComfyUI Serverless on RunPod

End-to-end walkthrough for deploying the [`alterpeace/runpod-comfy`](https://github.com/alterpeace/runpod-comfy)
image as a **RunPod Serverless endpoint** (pay-per-execution, scales to zero).

The image is already built and hosted publicly at
`ghcr.io/alterpeace/runpod-comfy:latest` (tags: `latest`, `39760b5`, `ea4d316`),
so there is **no build step required** to boot serverless — you only need to
wire it up in the RunPod console (or via the CLI tools in this repo).

> For the interactive / persistent alternative (Pods), see
> [`docs/LTX_2.3_LOCAL_AND_RUNPOD_TESTING.md`](LTX_2.3_LOCAL_AND_RUNPOD_TESTING.md)
> and [`lifecycle/README.md`](../lifecycle/README.md). This doc focuses on the
> serverless path.

---

## TL;DR — the 5-minute path

1. Create a **Network Volume** in RunPod (one-time) to hold models/outputs.
2. Create a **Serverless Endpoint** pointing at
   `ghcr.io/alterpeace/runpod-comfy:latest`, attach the volume, set
   `MODE=serverless`.
3. Seed the volume with LTX-2.3 models (once).
4. Invoke the endpoint with a workflow JSON.
5. Set `workersMin=0` so it scales to zero and costs nothing when idle.

---

## Serverless vs Pods — which to pick

| | Serverless | Pods |
|---|---|---|
| Billing | Per execution (GPU-seconds) | Continuous while pod exists |
| Scales to zero | Yes (`workersMin=0`) | No — you terminate manually |
| Interface | API/JSON only (handler in [`src/handler.py`](../src/handler.py:1)) | WebUI on port 8188 |
| Cold start | Yes (worker boots on first job) | No — always warm |
| Best for | API workloads, batch, infrequent use | Interactive clicking, debugging |

**Recommendation:** start with a **Pod** to verify the image boots and models
load (you can see the WebUI), then move to **Serverless** for production API
use. The image supports both via the `MODE` env var.

---

## Prerequisites

- A RunPod account (you're already logged in at
  <https://console.runpod.io/serverless>).
- A RunPod API key for CLI use — generate at
  <https://www.runpod.io/console/user/settings> → "API Keys". Only needed if
  you use the CLI tools below; the web console path needs no key.
- (Optional, for gated Lightricks models) a Hugging Face token with
  `HF_TOKEN` set on the endpoint.

---

## Step 1 — Create a Network Volume (one-time)

Serverless workers are ephemeral — anything not on a network volume is lost
when the worker scales down. Models and outputs must live on a volume.

**Web console:** <https://www.runpod.io/console/user/storage> →
"Network Volumes" → "New Volume". 100 GB is enough for the LTX-2.3
`low_vram_8gb` profile; pick a region close to the GPUs you'll use
(e.g. `US-OR` for Oregon, `EU-RO-1` for Romania).

**CLI:**
```bash
export RUNPOD_API_KEY=...
# Volume creation isn't in the lifecycle CLI; use the console for this one.
```

Note the **Volume ID** (e.g. `v1abc...`) — you'll attach it to the endpoint.

---

## Step 2 — Create the Serverless Endpoint

### Option A — Web console (no API key needed)

1. Go to <https://console.runpod.io/serverless> → "New Endpoint".
2. Fill in:
   - **Endpoint name:** `comfyui-serverless`
   - **Container image:** `ghcr.io/alterpeace/runpod-comfy:latest`
   - **GPU type:** see "Choosing a GPU" below. For LTX-2.3 fp8: `RTX 4090`
     (24 GB) or `A100 80GB`. For the GGUF Q4 profile: `RTX A4000` (16 GB)
     works but is slow.
   - **Min workers:** `0` (scale to zero — no idle cost)
   - **Max workers:** `3` (tune to your concurrency)
   - **Idle timeout:** `5` minutes
   - **Network volume:** select the volume from Step 1, mount at
     `/runpod-volume`
   - **Container disk:** `50` GB
3. Under **Environment variables**, set at minimum:
   ```
   MODE=serverless
   COMFYUI_PORT=8188
   COMFYUI_ARGS=--use-sage-attention --lowvram
   ```
   Optional:
   ```
   STORAGE_TYPE=volume
   VOLUME_OUTPUT_PATH=/runpod-volume/outputs
   HF_TOKEN=hf_xxx            # only for gated Lightricks IC-LoRA repos
   TIMEOUT=600                # max seconds per job
   ```
4. Click **Create**. The first invocation will cold-start a worker (pulls the
   ~20 GB image + boots ComfyUI — expect 3–8 min on first job, faster after).

### Option B — CLI (uses [`lifecycle/runpod_serverless.py`](../lifecycle/runpod_serverless.py:1))

```bash
export RUNPOD_API_KEY=...

uv run python lifecycle/runpod_serverless.py create \
  --name comfyui-serverless \
  --gpu "RTX 4090" \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --min-workers 0 \
  --max-workers 3 \
  --idle-timeout 5 \
  --volume-id <YOUR_VOLUME_ID> \
  --volume-mount /runpod-volume \
  --env MODE=serverless \
  --env COMFYUI_PORT=8188 \
  --env COMFYUI_ARGS=--use-sage-attention --lowvram \
  --env STORAGE_TYPE=volume \
  --env VOLUME_OUTPUT_PATH=/runpod-volume/outputs
```

Or via the deploy helper ([`scripts/deploy.sh`](../scripts/deploy.sh:1)):
```bash
./scripts/deploy.sh --mode serverless \
  --name comfyui-serverless \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --gpu "RTX 4090" \
  --volume-id <YOUR_VOLUME_ID> \
  --min-workers 0 --max-workers 3 --idle-timeout 5
```

The CLI prints the **Endpoint ID** — save it.

---

## Step 3 — Seed the volume with models (once)

The image ships ComfyUI + custom nodes but **no models**. You have two paths:

### Path 1 — Seed via a temporary Pod (easiest, interactive)

1. Deploy a Pod with the same image + same volume (so the volume is
   writable from a shell):
   ```bash
   uv run python lifecycle/runpod_pods.py create \
     --name model-seed \
     --gpu "RTX A4000" --spot \
     --image ghcr.io/alterpeace/runpod-comfy:latest \
     --volume-id <YOUR_VOLUME_ID> \
     --env MODE=pods --env ENABLE_SSH=true
   ```
2. SSH in (or use the RunPod web terminal) and run the installer from
   [`scripts/install_ltx23.sh`](../scripts/install_ltx23.sh:1):
   ```bash
   docker exec -it <pod> bash
   cd /workspace
   export HF_TOKEN=hf_...   # only for gated repos
   ./scripts/install_ltx23.sh --profile low_vram_8gb   # or mid_vram_12_24gb / full
   ```
   Models land in `/runpod-volume/models/...` and persist on the volume.
3. **Terminate** the seed pod (don't just stop — stopping doesn't stop
   billing):
   ```bash
   uv run python lifecycle/runpod_pods.py terminate --pod-id <seed_pod_id>
   ```

### Path 2 — Seed from B2 / S3

If you already have models in Backblaze B2 (see
[`storage/B2_RUNPOD_QUICKSTART.md`](../storage/B2_RUNPOD_QUICKSTART.md:1)),
mount or sync them onto the volume instead of re-downloading.

The serverless handler reads models from `/runpod-volume/models` (set by
`entrypoint.sh` when `MODE=serverless` and a volume is mounted), so however
you populate that path is fine.

---

## Step 4 — Invoke the endpoint

### CLI

```bash
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id <ENDPOINT_ID> \
  --workflow examples/text_to_image_simple.json \
  --wait --timeout 600
```

The handler ([`src/handler.py`](../src/handler.py:1)) accepts a workflow JSON
under `input.workflow` and returns output URLs (to the volume or S3,
depending on `STORAGE_TYPE`).

### Raw HTTP (curl)

```bash
curl -X POST "https://api.runpod.io/v2/<ENDPOINT_ID>/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"workflow": <workflow-json>}}'
```
Then poll `https://api.runpod.io/v2/<ENDPOINT_ID>/status/<JOB_ID>`.

### Python SDK

```python
import runpod
runpod.api_key = os.environ["RUNPOD_API_KEY"]
endpoint = runpod.Endpoint("<ENDPOINT_ID>")
job = endpoint.run({"input": {"workflow": workflow_dict}})
print(job.output())
```

---

## Step 5 — Operate it

```bash
# Status / workers
uv run python lifecycle/runpod_serverless.py status --endpoint-id <ID>

# Scale up for production traffic
uv run python lifecycle/runpod_serverless.py update \
  --endpoint-id <ID> --min-workers 1 --max-workers 10

# Tear down when done (stops all billing)
uv run python lifecycle/runpod_serverless.py delete --endpoint-id <ID>
```

---

## Choosing a GPU

Match the GPU to the model profile you seeded (see
[`config/ltx-2.3-models.json`](../config/ltx-2.3-models.json:1)):

| Profile | VRAM needed | RunPod GPU | Notes |
|---|---|---|---|
| `low_vram_8gb` (GGUF Q4) | ~8–12 GB | RTX A4000 (16 GB) | Cheapest, slowest |
| `mid_vram_12_24gb` (fp8) | ~24 GB | RTX 4090 (24 GB) | Best price/perf |
| `full` (BF16) | 32 GB+ | A100 80GB / H100 | Highest quality, $$$ |

Serverless bills per GPU-second, so a faster GPU often costs *less* per job
than a slow one. For LTX-2.3 fp8 video, `RTX 4090` is the sweet spot.

---

## Cost shape

- `workersMin=0` → **zero cost when idle.** You only pay when a job is
  actually running.
- Per-execution cost ≈ `(cold_start_seconds + run_seconds) × GPU $/sec`.
- Cold start pulls the image layer cache on the worker; first-ever job on a
  fresh worker is 3–8 min, subsequent jobs on the same warm worker are fast
  until `idle_timeout` expires.

## Sizing for LTX-2.3 V2V redetailing (IC-LoRA)

Concrete numbers for the "redetail video clips with IC-LoRAs" workload, from
this repo's own benchmarks
([`examples/ltx23_v2v_music_visuals_patch_README.md`](../examples/ltx23_v2v_music_visuals_patch_README.md:199)):

### The segment model

- LTX-2.3 processes **max ~385 frames (~16 s @ 24 fps) per generation** — so
  a 15 s clip is the natural unit of work: **1 request = 1 × 15 s segment**.
- A 10-minute video = **40 requests** (600 s ÷ 15 s). Never send 10 minutes
  as one request — it exceeds the model's context and the job timeout.
- Chain segments by feeding the last frame of segment A as the first frame
  of segment B (`LTXVImgToVideoConditionOnly`); clean up to ~5 extensions.

### GPU placement by resolution

| Target | GPU tier | Why |
|---|---|---|
| 720p in/out, fp8 + distilled + ≤2 IC-LoRAs | **RTX 4090 24 GB** | Documented sweet spot; disable audio to reclaim 2–3 GB |
| 720p, audio on or 3+ stacked LoRAs | 48 GB tier (A6000/L40) | Headroom for LoRA stack + audio branch |
| 1080p output | 4090 for V2V pass **+ separate SR pass** | The V2V DiT runs at 640×352 regardless; 1080p comes from FlashVSR (~10 min per 16 s segment) or USDU (15–40 min) |
| BF16 checkpoint / heavy batching | A100 80 GB | Only case where A100 earns its 2.5× per-second price |

**A100 80 GB is overkill for fp8 720p redetailing** — the repo's own VRAM
table calls it that. It costs ~2.5× more per second than a 4090 but is not
2.5× faster on this workload.

### RTX 4090 24 GB vs A6000/A40 48 GB (the common toss-up)

For 40–45 × 15 s segments (one 10-min video) of fp8 V2V redetailing:

| | RTX 4090 24 GB | A6000 / A40 48 GB | L40/L40S 48 GB |
|---|---|---|---|
| Generation | Ada (sm_8.9) | Ampere (sm_8.6) | Ada (sm_8.9) |
| FP8 tensor cores | **Yes — fp8 checkpoint runs natively** | No — fp8 dequantized to bf16, slower | Yes |
| FP16/BF16 compute | ~83 TFLOPS | ~37–39 TFLOPS | ~90 TFLOPS |
| Memory bandwidth | 1,008 GB/s | 768 / 696 GB/s | 864 GB/s |
| VRAM headroom | Tight: audio off, ≤2 IC-LoRAs, `--lowvram` | Comfortable: audio on, 3+ LoRAs, BF16 possible | Comfortable |
| **SageAttention in the hosted image** | **Works** (compiled for 8.9) | **Won't load** — see warning below | Works |
| Time per 16 s segment | ~200 s (repo benchmark) | ~300–400 s (est.) | ~200 s (est.) |
| Serverless price (approx.) | ~$0.00031/s (~$1.12/hr) | ~$0.00049/s (~$1.76/hr) | ~$0.00058/s (~$2.09/hr) |
| **Cost per 45-segment video** | **~$2.80** | ~$7.70 | ~$5.20 |
| Wall-clock, 3 workers | ~50 min | ~88 min | ~50 min |

> **⚠️ Arch gotcha:** the hosted image compiles SageAttention with
> `TORCH_CUDA_ARCH_LIST=8.9` ([`Dockerfile`](../Dockerfile:26)) — Ada only.
> On A6000/A40 (Ampere, sm_8.6) the `--use-sage-attention` flag in the
> default `COMFYUI_ARGS` will fail to load its kernels. To use the 48 GB
> Ampere tier you must either rebuild with
> `TORCH_CUDA_ARCH_LIST="8.6;8.9"` or drop `--use-sage-attention` from
> `COMFYUI_ARGS` (PyTorch itself runs fine on 8.6 — it's only the
> compiled-from-source attention kernels that are arch-locked).

**Verdict:** the **4090 wins decisively** for this workflow — ~2× the
compute, native FP8, higher memory bandwidth, matches the image's compiled
arch, and ~2.5–3× cheaper per video. The A6000/A40's only real advantage is
VRAM headroom (audio branch, 3+ LoRAs, BF16 later) — and if you need that,
the **L40/L40S** is the better 48 GB pick because it's Ada (FP8-native,
SageAttention-compatible). One operational caveat: serverless 4090 capacity
is popular and can queue at peak times; the 48 GB tiers often scale more
reliably. Verify current per-second prices in the endpoint GPU dropdown —
they drift.

### Execution time per 15 s segment (2-pass: 8-step + 3-step + latent upscale)

| GPU | Time per 16 s segment (720p out) |
|---|---|
| RTX 4090 | ~200 s (repo benchmark) |
| A100 80 GB | ~120–150 s (estimate) |
| + FlashVSR 1080p pass | + ~600 s per segment |

So **63 s average execution is optimistic** for 15 s 720p redetailing —
expect 120–200 s. 63 s is only realistic for ~5 s clips or a single-pass
8-step workflow.

### Requests/day and cost scenarios

`requests/day = (minutes of video per day × 60) ÷ 15 × passes per segment`

| Scenario | Requests/day | GPU-sec/day | GPU | Est. cost/day | Est. cost/mo |
|---|---|---|---|---|---|
| 10 min/day → 720p | 40 | ~8,000 | 4090 | ~$2.50 | ~$75 |
| 10 min/day → 1080p (V2V + FlashVSR) | 40 (or 80 as separate SR jobs) | ~32,000 | 4090 | ~$10 | ~$300 |
| 1,000 clips/day (= 4.2 h of video/day) → 720p | 1,000 | ~200,000 | 4090 | ~$62 | ~$1,860 |
| Same 1,000/day on A100 @ 63 s (the estimator settings) | 1,000 | 63,000 | A100 | $47.60 | $1,428 |
| Same 1,000/day on A100 @ realistic 130 s | 1,000 | 130,000 | A100 | ~$99 | ~$2,960 |

(A100 $0.00076/s verified from the RunPod estimator; 4090 tier is roughly
$0.0003/s — check the dropdown for current pricing.)

### Throughput / wall-clock

With `max-workers=3`, the 40 segments of a 10-min video run in parallel:
~40 ÷ 3 × 200 s ≈ **45 min wall-clock** per 10-min video on 4090s. Keep
`idle-timeout` at 5–10 min so all 40 chunks hit the warm worker (one cold
start amortized across the batch) and set the handler `TIMEOUT=600`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| First job times out | Raise `TIMEOUT` env to 600+; cold start is slow |
| `ComfyUI process died` in logs | `COMFYUI_ARGS` mismatch with GPU VRAM — drop `--use-sage-attention` or add `--lowvram` |
| Models not found | Volume not attached, or models seeded to wrong path (`/runpod-volume/models/...`) |
| `UNAUTHORIZED` pulling image | Image is public — confirm you used `ghcr.io/alterpeace/runpod-comfy:latest`, not the old `aaronghent` path |
| Outputs vanish | `STORAGE_TYPE=response` returns base64 in the response; for large video use `STORAGE_TYPE=volume` or `s3` |

---

## Reference: config files in this repo

- [`config/runpod-config-serverless.json`](../config/runpod-config-serverless.json:1) —
  serverless template (now points at your image).
- [`config/runpod-config-pods.json`](../config/runpod-config-pods.json:1) —
  pods template (now points at your image).
- [`lifecycle/runpod_serverless.py`](../lifecycle/runpod_serverless.py:1) —
  CLI for create/invoke/status/update/delete.
- [`lifecycle/runpod_pods.py`](../lifecycle/runpod_pods.py:1) —
  CLI for the Pod-based seeding/interactive path.
- [`src/handler.py`](../src/handler.py:1) — the serverless handler that runs
  inside the worker (boots ComfyUI, runs the workflow, returns output).
- [`plans/github-actions-build-push.md`](../plans/github-actions-build-push.md:1) —
  if you later want CI to auto-build on push (not needed to boot; image is
  already hosted).
