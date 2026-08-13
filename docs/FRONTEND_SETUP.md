# ComfyUI Frontend with RunPod Serverless

Run the official ComfyUI node-based frontend locally while routing all GPU
processing to a RunPod Serverless endpoint — consuming **0 local VRAM**.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Local Machine (0 GPU, 0 VRAM)                              │
│                                                             │
│  ┌──────────────┐    Vite dev proxy    ┌─────────────────┐  │
│  │  ComfyUI     │─────────────────────▶│  ComfyUI Proxy  │  │
│  │  Frontend    │  /prompt, /ws, etc.  │  (FastAPI)      │  │
│  │  (Vue.js)    │◀─────────────────────│                 │  │
│  │  :5173       │   REST + WebSocket   │  :8188          │  │
│  └──────────────┘                      └────────┬────────┘  │
│                                                 │            │
└─────────────────────────────────────────────────┼────────────┘
                                                  │ HTTPS
                                          POST /run, GET /status
                                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  RunPod Serverless (scales 0→N on demand)                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Worker (ghcr.io/alterpeace/runpod-comfy:latest)    │    │
│  │  - ComfyUI + handler.py                             │    │
│  │  - Network volume (models, custom_nodes)            │    │
│  │  - Boots on job → runs workflow → returns output    │    │
│  │  - Shuts down after idle timeout                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### The Protocol Mismatch

The ComfyUI Frontend expects a **live ComfyUI server** (HTTP REST + WebSocket).
RunPod Serverless exposes a **job queue API** (submit/poll). The proxy server
([`src/proxy_server.py`](../src/proxy_server.py)) bridges this gap by:

- Implementing the ComfyUI REST API subset the frontend needs
- Translating `POST /prompt` → `POST /v2/{id}/run` (RunPod)
- Simulating WebSocket execution events by polling RunPod job status
- Serving cached `object_info` for the node palette

---

## Prerequisites

