# OpenZiti Tunnel Integration

This directory contains scripts and configuration for OpenZiti tunnel integration, which provides secure access to ComfyUI and SSH services without exposing public endpoints.

## Overview

OpenZiti creates a zero-trust network overlay that allows you to securely access your RunPod instances from your local network without opening public ports.

## Files

- `tunnel_setup.sh` - Main script that initializes and manages the OpenZiti tunnel
- `ziti-config.json.example` - Example OpenZiti identity configuration format

## Configuration

The tunnel is configured via environment variables in your `.env` file:

### Option 1: File-based Identity

```bash
# Path to OpenZiti identity JSON file
OPENZITI_IDENTITY=/runpod-volume/ziti-identity.json

# OpenZiti controller URL (optional, usually in identity file)
OPENZITI_CONTROLLER=https://controller.example.com:443

# Service names for port forwarding
OPENZITI_SERVICE_HTTP=comfyui-http
OPENZITI_SERVICE_SSH=comfyui-ssh
```

### Option 2: Embedded JSON Identity

```bash
# Embed identity JSON directly (useful for deployment)
OPENZITI_IDENTITY_JSON='{"zt":"token","id":{...}}'

# Service names for port forwarding
OPENZITI_SERVICE_HTTP=comfyui-http
OPENZITI_SERVICE_SSH=comfyui-ssh
```

## Port Forwarding

The tunnel forwards the following services:

- **HTTP (ComfyUI)**: Port 8188 → OpenZiti service (configured via `OPENZITI_SERVICE_HTTP`)
- **SSH**: Port 22 → OpenZiti service (configured via `OPENZITI_SERVICE_SSH`)

**Note**: Services must be configured in your OpenZiti controller before they can be used.

## Usage

### Automatic Initialization

The tunnel is automatically initialized by `entrypoint.sh` if OpenZiti configuration is detected in your `.env` file.

### Manual Testing

```bash
# Test with file-based identity
export OPENZITI_IDENTITY=/path/to/identity.json
export OPENZITI_SERVICE_HTTP=comfyui-http
export OPENZITI_SERVICE_SSH=comfyui-ssh
./tunnel_setup.sh

# Test with embedded JSON
export OPENZITI_IDENTITY_JSON='{"zt":"...","id":{...}}'
./tunnel_setup.sh
```

### Health Monitoring

The script includes built-in health monitoring. To enable continuous monitoring:

```bash
KEEP_RUNNING=true ./tunnel_setup.sh
```

This will monitor the tunnel and attempt to restart it if it fails.

## Error Handling

The script is designed to fail gracefully:

- If no OpenZiti configuration is found, it exits silently (code 0)
- If `ziti-edge-tunnel` is not installed, it logs an error and continues
- If tunnel initialization fails, it logs the error and allows the system to continue
- All errors are logged with clear messages

This ensures that the absence of OpenZiti configuration doesn't prevent the system from running.

## Requirements

### Software

- `ziti-edge-tunnel` - OpenZiti tunnel client
  - Installation: https://openziti.io/docs/downloads

### OpenZiti Network Setup

Before using this integration, you need:

1. An OpenZiti network (controller + router)
2. An identity enrolled in the network
3. Services configured for HTTP and SSH forwarding
4. Appropriate policies to allow access

See the OpenZiti documentation for setup instructions: https://openziti.io/docs

## Accessing Services

Once the tunnel is running:

### ComfyUI WebUI

```bash
# Access via OpenZiti service name
http://comfyui-http.ziti:8188

# Or via local OpenZiti proxy (if configured)
http://localhost:8188
```

### SSH

```bash
# Access via OpenZiti service name
ssh root@comfyui-ssh.ziti

# Or via local OpenZiti proxy (if configured)
ssh root@localhost -p 22
```

## Troubleshooting

### Tunnel fails to start

Check the logs for specific error messages:
- "failed to open network interface" - Usually a permissions issue
- "failed to load identity" - Check your identity file path or JSON format
- "connection refused" - Check your OpenZiti controller URL

### Services not accessible

1. Verify services are configured in OpenZiti controller
2. Check service names match environment variables
3. Verify identity has access to services (check policies)
4. Check tunnel process is running: `ps aux | grep ziti-edge-tunnel`

### Identity file issues

- Ensure the identity file is valid JSON
- Check file permissions (should be readable)
- Verify the identity is enrolled in the network

## Security Notes

- **Never commit identity files or JSON to Git**
- Store identity files in network storage (`/runpod-volume/`)
- Use embedded JSON only for automated deployments
- Rotate identities regularly
- Use service-specific identities (don't share identities)

## Integration with Entrypoint

The `entrypoint.sh` script automatically:

1. Checks for `.env` file in `/runpod-volume/` or `/workspace/`
2. Loads OpenZiti configuration if present
3. Calls `tunnel_setup.sh` to initialize tunnel
4. Continues with normal startup if tunnel fails

This ensures OpenZiti is completely optional and doesn't block system startup.
