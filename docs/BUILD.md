# Docker Build Documentation

## Overview

The Dockerfile creates a multi-mode ComfyUI image that supports:
- **Local development** (Docker Compose)
- **RunPod Serverless** (pay-per-execution)
- **RunPod Pods** (persistent servers)

## Dockerfile Structure

The root `Dockerfile` is self-contained — it builds ComfyUI from scratch on
top of the official NVIDIA CUDA image.

### Base Image
```dockerfile
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS base
...
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04 AS runtime-base
```
Multi-stage build: a `devel` image for compiling CUDA extensions
(SageAttention, FlashAttention, xformers), and a slimmer `runtime` image for
the final container.

### System Dependencies
- **OpenSSH Server**: For SSH access and debugging
- **cloudflared**: For stable WebUI tunnel access on serverless (userspace, no CAP_NET_ADMIN needed)
- **rclone**: For B2/S3-compatible model storage mounting
- **curl/wget**: For downloading and health checks

### Python Dependencies
- **uv**: Fast Python package manager (10-100x faster than pip)
- **RunPod SDK**: For serverless handler integration
- **requests**: For HTTP API calls to ComfyUI
- **torch/torchvision/torchaudio**: Pinned version, locked at runtime via
  `PIP_CONSTRAINT`/`UV_CONSTRAINT` (`torch_lock.txt`) so ComfyUI-Manager or
  custom node installs can't silently upgrade PyTorch underneath you.

### Optional Dependencies
- **extra-requirements.txt**: Custom Python packages (if present)
- **add-dependancies.sh**: Custom setup script (if present)
- **ENABLE_XFORMERS / ENABLE_SAGEATTENTION / ENABLE_FLASHATTENTION**: build
  args to toggle optional attention kernels (compiling these adds
  significant build time)

### Layer Caching Optimization

The Dockerfile is structured to maximize Docker layer caching (4 stages:
`base` → `deps` → `runtime-base` → `runtime`):

1. **System packages** (rarely change)
2. **PyTorch + core ML deps** (only rebuild if TORCH_VERSION changes)
3. **ComfyUI + custom-node Python deps** (extra-requirements.txt)
4. **Runtime base** (rclone, cloudflared, SSH, user setup)
5. **Application code** (handler.py, comfyui_client.py, entrypoint.sh)
6. **Configuration files** (runpod-config-*.json, .env.example)

This means code changes don't require reinstalling all dependencies.

### Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8188/ || exit 1
```

Verifies ComfyUI WebUI is running and accessible.

### Entrypoint

```dockerfile
ENTRYPOINT ["/workspace/entrypoint.sh"]
```

The entrypoint script handles:
- Mode detection (local vs serverless vs pods)
- Configuration loading from .env
- Optional SSH server startup
- ComfyUI server startup
- Handler launch (serverless mode only)

## Building the Image

### Quick Build

```bash
./build.sh
```

This interactive script will:
1. Validate all required files are present
2. Build the Docker image
3. Tag with version and git commit SHA
4. Optionally push to GitHub Container Registry

### Manual Build

```bash
# Basic build
docker build -t comfyui-serverless:latest .

# Build with custom tag
docker build -t ghcr.io/username/comfyui-serverless:v1.0.0 .

# Build with build cache
docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t comfyui-serverless:latest .
```

### Environment Variables for Build

- `IMAGE_NAME`: Image name (default: comfyui-serverless)
- `REGISTRY`: Container registry (default: ghcr.io)
- `GITHUB_USERNAME`: GitHub username for registry
- `VERSION`: Image version tag (default: latest)
- `GITHUB_TOKEN`: GitHub personal access token for pushing

Example:
```bash
export IMAGE_NAME="my-comfyui"
export VERSION="1.0.0"
export GITHUB_USERNAME="myusername"
./build.sh
```

## Pushing to GitHub Container Registry

### Prerequisites

1. Create a GitHub Personal Access Token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `write:packages`, `read:packages`
   - Copy the token

2. Set environment variable:
   ```bash
   export GITHUB_TOKEN="ghp_your_token_here"
   ```

### Push Image

```bash
# Using build script (recommended)
./build.sh
# Answer 'y' when prompted to push

# Manual push
echo "$GITHUB_TOKEN" | docker login ghcr.io -u username --password-stdin
docker push ghcr.io/username/comfyui-serverless:latest
```

### Make Image Public

By default, GitHub Container Registry images are private. To make public:

1. Go to https://github.com/users/USERNAME/packages/container/comfyui-serverless/settings
2. Scroll to "Danger Zone"
3. Click "Change visibility" → "Public"

## Testing the Build

### Local Test with Docker Compose

```bash
docker-compose up
```

Access ComfyUI at http://localhost:8188

### Manual Test

```bash
# Run container
docker run --gpus all -p 8188:8188 -p 2222:22 \
  -e MODE=local \
  -e ENABLE_SSH=true \
  comfyui-serverless:latest

# Check logs
docker logs <container-id>

# Access ComfyUI
curl http://localhost:8188/
```

### Test with Optional Features

```bash
# Create test .env file
cat > test.env << EOF
ENABLE_SSH=true
SSH_PUBLIC_KEY="ssh-rsa AAAAB3NzaC1yc2E... user@host"
EOF

# Run with .env
docker run --gpus all -p 8188:8188 -p 2222:22 \
  -v $(pwd)/test.env:/workspace/.env:ro \
  comfyui-serverless:latest
```

## Troubleshooting

### Build Fails: "extra-requirements.txt not found"

This is expected if you don't have custom dependencies. The Dockerfile handles this gracefully.

### Build Fails: "uv: command not found"

The uv installer adds to PATH in the same RUN command. If this fails, check:
- Internet connectivity during build
- Proxy settings if behind corporate firewall

### Image Size Too Large

The base ComfyUI image is already large (~10GB). To reduce size:
- Don't include unnecessary models in the image
- Use network volumes for models instead
- Clean up apt cache (already done in Dockerfile)

### Health Check Failing

The health check expects ComfyUI to be running on port 8188. If using a different port:
```dockerfile
HEALTHCHECK CMD curl -f http://localhost:YOUR_PORT/ || exit 1
```

## Advanced Build Options

### Multi-Platform Build

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/username/comfyui-serverless:latest \
  --push .
```

### Build with Secrets

```bash
# For private model downloads during build
docker build --secret id=hf_token,src=.hf_token \
  -t comfyui-serverless:latest .
```

### Build with Custom Base Image

```bash
docker build --build-arg BASE_IMAGE=custom/comfyui:tag \
  -t comfyui-serverless:latest .
```

## File Requirements

### Required Files
- `Dockerfile`
- `handler.py`
- `comfyui_client.py`
- `entrypoint.sh`
- `pyproject.toml`
- `runpod-config.json`
- `.env.example`
- `ssh/setup_ssh.sh`
- `ssh/sshd_config`

### Optional Files
- `extra-requirements.txt` - Additional Python packages
- `add-dependancies.sh` - Custom setup script
- `uv.lock` - Locked dependency versions

### Excluded Files (.dockerignore)
- `.venv/`, `__pycache__/` - Local development artifacts
- `.git/` - Git repository
- `README.md` - Documentation
- `.env` - Secrets (never include in image!)

## Next Steps

After building:
1. Test locally with `docker-compose up`
2. Push to GitHub Container Registry
3. Deploy to RunPod Serverless or Pods
4. See deployment documentation for RunPod configuration