- **Node.js 18+** — for the frontend dev server ([install](https://nodejs.org/))
- **Python 3.10+** — for the proxy server (already have it if you run this project)
- **RunPod account** with:
  - A deployed serverless endpoint (see [`docs/SERVERLESS_DEPLOY.md`](SERVERLESS_DEPLOY.md))
  - Your RunPod API key (generate at
    <https://www.runpod.io/console/user/settings> → "API Keys")
- **Local ComfyUI** (optional, for fetching `object_info` cache) — see
  [`scripts/run_local.sh`](../scripts/run_local.sh)

---

## Quick Start

### 1. Configure `.env`

Add these to your [`.env`](../.env.example) file:

```bash
# RunPod serverless endpoint ID (from RunPod console → Serverless)
RUNPOD_ENDPOINT_ID=your-endpoint-id

# RunPod API key
RUNPOD_API_KEY=your-api-key

# Proxy port (default: 8188 — same as ComfyUI)
PROXY_PORT=8188
```

### 2. Fetch object_info cache

The frontend needs `object_info` to render the node palette. Fetch it from a
running ComfyUI instance that has the same custom nodes installed:

```bash
# Option A: From local Docker ComfyUI (recommended)
./scripts/run_local.sh                    # start ComfyUI in Docker
python scripts/fetch_object_info.py --source local

# Option B: From a RunPod Pod with your custom nodes
python scripts/fetch_object_info.py --source local --url http://<pod-url>:8188
```

This saves to [`config/object_info_cache.json`](../config/object_info_cache.json).

### 3. Start the frontend

```bash
./scripts/run_frontend.sh --serverless
```

This will:
1. Clone the official ComfyUI Frontend (if not already present)
2. Install npm dependencies
3. Start the proxy server on `:8188`
4. Start the frontend dev server on `:5173`

Open **<http://localhost:5173>** — you'll see the full node-based ComfyUI
interface. Build workflows visually, click "Queue Prompt", and the proxy
will submit to RunPod Serverless.

### 4. Stop everything

```bash
./scripts/stop_frontend.sh
```

---

## Running Modes

The [`run_frontend.sh`](../scripts/run_frontend.sh) script auto-detects the
backend, or you can force a mode:

| Flag | Backend | GPU | Use Case |
|---|---|---|---|
| (auto) | Detects local ComfyUI on :8188, falls back to RunPod | Either | Default |
| `--serverless` | Proxy → RunPod Serverless API | RunPod (remote) | No local GPU |
| `--local` | Frontend → Docker ComfyUI directly | Local GPU | Want new UI with local GPU |
| `--mock` | Proxy → Mock → Docker ComfyUI (full stack test) | Local GPU | Test serverless flow locally |
| `--debug` | Verbose proxy logging | Either | Debugging |

### Scenario A: Full local stack (GPU available)

```bash
./scripts/run_local.sh          # Docker ComfyUI on :8188
# Open http://localhost:8188 for built-in WebUI
```

### Scenario B: Frontend + Serverless (no local GPU)

```bash
./scripts/run_frontend.sh --serverless
# Open http://localhost:5173
# 0 local VRAM — all processing on RunPod
```

### Scenario C: Frontend + Local Docker (GPU available, want new UI)

```bash
./scripts/run_local.sh                    # start ComfyUI in Docker
./scripts/run_frontend.sh --local         # frontend → Docker ComfyUI
# Open http://localhost:5173
```

### Scenario D: Debug without any UI

```bash
# Validate workflow structure
python scripts/debug_workflow.py --workflow examples/text_to_image_simple.json --dry-run

# Test against local ComfyUI
python scripts/debug_workflow.py --target local --workflow examples/text_to_image_simple.json

# Test against RunPod serverless
python scripts/debug_workflow.py --target runpod \
    --workflow examples/text_to_image_simple.json --wait

# Override inputs
python scripts/debug_workflow.py --target runpod \
    --workflow examples/text_to_image_simple.json \
    --set-input 6.text="a cat" --set-input 3.seed=999 --wait
```

### Scenario E: All-in-Docker (everything in containers)

Run the full stack — ComfyUI, proxy, mock server, and frontend — all in Docker
containers using [`docker-compose.frontend.yml`](../docker-compose.frontend.yml):

```bash
# 1. Clone the frontend (one-time)
git clone https://github.com/Comfy-Org/ComfyUI_frontend.git frontend

# 2. Fetch object_info cache (from local ComfyUI)
./scripts/run_local.sh
python scripts/fetch_object_info.py --source local
./scripts/stop_frontend.sh  # stop the native frontend if running

# 3. Start everything in Docker — mock serverless mode (0 cloud cost)
docker compose -f docker-compose.yml -f docker-compose.frontend.yml \
    --profile mock up

# Open http://localhost:5173
```

**Services started:**

| Service | Container | Port | Purpose |
|---|---|---|---|
| ComfyUI | `comfy` | :8188 | GPU backend (from `docker-compose.yml`) |
| Mock RunPod | `comfy-mock` | :9090 | Simulates RunPod API → routes to ComfyUI |
| Proxy | `comfy-proxy` | :8189 | Translates ComfyUI API → RunPod API format |
| Frontend | `comfy-frontend` | :5173 | Vue.js node-based UI |

**For real RunPod serverless (no local GPU needed):**

```bash
# Set RunPod credentials in .env
echo "RUNPOD_ENDPOINT_ID=your-endpoint-id" >> .env
echo "RUNPOD_API_KEY=your-api-key" >> .env

# Start only proxy + frontend (no ComfyUI container needed)
docker compose -f docker-compose.yml -f docker-compose.frontend.yml \
    --profile serverless up
```

**Frontend-only (talks to existing ComfyUI on host):**

```bash
# If ComfyUI is already running on :8188 (native or Docker)
docker compose -f docker-compose.yml -f docker-compose.frontend.yml \
    --profile frontend-only up
```

**Stop all containers:**

```bash
docker compose -f docker-compose.yml -f docker-compose.frontend.yml down
```

---

## Custom Nodes & Models

### Custom Nodes

Custom nodes are installed on the RunPod serverless worker's Docker image
(baked in at build time) and/or on the network volume at
`/runpod-volume/custom_nodes/`.

The frontend learns about available nodes from the cached `object_info`. When
you add or update custom nodes:

```bash
# 1. Install the custom node on your local Docker ComfyUI
#    (or on a RunPod Pod with the same setup)

# 2. Refresh the object_info cache
python scripts/fetch_object_info.py --source local

# 3. Restart the proxy
./scripts/stop_frontend.sh
./scripts/run_frontend.sh --serverless
```

### Models

Models live on the RunPod network volume at `/runpod-volume/models/`. The
cached `object_info` includes model dropdown lists from when the cache was
fetched.

If you add a new model to the network volume:

```bash
# Re-fetch from local ComfyUI (if you have the same models locally)
python scripts/fetch_object_info.py --source local

# Or refresh just model lists (no worker cold-start)
python scripts/fetch_object_info.py --models-only --volume-id v1abc123
```

---

## Debugging

### Proxy Debug Mode

```bash
python src/proxy_server.py --debug
```

Logs every protocol translation:

```
[PROXY] POST /prompt - 8 nodes, client_id=abc
[PROXY] POST https://api.runpod.ai/v2/{id}/run - 8 nodes
[PROXY]   -> job_id=abc-123, status=IN_QUEUE
[PROXY] WS -> execution_start {prompt_id: uuid}
[PROXY] Polling status... IN_QUEUE (elapsed: 2.0s)
[PROXY] Polling status... IN_PROGRESS (elapsed: 5.1s)
[PROXY] WS -> executing {prompt_id: uuid, node: None}
[PROXY] Polling status... COMPLETED (elapsed: 12.3s)
[PROXY] WS -> executed {prompt_id: uuid, node: 9}
[PROXY] WS -> execution_success {prompt_id: uuid}
```

### Debug Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Proxy health, job count, connections |
| `GET /debug/jobs` | List all submitted jobs and their status |

### CLI Workflow Debugger

See [`scripts/debug_workflow.py`](../scripts/debug_workflow.py) for the
standalone CLI debugger that works without any UI.

---

## Limitations

| Limitation | Mitigation |
|---|---|
| **Cold start delay** (5-30s per job) | Proxy shows "Queued..." status in WebSocket events |
| **No real-time preview** | Serverless returns final output only — frontend shows "Executing..." until complete |
| **object_info can go stale** | Re-run `fetch_object_info.py` after adding custom nodes |
| **No model browsing** | Proxy returns cached model list from `object_info` |
| **Image uploads need pre-loading** | Proxy stores locally, embeds base64 in job payload |
| **WebSocket is simulated** | Polling-based (default 2s interval), not true real-time |

---

## File Reference

| File | Purpose |
|---|---|
| [`src/proxy_server.py`](../src/proxy_server.py) | FastAPI proxy: REST + WebSocket translation |
| [`scripts/fetch_object_info.py`](../scripts/fetch_object_info.py) | Cache `object_info` from ComfyUI |
| [`scripts/debug_workflow.py`](../scripts/debug_workflow.py) | Standalone CLI workflow debugger |
| [`scripts/run_frontend.sh`](../scripts/run_frontend.sh) | Start proxy + frontend dev server |
| [`scripts/stop_frontend.sh`](../scripts/stop_frontend.sh) | Stop proxy + frontend |
| [`config/object_info_cache.json`](../config/object_info_cache.json) | Cached node definitions (gitignored) |
| [`tests/test_proxy_server.py`](../tests/test_proxy_server.py) | Proxy server unit tests |
| [`tests/test_debug_workflow.py`](../tests/test_debug_workflow.py) | Debug workflow unit tests |
| [`plans/frontend-serverless-setup.md`](../plans/frontend-serverless-setup.md) | Full architecture plan |

---

## Troubleshooting

### "Node palette is empty"

The `object_info` cache is missing or empty. Run:

```bash
./scripts/run_local.sh
python scripts/fetch_object_info.py --source local
```

### "Proxy will fail on /prompt submissions"

`RUNPOD_ENDPOINT_ID` or `RUNPOD_API_KEY` not set. Add them to `.env`:

```bash
RUNPOD_ENDPOINT_ID=your-endpoint-id
RUNPOD_API_KEY=your-api-key
```

### "Job takes forever / times out"

Serverless workers have a cold start (5-30s). The first job after idle will
be slow. Check the endpoint status:

```bash
python lifecycle/runpod_serverless.py status --endpoint-id YOUR_ID
```

### "WebSocket not connecting"

The proxy simulates WebSocket events. Make sure the proxy is running on
the port specified in `frontend/.env` (`DEV_SERVER_COMFYUI_URL`).

### "Custom node not found"

The node isn't in the `object_info` cache. Either:
1. Install the node on your local ComfyUI and re-fetch: `python scripts/fetch_object_info.py --source local`
2. Or the node isn't installed on the serverless worker — add it to the Docker image or network volume

### "Model not in dropdown"

The model list is cached. Add the model to your local ComfyUI's `models/`
directory and re-fetch, or use `--models-only` to refresh just model lists.
