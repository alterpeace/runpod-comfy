# ComfyUI WebUI Access - Always Available

## Remote Access Matrix (RunPod)

| Where ComfyUI runs | Inbound? | How to reach the WebUI | Script |
|---|---|---|---|
| **Pod** | Public SSH (IP:port from Connect panel) | `ssh -L 8188:127.0.0.1:8188 root@<ip> -p <port>` → http://localhost:8188 | [`scripts/tunnel_webui.sh`](../scripts/tunnel_webui.sh) / [`.ps1`](../scripts/tunnel_webui.ps1) |
| **Serverless worker** | ❌ outbound-only | **Not accessible** — serverless workers have no inbound ports. Use the API (`/run`, `/runsync`) or a Pod for interactive access. | — |
| **Local docker** | direct | http://localhost:8188 | — |

> **Note:** The ComfyUI WebUI runs inside serverless workers (on `127.0.0.1:8188`)
> but is **not reachable** because RunPod serverless containers are outbound-only
> with no exposed ports. For interactive WebUI sessions, use a **Pod** instead.
> Serverless is designed for headless API-driven workflow execution.

## Core Principle

**The ComfyUI WebUI is ALWAYS running and accessible in ALL modes.**

This is a fundamental design requirement enforced throughout the spec, design, and implementation.

## Why This Matters

1. **Local Development**: WebUI is the primary interface for creating and testing workflows
2. **Serverless Debugging**: Access WebUI while handler processes jobs to debug issues
3. **Manual Testing**: Test workflows manually before automating them via the handler API
4. **Consistent Experience**: Same interface available in development and production

## Implementation

### Entrypoint Script (`entrypoint.sh`)

```bash
# ALWAYS starts ComfyUI with external access
python /comfyui/main.py --listen 0.0.0.0 --port $COMFYUI_PORT &

# Health check ensures WebUI is ready
while ! curl -s http://127.0.0.1:$COMFYUI_PORT/; do
    sleep 1
done

log_success "ComfyUI WebUI is running and accessible"
```

### Access Methods

#### Local Mode
```bash
# Direct access
http://localhost:8188
```

#### Serverless Mode (RunPod)
```bash
# The WebUI runs on 127.0.0.1:8188 inside the worker but is NOT reachable
# from outside — serverless workers are outbound-only with no exposed ports.
# Use the API instead:
#   POST https://api.runpod.io/v2/<ENDPOINT_ID>/runsync
# For interactive WebUI access, deploy a Pod instead.
```

## Mode Comparison

| Feature | Local Mode | Serverless Mode |
|---------|-----------|-----------------|
| **WebUI Running** | ✅ Yes | ✅ Yes |
| **WebUI Accessible** | ✅ Direct HTTP | ✅ Via Proxy/Tunnel |
| **Handler Running** | ❌ No | ✅ Yes |
| **Primary Use** | Interactive Development | Automated Jobs + Manual Testing |

## Spec Updates

### Requirements (Requirement 8)
- Added explicit criteria that WebUI SHALL be accessible in both modes
- Added criteria that WebUI SHALL remain accessible while handler processes jobs
- Added criteria for --listen 0.0.0.0 binding

### Design Document
- Added "Always-On ComfyUI WebUI" to overview
- Added "Critical Design Principle: WebUI Accessibility" section
- Added dedicated "ComfyUI WebUI Access in All Modes" section
- Updated mode descriptions to emphasize WebUI availability
- Added WebUI + Handler coexistence diagram

### Tasks (Task 4)
- Added requirement to start ComfyUI with --listen 0.0.0.0
- Added health check requirement
- Added logging for WebUI access information

## Benefits

1. **Development**: Build workflows interactively in the WebUI
2. **Testing**: Test workflows manually before automating
3. **Debugging**: Watch WebUI while handler processes jobs
4. **Flexibility**: Choose between manual (WebUI) or automated (API) workflow execution
5. **Consistency**: Same interface in local and production environments

## Technical Details

### Port Configuration
- Default: 8188
- Configurable via: `COMFYUI_PORT` environment variable
- Always bound to: `0.0.0.0` (external access)

### Process Management
- ComfyUI runs in background (doesn't block other services)
- Process ID tracked for monitoring
- Health check ensures readiness before proceeding

### Coexistence with Handler
In serverless mode, both run simultaneously:
- **ComfyUI Server**: Handles both WebUI requests and API calls
- **Handler**: Submits jobs to ComfyUI API
- **No Conflict**: They use the same ComfyUI instance via different interfaces
