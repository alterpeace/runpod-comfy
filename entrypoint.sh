#!/bin/bash
set -e

# Colors for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

log_info "=== ComfyUI Entrypoint Script ==="

# Set permissive umask so all created files have 777 permissions
umask 000

# ============================================================================
# UID/GID MAPPING (inspired by mmartial/ComfyUI-Nvidia-Docker)
# ============================================================================
setup_user() {
    local wanted_uid=${WANTED_UID:-1000}
    local wanted_gid=${WANTED_GID:-1000}
    
    # Skip if running as root and no mapping requested
    if [ "$(id -u)" = "0" ] && [ "$wanted_uid" = "0" ]; then
        log_info "Running as root (no UID/GID mapping)"
        return 0
    fi
    
    # Skip if already running as the correct user
    if [ "$(id -u)" = "$wanted_uid" ]; then
        log_info "Already running as UID $wanted_uid"
        return 0
    fi
    
    # Only remap if running as root
    if [ "$(id -u)" = "0" ]; then
        log_info "Setting up user mapping: UID=$wanted_uid GID=$wanted_gid"
        
        # Modify comfy user if it exists, otherwise create it
        if id comfy &>/dev/null; then
            usermod -u "$wanted_uid" comfy 2>/dev/null || true
            groupmod -g "$wanted_gid" comfy 2>/dev/null || true
        else
            groupadd -g "$wanted_gid" comfy 2>/dev/null || true
            useradd -m -u "$wanted_uid" -g "$wanted_gid" -s /bin/bash comfy 2>/dev/null || true
        fi
        
        # Fix ownership of key directories
        if [ "$FORCE_CHOWN" = "true" ] || [ -n "$FORCE_CHOWN" ] && [ "$FORCE_CHOWN" != "false" ]; then
            log_info "FORCE_CHOWN enabled - fixing ownership (this may take a while)..."
            chown -R "$wanted_uid:$wanted_gid" /comfyui 2>/dev/null || true
            chown -R "$wanted_uid:$wanted_gid" /workspace 2>/dev/null || true
        fi
        
        log_success "User mapping complete"
    fi
}

# ============================================================================
# TORCH_LOCK VERIFICATION
# ============================================================================
verify_torch_lock() {
    log_info "Verifying TORCH_LOCK constraints..."
    
    local constraint_file="/comfyui/venv/constraints/torch_lock.txt"
    
    if [ -f "$constraint_file" ]; then
        log_success "TORCH_LOCK constraint file found"
        log_info "Locked versions:"
        grep -E "^torch|^torchvision|^torchaudio|^xformers" "$constraint_file" | while read line; do
            log_info "  - $line"
        done
        
        # Verify PIP_CONSTRAINT is set
        if [ -n "$PIP_CONSTRAINT" ]; then
            log_success "PIP_CONSTRAINT is set: $PIP_CONSTRAINT"
        else
            log_warning "PIP_CONSTRAINT not set - runtime installs may upgrade torch!"
            export PIP_CONSTRAINT="$constraint_file"
        fi
        
        # Verify UV_CONSTRAINT is set
        if [ -n "$UV_CONSTRAINT" ]; then
            log_success "UV_CONSTRAINT is set: $UV_CONSTRAINT"
        else
            export UV_CONSTRAINT="$constraint_file"
        fi
    else
        log_warning "TORCH_LOCK constraint file not found at $constraint_file"
    fi
}

