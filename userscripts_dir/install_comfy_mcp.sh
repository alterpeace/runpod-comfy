#!/bin/bash
# =============================================================================
# install_comfy_mcp.sh — Install comfyui-mcp + ComfyUI Agent Panel
# =============================================================================
# This userscript runs at container startup (via run_userscripts in entrypoint.sh)
# when ENABLE_MCP=true. It installs TWO components:
#
# 1. comfyui-mcp (npm package) — the MCP server + orchestrator that AI agents
#    (Claude Code, Cursor, ChatGPT) connect to. Drives ComfyUI's HTTP API.
#    https://github.com/artokun/comfyui-mcp
#
# 2. comfyui-mcp-panel (ComfyUI custom node) — the sidebar UI panel that embeds
#    an autonomous AI agent in ComfyUI's sidebar. Pure frontend extension (no
#    Python deps), serves JS via WEB_DIRECTORY.
#    https://github.com/artokun/comfyui-mcp-panel
#
# The panel connects to the MCP server's loopback bridge to drive the live graph.
# Both require Node.js >= 22 (baked into the Docker image runtime-base stage).
# =============================================================================
set -e

# Colors (match entrypoint.sh style)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# Only run if MCP is explicitly enabled
if [ "${ENABLE_MCP}" != "true" ]; then
    log_info "ENABLE_MCP is not 'true' — skipping comfyui-mcp install"
    exit 0
fi

log_info "=== Installing comfyui-mcp + Agent Panel ==="

# Verify Node.js is available (baked into image via Dockerfile)
if ! command -v node &>/dev/null; then
    log_error "Node.js not found — comfyui-mcp requires Node.js >= 22"
    log_error "This should have been installed in the Docker image runtime-base stage."
    exit 1
fi

NODE_VERSION=$(node --version)
log_info "Node.js version: ${NODE_VERSION}"

# Parse major version and verify >= 22
NODE_MAJOR=$(echo "$NODE_VERSION" | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 22 ]; then
    log_error "Node.js >= 22 required, found ${NODE_VERSION}"
    exit 1
fi

# =============================================================================
# Component 1: comfyui-mcp npm package (MCP server + orchestrator)
# =============================================================================
log_info "--- Installing comfyui-mcp (MCP server) via npm ---"

# Install comfyui-mcp globally (idempotent — npm install -g skips if already present)
if npm install -g comfyui-mcp@latest 2>&1; then
    log_success "comfyui-mcp npm package installed"
else
    log_error "Failed to install comfyui-mcp npm package"
    exit 1
fi

# Verify the binary is on PATH
if command -v comfyui-mcp &>/dev/null; then
    MCP_VERSION=$(comfyui-mcp --version 2>/dev/null || echo "unknown")
    log_success "comfyui-mcp ready (version: ${MCP_VERSION})"
else
    log_error "comfyui-mcp command not found after install"
    log_error "Check npm global bin path is on PATH: $(npm config get prefix)/bin"
    exit 1
fi

# =============================================================================
# Component 2: comfyui-mcp-panel (ComfyUI custom node — sidebar panel)
# =============================================================================
log_info "--- Installing ComfyUI Agent Panel (custom node) ---"

CUSTOM_NODES_DIR="${COMFYUI_PATH:-/comfyui}/custom_nodes"
PANEL_REPO="https://github.com/artokun/comfyui-mcp-panel.git"
PANEL_NAME="comfyui-mcp-panel"
PANEL_TARGET="${CUSTOM_NODES_DIR}/${PANEL_NAME}"

mkdir -p "$CUSTOM_NODES_DIR"

if [ -d "$PANEL_TARGET/.git" ]; then
    log_info "Panel already present, pulling latest..."
    git -C "$PANEL_TARGET" pull --ff-only || log_warning "Failed to update panel (continuing with existing)"
else
    log_info "Cloning ${PANEL_NAME}..."
    if git clone --depth 1 "$PANEL_REPO" "$PANEL_TARGET"; then
        log_success "ComfyUI Agent Panel cloned to ${PANEL_TARGET}"
    else
        log_error "Failed to clone ComfyUI Agent Panel"
        exit 1
    fi
fi

# The panel is a pure frontend extension (no Python deps, no requirements.txt)
# — it only serves JS via WEB_DIRECTORY. No pip install needed.
log_info "Panel has no Python dependencies (pure frontend extension)"

log_success "=== comfyui-mcp + Agent Panel install complete ==="
log_info "MCP server will be started by entrypoint.sh after ComfyUI is ready"
log_info "Agent Panel tab (💬) will appear in ComfyUI sidebar after restart"
