# ComfyUI RunPod Deployment

A unified ComfyUI deployment for local development and RunPod (Serverless/Pods) with Backblaze B2 storage integration.

## Quick Start

### Run Locally

```bash
# Start ComfyUI with Docker Compose
docker-compose up

# Access WebUI
open http://localhost:8188
```

### Deploy to RunPod with B2 Storage

```bash
# 1. Build and push image
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=your-token
./build.sh --push

# 2. Deploy to RunPod
export RUNPOD_API_KEY=your-api-key
./deploy.sh --mode serverless \
  --name comfyui-api \
  --image ghcr.io/$GITHUB_USERNAME/comfyui-serverless:latest
```

## Common Commands

### Local Development

```bash
# Start container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose build
docker-compose up -d
```

### Building Images

```bash
# Build locally (no push)
./build.sh

# Build and push to GitHub Container Registry
./build.sh --username your-github-user --push

# Build with version tag
./build.sh --username your-github-user --tag v1.0.0 --push
```

### Deploying to RunPod

```bash
# Deploy serverless endpoint
./deploy.sh --mode serverless \
  --name comfyui-api \
  --image ghcr.io/user/comfyui-serverless:latest \
  --gpu "NVIDIA RTX A4000"

# Deploy persistent pod
./deploy.sh --mode pods \
  --name comfyui-workspace \
  --image ghcr.io/user/comfyui-serverless:latest \
  --spot  # Use spot instance (cheaper)

# Deploy with existing volume (reuse models)
./deploy.sh --mode serverless \
  --name comfyui-api \
  --image ghcr.io/user/comfyui-serverless:latest \
  --volume-id abc123def456
```

### Testing

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_handler.py -v

# Run with coverage
uv run pytest --cov=. tests/
```

### Managing B2 Storage

```bash
# Set B2 credentials
export B2_BUCKET=my-comfyui-models
export B2_KEY_ID=your-key-id
export B2_APP_KEY=your-app-key
export B2_ENDPOINT=s3.us-west-004.backblazeb2.com

# List bucket contents
uv run python storage/manage_b2.py list

# Calculate storage costs
uv run python storage/manage_b2.py size

# Clean old files (dry run)
uv run python storage/manage_b2.py clean --older-than 90

# Verify local files match B2
uv run python storage/manage_b2.py verify --local ./models
```

## Project Structure

```
runpod-serverless/
├── handler.py              # RunPod serverless handler
├── comfyui_client.py       # ComfyUI API client
├── entrypoint.sh           # Container entrypoint
├── docker-compose.yml      # Local development config
├── Dockerfile              # Container build
├── build.sh                # Build automation
├── deploy.sh               # Deployment automation
├── storage/                # B2 storage integration
│   ├── manage_b2.py        # B2 management CLI
│   ├── setup_b2_mount.sh   # rclone mount setup
│   ├── setup_b2_sync.sh    # B2 sync setup
│   └── examples/           # Example configurations
├── lifecycle/              # RunPod lifecycle management
├── tests/                  # Test suite
└── examples/               # Example workflows
```

## Local Development Setup

### Prerequisites

- Docker with GPU support (NVIDIA Container Toolkit)
- NVIDIA GPU with 8GB+ VRAM
- 50GB+ free disk space

> **Using Podman instead of Docker?** (e.g. Linux Mint 22 / Ubuntu 24.04 "noble", where
> `docker` is a Podman/crun shim.) Two Podman-specific issues to know about:
>
> 1. Podman 4.9.x ships a CDI parser that doesn't support the CDI v0.7.0 spec generated
>    by recent NVIDIA Container Toolkit releases, so GPU access fails with
>    `unresolvable CDI devices nvidia.com/gpu=all`. Run this once per boot / driver
>    update before starting the stack:
>    ```bash
>    ./scripts/fix_local_gpu_cdi.sh
>    ```
> 2. `docker compose` here resolves to Podman's Docker-API emulation
>    (`podman system service`), which silently drops the `devices:` GPU entry - the
>    container starts but never gets the GPU. Use `podman-compose` instead, which talks
>    to the Podman CLI directly and correctly resolves the CDI device:
>    ```bash
>    podman-compose up
>    ```
>
> Neither of these affects the built image or RunPod deployments - they're purely about
> how this local container runtime is invoked.

### Reusing an Existing ComfyUI Install (models, custom_nodes, etc.)

By default, `docker-compose.yml` mounts `./.local/{models,output,input,custom_nodes,user}`
- empty, gitignored placeholders inside the repo. If you already have a ComfyUI install
elsewhere (e.g. `~/comfy`), point the local dev mounts at it instead of copying anything:

```bash
# Symlink approach (recommended - keeps docker-compose.yml untouched):
rm -rf .local/models .local/custom_nodes .local/output .local/input .local/user
ln -s ~/comfy/models .local/models
ln -s ~/comfy/custom_nodes .local/custom_nodes
ln -s ~/comfy/output .local/output
ln -s ~/comfy/input .local/input
ln -s ~/comfy/user .local/user
```

Or point at a different directory entirely without touching `.local/` via the
`COMFY_DATA_DIR` env var (checked for `models/`, `custom_nodes/`, `output/`, `input/`,
`user/` subdirectories):

```bash
COMFY_DATA_DIR=~/comfy docker compose up   # or podman-compose up, see below
```

This is **local development only**. On RunPod, `entrypoint.sh` sets up storage from
`/runpod-volume` (network volume) or B2 (`STORAGE_BACKEND=b2-mount`/`b2-sync`) - RunPod
never reads `docker-compose.yml` or `.local/`, so nothing here needs to match RunPod's
layout.

### Step 1: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit as needed (optional for local)
nano .env
```