# ============================================================================
# USERSCRIPTS EXECUTION (inspired by mmartial/ComfyUI-Nvidia-Docker)
# ============================================================================
run_userscripts() {
    local scripts_dir="/userscripts_dir"
    
    if [ -d "$scripts_dir" ] && [ "$(ls -A $scripts_dir/*.sh 2>/dev/null)" ]; then
        log_info "Found userscripts in $scripts_dir"
        
        # Run executable .sh scripts in alphanumeric order
        for script in $(ls -1 "$scripts_dir"/*.sh 2>/dev/null | sort); do
            if [ -x "$script" ]; then
                log_info "Running userscript: $(basename $script)"
                
                # Source the script so it can access our environment
                if bash "$script"; then
                    log_success "Userscript completed: $(basename $script)"
                else
                    log_warning "Userscript failed: $(basename $script) (continuing...)"
                fi
            else
                log_info "Skipping non-executable: $(basename $script)"
            fi
        done
        
        log_success "Userscripts execution complete"
    else
        log_info "No userscripts found in $scripts_dir (this is normal)"
    fi
}

# ============================================================================
# RUN USER SETUP
# ============================================================================
setup_user

# ============================================================================
# MODE DETECTION
# ============================================================================
log_info "Detecting operating mode..."

# Determine mode based on environment
if [ -n "$RUNPOD_POD_ID" ]; then
    # Running in RunPod environment
    if [ -z "$MODE" ]; then
        # Default to serverless if MODE not explicitly set
        MODE="serverless"
        log_success "Mode: SERVERLESS (RunPod environment detected, MODE not set)"
    else
        log_success "Mode: $MODE (explicitly set via MODE env var)"
    fi
else
    # Running locally
    if [ -z "$MODE" ]; then
        MODE="local"
        log_success "Mode: LOCAL (default)"
    else
        log_success "Mode: $MODE (explicitly set via MODE env var)"
    fi
fi

# Validate MODE value
VALID_MODES=("local" "serverless" "pods")
MODE_VALID=false

for valid_mode in "${VALID_MODES[@]}"; do
    if [ "$MODE" = "$valid_mode" ]; then
        MODE_VALID=true
        break
    fi
done

if [ "$MODE_VALID" = false ]; then
    log_error "Invalid MODE value: '$MODE'"
    log_error "Valid modes are: local, serverless, pods"
    exit 1
fi

log_success "Mode validation: OK"

# ============================================================================
# CONFIGURATION LOADING
# ============================================================================
log_info "Loading configuration..."

ENV_LOADED=false

# Check RunPod network volume first (production)
if [ -f "/runpod-volume/.env" ]; then
    log_info "Found .env in /runpod-volume/ (network storage)"
    set -a
    source /runpod-volume/.env
    set +a
    ENV_LOADED=true
    log_success "Configuration loaded from /runpod-volume/.env"
# Check local workspace (development)
elif [ -f "/workspace/.env" ]; then
    log_info "Found .env in /workspace/ (local mount)"
    set -a
    source /workspace/.env
    set +a
    ENV_LOADED=true
    log_success "Configuration loaded from /workspace/.env"
else
    log_warning "No .env file found - using defaults"
    log_info "Checked: /runpod-volume/.env and /workspace/.env"
fi

# ============================================================================
# FEATURE DETECTION
# ============================================================================
log_info "Detecting enabled features..."

OPENZITI_ENABLED=false
SSH_ENABLED=false
MCP_ENABLED=false

# Check OpenZiti configuration
if [ -n "$OPENZITI_IDENTITY" ] || [ -n "$OPENZITI_IDENTITY_JSON" ]; then
    OPENZITI_ENABLED=true
    log_success "✓ OpenZiti tunnel: ENABLED"
else
    log_info "✗ OpenZiti tunnel: DISABLED (no OPENZITI_IDENTITY* vars)"
fi

# Check SSH configuration
if [ "$ENABLE_SSH" = "true" ] && [ -n "$SSH_PUBLIC_KEY" ]; then
    SSH_ENABLED=true
    log_success "✓ SSH server: ENABLED"
elif [ "$ENABLE_SSH" = "true" ] && [ -z "$SSH_PUBLIC_KEY" ]; then
    log_warning "✗ SSH server: DISABLED (ENABLE_SSH=true but SSH_PUBLIC_KEY not set)"
else
    log_info "✗ SSH server: DISABLED"
fi

# Check MCP (Comfy MCP server) configuration
# ENABLE_MCP=true installs comfyui-mcp (npm) + comfyui-mcp-panel (custom node)
# via userscripts_dir/install_comfy_mcp.sh, then starts the MCP server after
# ComfyUI is ready. Agents (Claude Code, Cursor, ChatGPT) connect to drive ComfyUI.
if [ "$ENABLE_MCP" = "true" ]; then
    MCP_ENABLED=true
    log_success "✓ Comfy MCP server: ENABLED"
    log_info "  MCP_PORT: ${MCP_PORT:-8765}"
    log_info "  MCP_TRANSPORT: ${MCP_TRANSPORT:-http}"
    log_info "  MCP_COMFYUI_URL: ${MCP_COMFYUI_URL:-http://127.0.0.1:8188}"
else
    log_info "✗ Comfy MCP server: DISABLED (set ENABLE_MCP=true to enable)"
fi

# ============================================================================
# OPENZITI TUNNEL INITIALIZATION
# ============================================================================
if [ "$OPENZITI_ENABLED" = true ]; then
    log_info "Initializing OpenZiti tunnel..."
    
    if [ -f "/workspace/openziti/tunnel_setup.sh" ]; then
        bash /workspace/openziti/tunnel_setup.sh &
        ZITI_PID=$!
        log_success "OpenZiti tunnel started (PID: $ZITI_PID)"
    else
        log_error "OpenZiti tunnel script not found at /workspace/openziti/tunnel_setup.sh"
        log_warning "Continuing without OpenZiti tunnel..."
    fi
fi

# ============================================================================
# SSH SERVER INITIALIZATION
# ============================================================================
if [ "$SSH_ENABLED" = true ]; then
    log_info "Starting SSH server..."
    
    if [ -f "/workspace/ssh/setup_ssh.sh" ]; then
        bash /workspace/ssh/setup_ssh.sh
        log_success "SSH server started"
    else
        log_error "SSH setup script not found at /workspace/ssh/setup_ssh.sh"
        log_warning "Continuing without SSH server..."
    fi
fi

# ============================================================================
# STORAGE BACKEND SETUP
# ============================================================================
log_info "Setting up storage backend..."

# Default to network-volume if not specified
STORAGE_BACKEND=${STORAGE_BACKEND:-network-volume}
log_info "Storage backend: $STORAGE_BACKEND"

case "$STORAGE_BACKEND" in
    "network-volume")
        log_success "Using network volume storage (default)"
        log_info "Models will be loaded from /runpod-volume/models"
        # Symlink network volume model dirs into /comfyui/models so ComfyUI
        # can discover them. Without this, CheckpointLoaderSimple and other
        # model loaders see empty directories and reject workflows with
        # "Value not in list" validation errors.
        if [ -d "/runpod-volume/models" ]; then
            for subdir in /runpod-volume/models/*/; do
                [ -d "$subdir" ] || continue
                name="$(basename "$subdir")"
                target="/comfyui/models/$name"
                if [ ! -e "$target" ]; then
                    ln -sf "$subdir" "$target" 2>/dev/null && \
                        log_info "  Linked: /comfyui/models/$name -> /runpod-volume/models/$name"
                fi
            done
            log_success "Network volume models linked to /comfyui/models/"
        else
            log_warning "No /runpod-volume/models directory found — models will be empty"
        fi
        # Also link custom_nodes, input, output, user if they exist on the volume
        for dirpair in "custom_nodes:/comfyui/custom_nodes" "input:/comfyui/input" "output:/comfyui/output" "user:/comfyui/user"; do
            volname="${dirpair%%:*}"
            target="${dirpair##*:}"
            if [ -d "/runpod-volume/$volname" ] && [ ! -e "$target" ]; then
                ln -sf "/runpod-volume/$volname" "$target" 2>/dev/null && \
                    log_info "  Linked: $target -> /runpod-volume/$volname"
            fi
        done
        ;;
    "b2-mount")
        log_info "Setting up B2 mount with rclone..."
        if [ -f "/workspace/storage/setup_b2_mount.sh" ]; then
            bash /workspace/storage/setup_b2_mount.sh
            if [ $? -ne 0 ]; then
                log_error "B2 mount setup failed"
                log_error "Check B2 credentials and configuration"
                exit 1
            fi
            log_success "B2 storage mounted successfully"
        else
            log_error "B2 mount script not found at /workspace/storage/setup_b2_mount.sh"
            exit 1
        fi
        ;;
    "b2-sync")
        log_info "Syncing models from B2 to local storage..."
        if [ -f "/workspace/storage/setup_b2_sync.sh" ]; then
            bash /workspace/storage/setup_b2_sync.sh
            if [ $? -ne 0 ]; then
                log_error "B2 sync failed"
                log_error "Check B2 credentials, configuration, and available disk space"
                exit 1
            fi
            log_success "B2 storage synced successfully"
        else
            log_error "B2 sync script not found at /workspace/storage/setup_b2_sync.sh"
            exit 1
        fi
        ;;
    *)
        log_warning "Unknown STORAGE_BACKEND value: '$STORAGE_BACKEND'"
        log_warning "Valid options are: network-volume, b2-mount, b2-sync"
        log_warning "Falling back to network-volume (default)"
        STORAGE_BACKEND="network-volume"
        ;;
