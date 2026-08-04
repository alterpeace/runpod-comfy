# Testing Guide

This guide explains how to test the ComfyUI RunPod serverless handler locally and on deployed endpoints.

## Local Testing

### Prerequisites

- Docker installed and running
- GPU support configured (for actual image generation)
- Built Docker image

### Building the Image

```bash
# Build with default tag (comfyui-serverless:latest)
./build.sh

# Or let the test script build it with a custom tag
IMAGE_NAME=comfyui-serverless:local ./test_local.sh
```

The test script will automatically build the image if it doesn't exist (for local images only).

### Running Local Tests

#### Basic Usage

```bash
# Test with default workflow
./test_local.sh

# Test with specific workflow
./test_local.sh examples/text_to_image_simple.json
./test_local.sh examples/image_to_image.json
```

#### Custom Configuration

You can customize the test environment using environment variables:

```bash
# Use a custom image
IMAGE_NAME=my-registry/comfyui:v1.0 ./test_local.sh

# Use locally built image
IMAGE_NAME=comfyui-serverless:local ./test_local.sh

# Use custom container name and port
CONTAINER_NAME=my-test TEST_PORT=8080 ./test_local.sh

# Combine multiple options
IMAGE_NAME=comfyui-serverless:local \
CONTAINER_NAME=comfyui-dev \
TEST_PORT=8080 \
./test_local.sh examples/text_to_image_simple.json
```

#### Available Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_NAME` | `ghcr.io/$(whoami)/comfyui-serverless:latest` | Docker image to use |
| `CONTAINER_NAME` | `comfyui-test` | Name for the test container |
| `TEST_PORT` | `8188` | Port to expose ComfyUI WebUI |

### What the Script Does

1. Validates the workflow file exists
2. Checks Docker is running
3. Builds the image if it doesn't exist
4. Stops any existing test container
5. Starts a new container with GPU support
6. Waits for ComfyUI to be ready
7. Executes the handler with your workflow
8. Leaves the container running for manual testing

### Manual Testing

After the script completes, the container remains running so you can:

- Access ComfyUI WebUI: `http://localhost:8188`
- View logs: `docker logs -f comfyui-test`
- Execute commands: `docker exec -it comfyui-test bash`

To stop and remove the container:

```bash
docker stop comfyui-test && docker rm comfyui-test
```

## RunPod Endpoint Testing

### Prerequisites

- Deployed RunPod serverless endpoint
- RunPod API key
- Python 3.8+

### Setup

```bash
# Set your credentials
export RUNPOD_ENDPOINT_ID="your-endpoint-id"
export RUNPOD_API_KEY="your-api-key"
```

### Running Endpoint Tests

#### Basic Usage

```bash
# Test with default workflow
python test_runpod.py

# Test with specific workflow
python test_runpod.py --workflow examples/text_to_image_simple.json
```

#### Advanced Options

```bash
# Test image-to-image workflow
python test_runpod.py \
  --workflow examples/image_to_image.json \
  --input-image path/to/input.png \
  --input-image-name input_image.png

# Custom timeout
python test_runpod.py \
  --workflow examples/text_to_image_simple.json \
  --timeout 600

# Custom output directory
python test_runpod.py \
  --workflow examples/text_to_image_simple.json \
  --output-dir my_outputs

# Verbose output (shows full response JSON)
python test_runpod.py \
  --workflow examples/text_to_image_simple.json \
  --verbose
```

#### Command-Line Options

```
--endpoint-id ID      RunPod endpoint ID (or set RUNPOD_ENDPOINT_ID)
--api-key KEY         RunPod API key (or set RUNPOD_API_KEY)
--workflow FILE       Path to workflow JSON file
--input-image FILE    Path to input image for img2img workflows
--input-image-name    Name for input image in workflow
--timeout SECONDS     Custom timeout in seconds
--output-dir DIR      Directory to save output images
--verbose             Print full response JSON
```

## Automated Testing

### Running Unit Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_integration.py
uv run pytest tests/test_performance.py
uv run pytest tests/test_concurrent.py

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=. tests/
```

### Test Suites

#### Integration Tests (`tests/test_integration.py`)
- Complete workflow execution (text-to-image, image-to-image)
- Storage integration (volume, S3, response)
- Error handling scenarios
- Cleanup functionality

#### Performance Tests (`tests/test_performance.py`)
- Cold start and warm start timing
- Workflow complexity handling
- Memory efficiency
- Timeout handling
- Metadata accuracy

#### Concurrent Tests (`tests/test_concurrent.py`)
- Multiple concurrent job execution
- Job isolation
- Resource management
- Throughput and scaling

## Example Workflows

### Text-to-Image

```bash
./test_local.sh examples/text_to_image_simple.json
```

Generates a 512x512 image from a text prompt using Stable Diffusion XL.

### Image-to-Image

```bash
# Local testing
./test_local.sh examples/image_to_image.json

# RunPod testing
python test_runpod.py \
  --workflow examples/image_to_image.json \
  --input-image path/to/input.png
```

Transforms an input image using style transfer with 75% denoise strength.

## Troubleshooting

### Docker Image Not Found

If you see "Unable to find image" error:

**For local images** (no registry prefix):
```bash
# The script will automatically build it
IMAGE_NAME=comfyui-serverless:local ./test_local.sh

# Or build manually first
docker build -t comfyui-serverless:local .
```

**For remote images** (with registry prefix):
```bash
# Pull the image first
docker pull ghcr.io/username/comfyui-serverless:latest

# Then run the test
IMAGE_NAME=ghcr.io/username/comfyui-serverless:latest ./test_local.sh
```

**Note:** The script distinguishes between local and remote images:
- Local: `comfyui-serverless:local`, `myimage:v1.0`
- Remote: `ghcr.io/user/image:latest`, `docker.io/user/image:latest`

### Container Fails to Start

Check Docker logs:

```bash
docker logs comfyui-test
```

Common issues:
- GPU not available: Add `--gpus all` flag or remove GPU requirement
- Port already in use: Change `TEST_PORT` environment variable
- Insufficient memory: Increase Docker memory limit

### RunPod Endpoint Timeout

If requests timeout:

```bash
# Increase timeout
python test_runpod.py --timeout 900
```

### Permission Denied

Make scripts executable:

```bash
chmod +x test_local.sh test_runpod.py
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test Handler

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run tests
        run: uv run pytest -v
```

## Best Practices

1. **Always test locally first** before deploying to RunPod
2. **Use version tags** for Docker images in production
3. **Set appropriate timeouts** based on workflow complexity
4. **Monitor resource usage** during concurrent testing
5. **Keep test workflows simple** for faster iteration
6. **Use environment variables** for sensitive data (API keys)
7. **Clean up test containers** after testing

## Additional Resources

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [RunPod Serverless Documentation](https://docs.runpod.io/serverless/overview)
- [Example Workflows](./examples/README.md)