### Step 2: Prepare Models

```bash
# Create model directories
mkdir -p models/checkpoints models/loras models/vae

# Download a model (example)
cd models/checkpoints
wget https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors
```

### Step 3: Start ComfyUI

```bash
docker-compose up
```

Access WebUI at http://localhost:8188

## RunPod Deployment with Backblaze B2

Using B2 for model storage saves 60-95% compared to RunPod network volumes alone.

### Cost Comparison (100GB models)

| Storage Method | Monthly Cost |
|----------------|--------------|
| RunPod Network Volume Only | ~$10/month |
| B2 + Small Cache Volume | ~$5/month |
| B2 Storage Only | ~$0.50/month |

### Step 1: Create Backblaze B2 Account

1. Sign up at https://www.backblaze.com/b2/sign-up.html
2. Create a bucket (e.g., `my-comfyui-models`)
3. Generate application keys with Read/Write access
4. Note your endpoint (e.g., `s3.us-west-004.backblazeb2.com`)

### Step 2: Upload Models to B2

```bash
# Install rclone
curl https://rclone.org/install.sh | bash

# Configure rclone
cat > ~/.config/rclone/rclone.conf <<EOF
[b2]
type = s3
provider = Other
access_key_id = YOUR_KEY_ID
secret_access_key = YOUR_APP_KEY
endpoint = s3.us-west-004.backblazeb2.com
region = us-west-004
EOF

# Upload models
rclone sync ./models b2:my-comfyui-models/models --progress
```

### Step 3: Build and Push Docker Image

```bash
export GITHUB_USERNAME=your-username
export GITHUB_TOKEN=your-token  # needs write:packages permission

./build.sh --username $GITHUB_USERNAME --push
```

### Step 4: Deploy to RunPod

```bash
export RUNPOD_API_KEY=your-runpod-api-key

./deploy.sh --mode serverless \
  --name comfyui-api \
  --image ghcr.io/$GITHUB_USERNAME/comfyui-serverless:latest \
  --gpu "NVIDIA RTX A4000"
```

### Step 5: Configure B2 in RunPod

Add these environment variables in RunPod dashboard (or upload `.env` to network volume):

```bash
STORAGE_BACKEND=b2-mount
B2_BUCKET=my-comfyui-models
B2_KEY_ID=your-key-id
B2_APP_KEY=your-app-key
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_PATH=models
RCLONE_CACHE_SIZE=50G
```

### Storage Backend Options

| Backend | Best For | Startup | Performance |
|---------|----------|---------|-------------|
| `network-volume` | Small libraries (<50GB) | Instant | Fast |
| `b2-mount` | Large libraries, cost savings | Instant | Medium (cached) |
| `b2-sync` | Max performance, infrequent restarts | 20-40min | Fast |

## Environment Variables

### Required for RunPod

| Variable | Description |
|----------|-------------|
| `RUNPOD_API_KEY` | RunPod API key |

### Required for B2 Storage

| Variable | Description |
|----------|-------------|
| `STORAGE_BACKEND` | `network-volume`, `b2-mount`, or `b2-sync` |
| `B2_BUCKET` | B2 bucket name |
| `B2_KEY_ID` | B2 access key ID |
| `B2_APP_KEY` | B2 application key |
| `B2_ENDPOINT` | B2 S3 endpoint URL |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | auto-detected | `local`, `serverless`, or `pods` |
| `COMFYUI_PORT` | `8188` | ComfyUI server port |
| `COMFYUI_ARGS` | `--use-sage-attention --lowvram` | ComfyUI startup args |
| `B2_REGION` | `us-west-004` | B2 region |
| `B2_PATH` | (empty) | Subdirectory in bucket |
| `RCLONE_CACHE_SIZE` | `20G` | Cache size for b2-mount |
| `ENABLE_SSH` | `false` | Enable SSH server |
| `SSH_PUBLIC_KEY` | (none) | SSH public key for auth |

## API Usage

### Invoke Serverless Endpoint

```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "workflow": { ... },
      "images": {}
    }
  }'
```

### Check Job Status