esac

log_success "Storage backend setup complete: $STORAGE_BACKEND"

# ============================================================================
# NVIDIA LIBRARY SYMLINKS (local dev with explicit GPU passthrough)
# ============================================================================
# When GPU passthrough is done via explicit volume mounts (instead of CDI or
# the NVIDIA Container Toolkit runtime), only the versioned .so files are
# mounted (e.g. libcuda.so.580.173.02). The unversioned symlinks that the
# dynamic linker resolves (libcuda.so.1, libcuda.so) are missing, causing
# torch.cuda to fail with "Found no NVIDIA driver". This function creates
# those symlinks and refreshes ldconfig so the libraries are discoverable.
setup_nvidia_symlinks() {
    local lib_dir="/usr/lib/x86_64-linux-gnu"
    local found=0

    if [ ! -d "$lib_dir" ]; then
        return 0
    fi

    # For each versioned NVIDIA .so file, create the .so.1 and .so symlinks
    for so_file in "$lib_dir"/libcuda.so.* "$lib_dir"/libnvidia-ml.so.* \
                   "$lib_dir"/libnvidia-cfg.so.* "$lib_dir"/libnvcuvid.so.* \
                   "$lib_dir"/libnvidia-encode.so.* "$lib_dir"/libnvidia-fbc.so.* \
                   "$lib_dir"/libnvidia-opticalflow.so.* "$lib_dir"/libnvidia-opencl.so.* \
                   "$lib_dir"/libnvidia-gpucomp.so.* "$lib_dir"/libnvidia-allocator.so.* \
                   "$lib_dir"/libnvidia-tls.so.* "$lib_dir"/libnvidia-ptxjitcompiler.so.* \
                   "$lib_dir"/libnvidia-nvvm.so.* "$lib_dir"/libnvidia-ngx.so.* \
                   "$lib_dir"/libnvidia-glcore.so.* "$lib_dir"/libnvidia-glsi.so.* \
                   "$lib_dir"/libnvidia-glvkspirv.so.* "$lib_dir"/libnvidia-eglcore.so.* \
                   "$lib_dir"/libnvidia-rtcore.so.* "$lib_dir"/libnvoptix.so.* \
                   "$lib_dir"/libEGL_nvidia.so.* "$lib_dir"/libGLESv1_CM_nvidia.so.* \
                   "$lib_dir"/libGLESv2_nvidia.so.* "$lib_dir"/libGLX_nvidia.so.* \
                   "$lib_dir"/libvdpau_nvidia.so.*; do

        [ -e "$so_file" ] || continue
        [ -L "$so_file" ] && continue  # Skip if already a symlink

        local base="${so_file%.so.*}"   # e.g. /usr/lib/.../libcuda
        local major="${so_file#*.so.}"  # e.g. 580.173.02
        local major_ver="${major%%.*}"  # e.g. 580

        # Create libfoo.so.<major> -> libfoo.so.<full>
        local link_major="${base}.so.${major_ver}"
        if [ ! -e "$link_major" ]; then
            ln -sf "$(basename "$so_file")" "$link_major" 2>/dev/null && found=$((found + 1))
        fi

        # Create libfoo.so -> libfoo.so.<major>
        local link_base="${base}.so"
        if [ ! -e "$link_base" ]; then
            ln -sf "$(basename "$link_major")" "$link_base" 2>/dev/null && found=$((found + 1))
        fi
    done

    if [ "$found" -gt 0 ]; then
        log_info "Created $found NVIDIA library symlinks"
        # Refresh the dynamic linker cache
        if command -v ldconfig &>/dev/null; then
            ldconfig "$lib_dir" 2>/dev/null || true
            log_info "Refreshed ldconfig cache for NVIDIA libraries"
        fi
    fi
}
setup_nvidia_symlinks

