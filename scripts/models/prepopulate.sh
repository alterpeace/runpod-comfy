#!/bin/bash
# =============================================================================
# Prepopulate a RunPod serverless endpoint with all models and dependencies.
#
# Wrapper around scripts/models/prepopulate_serverless.py that loads .env
# and runs the Python script with uv.
#
# Usage:
#   ./scripts/models/prepopulate.sh                              # full prepopulation
#   ./scripts/models/prepopulate.sh --endpoint-id cyas3eys1k3ihe # specify endpoint
#   ./scripts/models/prepopulate.sh --models-only               # LTX-2.5 models only
#   ./scripts/models/prepopulate.sh --seedvr2-only               # SeedVR2 only
#   ./scripts/models/prepopulate.sh --deps-only                 # deps only
#   ./scripts/models/prepopulate.sh --dry-run                    # show what would happen
#   ./scripts/models/prepopulate.sh --verify-only                # check volume state
#   ./scripts/models/prepopulate.sh --seedvr2-7b                 # include 7B SeedVR2
#
# Environment:
#   RUNPOD_API_KEY   RunPod API key (required, from .env)
#   HF_TOKEN         HuggingFace token for gated LTX-2.5 repos (required)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

if [ -z "${RUNPOD_API_KEY:-}" ]; then
    echo -e "\033[0;31m[ERROR]\033[0m RUNPOD_API_KEY not set. Add it to .env or export it."
    exit 1
fi

exec uv run python "$SCRIPT_DIR/prepopulate_serverless.py" "$@"
