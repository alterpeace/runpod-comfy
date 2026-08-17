#!/bin/bash
# =============================================================================
# Trigger LTX-2.5 model downloads on a RunPod serverless endpoint.
#
# This script sends a "download_models" job to a RunPod serverless endpoint
# via the RunPod API. The worker runs scripts/models/download_ltx25_models.py
# inside the container, downloading models to /runpod-volume/models/ on the
# network volume — no SSH access required.
#
# Usage:
#   ./scripts/models/download_ltx25_runpod.sh --endpoint-id <id> --profile mid_vram_24gb
#   ./scripts/models/download_ltx25_runpod.sh --endpoint-id <id> --ids checkpoint_dev_int8 distilled_lora
#   ./scripts/models/download_ltx25_runpod.sh --endpoint-id <id> --profile low_vram_8gb --dry-run
#   ./scripts/models/download_ltx25_runpod.sh --endpoint-id <id> --profile full --force
#   ./scripts/models/download_ltx25_runpod.sh --endpoint-id <id> --list
#
# Prerequisites:
#   - RUNPOD_API_KEY set in .env or environment
#   - HF_TOKEN set (LTX-2.5 is auto-gated on HuggingFace)
#   - The serverless endpoint must be running the updated handler with
#     action="download_models" support
#
# Environment:
#   RUNPOD_API_KEY   RunPod API key (required)
#   HF_TOKEN         HuggingFace token for gated repos (passed to the worker)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Defaults
ENDPOINT_ID=""
PROFILE=""
IDS=()
DRY_RUN=false
FORCE=false
MANIFEST="ltx-2.5"
LIST_ONLY=false
WAIT=true
TIMEOUT=3300

usage() {
    sed -n '2,30p' "$0" | sed 's/^# //; s/^#//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --endpoint-id)
            ENDPOINT_ID="$2"; shift 2 ;;
        --profile)
            PROFILE="$2"; shift 2 ;;
        --ids)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do IDS+=("$1"); shift; done ;;
        --manifest)
            MANIFEST="$2"; shift 2 ;;
        --dry-run)
            DRY_RUN=true; shift ;;
        --force)
            FORCE=true; shift ;;
        --list)
            LIST_ONLY=true; shift ;;
        --no-wait)
            WAIT=false; shift ;;
        --timeout)
            TIMEOUT="$2"; shift 2 ;;
        -h|--help)
            usage ;;
        *)
            log_error "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$ENDPOINT_ID" ]; then
    log_error "--endpoint-id is required"
    echo "  Find your endpoint ID at: https://www.runpod.io/console/serverless"
    exit 1
fi

if [ -z "$RUNPOD_API_KEY" ]; then
    log_error "RUNPOD_API_KEY not set. Add it to .env or export it."
    exit 1
fi

# If --list, just run the local download script in list mode (no API call needed)
if [ "$LIST_ONLY" = true ]; then
    log_info "Listing available LTX-2.5 models (local manifest):"
    python3 "$SCRIPT_DIR/download_ltx25_models.py" \
        --manifest "$PROJECT_ROOT/config/ltx-2.5-models.json" --list
    exit 0
fi

