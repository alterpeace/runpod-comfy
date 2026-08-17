# Pod Lifecycle — Seed, SSH, Terminate

Quick reference for the full pod lifecycle: create a pod, SSH in, run commands,
and terminate to stop billing.

## TL;DR

```bash
# 1. Create a spot pod with volume attached
uv run python lifecycle/runpod_pods.py create \
  --name ltx25-seed \
  --gpu "RTX A4000" --spot \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --volume-id <VOLUME_ID> \
  --env MODE=pods --env ENABLE_SSH=true

# 2. SSH in (get IP:port from the RunPod console → Connect tab)
ssh root@<POD_IP> -p <SSH_PORT>

# 3. Run your commands inside the pod
export HF_TOKEN=hf_...
./scripts/models/install_models.sh --profile mid_vram_24gb

# 4. Exit SSH
exit

# 5. TERMINATE the pod (stops billing immediately)
uv run python lifecycle/runpod_pods.py terminate --pod-id <POD_ID>
```

## Step-by-Step

### Step 1 — Create the Pod

```bash
uv run python lifecycle/runpod_pods.py create \
  --name ltx25-seed \
  --gpu "RTX A4000" --spot \
  --image ghcr.io/alterpeace/runpod-comfy:latest \
  --volume-id <VOLUME_ID> \
  --env MODE=pods --env ENABLE_SSH=true
```

**Parameters:**
- `--name` — any descriptive name (e.g. `ltx25-seed`, `model-download`, `debug-session`)
- `--gpu` — GPU type (e.g. `RTX A4000`, `RTX 4090`, `A100 80GB`)
- `--spot` — use spot instance (cheaper, ~50% off, but can be interrupted)
- `--image` — Docker image to run
- `--volume-id` — RunPod network volume ID (e.g. `el6aj9vatl`)
- `--env` — environment variables (repeat for multiple)

**Output:**
```
✅ Pod created successfully!
Pod ID: abc123def456
Status: RUNNING
```

**Save the Pod ID** — you'll need it to terminate later.

### Step 2 — Get SSH Connection Details

1. Go to https://console.runpod.io/pods
2. Click on your pod (`ltx25-seed`)
3. Click the **Connect** tab
4. Note the **Public IP** and **SSH Port** (e.g. `203.0.113.5:41234`)

Or use the CLI to list pods and get connection info:
```bash
uv run python lifecycle/runpod_pods.py list
```

### Step 3 — SSH In

```bash
ssh root@<POD_IP> -p <SSH_PORT>
```

Example:
```bash
ssh root@203.0.113.5 -p 41234
```

You're now inside the container. The workspace is at `/workspace`, ComfyUI is at
`/comfyui`, and the network volume is at `/runpod-volume`.

### Step 4 — Run Commands Inside the Pod

#### Download LTX-2.5 models to the volume:
```bash
cd /workspace
export HF_TOKEN=hf_your_token_here
./scripts/models/install_models.sh --profile mid_vram_24gb
```

Models land in `/runpod-volume/models/` and persist after the pod is terminated.

#### Download LTX-2.3 models:
```bash
./scripts/models/install_models.sh --version 23 --profile mid_vram_12_24gb
```

#### Access the ComfyUI WebUI:
The WebUI runs on port 8188. Use SSH port forwarding from your local machine:
```bash
# On your LOCAL machine (not inside the pod):
ssh -L 8188:127.0.0.1:8188 root@<POD_IP> -p <SSH_PORT>
# Then open http://localhost:8188 in your browser
```

Or use the tunnel script:
```bash
./scripts/build/tunnel_webui.sh <POD_IP> <SSH_PORT>
```

#### Install custom nodes:
```bash
./scripts/models/install_models.sh --skip-models  # nodes only
# or
./scripts/build/update_custom_nodes.sh
```

### Step 5 — Exit SSH

```bash
exit
```

This closes your SSH session but does **NOT** stop the pod or billing.

### Step 6 — TERMINATE the Pod

**This is the most important step.** Stopping a pod does NOT stop billing —
you must **terminate** it.

```bash
uv run python lifecycle/runpod_pods.py terminate --pod-id <POD_ID>
```

Example:
```bash
uv run python lifecycle/runpod_pods.py terminate --pod-id abc123def456
```

**Verify it's terminated:**
```bash
uv run python lifecycle/runpod_pods.py list
# The pod should no longer appear, or show status "TERMINATED"
```

## Billing Reference

| Action | Billing stops? | Data preserved? |
|---|---|---|
| **Exit SSH** | ❌ No — pod still running | ✅ Yes |
| **Stop pod** (RunPod console) | ❌ No — still billed at reduced rate | ✅ Yes (can restart) |
| **Terminate pod** | ✅ Yes — billing stops immediately | ❌ Container disk lost, ✅ Network volume persists |

**You only pay for the time between pod creation and termination.**
A 30-minute model download on an RTX A4000 spot pod costs ~$0.20.

## Common Pod Operations

### List all pods
```bash
uv run python lifecycle/runpod_pods.py list
```

### Check pod status
```bash
uv run python lifecycle/runpod_pods.py status --pod-id <POD_ID>
```

### Stop a pod (does NOT stop billing — prefer terminate)
```bash
uv run python lifecycle/runpod_pods.py stop --pod-id <POD_ID>
```

### Terminate a pod (STOPS billing)
```bash
uv run python lifecycle/runpod_pods.py terminate --pod-id <POD_ID>
```

## Tips

- **Use spot pods for downloads** — they're ~50% cheaper and interruptions
  don't matter (the install script resumes from where it left off)
- **Use on-demand pods for interactive work** — spot interruptions will kill
  your SSH session and any running processes
- **Always terminate when done** — set a reminder or timer. A forgotten pod
  running for a week on an RTX 4090 costs ~$57
- **Network volume data persists** — models, outputs, and `.env` files on
  `/runpod-volume/` survive pod termination. Container disk (`/workspace/`)
  does NOT.
- **Multiple pods can share one volume** — but only one pod can write at a
  time. For concurrent access, use separate volumes.
