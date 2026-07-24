# Quick Start Guide

Get up and running with local testing in 2 minutes.

## Prerequisites

- Docker with GPU support
- Git

## Quick Test (Recommended)

```bash
# Clone and navigate to the directory
cd runpod-comfy

# Run test with auto-build
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh
```

That's it! The script will:
1. Build the Docker image if needed
2. Start a container
3. Run a test workflow
4. Leave the container running for you to explore

## What Just Happened?

The test script:
- ✅ Built a Docker image tagged `comfyui-serverless:local`
- ✅ Started a container with GPU support
- ✅ Ran a text-to-image workflow
- ✅ Left the container running at `http://localhost:8188`

## Next Steps

### View the Results

```bash
# Check container logs
docker logs -f comfyui-test

# Access ComfyUI WebUI
open http://localhost:8188
```

### Try Different Workflows

```bash
# Image-to-image transformation
IMAGE_NAME=comfyui-serverless:local \
./scripts/test_local.sh examples/image_to_image.json

# Custom workflow
IMAGE_NAME=comfyui-serverless:local \
./scripts/test_local.sh path/to/your/workflow.json
```

### Clean Up

```bash
# Stop and remove the test container
docker stop comfyui-test && docker rm comfyui-test
```

## Common Scenarios

### Scenario 1: First Time Setup

```bash
# Just run it - everything is automatic
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh
```

### Scenario 2: Testing After Code Changes

```bash
# Rebuild the image
docker build -t comfyui-serverless:local .

# Run tests
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh
```

### Scenario 3: Using a Pre-built Image

```bash
# Pull from registry
docker pull ghcr.io/username/comfyui-serverless:latest

# Test it
IMAGE_NAME=ghcr.io/username/comfyui-serverless:latest ./scripts/test_local.sh
```

### Scenario 4: Custom Configuration

```bash
# Use custom port and container name
IMAGE_NAME=comfyui-serverless:local \
CONTAINER_NAME=my-test \
TEST_PORT=8080 \
./scripts/test_local.sh examples/text_to_image_simple.json
```

## Troubleshooting

### "Docker is not running"

```bash
# Start Docker
sudo systemctl start docker  # Linux
# or open Docker Desktop      # Mac/Windows
```

### "Image not found" (Remote Image)

```bash
# Pull the image first
docker pull ghcr.io/username/comfyui-serverless:latest

# Or use a local image name (auto-builds)
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh
```

### "Container stopped unexpectedly"

```bash
# Check the logs
docker logs comfyui-test

# Common issues:
# - GPU not available: Remove --gpus all from script
# - Port in use: Use TEST_PORT=8080
# - Out of memory: Increase Docker memory limit
```

### Build Fails

```bash
# Check you're in the right directory
pwd  # Should show .../runpod-comfy

# Verify Dockerfile exists
ls -la Dockerfile

# Try building manually to see detailed errors
docker build -t comfyui-serverless:local .
```

## Understanding Image Names

The script automatically detects whether an image is local or remote:

**Local Images** (auto-build if not found):
- `comfyui-serverless:local`
- `myimage:v1.0`
- `test:latest`

**Remote Images** (must be pulled first):
- `ghcr.io/user/image:latest`
- `docker.io/user/image:latest`
- `registry.example.com/image:latest`

## Running Automated Tests

```bash
# Install dependencies
pip install uv
uv sync

# Run all tests
uv run pytest

# Run specific test suite
uv run pytest tests/test_integration.py -v
```

