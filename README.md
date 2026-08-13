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
> `docker` is a Podman/crun shim.) There are three Podman-specific issues that prevent
> GPU passthrough through `docker compose up`:
>
> 1. Podman 4.9.x ships a CDI parser that doesn't support the CDI v0.7.0 spec generated
>    by recent NVIDIA Container Toolkit releases, so GPU access fails with
>    `unresolvable CDI devices nvidia.com/gpu=all`.
> 2. The external Docker Compose provider (v5.x) mangles the CDI device string
>    `nvidia.com/gpu=all` into path-based `source:target` syntax, which Podman no
>    longer recognizes as CDI. The `deploy.resources` GPU block is also silently
>    ignored.
> 3. The CDI spec only mounts versioned `.so` files (e.g. `libcuda.so.580.173.02`),
>    not the unversioned symlinks (`libcuda.so.1`) that the dynamic linker resolves.
>
> **One-command fix** — run this after every reboot or driver update:
> ```bash
> ./scripts/setup_local_gpu.sh
> ```
> This patches the CDI spec, generates a `docker-compose.gpu.yml` override with
> explicit device + library mounts, creates NVIDIA `.so` symlinks inside the
> container at startup (via `entrypoint.sh`), and restarts the container.
>
> After the first run, you can start normally with:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
> ```
> Or add to `.env`:
> ```bash
> COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
> ```
> Then just `docker compose up -d`.
>
> None of this affects the built image or RunPod deployments - they're purely about
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
./scripts/run_local.sh
```

This automatically handles GPU passthrough (patches CDI spec if needed, generates
the GPU compose override) and starts the container. Access WebUI at
http://localhost:8188.

Other options:
```bash
./scripts/run_local.sh --build   # rebuild image first
./scripts/run_local.sh --logs    # start + follow logs
```

For RunPod deployments:
```bash
./scripts/run_runpod.sh serverless deploy    # deploy serverless endpoint
./scripts/run_runpod.sh pods create --gpu "RTX 4090" --name "comfy-prod"
```

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

### GPU not visible / "Found no NVIDIA driver on your system"

This happens on Podman-based local setups (where `docker` is a Podman/crun shim).
There are three separate issues:

1. **CDI v0.7.0 incompatibility** — Podman 4.9.x doesn't support the CDI v0.7.0
   schema NVIDIA Container Toolkit generates by default.
2. **Compose CDI mangling** — The external Docker Compose provider (v5.x) converts
   `nvidia.com/gpu=all` into path-based `source:target` syntax, which Podman no
   longer recognizes as CDI. The `deploy.resources` GPU block is also silently
   ignored.
3. **Missing library symlinks** — The CDI spec only mounts versioned `.so` files
   (e.g. `libcuda.so.580.173.02`), not the unversioned symlinks (`libcuda.so.1`)
   that the dynamic linker resolves.

**One-command fix** for all three:

```bash
./scripts/setup_local_gpu.sh
```

This patches the CDI spec, generates `docker-compose.gpu.yml` with explicit
device + library mounts, creates NVIDIA `.so` symlinks at container startup,
and restarts the container. Re-run after every reboot or driver update (the
CDI spec on `/var/run/cdi` is tmpfs and resets on reboot).

After the first run, start normally with:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Or add to `.env`:
```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
```

This is a local-only workaround; it does not need to be applied on RunPod.

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

## Additional Documentation

- [Build Documentation](BUILD.md) - Docker build details
- [B2 Quick Start](storage/B2_RUNPOD_QUICKSTART.md) - Detailed B2 setup guide
- [Storage Migration](storage/MIGRATION.md) - Migrate between storage backends
- [Example Configs](storage/examples/) - Pre-configured .env examples
- [Testing Guide](TESTING.md) - Test suite documentation

## License

MIT
