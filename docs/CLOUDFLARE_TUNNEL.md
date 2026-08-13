# Cloudflare Tunnel — Stable WebUI Access on Serverless

## Overview

Cloudflare Tunnel (`cloudflared`) provides a **stable, public HTTPS URL** for
the ComfyUI WebUI, even when running on RunPod serverless workers that have no
inbound ports.

Unlike OpenZiti (which was removed because it requires `CAP_NET_ADMIN` to create
TUN/TAP interfaces — not available in serverless containers), `cloudflared` is a
**userspace** reverse tunnel. It dials **out** to Cloudflare's edge via standard
HTTPS. No kernel interfaces, no special capabilities, no root required.

## How It Works

```
Browser ──HTTPS──> Cloudflare Edge ──tunnel──> cloudflared (worker) ──> ComfyUI :8188
                    (stable hostname)           (outbound-only)
```

1. `cloudflared` runs inside the serverless worker alongside ComfyUI
2. It connects outbound to Cloudflare's edge network
3. Cloudflare routes traffic from your stable hostname through the tunnel to ComfyUI
4. When a new worker boots, it reconnects to the same tunnel — **same URL, different worker**

## Prerequisites

- A **Cloudflare account** (free tier is sufficient)
- A **domain managed by Cloudflare** (can be a cheap $10/year domain)
- Access to the **Cloudflare Zero Trust dashboard**: <https://one.dash.cloudflare.com>

## Setup Guide

### Step 1 — Create a Named Tunnel

1. Go to <https://one.dash.cloudflare.com> → **Networks** → **Tunnels**
2. Click **Create a tunnel** → select **Cloudflare Tunnel**
3. Name it (e.g. `comfyui`)
4. After creation, note the **Tunnel ID** (a UUID like `a1b2c3d4-...`)
5. Download the **credentials JSON file** (`<tunnel-id>.json`)

### Step 2 — Configure the Public Hostname

1. In the tunnel's **Public Hostname** tab, click **Add a public hostname**
2. Set:
   - **Subdomain:** `comfyui` (or whatever you prefer)
   - **Domain:** select your Cloudflare domain
   - **Type:** `HTTP`
   - **URL:** `127.0.0.1:8188`
3. Save. This creates a DNS CNAME record automatically.

Your WebUI will be accessible at `https://comfyui.yourdomain.com`.

### Step 3 — Place Credentials on the Network Volume

The credentials file must be accessible to every serverless worker. Place it on
the RunPod network volume so all workers share the same tunnel identity.

Using a seed pod (or any pod with the volume attached):

```bash
# Copy the credentials file to the network volume
scp <tunnel-id>.json root@<seed-pod-ip>:/runpod-volume/cloudflared-credentials.json
```

Or upload via the RunPod console's file manager.

### Step 4 — Configure Environment Variables

Set these on your serverless endpoint (or in `/runpod-volume/.env`):

```bash
# Tunnel UUID from the Cloudflare dashboard
CLOUDFLARED_TUNNEL_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Path to credentials file on the network volume
CLOUDFLARED_CREDENTIALS_PATH=/runpod-volume/cloudflared-credentials.json

# The public hostname you configured
CLOUDFLARED_HOSTNAME=comfyui.yourdomain.com
```

### Step 5 — Deploy

When a worker boots, [`entrypoint.sh`](../entrypoint.sh) will:
1. Detect the Cloudflare tunnel config
2. Wait for ComfyUI to be healthy on port 8188
3. Generate a `config.yml` mapping the hostname to `http://127.0.0.1:8188`
4. Start `cloudflared tunnel run` in the background
5. Log the public URL

The tunnel reconnects automatically on every worker boot — the URL stays the same.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CLOUDFLARED_TUNNEL_ID` | Yes | Tunnel UUID from the Cloudflare dashboard |
| `CLOUDFLARED_CREDENTIALS_PATH` | Yes | Path to the credentials JSON file |
| `CLOUDFLARED_HOSTNAME` | Yes | Public hostname (e.g. `comfyui.yourdomain.com`) |

## Uptime Considerations

The tunnel only works while a worker is running:

| Setting | Tunnel uptime | Cost |
|---|---|---|
| `workersMin=0` (default) | Only during jobs + idle timeout (300s) | Pay-per-execution |
| `workersMin=1` | Always on | Bills 24/7 (like a Pod) |

For **interactive WebUI sessions**, set `workersMin=1` so a worker is always
available. For **debugging during jobs**, `workersMin=0` is fine — the tunnel
will be active while the job runs.

## Quick Tunnels (Ephemeral, No Setup)

If you don't need a stable URL and just want temporary access for debugging,
you can use a **Quick Tunnel** — no Cloudflare account or domain needed:

```bash
cloudflared tunnel --url http://127.0.0.1:8188
```

This generates a random `https://<random>.trycloudflare.com` URL printed to
stderr. The URL changes on every restart and is rate-limited — not suitable
for production, but useful for quick debugging.

## WebSocket Support

Cloudflare Tunnels support WebSocket, which ComfyUI uses for real-time
progress updates, node execution events, and image previews. These work
through the tunnel with minimal added latency.

## Troubleshooting

### Tunnel doesn't start

Check the worker logs for:
- `cloudflared not found` — the Docker image needs rebuilding with the
  cloudflared install step
- `credentials file not found` — verify the path in
  `CLOUDFLARED_CREDENTIALS_PATH` matches where you placed the file on the
  volume
- `failed to connect to Cloudflare edge` — network issue or invalid
  credentials

### WebUI loads but WebSocket doesn't connect

Cloudflare may buffer WebSocket frames. If you see the UI but no progress
updates, check that your tunnel's protocol is set to `http2` (the default
in the generated config).

### DNS not resolving

Verify the CNAME record was created in Cloudflare DNS:
- Go to **DNS** → **Records** in the Cloudflare dashboard
- Look for a CNAME with your subdomain pointing to `<tunnel-id>.cfargotunnel.com`

## Security Notes

- The tunnel credentials file (`<tunnel-id>.json`) is a secret — never commit
  it to Git. Store it only on the network volume.
- The WebUI is publicly accessible at the configured hostname. Consider adding
  Cloudflare Access policies (Zero Trust → Access → Applications) to require
  authentication before reaching the WebUI.
- Rotate tunnel credentials if the file is compromised.

## Comparison with Alternatives

| Feature | Cloudflare Named Tunnel | Quick Tunnel | Pod (SSH) |
|---|---|---|---|
| Stable URL | ✅ Yes | ❌ Random per restart | ✅ (IP:port) |
| Requires domain | Yes | No | No |
| Requires account | Yes (free) | No | No |
| Works on serverless | ✅ | ✅ | ❌ (needs Pod) |
| CAP_NET_ADMIN needed | No | No | N/A |
| WebSocket support | ✅ | ✅ | ✅ |
| TLS | ✅ Automatic | ✅ Automatic | ❌ (manual) |
| Cost | Free | Free | Pod billing |
| Uptime | While worker runs | While worker runs | While pod runs |

## References

- [Cloudflare Tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Create a named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
- [`entrypoint.sh`](../entrypoint.sh) — tunnel startup logic
- [`.env.example`](../.env.example) — configuration template
