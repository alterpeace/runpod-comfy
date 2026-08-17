#!/bin/bash
# Local testing script for RunPod serverless handler
# Tests the handler in a local Docker container
#
# Usage:
#   ./test_local.sh [workflow_file.json]
#
# Environment Variables:
#   IMAGE_NAME       - Docker image to use (default: ghcr.io/$(whoami)/comfyui-serverless:latest)
#   CONTAINER_NAME   - Container name (default: comfyui-test)
#   TEST_PORT        - Port to expose (default: 8188)
#
# Examples:
#   # Use default image
#   ./test_local.sh examples/text_to_image_simple.json
#
#   # Use local image (will auto-build if not found)
#   IMAGE_NAME=comfyui-serverless:local ./test_local.sh
#
#   # Use remote image (must exist or be pulled first)
#   IMAGE_NAME=ghcr.io/user/comfyui:v1 ./test_local.sh
#
# Notes:
#   - Local images (no registry prefix) will be built automatically if not found
#   - Remote images (with registry prefix) must be pulled manually first
#   - The script detects local vs remote based on image name format

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-comfyui-test}"
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/$(whoami)/comfyui-serverless:latest}"
WORKFLOW_FILE="${1:-$PROJECT_ROOT/examples/text_to_image_simple.json}"
TEST_PORT="${TEST_PORT:-8188}"

echo -e "${BLUE}=== ComfyUI Local Testing Script ===${NC}"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo -e "  Image: ${YELLOW}${IMAGE_NAME}${NC}"
echo -e "  Container: ${YELLOW}${CONTAINER_NAME}${NC}"
echo -e "  Port: ${YELLOW}${TEST_PORT}${NC}"
echo ""

# Check if workflow file exists
if [ ! -f "$WORKFLOW_FILE" ]; then
    echo -e "${RED}Error: Workflow file not found: $WORKFLOW_FILE${NC}"
    echo ""
    echo "Usage: $0 [workflow_file.json]"
    echo ""
    echo "Examples:"
    echo "  $0 examples/text_to_image_simple.json"
    echo "  IMAGE_NAME=myimage:tag $0 examples/image_to_image.json"
    echo ""
    echo "Environment Variables:"
    echo "  IMAGE_NAME       - Docker image to use"
    echo "  CONTAINER_NAME   - Container name"
    echo "  TEST_PORT        - Port to expose"
    exit 1
fi

echo -e "${BLUE}Testing with workflow: ${YELLOW}$WORKFLOW_FILE${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

# Check if image exists
if ! docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Image $IMAGE_NAME not found${NC}"
    
    # Check if it's a local image (no registry prefix)
    if [[ ! "$IMAGE_NAME" =~ ^[a-z0-9.-]+\.[a-z]{2,}/ ]] && [[ ! "$IMAGE_NAME" =~ ^ghcr\.io/ ]]; then
        echo -e "${BLUE}Building local image with tag: $IMAGE_NAME${NC}"
        # Extract tag from image name
        IMAGE_TAG="${IMAGE_NAME##*:}"
        if [ "$IMAGE_TAG" = "$IMAGE_NAME" ]; then
            IMAGE_TAG="latest"
        fi
        
        # Build with the specified tag
        docker build -t "$IMAGE_NAME" -f "$PROJECT_ROOT/Dockerfile" "$PROJECT_ROOT" || {
            echo -e "${RED}Failed to build image${NC}"
            exit 1
        }
        echo -e "${GREEN}✓ Image built successfully${NC}"
    else
        echo -e "${RED}Error: Remote image $IMAGE_NAME not found${NC}"
        echo -e "${YELLOW}Hint: For local images, use a name without registry prefix${NC}"
        echo -e "${YELLOW}Example: IMAGE_NAME=comfyui-serverless:local ./test_local.sh${NC}"
        exit 1
    fi
fi

# Stop and remove existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Stopping existing container...${NC}"
    docker stop "$CONTAINER_NAME" > /dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true
fi

# Start container
echo -e "${BLUE}Starting container...${NC}"
docker run -d \
    --name "$CONTAINER_NAME" \
    --gpus all \
    -p ${TEST_PORT}:8188 \
    -e MODE=local \
    -e COMFYUI_ARGS="--lowvram" \
    -v "$PROJECT_ROOT/examples:/workspace/examples:ro" \
    -v "$PROJECT_ROOT/models:/comfyui/models:ro" \
    "$IMAGE_NAME"

# Wait for container to be ready
echo -e "${BLUE}Waiting for ComfyUI to start...${NC}"
MAX_WAIT=120
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if docker logs "$CONTAINER_NAME" 2>&1 | grep -q "ComfyUI WebUI is ready"; then
        echo -e "${GREEN}✓ ComfyUI is ready${NC}"
        break
    fi
    
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${RED}Error: Container stopped unexpectedly${NC}"
        echo -e "${YELLOW}Container logs:${NC}"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo -e "${RED}Error: ComfyUI failed to start within ${MAX_WAIT}s${NC}"
    echo -e "${YELLOW}Container logs:${NC}"
    docker logs "$CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" > /dev/null 2>&1
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1
    exit 1
fi

# Test handler with workflow
echo -e "${BLUE}Testing handler with workflow...${NC}"
echo ""

# Create test job payload
TEST_JOB=$(cat <<EOF
{
    "id": "test-job-$(date +%s)",
    "input": {
        "workflow": $(cat "$WORKFLOW_FILE")
    }
}
EOF
)

# Execute handler test inside container
docker exec "$CONTAINER_NAME" python3 -c "
import sys
import json
sys.path.insert(0, '/workspace')

from handler import handler

# Load test job
job = json.loads('''$TEST_JOB''')

# Execute handler
print('Executing handler...')
result = handler(job)

# Print result
print(json.dumps(result, indent=2))

# Check result
if result.get('status') == 'success':
    print('\n✓ Handler test PASSED')
    sys.exit(0)
else:
    print('\n✗ Handler test FAILED')
    sys.exit(1)
" || {
    echo -e "${RED}Handler test failed${NC}"
    echo -e "${YELLOW}Container logs:${NC}"
    docker logs "$CONTAINER_NAME" --tail 50
    docker stop "$CONTAINER_NAME" > /dev/null 2>&1
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1
    exit 1
}

echo ""
echo -e "${GREEN}=== Test completed successfully ===${NC}"
echo ""
echo -e "${BLUE}Container is still running for manual testing:${NC}"
echo -e "  ComfyUI WebUI: ${YELLOW}http://localhost:${TEST_PORT}${NC}"
echo -e "  Container name: ${YELLOW}${CONTAINER_NAME}${NC}"
echo ""
echo -e "${BLUE}To view logs:${NC}"
echo -e "  docker logs -f ${CONTAINER_NAME}"
echo ""
echo -e "${BLUE}To stop and remove container:${NC}"
echo -e "  docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}"
echo ""
