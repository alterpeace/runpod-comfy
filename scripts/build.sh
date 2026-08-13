#!/bin/bash

# Build automation script for RunPod Serverless ComfyUI
# This script builds the Docker image and pushes it to GitHub Container Registry (ghcr.io)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
IMAGE_NAME="comfyui-serverless"
REGISTRY="ghcr.io"
BUILD_CONTEXT="$PROJECT_ROOT"
DOCKERFILE="$PROJECT_ROOT/Dockerfile"

# Parse command line arguments
PUSH=false
TAG_VERSION=""
GITHUB_USERNAME=""

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Build and optionally push Docker image to GitHub Container Registry.

OPTIONS:
    -u, --username USERNAME    GitHub username (required for push)
    -t, --tag VERSION         Additional version tag (e.g., v1.0.0, 1.2.3)
    -p, --push                Push image to registry after build
    -h, --help                Show this help message

EXAMPLES:
    # Build only (local testing)
    $0

    # Build and push with latest tag
    $0 --username myuser --push

    # Build and push with version tag
    $0 --username myuser --tag v1.0.0 --push

    # Build and push with semantic version
    $0 --username myuser --tag 1.2.3 --push

ENVIRONMENT VARIABLES:
    GITHUB_TOKEN              GitHub Personal Access Token (required for push)
    GITHUB_USERNAME           GitHub username (alternative to --username)

NOTES:
    - Images are always tagged with 'latest' and commit SHA
    - Use --tag to add additional version tags
    - GITHUB_TOKEN must be set for pushing to ghcr.io
    - Generate token at: https://github.com/settings/tokens
    - Token needs 'write:packages' permission

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--username)
            GITHUB_USERNAME="$2"
            shift 2
            ;;
        -t|--tag)
            TAG_VERSION="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Get GitHub username from environment if not provided
if [ -z "$GITHUB_USERNAME" ] && [ -n "$GITHUB_USERNAME_ENV" ]; then
    GITHUB_USERNAME="$GITHUB_USERNAME_ENV"
fi

# Validation: Check required files
log_info "Validating required files..."

