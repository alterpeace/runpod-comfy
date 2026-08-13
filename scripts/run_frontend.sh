#!/bin/bash
# =============================================================================
# Start the ComfyUI Frontend + Proxy Server for local development.
#
# This script:
#   1. Checks if the official ComfyUI Frontend is cloned (clones if missing)
#   2. Checks if object_info cache exists (offers to fetch if missing)
#   3. Starts the proxy server (translates ComfyUI API → RunPod Serverless)
#   4. Starts the ComfyUI Frontend dev server (Vite, port 5173)
#
# Usage:
#   ./scripts/run_frontend.sh                # auto-detect backend
#   ./scripts/run_frontend.sh --serverless    # force proxy → RunPod serverless
#   ./scripts/run_frontend.sh --local         # frontend → local Docker ComfyUI
#   ./scripts/run_frontend.sh --debug         # verbose proxy logging
#
# Prerequisites:
#   - Node.js 18+ (for frontend dev server)
#   - Python venv with fastapi, uvicorn, httpx (uv sync)
#   - .env with RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY (for --serverless mode)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Defaults
MODE="auto"
DEBUG=false
PROXY_PORT="${PROXY_PORT:-8188}"
MOCK_PORT="${MOCK_PORT:-9090}"
FRONTEND_DIR="$PROJECT_DIR/frontend"
PROXY_PID=""
FRONTEND_PID=""
MOCK_PID=""

# Parse args
for arg in "$@"; do
    case "$arg" in
        --serverless) MODE="serverless" ;;
        --local)      MODE="local" ;;
        --mock)       MODE="mock" ;;
        --debug)      DEBUG=true ;;
        --help|-h)
            echo "Usage: $0 [--serverless|--local|--mock] [--debug]"
            echo ""
            echo "  --serverless  Force proxy mode (frontend → proxy → RunPod API)"
            echo "  --local       Force local mode (frontend → Docker ComfyUI on :8188)"
            echo "  --mock        Mock serverless mode (frontend → proxy → mock → Docker ComfyUI)"
            echo "  --debug       Enable verbose proxy logging"
            exit 0
            ;;
    esac
done