```bash
curl https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/status/JOB_ID \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs comfyui

# Verify GPU access
docker run --gpus all nvidia/cuda:11.8-base nvidia-smi
```

### GPU not visible / "unresolvable CDI devices nvidia.com/gpu=all"

This happens on Podman-based local setups (Podman 4.9.x doesn't support the CDI v0.7.0
schema NVIDIA Container Toolkit now generates by default). Fix it with:

```bash
./scripts/fix_local_gpu_cdi.sh
```

Re-run this after a reboot, NVIDIA driver update, or `nvidia-container-toolkit` update —
the patched spec lives partly on tmpfs and gets regenerated (unpatched) by those events.
This is a local-only workaround; it does not need to be applied on RunPod.

### Container starts but GPU still isn't used (no CDI error, just no CUDA)

If `docker` on your machine is a Podman shim, `docker compose up` talks to Podman's
Docker-API emulation layer, which drops the Compose `devices:` GPU entry without
erroring — ComfyUI starts but logs `Found no NVIDIA driver on your system`. Use
`podman-compose` instead, which resolves the CDI device correctly:

```bash
podman-compose up
```

Verify which one you have with `readlink -f "$(which docker)"` — if it points at
`podman`, use `podman-compose` for this project.

### Models not loading

```bash
# Check model directory
ls -la models/checkpoints/

# For B2: verify credentials
rclone lsd b2:your-bucket

# Check B2 mount logs
docker-compose exec comfyui cat /tmp/rclone-mount.log
```

### B2 connection issues

```bash
# Test B2 connectivity
rclone ls b2:your-bucket/models

# Check environment variables
docker-compose exec comfyui env | grep B2_
```

### RunPod deployment fails

```bash
# Verify API key
curl -H "Authorization: Bearer $RUNPOD_API_KEY" \
  https://api.runpod.ai/v2/

# Check image is accessible
docker pull ghcr.io/your-user/comfyui-serverless:latest
```

## Agent / MCP Access (Optional)

This image includes opt-in support for [Comfy MCP](https://github.com/artokun/comfyui-mcp) —
an MCP (Model Context Protocol) server that lets AI agents (Claude Code, Cursor, ChatGPT)
drive the ComfyUI instance: generate images/video/audio, author and run workflows, manage
models and custom nodes, and edit the live graph in natural language.

Also installs the [ComfyUI Agent Panel](https://github.com/artokun/comfyui-mcp-panel) —
an autonomous AI agent embedded in ComfyUI's sidebar (💬 tab) that drives your canvas
on Claude or ChatGPT (your own subscription, no API keys).

### Enabling MCP

Set `ENABLE_MCP=true` in your `.env` file (or RunPod environment variables):

```bash
# In .env or /runpod-volume/.env
ENABLE_MCP=true
MCP_TRANSPORT=http        # http (default), tunnel, or stdio
MCP_PORT=8765             # default port for HTTP transport
MCP_HTTP_TOKEN=your-secret # recommended for non-loopback access
```

When enabled, the container startup:
1. Installs `comfyui-mcp` (npm package) + `comfyui-mcp-panel` (custom node) via userscript
2. Starts the MCP server as a background process after ComfyUI is ready
3. The Agent Panel tab (💬) appears in the ComfyUI sidebar

### Transport Modes

| Mode | Use Case | Access |
|------|----------|--------|
| `http` (default) | Agent connects via SSH tunnel, OpenZiti, or RunPod proxy | `http://<host>:8765/mcp` |
| `tunnel` | Public access without exposing ports | Auto-generated `https://...` URL (printed to logs) |
| `stdio` | Agent runs on the same host | Local pipe (no port) |

### Connecting from Claude Code

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "comfyui": {
      "url": "http://localhost:8765/mcp",
      "headers": { "Authorization": "Bearer your-secret-token" }
    }
  }
}
```

For remote pods, use SSH port-forwarding:
```bash
ssh -L 8765:localhost:8765 -p 2222 comfy@<pod-host>
# Then point Claude Code at http://localhost:8765/mcp
```

### Using the Agent Panel

1. Open ComfyUI in your browser
2. Click the **Agent** tab (💬) in the sidebar
3. Sign in to your provider once: `claude` (Claude) or `codex login` (ChatGPT)
4. Click **Connect** — the panel starts the background orchestrator on your subscription
5. Type a request: "build a Flux txt2img graph and run it"

See the [comfyui-mcp documentation](https://comfyui-mcp.artokun.io/docs) for full details.

## Additional Documentation

- [Build Documentation](BUILD.md) - Docker build details
- [B2 Quick Start](storage/B2_RUNPOD_QUICKSTART.md) - Detailed B2 setup guide
- [Storage Migration](storage/MIGRATION.md) - Migrate between storage backends
- [Example Configs](storage/examples/) - Pre-configured .env examples
- [Testing Guide](TESTING.md) - Test suite documentation

## License

MIT