# ============================================================================
# CUSTOM NODE DEPENDENCY AUTO-INSTALL
# ============================================================================
# Scans all custom_nodes/*/requirements.txt files and installs missing
# dependencies using uv pip install with torch lock constraints to prevent
# torch/torchvision/xformers from being upgraded.
#
# Controlled by env var: AUTO_INSTALL_CUSTOM_NODE_DEPS (default: true)
# Set to "false" to skip (useful for faster restarts when deps are stable).
install_custom_node_deps() {
    if [ "${AUTO_INSTALL_CUSTOM_NODE_DEPS:-true}" = "false" ]; then
        log_info "Custom node dependency auto-install skipped (AUTO_INSTALL_CUSTOM_NODE_DEPS=false)"
        return 0
    fi

    local custom_nodes_dir="/comfyui/custom_nodes"
    local constraint_file="/comfyui/venv/constraints/torch_lock.txt"
    local marker_file="/comfyui/venv/.custom_node_deps_installed"
    local count=0
    local installed=0

    if [ ! -d "$custom_nodes_dir" ]; then
        log_info "No custom_nodes directory found — skipping dependency install"
        return 0
    fi

    # Count requirements.txt files
    for req in "$custom_nodes_dir"/*/requirements.txt; do
        [ -f "$req" ] && count=$((count + 1))
    done

    if [ "$count" -eq 0 ]; then
        log_info "No custom node requirements.txt files found"
        return 0
    fi

    log_info "Scanning $count custom node(s) for missing dependencies..."

    # Build uv pip install command with constraints.
    # --no-deps: Only install exact packages from requirements.txt, NOT their
    # transitive dependencies. This prevents pulling in incompatible packages
    # (e.g. wheels compiled against NumPy 1.x) that break already-working nodes.
    # Transitive deps should already be in the image via extra-requirements.txt.
    local uv_cmd="uv pip install --no-deps"
    if [ -f "$constraint_file" ]; then
        uv_cmd="$uv_cmd --constraint $constraint_file"
    fi
    uv_cmd="$uv_cmd --python /comfyui/venv/bin/python"

    # Some custom nodes have complex dependency trees that need transitive deps
    # installed (not just the top-level packages). These are installed WITH deps
    # (using constraints to protect torch). Add node directory names here.
    local full_deps_nodes="ComfyUI_FL-MCP"

    # Install each requirements.txt
    for req in "$custom_nodes_dir"/*/requirements.txt; do
        [ -f "$req" ] || continue
        local node_name
        node_name=$(basename "$(dirname "$req")")

        # Determine whether to use --no-deps or full deps install
        local use_full_deps=false
        for fdn in $full_deps_nodes; do
            if [ "$node_name" = "$fdn" ]; then
                use_full_deps=true
                break
            fi
        done

        local install_cmd
        if [ "$use_full_deps" = true ]; then
            # Full deps install (with torch lock constraints to prevent torch upgrades)
            install_cmd="uv pip install"
            if [ -f "$constraint_file" ]; then
                install_cmd="$install_cmd --constraint $constraint_file"
            fi
            install_cmd="$install_cmd --python /comfyui/venv/bin/python"
        else
            install_cmd="$uv_cmd"
        fi

        if eval "$install_cmd -r \"$req\"" 2>&1 | grep -q "Installed\|Downloaded"; then
            installed=$((installed + 1))
            log_info "  Installed deps for: $node_name$( [ "$use_full_deps" = true ] && echo " (full deps)" )"
        fi
    done

    if [ "$installed" -gt 0 ]; then
        log_success "Installed dependencies for $installed custom node(s)"
        # Write marker so we know deps were installed this session
        date -u +"%Y-%m-%dT%H:%M:%SZ" > "$marker_file" 2>/dev/null || true
    else
        log_info "All custom node dependencies already satisfied"
    fi
}
install_custom_node_deps

