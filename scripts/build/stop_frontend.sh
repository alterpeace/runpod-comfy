#!/bin/bash
# =============================================================================
# Stop the ComfyUI Frontend dev server and Proxy server.
#
# Usage:
#   ./scripts/build/stop_frontend.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

stopped_any=false

# Stop proxy server (python src/proxy_server.py)
PROXY_PIDS=$(pgrep -f "proxy_server.py" 2>/dev/null || true)
if [ -n "$PROXY_PIDS" ]; then
    echo -e "${YELLOW}Stopping proxy server (PID: $PROXY_PIDS)...${NC}"
    echo "$PROXY_PIDS" | xargs kill 2>/dev/null || true
    stopped_any=true
    echo -e "${GREEN}✓ Proxy stopped${NC}"
else
    echo -e "${GREEN}Proxy server not running${NC}"
fi

# Stop frontend dev server (npm run dev / vite)
FRONTEND_PIDS=$(pgrep -f "vite.*ComfyUI_frontend\|npm run dev.*frontend" 2>/dev/null || true)
if [ -n "$FRONTEND_PIDS" ]; then
    echo -e "${YELLOW}Stopping frontend dev server (PID: $FRONTEND_PIDS)...${NC}"
    echo "$FRONTEND_PIDS" | xargs kill 2>/dev/null || true
    stopped_any=true
    echo -e "${GREEN}✓ Frontend stopped${NC}"
else
    echo -e "${GREEN}Frontend dev server not running${NC}"
fi

# Also check for any process listening on port 5173 (frontend) or 8188 (proxy)
for port in 5173 8188; do
    PIDS=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "${YELLOW}Killing process on port $port (PID: $PIDS)...${NC}"
        echo "$PIDS" | xargs kill 2>/dev/null || true
        stopped_any=true
    fi
done

if [ "$stopped_any" = true ]; then
    echo -e "\n${GREEN}All frontend processes stopped.${NC}"
else
    echo -e "\n${GREEN}Nothing to stop — no frontend processes running.${NC}"
fi