# Load .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# =============================================================================
# Cleanup function
# =============================================================================
cleanup() {
    echo -e "\n${BLUE}[run_frontend] Shutting down...${NC}"
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        echo -e "${GREEN}  Frontend stopped${NC}"
    fi
    if [ -n "$PROXY_PID" ]; then
        kill "$PROXY_PID" 2>/dev/null || true
        echo -e "${GREEN}  Proxy stopped${NC}"
    fi
    if [ -n "$MOCK_PID" ]; then
        kill "$MOCK_PID" 2>/dev/null || true
        echo -e "${GREEN}  Mock server stopped${NC}"
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# =============================================================================
# Step 1: Check/clone ComfyUI Frontend
# =============================================================================
echo -e "${CYAN}=== ComfyUI Frontend Setup ===${NC}"

if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${YELLOW}Frontend not found at $FRONTEND_DIR${NC}"
    echo -e "${BLUE}Cloning official ComfyUI Frontend...${NC}"
    git clone https://github.com/Comfy-Org/ComfyUI_frontend.git "$FRONTEND_DIR"
    echo -e "${GREEN}✓ Frontend cloned${NC}"
else
    echo -e "${GREEN}✓ Frontend found at $FRONTEND_DIR${NC}"
fi

# Check if node_modules exists
# The ComfyUI Frontend uses pnpm (has pnpm-lock.yaml + pnpm-workspace.yaml)
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${BLUE}Installing frontend dependencies...${NC}"

    # Check for pnpm, install if missing
    if ! command -v pnpm &>/dev/null; then
        echo -e "${YELLOW}  pnpm not found, installing...${NC}"
        npm install -g pnpm
    fi

    cd "$FRONTEND_DIR"
    pnpm install
    cd "$PROJECT_DIR"
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
fi

# =============================================================================
# Step 2: Check object_info cache (serverless mode only)
# =============================================================================
CACHE_PATH="${OBJECT_INFO_CACHE:-config/object_info_cache.json}"

if [ "$MODE" = "auto" ]; then
    # Auto-detect: check if local ComfyUI is running on :8188
    if curl -s http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Local ComfyUI detected on :8188${NC}"
        MODE="local"
    else
        if [ -n "${RUNPOD_ENDPOINT_ID:-}" ]; then
            echo -e "${YELLOW}No local ComfyUI, using RunPod serverless proxy${NC}"
            MODE="serverless"
        else
            echo -e "${RED}No local ComfyUI on :8188 and no RUNPOD_ENDPOINT_ID set${NC}"
            echo -e "${YELLOW}Options:${NC}"
            echo -e "  1. Start local ComfyUI: ./scripts/run_local.sh"
            echo -e "  2. Set RUNPOD_ENDPOINT_ID in .env for serverless mode"
            exit 1
        fi
    fi
fi

if [ "$MODE" = "serverless" ] || [ "$MODE" = "mock" ]; then
    if [ ! -f "$CACHE_PATH" ]; then
        echo -e "${YELLOW}object_info cache not found at $CACHE_PATH${NC}"
        echo -e "${BLUE}Fetching from local ComfyUI (if available)...${NC}"
        if curl -s http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
            PYTHON="${PROJECT_DIR}/.venv/bin/python"
            if [ ! -f "$PYTHON" ]; then
                PYTHON="python"
            fi
            "$PYTHON" "$SCRIPT_DIR/fetch_object_info.py" --source local || true
        else
            echo -e "${RED}  No local ComfyUI running to fetch from${NC}"
            echo -e "${YELLOW}  Start local ComfyUI first: ./scripts/run_local.sh${NC}"
            echo -e "${YELLOW}  Then: python scripts/fetch_object_info.py --source local${NC}"
            echo -e "${YELLOW}  The frontend will work but the node palette will be empty${NC}"
        fi
    else
        echo -e "${GREEN}✓ object_info cache found: $CACHE_PATH${NC}"
    fi
fi

# =============================================================================
# Step 3: Create frontend/.env
# =============================================================================
FRONTEND_ENV="$FRONTEND_DIR/.env"

if [ "$MODE" = "local" ]; then
    # In local mode, frontend talks directly to Docker ComfyUI
    echo "DEV_SERVER_COMFYUI_URL=http://127.0.0.1:8188" > "$FRONTEND_ENV"
    echo -e "${GREEN}✓ frontend/.env → http://127.0.0.1:8188 (local ComfyUI)${NC}"
else
    # In serverless/mock mode, frontend talks to our proxy
    echo "DEV_SERVER_COMFYUI_URL=http://127.0.0.1:${PROXY_PORT}" > "$FRONTEND_ENV"
    echo -e "${GREEN}✓ frontend/.env → http://127.0.0.1:${PROXY_PORT} (proxy)${NC}"
fi

# =============================================================================
# Step 4: Start mock server (mock mode only)
# =============================================================================
if [ "$MODE" = "mock" ]; then
    echo -e "\n${CYAN}=== Starting Mock RunPod Server ===${NC}"

    # Check that local ComfyUI is running
    if ! curl -s http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Local ComfyUI not running on :8188${NC}"
        echo -e "${YELLOW}  Start it first: ./scripts/run_local.sh${NC}"
        exit 1
    fi

    PYTHON="${PROJECT_DIR}/.venv/bin/python"
    if [ ! -f "$PYTHON" ]; then
        PYTHON="python"
    fi

    "$PYTHON" "$SCRIPT_DIR/mock_runpod_server.py" --port "$MOCK_PORT" &
    MOCK_PID=$!

    echo -e "${GREEN}✓ Mock server started (PID: $MOCK_PID, port: $MOCK_PORT)${NC}"

    # Wait for mock to be ready
    echo -ne "${BLUE}  Waiting for mock server...${NC}"
    for i in $(seq 1 10); do
        if curl -s "http://127.0.0.1:${MOCK_PORT}/" >/dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
fi

# =============================================================================
# Step 5: Start proxy server (serverless and mock modes)
# =============================================================================
if [ "$MODE" = "serverless" ] || [ "$MODE" = "mock" ]; then
    echo -e "\n${CYAN}=== Starting Proxy Server ===${NC}"

    PYTHON="${PROJECT_DIR}/.venv/bin/python"
    if [ ! -f "$PYTHON" ]; then
        PYTHON="python"
    fi

    DEBUG_FLAG=""
    if [ "$DEBUG" = true ]; then
        DEBUG_FLAG="--debug"
    fi

    if [ "$MODE" = "mock" ]; then
        # Point proxy at mock server instead of real RunPod
        export RUNPOD_API_BASE="http://127.0.0.1:${MOCK_PORT}/v2"
        export RUNPOD_ENDPOINT_ID="local-test"
        export RUNPOD_API_KEY="mock-key"
    fi

    "$PYTHON" "$PROJECT_DIR/src/proxy_server.py" --port "$PROXY_PORT" $DEBUG_FLAG &
    PROXY_PID=$!

    echo -e "${GREEN}✓ Proxy server started (PID: $PROXY_PID, port: $PROXY_PORT)${NC}"

    # Wait for proxy to be ready
    echo -ne "${BLUE}  Waiting for proxy...${NC}"
    for i in $(seq 1 10); do
        if curl -s "http://127.0.0.1:${PROXY_PORT}/health" >/dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
fi

# =============================================================================
# Step 6: Start frontend dev server
# =============================================================================
echo -e "\n${CYAN}=== Starting Frontend Dev Server ===${NC}"

cd "$FRONTEND_DIR"
pnpm dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
cd "$PROJECT_DIR"

echo -e "${GREEN}✓ Frontend dev server started (PID: $FRONTEND_PID)${NC}"

# =============================================================================
# Step 7: Print summary
# =============================================================================
echo -e "\n${CYAN}=== Ready! ===${NC}"
echo -e "${GREEN}  Frontend:  http://localhost:5173${NC}"
if [ "$MODE" = "mock" ]; then
    echo -e "${GREEN}  Proxy:     http://localhost:${PROXY_PORT}${NC}"
    echo -e "${GREEN}  Mock:       http://localhost:${MOCK_PORT}${NC}"
    echo -e "${GREEN}  Backend:    Local Docker ComfyUI (http://localhost:8188)${NC}"
    echo -e "${YELLOW}  Mode:       MOCK (full stack test, 0 cloud cost)${NC}"
elif [ "$MODE" = "serverless" ]; then
    echo -e "${GREEN}  Proxy:     http://localhost:${PROXY_PORT}${NC}"
    echo -e "${GREEN}  Backend:    RunPod Serverless (${RUNPOD_ENDPOINT_ID:-not set})${NC}"
    echo -e "${YELLOW}  Note: First job will cold-start a worker (5-30s delay)${NC}"
else
    echo -e "${GREEN}  Backend:    Local ComfyUI (http://localhost:8188)${NC}"
fi
echo -e "${BLUE}  Press Ctrl+C to stop${NC}"
echo ""

# Wait for either process to exit
wait