# ============================================================================
# TORCH_LOCK & USERSCRIPTS
# ============================================================================
verify_torch_lock
run_userscripts

# ============================================================================
# COMFYUI SERVER STARTUP
# ============================================================================
log_info "Starting ComfyUI server..."

# Activate virtual environment if it exists
if [ -d "/comfyui/venv" ]; then
    log_info "Activating virtual environment at /comfyui/venv"
    source /comfyui/venv/bin/activate
fi

# Set default ComfyUI port if not configured
COMFYUI_PORT=${COMFYUI_PORT:-8188}

# Set default ComfyUI arguments if not configured
COMFYUI_ARGS=${COMFYUI_ARGS:-""}

# Build ComfyUI command
COMFYUI_CMD="python /comfyui/main.py --listen 0.0.0.0 --port $COMFYUI_PORT"

if [ -n "$COMFYUI_ARGS" ]; then
    COMFYUI_CMD="$COMFYUI_CMD $COMFYUI_ARGS"
fi

log_info "ComfyUI command: $COMFYUI_CMD"

# Start ComfyUI in background
$COMFYUI_CMD &
COMFYUI_PID=$!

log_success "ComfyUI server started (PID: $COMFYUI_PID)"

# Wait for ComfyUI to be ready
log_info "Waiting for ComfyUI to be ready..."
MAX_WAIT=180
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://127.0.0.1:$COMFYUI_PORT/ > /dev/null 2>&1; then
        log_success "ComfyUI WebUI is ready"
        break
    fi
    
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    
    if [ $((WAIT_COUNT % 10)) -eq 0 ]; then
        log_info "Still waiting for ComfyUI... ($WAIT_COUNT/${MAX_WAIT}s)"
    fi
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    log_error "ComfyUI failed to start within ${MAX_WAIT} seconds"
    exit 1
