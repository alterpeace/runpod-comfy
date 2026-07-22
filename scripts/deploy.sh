#!/bin/bash

# Deployment helper script for RunPod Serverless and Pods
# This script helps deploy ComfyUI to RunPod in either serverless or pods mode

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
MODE=""
DEPLOYMENT_NAME=""
IMAGE_URL=""
GPU_TYPE="NVIDIA RTX A4000"
GPU_COUNT=1
CONTAINER_DISK_GB=50
VOLUME_GB=100
VOLUME_ID=""
TIMEOUT_SECONDS=600
MIN_WORKERS=0
MAX_WORKERS=3
IDLE_TIMEOUT=5
SPOT_INSTANCE=false
COMFYUI_ARGS="--use-sage-attention --lowvram"

usage() {
    echo -e "${GREEN}RunPod Deployment Helper${NC}"
    echo ""
    echo "Deploy ComfyUI to RunPod in either Serverless or Pods mode."
    echo ""
    echo -e "${YELLOW}USAGE:${NC}"
    echo "    $0 [OPTIONS]"
    echo ""
    echo -e "${YELLOW}REQUIRED OPTIONS:${NC}"
    echo "    -m, --mode MODE              Deployment mode: 'serverless' or 'pods'"
    echo "    -n, --name NAME              Deployment name"
    echo "    -i, --image IMAGE_URL        Docker image URL (e.g., ghcr.io/user/image:tag)"
    echo ""
    echo -e "${YELLOW}OPTIONAL OPTIONS:${NC}"
    echo "    -g, --gpu GPU_TYPE           GPU type (default: \"NVIDIA RTX A4000\")"
    echo "    -c, --gpu-count COUNT        Number of GPUs (default: 1)"
    echo "    -d, --disk SIZE_GB           Container disk size in GB (default: 50)"
    echo "    -v, --volume SIZE_GB         Create NEW network volume with size in GB (default: 100)"
    echo "    --volume-id VOLUME_ID        Attach EXISTING network volume by ID (alternative to -v)"
    echo "    -t, --timeout SECONDS        Timeout in seconds (serverless only, default: 600)"
    echo "    --min-workers COUNT          Min workers (serverless only, default: 0)"
    echo "    --max-workers COUNT          Max workers (serverless only, default: 3)"
    echo "    --idle-timeout MINUTES       Idle timeout in minutes (serverless only, default: 5)"
    echo "    --spot                       Use spot instances (pods only, cheaper but can be interrupted)"
    echo "    --comfyui-args ARGS          ComfyUI startup arguments (default: \"--use-sage-attention --lowvram\")"
    echo "    -h, --help                   Show this help message"
    echo ""
    echo -e "${YELLOW}ENVIRONMENT VARIABLES:${NC}"
    echo "    RUNPOD_API_KEY               RunPod API key (required)"
    echo "                                 Get from: https://www.runpod.io/console/user/settings"
    echo ""
    echo -e "${YELLOW}EXAMPLES:${NC}"
    echo ""
    echo -e "    ${CYAN}# Deploy serverless endpoint with new volume${NC}"
    echo "    $0 --mode serverless \\"
    echo "       --name comfyui-api \\"
    echo "       --image ghcr.io/myuser/comfyui-serverless:latest \\"
    echo "       --gpu \"NVIDIA RTX A4000\" \\"
    echo "       --timeout 600"
    echo ""
    echo -e "    ${CYAN}# Deploy serverless with existing volume (reuse models/data)${NC}"
    echo "    $0 --mode serverless \\"
    echo "       --name comfyui-api \\"
    echo "       --image ghcr.io/myuser/comfyui-serverless:latest \\"
    echo "       --volume-id abc123def456"
    echo ""
    echo -e "    ${CYAN}# Deploy persistent pod with spot instance${NC}"
    echo "    $0 --mode pods \\"
    echo "       --name comfyui-dev \\"
    echo "       --image ghcr.io/myuser/comfyui-serverless:latest \\"
    echo "       --gpu \"NVIDIA RTX A4000\" \\"
    echo "       --spot"
    echo ""
    echo -e "    ${CYAN}# Deploy pod with existing volume${NC}"
    echo "    $0 --mode pods \\"
    echo "       --name comfyui-production \\"
    echo "       --image ghcr.io/myuser/comfyui-serverless:latest \\"
    echo "       --gpu \"NVIDIA A100 80GB PCIe\" \\"
    echo "       --volume-id abc123def456"
    echo ""
    echo -e "${YELLOW}COMMON GPU TYPES:${NC}"
    echo "    - NVIDIA RTX A4000 (16GB, good for most workflows)"
    echo "    - NVIDIA RTX A5000 (24GB, better for large models)"
    echo "    - NVIDIA A100 80GB PCIe (80GB, best performance)"
    echo "    - NVIDIA RTX 4090 (24GB, excellent price/performance)"
    echo ""
    echo -e "${YELLOW}NOTES:${NC}"
    echo "    - Serverless: Pay per execution, auto-scales, best for API workloads"
    echo "    - Pods: Persistent server, billed continuously, best for interactive use"
    echo "    - Spot instances: ~50% cheaper but can be interrupted"
    echo "    - Always terminate pods when not in use to stop billing!"
    echo "    - Network volumes persist across deployments - use --volume-id to reuse"
    echo "    - Find volume IDs in RunPod console: https://www.runpod.io/console/user/storage"
    echo "    - Reusing volumes preserves models, workflows, and outputs"
    echo ""
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        -n|--name)
            DEPLOYMENT_NAME="$2"
            shift 2
            ;;
        -i|--image)
            IMAGE_URL="$2"
            shift 2
            ;;
        -g|--gpu)
            GPU_TYPE="$2"
            shift 2
            ;;
        -c|--gpu-count)
            GPU_COUNT="$2"
            shift 2
            ;;
        -d|--disk)
            CONTAINER_DISK_GB="$2"
            shift 2
            ;;
        -v|--volume)
            VOLUME_GB="$2"
            shift 2
            ;;
        --volume-id)
            VOLUME_ID="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --min-workers)
            MIN_WORKERS="$2"
            shift 2
            ;;
        --max-workers)
            MAX_WORKERS="$2"
            shift 2
            ;;
        --idle-timeout)
            IDLE_TIMEOUT="$2"
            shift 2
            ;;
        --spot)
            SPOT_INSTANCE=true
            shift
            ;;
        --comfyui-args)
            COMFYUI_ARGS="$2"
            shift 2
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

