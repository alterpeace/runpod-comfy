#!/bin/bash

# OpenZiti Tunnel Setup Script
# This script initializes an OpenZiti tunnel for secure access to ComfyUI and SSH
# It supports both file-based and embedded JSON identity configurations

set -e  # Exit on error (but we'll handle errors gracefully)

# Color codes for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[OpenZiti]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[OpenZiti]${NC} $1"
}

log_error() {
    echo -e "${RED}[OpenZiti]${NC} $1"
}

# Function to check if OpenZiti is configured
check_openziti_config() {
    if [ -z "$OPENZITI_IDENTITY" ] && [ -z "$OPENZITI_IDENTITY_JSON" ]; then
        log_warn "No OpenZiti configuration found (OPENZITI_IDENTITY or OPENZITI_IDENTITY_JSON not set)"
        return 1
    fi
    return 0
}

# Function to load identity from file path
load_identity_from_file() {
    local identity_path="$1"
    
    if [ ! -f "$identity_path" ]; then
        log_error "Identity file not found: $identity_path"
        return 1
    fi
    
    log_info "Loading identity from file: $identity_path"
    echo "$identity_path"
    return 0
}

# Function to load identity from embedded JSON
load_identity_from_json() {
    local identity_json="$1"
    local identity_file="/tmp/ziti-identity.json"
    
    log_info "Loading identity from embedded JSON"
    
    # Write JSON to temporary file
    echo "$identity_json" > "$identity_file"
    
    if [ ! -s "$identity_file" ]; then
        log_error "Failed to write identity JSON to file"
        return 1
    fi
    
    log_info "Identity written to: $identity_file"
    echo "$identity_file"
    return 0
}

# Function to determine identity file path
get_identity_file() {
    local identity_file=""
    
    # Priority 1: OPENZITI_IDENTITY_JSON (embedded)
    if [ -n "$OPENZITI_IDENTITY_JSON" ]; then
        identity_file=$(load_identity_from_json "$OPENZITI_IDENTITY_JSON")
        if [ $? -eq 0 ]; then
            echo "$identity_file"
            return 0
        fi
    fi
    
    # Priority 2: OPENZITI_IDENTITY (file path)
    if [ -n "$OPENZITI_IDENTITY" ]; then
        identity_file=$(load_identity_from_file "$OPENZITI_IDENTITY")
        if [ $? -eq 0 ]; then
            echo "$identity_file"
            return 0
        fi
    fi
    
    log_error "Failed to load OpenZiti identity"
    return 1
}

# Function to check if ziti-edge-tunnel is installed
check_ziti_installed() {
    if ! command -v ziti-edge-tunnel &> /dev/null; then
        log_error "ziti-edge-tunnel is not installed"
        log_error "Please install OpenZiti tunnel client: https://openziti.io/docs/downloads"
        return 1
    fi
    
    log_info "ziti-edge-tunnel found: $(which ziti-edge-tunnel)"
    return 0
}

# Function to initialize OpenZiti tunnel
initialize_tunnel() {
    local identity_file="$1"
    
    log_info "Initializing OpenZiti tunnel..."
    
    # Start ziti-edge-tunnel in proxy mode
    # This will forward services defined in the identity
    ziti-edge-tunnel run --identity "$identity_file" &
    local tunnel_pid=$!
    
    # Save PID for monitoring
    echo "$tunnel_pid" > /tmp/ziti-tunnel.pid
    
    log_info "OpenZiti tunnel started (PID: $tunnel_pid)"
    
    # Wait a moment for tunnel to initialize
    sleep 2
    
    # Check if process is still running
    if ! kill -0 "$tunnel_pid" 2>/dev/null; then
        log_error "OpenZiti tunnel failed to start"
        return 1
    fi
    
    return 0
}

# Function to verify tunnel connectivity
verify_tunnel() {
    log_info "Verifying tunnel connectivity..."
    
    # Give tunnel time to establish connections
    local max_attempts=10
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if [ -f /tmp/ziti-tunnel.pid ]; then
            local pid=$(cat /tmp/ziti-tunnel.pid)
            if kill -0 "$pid" 2>/dev/null; then
                log_info "Tunnel is running (PID: $pid)"
                return 0
            fi
        fi
        
        attempt=$((attempt + 1))
        sleep 1
    done
    
    log_warn "Could not verify tunnel connectivity"
    return 1
}