fi

# ============================================================================
# COMFY MCP SERVER STARTUP (optional — agent-driven control of ComfyUI)
# ============================================================================
# Starts the comfyui-mcp MCP server in the background so AI agents
# (Claude Code, Cursor, ChatGPT) can drive this ComfyUI instance.
# Requires ENABLE_MCP=true and the userscript to have installed comfyui-mcp.
if [ "$MCP_ENABLED" = true ]; then
    log_info "Starting Comfy MCP server..."

    # Set defaults for MCP configuration
    MCP_PORT=${MCP_PORT:-8765}
    MCP_TRANSPORT=${MCP_TRANSPORT:-http}
    MCP_COMFYUI_URL=${MCP_COMFYUI_URL:-http://127.0.0.1:8188}

    # Verify comfyui-mcp is installed (should have been done by userscript)
    if ! command -v comfyui-mcp &>/dev/null; then
        log_error "comfyui-mcp not found — userscript install may have failed"
        log_warning "Continuing without MCP server. Check userscripts logs."
    else
        # Build the MCP server command based on transport mode
        # - http: Streamable-HTTP on loopback (agents connect via tunnel/proxy)
        # - tunnel: cloudflared public HTTPS tunnel (auto-generated URL + token)
        # - stdio: local pipe (for agents running on the same host)
        MCP_CMD="COMFYUI_URL=${MCP_COMFYUI_URL} comfyui-mcp"

        case "$MCP_TRANSPORT" in
            http)
                # Set auth token if provided, otherwise open (loopback only)
                if [ -n "$MCP_HTTP_TOKEN" ]; then
                    MCP_CMD="COMFYUI_MCP_HTTP_TOKEN=${MCP_HTTP_TOKEN} ${MCP_CMD} --http --port ${MCP_PORT}"
                else
                    MCP_CMD="${MCP_CMD} --http --port ${MCP_PORT}"
                fi
                ;;
            tunnel)
                # --tunnel forces HTTP transport + cloudflared quick tunnel
                # Generates a public https://... URL + auth token, printed to logs
                MCP_CMD="${MCP_CMD} --tunnel"
                ;;
            stdio)
                # stdio transport — for agents on the same host (no port needed)
                MCP_CMD="${MCP_CMD}"
                ;;
            *)
                log_warning "Unknown MCP_TRANSPORT: '$MCP_TRANSPORT' (valid: http, tunnel, stdio)"
                log_warning "Defaulting to http"
                MCP_CMD="${MCP_CMD} --http --port ${MCP_PORT}"
                MCP_TRANSPORT="http"
                ;;
        esac

        log_info "MCP command: $MCP_CMD"
        log_info "MCP transport: $MCP_TRANSPORT"
        log_info "MCP targeting ComfyUI at: $MCP_COMFYUI_URL"

        # Start MCP server in background
        eval "$MCP_CMD" &
        MCP_PID=$!
        log_success "Comfy MCP server started (PID: $MCP_PID)"

        if [ "$MCP_TRANSPORT" = "http" ]; then
            log_info "MCP endpoint: http://0.0.0.0:${MCP_PORT}/mcp"
            if [ -z "$MCP_HTTP_TOKEN" ]; then
                log_warning "MCP HTTP server has NO auth token — restrict network access!"
            fi
        elif [ "$MCP_TRANSPORT" = "tunnel" ]; then
            log_info "MCP tunnel URL will be printed above — check logs for https://... URL"
        fi
    fi