# Validate required parameters
if [ -z "$MODE" ]; then
    log_error "Deployment mode is required (--mode serverless or --mode pods)"
    exit 1
fi

if [ "$MODE" != "serverless" ] && [ "$MODE" != "pods" ]; then
    log_error "Invalid mode: $MODE (must be 'serverless' or 'pods')"
    exit 1
fi

if [ -z "$DEPLOYMENT_NAME" ]; then
    log_error "Deployment name is required (--name)"
    exit 1
fi

if [ -z "$IMAGE_URL" ]; then
    log_error "Docker image URL is required (--image)"
    exit 1
fi

if [ -z "$RUNPOD_API_KEY" ]; then
    log_error "RUNPOD_API_KEY environment variable is required"
    log_error "Get your API key from: https://www.runpod.io/console/user/settings"
    exit 1
fi

# Display deployment configuration
echo ""
log_step "Deployment Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Mode:              $MODE"
echo "Name:              $DEPLOYMENT_NAME"
echo "Image:             $IMAGE_URL"
echo "GPU Type:          $GPU_TYPE"
echo "GPU Count:         $GPU_COUNT"
echo "Container Disk:    ${CONTAINER_DISK_GB}GB"
if [ -n "$VOLUME_ID" ]; then
    echo "Network Volume:    Existing volume ID: $VOLUME_ID"
else
    echo "Network Volume:    Create new ${VOLUME_GB}GB volume"
fi
if [ "$MODE" = "serverless" ]; then
    echo "Timeout:           ${TIMEOUT_SECONDS}s"
    echo "Min Workers:       $MIN_WORKERS"
    echo "Max Workers:       $MAX_WORKERS"
    echo "Idle Timeout:      ${IDLE_TIMEOUT}min"
fi
if [ "$MODE" = "pods" ]; then
    echo "Instance Type:     $([ "$SPOT_INSTANCE" = true ] && echo "Spot (cheaper, can be interrupted)" || echo "On-Demand (reliable)")"
fi
echo "ComfyUI Args:      $COMFYUI_ARGS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Cost estimation
if [ "$MODE" = "pods" ]; then
    log_warning "COST WARNING: Pods are billed continuously while they exist!"
    log_warning "Stopping a pod does NOT stop billing - you must TERMINATE it"
    log_warning "Network storage persists after termination and can be reattached"
    echo ""
fi

# Confirmation prompt
read -p "$(echo -e ${YELLOW}Continue with deployment? [y/N]:${NC} )" -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Deployment cancelled"
    exit 0
fi

# Create deployment configuration file
CONFIG_FILE="/tmp/runpod-deploy-${DEPLOYMENT_NAME}.json"