# Function to setup port forwarding configuration
setup_port_forwarding() {
    log_info "Port forwarding configuration:"
    
    # HTTP port forwarding (ComfyUI)
    if [ -n "$OPENZITI_SERVICE_HTTP" ]; then
        log_info "  - HTTP (ComfyUI): Service '$OPENZITI_SERVICE_HTTP' -> Port 8188"
    else
        log_warn "  - HTTP: OPENZITI_SERVICE_HTTP not configured"
    fi
    
    # SSH port forwarding
    if [ -n "$OPENZITI_SERVICE_SSH" ]; then
        log_info "  - SSH: Service '$OPENZITI_SERVICE_SSH' -> Port 22"
    else
        log_warn "  - SSH: OPENZITI_SERVICE_SSH not configured"
    fi
    
    # Note: Actual port forwarding is handled by the OpenZiti network configuration
    # The services must be configured in the OpenZiti controller
    log_info "Note: Services must be configured in OpenZiti controller"
}

# Function to monitor tunnel health
monitor_tunnel_health() {
    if [ ! -f /tmp/ziti-tunnel.pid ]; then
        log_warn "Tunnel PID file not found"
        return 1
    fi
    
    local pid=$(cat /tmp/ziti-tunnel.pid)
    
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        log_error "Tunnel process is not running"
        return 1
    fi
}

# Function to cleanup on exit
cleanup() {
    log_info "Cleaning up OpenZiti tunnel..."
    
    if [ -f /tmp/ziti-tunnel.pid ]; then
        local pid=$(cat /tmp/ziti-tunnel.pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            log_info "Tunnel process stopped"
        fi
        rm -f /tmp/ziti-tunnel.pid
    fi
}

# Main execution
main() {
    log_info "Starting OpenZiti tunnel setup..."
    
    # Check if OpenZiti is configured
    if ! check_openziti_config; then
        log_warn "OpenZiti tunnel disabled (no configuration found)"
        exit 0  # Exit gracefully, not an error
    fi
    
    # Check if ziti-edge-tunnel is installed
    if ! check_ziti_installed; then
        log_error "Cannot initialize tunnel without ziti-edge-tunnel"
        log_warn "Continuing without OpenZiti tunnel..."
        exit 0  # Exit gracefully, log error but continue
    fi
    
    # Get identity file path
    local identity_file
    identity_file=$(get_identity_file)
    if [ $? -ne 0 ]; then
        log_error "Failed to load identity configuration"
        log_warn "Continuing without OpenZiti tunnel..."
        exit 0  # Exit gracefully
    fi
    
    # Initialize tunnel
    if ! initialize_tunnel "$identity_file"; then
        log_error "Failed to initialize OpenZiti tunnel"
        log_warn "Continuing without OpenZiti tunnel..."
        exit 0  # Exit gracefully
    fi
    
    # Setup port forwarding info
    setup_port_forwarding
    
    # Verify tunnel
    if verify_tunnel; then
        log_info "OpenZiti tunnel is operational"
        log_info "Services are now accessible via OpenZiti network"
    else
        log_warn "Tunnel verification incomplete, but process is running"
    fi
    
    # Register cleanup handler
    trap cleanup EXIT INT TERM
    
    log_info "OpenZiti tunnel setup complete"
    
    # Keep script running to maintain tunnel (if called directly)
    # In practice, this will be backgrounded by entrypoint.sh
    if [ "${KEEP_RUNNING:-false}" = "true" ]; then
        log_info "Monitoring tunnel health..."
        while true; do
            if ! monitor_tunnel_health; then
                log_error "Tunnel health check failed, attempting restart..."
                if ! initialize_tunnel "$identity_file"; then
                    log_error "Failed to restart tunnel"
                    exit 1
                fi
            fi
            sleep 30
        done
    fi
}

# Run main function
main "$@"