# Validate that either profile or ids is specified
if [ -z "$PROFILE" ] && [ ${#IDS[@]} -eq 0 ]; then
    log_error "Either --profile or --ids must be specified"
    exit 1
fi

if [ -n "$PROFILE" ] && [ ${#IDS[@]} -gt 0 ]; then
    log_error "--profile and --ids are mutually exclusive"
    exit 1
fi

# Warn about HF_TOKEN
if [ -z "$HF_TOKEN" ] && [ -z "$HUGGING_FACE_HUB_TOKEN" ]; then
    log_warning "HF_TOKEN not set — gated LTX-2.5 repos will fail on the worker."
    log_warning "Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access'."
    log_warning "Get a token at https://huggingface.co/settings/tokens"
    echo ""
    read -p "$(echo -e ${YELLOW}Continue anyway? [y/N]:${NC} )" -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 0
fi

# Build the job payload
JOB_INPUT=$(cat <<EOF
{
  "action": "download_models",
  "manifest": "${MANIFEST}",
EOF
)

if [ -n "$PROFILE" ]; then
    JOB_INPUT+=$(printf '\n  "profile": "%s",' "$PROFILE")
fi

if [ ${#IDS[@]} -gt 0 ]; then
    IDS_JSON=$(printf '%s\n' "${IDS[@]}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().split()))')
    JOB_INPUT+=$(printf '\n  "ids": %s,' "$IDS_JSON")
fi

JOB_INPUT+=$(printf '\n  "dry_run": %s,' "$DRY_RUN")
JOB_INPUT+=$(printf '\n  "force": %s' "$FORCE")

# Pass HF token if set (so the worker doesn't need it in env)
if [ -n "$HF_TOKEN" ]; then
    JOB_INPUT+=$(printf ',\n  "hf_token": "%s"' "$HF_TOKEN")
fi

JOB_INPUT+=$(echo -e '\n}')

PAYLOAD=$(cat <<EOF
{
  "input": ${JOB_INPUT}
}
EOF
)

log_info "=== LTX-2.5 Model Download via RunPod Serverless ==="
log_info "Endpoint ID:  $ENDPOINT_ID"
if [ -n "$PROFILE" ]; then
    log_info "Profile:      $PROFILE"
fi
if [ ${#IDS[@]} -gt 0 ]; then
    log_info "Model IDs:     ${IDS[*]}"
fi
log_info "Manifest:     $MANIFEST"
log_info "Dry run:      $DRY_RUN"
log_info "Force:        $FORCE"
log_info "Wait:         $WAIT"
echo ""

# Submit the job
log_info "Submitting download job to RunPod endpoint..."

API_URL="https://api.runpod.ai/v2/${ENDPOINT_ID}/run"

RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

# Extract job ID
JOB_ID=$(echo "$RESPONSE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))' 2>/dev/null || echo "")

if [ -z "$JOB_ID" ]; then
    log_error "Failed to submit job. API response:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

log_success "Job submitted: $JOB_ID"

if [ "$WAIT" = false ]; then
    log_info "Check status with:"
    echo "  curl -s -H 'Authorization: Bearer ${RUNPOD_API_KEY}' \\"
    echo "    https://api.runpod.ai/v2/${ENDPOINT_ID}/status/${JOB_ID} | python3 -m json.tool"
    exit 0
fi

# Poll for completion
log_info "Waiting for download to complete (timeout: ${TIMEOUT}s)..."

STATUS_URL="https://api.runpod.ai/v2/${ENDPOINT_ID}/status/${JOB_ID}"
START_TIME=$(date +%s)

while true; do
    ELAPSED=$(( $(date +%s) - START_TIME ))
    if [ $ELAPSED -gt $TIMEOUT ]; then
        log_error "Timeout waiting for job $JOB_ID after ${TIMEOUT}s"
        log_info "Check status manually:"
        echo "  curl -s -H 'Authorization: Bearer ${RUNPOD_API_KEY}' \\"
        echo "    ${STATUS_URL} | python3 -m json.tool"
        exit 1
    fi

    STATUS_RESPONSE=$(curl -s -H "Authorization: Bearer ${RUNPOD_API_KEY}" "$STATUS_URL")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' 2>/dev/null || echo "")

    case "$STATUS" in
        COMPLETED)
            log_success "Job completed!"
            echo ""
            echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"

            # Extract and display download summary
            echo ""
            echo "$STATUS_RESPONSE" | python3 -c '
import json, sys
d = json.load(sys.stdin)
out = d.get("output", {})
if isinstance(out, dict):
    meta = d.get("metadata", {})
    print(f"  Downloaded: {out.get(\"downloaded\", \"?\")}")
    print(f"  Skipped:    {out.get(\"skipped\", \"?\")}")
    print(f"  Failed:     {out.get(\"failed\", \"?\")}")
    print(f"  Dry run:    {out.get(\"dry_run\", \"?\")}")
    print(f"  Output dir: {out.get(\"output_dir\", \"?\")}")
    print(f"  Time:       {meta.get(\"execution_time\", \"?\")}s")
    stdout = out.get("stdout", "")
    if stdout:
        print(f"\n  --- Download log ---")
        for line in stdout.strip().splitlines():
            print(f"  {line}")
' 2>/dev/null
            exit 0
            ;;
        FAILED)
            log_error "Job failed!"
            echo ""
            echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
            exit 1
            ;;
        CANCELLED)
            log_error "Job cancelled."
            exit 1
            ;;
        IN_QUEUE|IN_PROGRESS)
            echo -ne "\r  Status: $STATUS (${ELAPSED}s elapsed)...  "
            sleep 5
            ;;
        "")
            echo -ne "\r  Waiting for status... (${ELAPSED}s)  "
            sleep 5
            ;;
        *)
            log_warning "Unknown status: $STATUS"
            sleep 5
            ;;
    esac
done