fi

# ============================================================================
# MODE-SPECIFIC BEHAVIOR
# ============================================================================
log_info "Executing mode-specific behavior..."

if [ "$MODE" = "serverless" ]; then
    log_info "=== SERVERLESS MODE ==="
    log_info "ComfyUI WebUI is accessible for testing and debugging"
    log_info "Starting RunPod handler for API-driven job processing..."
    
    # Start the RunPod handler (this will block and process jobs)
    cd /workspace
    python -u handler.py
    
elif [ "$MODE" = "pods" ]; then
    log_info "=== PODS MODE ==="
    log_success "ComfyUI is running at http://localhost:$COMFYUI_PORT"
    log_info "Access via RunPod proxy, OpenZiti tunnel, or SSH tunnel"
    
    if [ "$SSH_ENABLED" = true ]; then
        log_success "SSH is available on port 22"
    fi
    
    if [ "$OPENZITI_ENABLED" = true ]; then
        log_success "OpenZiti tunnel is active"
    fi

    if [ "$MCP_ENABLED" = true ]; then
        log_success "Comfy MCP server is running on port ${MCP_PORT:-8765}"
        log_info "Agent Panel tab (💬) available in ComfyUI sidebar"
    fi
    
    log_warning "REMINDER: This pod will continue billing until TERMINATED"
    log_warning "Stopping the pod does NOT stop billing - you must TERMINATE it"
    log_info "Container will keep running. Use RunPod UI/API to terminate."
    
    # Keep container alive and monitor ComfyUI process
    while kill -0 $COMFYUI_PID 2>/dev/null; do
        sleep 5
    done
    
    log_error "ComfyUI process died unexpectedly"
    exit 1
    
elif [ "$MODE" = "local" ]; then
    log_info "=== LOCAL MODE ==="
    log_success "ComfyUI is running at http://localhost:$COMFYUI_PORT"
    
    if [ "$SSH_ENABLED" = true ]; then
        log_success "SSH is available on port 22"
    fi
    
    if [ "$OPENZITI_ENABLED" = true ]; then
        log_success "OpenZiti tunnel is active"
    fi

    if [ "$MCP_ENABLED" = true ]; then
        log_success "Comfy MCP server is running on port ${MCP_PORT:-8765}"
        log_info "Agent Panel tab (💬) available in ComfyUI sidebar"
    fi
    
    log_info "Container will keep running. Press Ctrl+C to stop."
    
    # Keep container alive and monitor ComfyUI process
    while kill -0 $COMFYUI_PID 2>/dev/null; do
        sleep 5
    done
    
    log_error "ComfyUI process died unexpectedly"
    exit 1
fi
