#!/bin/bash
# =============================================================================
# Sync models/custom_nodes to RunPod S3-compatible network storage.
#
# RunPod network volumes are exposed via an S3-compatible API. This script
# uploads local models (and optionally custom_nodes) to the bucket so they're
# available when you deploy on RunPod (mounted at /runpod-volume/).
#
# Usage:
#   ./scripts/storage/sync_to_runpod_s3.sh                    # sync models only
#   ./scripts/storage/sync_to_runpod_s3.sh --nodes            # also sync custom_nodes
#   ./scripts/storage/sync_to_runpod_s3.sh --dry-run          # preview only
#   ./scripts/storage/sync_to_runpod_s3.sh --ltx23            # sync only LTX 2.3 models
#
# Environment (set in .env or export):
#   RUNPOD_S3_ENDPOINT   e.g. https://s3api-us-ca-2.runpod.io
#   RUNPOD_S3_REGION     e.g. us-ca-2
#   RUNPOD_S3_BUCKET     e.g. your-volume-id
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# Load .env
if [ -f .env ]; then
    set -a; source .env; set +a
fi

ENDPOINT="${RUNPOD_S3_ENDPOINT:-https://s3api-us-ca-2.runpod.io}"
REGION="${RUNPOD_S3_REGION:-us-ca-2}"
BUCKET="${RUNPOD_S3_BUCKET:-your-volume-id}"
MODELS_DIR="${COMFY_DATA_DIR:-./.local}/models"
NODES_DIR="${COMFY_DATA_DIR:-./.local}/custom_nodes"

DRY_RUN=false
SYNC_NODES=false
LTX23_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true ;;
        --nodes)    SYNC_NODES=true ;;
        --ltx23)    LTX23_ONLY=true ;;
    esac
done

AWS_CMD="aws s3 sync"
if [ "$DRY_RUN" = true ]; then
    AWS_CMD="$AWS_CMD --dryrun"
fi
AWS_CMD="$AWS_CMD --endpoint-url $ENDPOINT --region $REGION"

echo "=========================================="
echo "  Sync to RunPod S3 Storage"
echo "=========================================="
echo "  Endpoint: $ENDPOINT"
echo "  Region:   $REGION"
echo "  Bucket:   $BUCKET"
echo "  Source:   $MODELS_DIR"
echo "=========================================="
echo ""

if [ "$LTX23_ONLY" = true ]; then
    echo "--- Syncing LTX 2.3 models only ---"
    # Upload specific LTX 2.3 files (resolve symlinks with --follow-symlinks)
    for subdir in unet text_encoders loras vae; do
        if [ -d "$MODELS_DIR/$subdir" ]; then
            for f in "$MODELS_DIR/$subdir"/ltx-2.3* "$MODELS_DIR/$subdir"/LTX-2.3* "$MODELS_DIR/$subdir"/gemma_3_12B_it_fp4*; do
                [ -e "$f" ] || continue
                echo "  Uploading: $(basename "$f")"
                $AWS_CMD "$f" "s3://$BUCKET/models/$subdir/$(basename "$f")" --follow-symlinks
            done
        fi
    done
else
    echo "--- Syncing all models ---"
    $AWS_CMD "$MODELS_DIR" "s3://$BUCKET/models" --follow-symlinks
fi

if [ "$SYNC_NODES" = true ]; then
    echo ""
    echo "--- Syncing custom_nodes ---"
    $AWS_CMD "$NODES_DIR" "s3://$BUCKET/custom_nodes" --follow-symlinks --exclude ".git/*"
fi

echo ""
echo "=========================================="
echo "  ✅ Sync complete!"
echo "=========================================="
echo ""
echo "  Verify: aws s3 ls --region $REGION --endpoint-url $ENDPOINT s3://$BUCKET/models/"