REQUIRED_FILES=(
    "$DOCKERFILE"
    "$SCRIPT_DIR/../src/handler.py"
    "$SCRIPT_DIR/../src/comfyui_client.py"
    "$SCRIPT_DIR/../entrypoint.sh"
    "$SCRIPT_DIR/../pyproject.toml"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    log_error "Missing required files:"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    exit 1
fi

log_success "All required files present"

# Get git commit SHA for tagging
if command -v git &> /dev/null && [ -d "$PROJECT_ROOT/.git" ]; then
    COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    log_info "Git commit SHA: $COMMIT_SHA"
else
    COMMIT_SHA="unknown"
    log_warning "Git not available, using 'unknown' for commit SHA"
fi

# Build image tags
TAGS=()

if [ -n "$GITHUB_USERNAME" ]; then
    # Full registry path
    BASE_IMAGE="$REGISTRY/$GITHUB_USERNAME/$IMAGE_NAME"
    
    # Always tag with latest
    TAGS+=("$BASE_IMAGE:latest")
    
    # Tag with commit SHA if available
    if [ "$COMMIT_SHA" != "unknown" ]; then
        TAGS+=("$BASE_IMAGE:$COMMIT_SHA")
    fi
    
    # Tag with version if provided
    if [ -n "$TAG_VERSION" ]; then
        TAGS+=("$BASE_IMAGE:$TAG_VERSION")
    fi
else
    # Local build without registry path
    BASE_IMAGE="$IMAGE_NAME"
    TAGS+=("$BASE_IMAGE:latest")
    
    if [ "$COMMIT_SHA" != "unknown" ]; then
        TAGS+=("$BASE_IMAGE:$COMMIT_SHA")
    fi
    
    if [ -n "$TAG_VERSION" ]; then
        TAGS+=("$BASE_IMAGE:$TAG_VERSION")
    fi
fi

# Build Docker image
log_info "Building Docker image..."
log_info "Build context: $BUILD_CONTEXT"
log_info "Dockerfile: $DOCKERFILE"
log_info "Tags:"
for tag in "${TAGS[@]}"; do
    echo "  - $tag"
done

# Construct docker build command with all tags
# --network host ensures DNS works during build (avoids aardvark-dns issues with Podman)
BUILD_CMD="docker build --network host"
for tag in "${TAGS[@]}"; do
    BUILD_CMD="$BUILD_CMD -t $tag"
done

# Pass build args (defaults match Dockerfile ARGs; override via env vars)
BUILD_CMD="$BUILD_CMD \
    --build-arg COMFYUI_VERSION=\${COMFYUI_VERSION:-v0.32.0} \
    --build-arg TORCH_VERSION=\${TORCH_VERSION:-2.10.0} \
    --build-arg TORCH_FLAVOR=\${TORCH_FLAVOR:-cu129} \
    --build-arg XFORMERS_VERSION=\${XFORMERS_VERSION:-0.0.34} \
    --build-arg ENABLE_XFORMERS=\${ENABLE_XFORMERS:-false} \
    --build-arg ENABLE_SAGEATTENTION=\${ENABLE_SAGEATTENTION:-true} \
    --build-arg ENABLE_FLASHATTENTION=\${ENABLE_FLASHATTENTION:-false} \
    --build-arg ENABLE_TENSORRT=\${ENABLE_TENSORRT:-false} \
    --build-arg TORCH_CUDA_ARCH_LIST=\${TORCH_CUDA_ARCH_LIST:-8.9} \
    --build-arg MAX_JOBS=\${MAX_JOBS:-2}"

BUILD_CMD="$BUILD_CMD -f $DOCKERFILE $BUILD_CONTEXT"

log_info "Running: $BUILD_CMD"
if eval "$BUILD_CMD"; then
    log_success "Docker image built successfully"
else
    log_error "Docker build failed"
    exit 1
fi

# Push to registry if requested
if [ "$PUSH" = true ]; then
    log_info "Preparing to push image to registry..."
    
    # Validate GitHub username
    if [ -z "$GITHUB_USERNAME" ]; then
        log_error "GitHub username is required for pushing"
        log_error "Provide it with --username or set GITHUB_USERNAME environment variable"
        exit 1
    fi
    
    # Validate GitHub token
    if [ -z "$GITHUB_TOKEN" ]; then
        log_error "GITHUB_TOKEN environment variable is required for pushing"
        log_error "Generate a token at: https://github.com/settings/tokens"
        log_error "Token needs 'write:packages' permission"
        exit 1
    fi
    
    # Authenticate with GitHub Container Registry
    log_info "Authenticating with GitHub Container Registry..."
    if echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin 2>/dev/null; then
        log_success "Authentication successful"
    else
        log_error "Authentication failed"
        log_error "Please check your GITHUB_TOKEN and username"
        exit 1
    fi
    
    # Push all tags
    log_info "Pushing images to registry..."
    for tag in "${TAGS[@]}"; do
        # Only push tags with registry path
        if [[ "$tag" == "$REGISTRY"* ]]; then
            log_info "Pushing: $tag"
            if docker push "$tag"; then
                log_success "Pushed: $tag"
            else
                log_error "Failed to push: $tag"
                exit 1
            fi
        fi
    done
    
    log_success "All images pushed successfully"
    echo ""
    log_info "Images available at:"
    for tag in "${TAGS[@]}"; do
        if [[ "$tag" == "$REGISTRY"* ]]; then
            echo "  - $tag"
        fi
    done
    echo ""
    log_info "To use in RunPod, reference: $BASE_IMAGE:latest"
    
else
    log_info "Build complete (not pushing to registry)"
    log_info "To push, run with --push flag and set GITHUB_TOKEN"
fi

log_success "Build script completed successfully"