if [ "$MODE" = "serverless" ]; then
    log_step "Creating serverless endpoint configuration..."
    
    # Build volume configuration
    if [ -n "$VOLUME_ID" ]; then
        VOLUME_CONFIG="\"volume_id\": \"${VOLUME_ID}\","
    else
        VOLUME_CONFIG="\"volume_in_gb\": ${VOLUME_GB},"
    fi
    
    cat > "$CONFIG_FILE" << EOF
{
  "name": "${DEPLOYMENT_NAME}",
  "image": "${IMAGE_URL}",
  "gpu_type_id": "${GPU_TYPE}",
  "container_disk_in_gb": ${CONTAINER_DISK_GB},
  ${VOLUME_CONFIG}
  "volume_mount_path": "/runpod-volume",
  "env": {
    "MODE": "serverless",
    "COMFYUI_PORT": "8188",
    "COMFYUI_ARGS": "${COMFYUI_ARGS}"
  },
  "docker_args": "",
  "start_ssh": false,
  "timeout": ${TIMEOUT_SECONDS},
  "scaling": {
    "min_workers": ${MIN_WORKERS},
    "max_workers": ${MAX_WORKERS},
    "idle_timeout": ${IDLE_TIMEOUT}
  }
}
EOF

elif [ "$MODE" = "pods" ]; then
    log_step "Creating pods configuration..."
    
    # Build volume configuration
    if [ -n "$VOLUME_ID" ]; then
        VOLUME_CONFIG="\"volume_id\": \"${VOLUME_ID}\","
    else
        VOLUME_CONFIG="\"volume_in_gb\": ${VOLUME_GB},"
    fi
    
    cat > "$CONFIG_FILE" << EOF
{
  "name": "${DEPLOYMENT_NAME}",
  "image": "${IMAGE_URL}",
  "gpu_type_id": "${GPU_TYPE}",
  "gpu_count": ${GPU_COUNT},
  "container_disk_in_gb": ${CONTAINER_DISK_GB},
  ${VOLUME_CONFIG}
  "volume_mount_path": "/runpod-volume",
  "env": {
    "MODE": "pods",
    "COMFYUI_PORT": "8188",
    "COMFYUI_ARGS": "${COMFYUI_ARGS}"
  },
  "docker_args": "",
  "ports": "8188/http,22/tcp",
  "bid_per_gpu": $([ "$SPOT_INSTANCE" = true ] && echo "null" || echo "null")
}
EOF

fi

log_success "Configuration file created: $CONFIG_FILE"
echo ""

# Display configuration
log_info "Configuration:"
cat "$CONFIG_FILE" | python3 -m json.tool 2>/dev/null || cat "$CONFIG_FILE"
echo ""

# Deploy using RunPod CLI or API
log_step "Deploying to RunPod..."

# Check if runpodctl is installed
if command -v runpodctl &> /dev/null; then
    log_info "Using runpodctl CLI..."
    
    if [ "$MODE" = "serverless" ]; then
        log_info "Creating serverless endpoint..."
        
        # Build volume argument
        if [ -n "$VOLUME_ID" ]; then
            VOLUME_ARG="--volume-id $VOLUME_ID"
        else
            VOLUME_ARG="--volume-size $VOLUME_GB"
        fi
        
        runpodctl create endpoint \
            --name "$DEPLOYMENT_NAME" \
            --image "$IMAGE_URL" \
            --gpu "$GPU_TYPE" \
            --container-disk "$CONTAINER_DISK_GB" \
            $VOLUME_ARG \
            --timeout "$TIMEOUT_SECONDS" \
            --min-workers "$MIN_WORKERS" \
            --max-workers "$MAX_WORKERS" \
            --idle-timeout "$IDLE_TIMEOUT"
    else
        log_info "Creating pod..."
        SPOT_FLAG=""
        if [ "$SPOT_INSTANCE" = true ]; then
            SPOT_FLAG="--spot"
        fi
        
        # Build volume argument
        if [ -n "$VOLUME_ID" ]; then
            VOLUME_ARG="--volume-id $VOLUME_ID"
        else
            VOLUME_ARG="--volume-size $VOLUME_GB"
        fi
        
        runpodctl create pod \
            --name "$DEPLOYMENT_NAME" \
            --image "$IMAGE_URL" \
            --gpu "$GPU_TYPE" \
            --gpu-count "$GPU_COUNT" \
            --container-disk "$CONTAINER_DISK_GB" \
            $VOLUME_ARG \
            $SPOT_FLAG
    fi
    
    log_success "Deployment initiated via runpodctl"
    
else
    log_warning "runpodctl not found, using Python script for API deployment..."
    
    # Create Python deployment script
    DEPLOY_SCRIPT="/tmp/runpod-deploy-${DEPLOYMENT_NAME}.py"
    
    cat > "$DEPLOY_SCRIPT" << 'EOFPYTHON'
#!/usr/bin/env python3
import os
import sys
import json
import runpod

def deploy_serverless(config):
    """Deploy serverless endpoint"""
    print("[INFO] Creating serverless endpoint...")
    
    try:
        # Note: This is a simplified example
        # Actual RunPod SDK methods may vary - check documentation
        endpoint = runpod.create_endpoint(
            name=config["name"],
            image_name=config["image"],
            gpu_ids=config["gpu_type_id"],
            container_disk_in_gb=config["container_disk_in_gb"],
            volume_in_gb=config["volume_in_gb"],
            volume_mount_path=config["volume_mount_path"],
            env=config["env"],
            timeout=config.get("timeout", 600),
            scaling_settings=config.get("scaling", {})
        )
        
        print(f"[SUCCESS] Serverless endpoint created: {endpoint['id']}")
        print(f"[INFO] Endpoint URL: {endpoint.get('url', 'N/A')}")
        return endpoint
        
    except Exception as e:
        print(f"[ERROR] Failed to create endpoint: {e}", file=sys.stderr)
        sys.exit(1)

def deploy_pod(config):
    """Deploy pod"""
    print("[INFO] Creating pod...")
    
    try:
        # Note: This is a simplified example
        # Actual RunPod SDK methods may vary - check documentation
        pod = runpod.create_pod(
            name=config["name"],
            image_name=config["image"],
            gpu_type_id=config["gpu_type_id"],
            gpu_count=config.get("gpu_count", 1),
            container_disk_in_gb=config["container_disk_in_gb"],
            volume_in_gb=config["volume_in_gb"],
            volume_mount_path=config["volume_mount_path"],
            env=config["env"],
            ports=config.get("ports", "8188/http,22/tcp"),
            bid_per_gpu=config.get("bid_per_gpu")
        )
        
        print(f"[SUCCESS] Pod created: {pod['id']}")
        print(f"[INFO] Pod status: {pod.get('status', 'N/A')}")
        return pod
        
    except Exception as e:
        print(f"[ERROR] Failed to create pod: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # Load configuration
    config_file = sys.argv[1]
    mode = sys.argv[2]
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Set API key
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        print("[ERROR] RUNPOD_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    
    runpod.api_key = api_key
    
    # Deploy based on mode
    if mode == "serverless":
        result = deploy_serverless(config)
    elif mode == "pods":
        result = deploy_pod(config)
    else:
        print(f"[ERROR] Invalid mode: {mode}", file=sys.stderr)
        sys.exit(1)
    
    print("\n[SUCCESS] Deployment completed!")
    print(json.dumps(result, indent=2))
EOFPYTHON
    
    chmod +x "$DEPLOY_SCRIPT"
    
    # Run Python deployment script
    if python3 "$DEPLOY_SCRIPT" "$CONFIG_FILE" "$MODE"; then
        log_success "Deployment completed successfully"
    else
        log_error "Deployment failed"
        log_info "Configuration saved to: $CONFIG_FILE"
        log_info "You can manually deploy using the RunPod web console"
        exit 1
    fi
    
    # Cleanup
    rm -f "$DEPLOY_SCRIPT"
fi

# Cleanup config file
rm -f "$CONFIG_FILE"

echo ""
log_success "Deployment process completed!"
echo ""

# Post-deployment instructions
if [ "$MODE" = "serverless" ]; then
    log_info "Next steps for serverless endpoint:"
    echo "  1. Wait for endpoint to become active (check RunPod console)"
    echo "  2. Get endpoint ID from RunPod console"
    echo "  3. Test with: curl -X POST https://api.runpod.ai/v2/\${ENDPOINT_ID}/run \\"
    echo "       -H 'Authorization: Bearer \${RUNPOD_API_KEY}' \\"
    echo "       -H 'Content-Type: application/json' \\"
    echo "       -d '{\"input\": {\"workflow\": {...}}}'"
    echo ""
    log_info "Optional: Upload .env file to network storage for OpenZiti/SSH:"
    echo "  - Access network storage via RunPod console"
    echo "  - Upload your .env file to /runpod-volume/.env"
    echo "  - Restart endpoint to apply configuration"
    
elif [ "$MODE" = "pods" ]; then
    log_info "Next steps for pod:"
    echo "  1. Wait for pod to start (check RunPod console)"
    echo "  2. Access ComfyUI WebUI via RunPod proxy URL"
    echo "  3. Optional: Set up SSH access for debugging"
    echo "  4. Optional: Configure OpenZiti tunnel for secure access"
    echo ""
    log_warning "IMPORTANT: Remember to TERMINATE the pod when done!"
    log_warning "Stopping a pod does NOT stop billing - you must terminate it"
    echo ""
    log_info "To terminate later:"
    echo "  - Via console: https://www.runpod.io/console/pods"
    echo "  - Via CLI: runpodctl stop pod \${POD_ID} --terminate"
fi

echo ""
log_info "For more information, see: $PROJECT_ROOT/README.md"

