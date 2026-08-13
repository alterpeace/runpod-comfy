#!/bin/bash

# SSH Server Setup Script for ComfyUI Development
# This script configures and starts an SSH server for debugging and package installation

set -e  # Exit on error

# Color codes for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[SSH Setup]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SSH Setup]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[SSH Setup]${NC} $1"
}

log_error() {
    echo -e "${RED}[SSH Setup]${NC} $1"
}

# Check if SSH is enabled
if [ "$ENABLE_SSH" != "true" ]; then
    log_info "SSH is not enabled (ENABLE_SSH != true). Skipping SSH setup."
    exit 0
fi

log_info "Starting SSH server setup..."

# Create SSH directory if it doesn't exist
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Generate SSH host keys if not present
log_info "Checking SSH host keys..."
if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
    log_info "Generating SSH host keys..."
    ssh-keygen -A
    log_success "SSH host keys generated"
else
    log_info "SSH host keys already exist"
fi

# Configure authorized_keys
log_info "Configuring SSH authentication..."

# Check if SSH_AUTHORIZED_KEYS_PATH is provided (network storage)
if [ -n "$SSH_AUTHORIZED_KEYS_PATH" ] && [ -f "$SSH_AUTHORIZED_KEYS_PATH" ]; then
    log_info "Using authorized_keys from: $SSH_AUTHORIZED_KEYS_PATH"
    cp "$SSH_AUTHORIZED_KEYS_PATH" /root/.ssh/authorized_keys
    log_success "Copied authorized_keys from network storage"
# Check if SSH_PUBLIC_KEY is provided (environment variable)
elif [ -n "$SSH_PUBLIC_KEY" ]; then
    log_info "Using SSH_PUBLIC_KEY from environment variable"
    echo "$SSH_PUBLIC_KEY" > /root/.ssh/authorized_keys
    log_success "Wrote SSH_PUBLIC_KEY to authorized_keys"
else
    log_error "No SSH public key provided!"
    log_error "Please set either SSH_PUBLIC_KEY or SSH_AUTHORIZED_KEYS_PATH"
    exit 1
fi

# Set proper permissions on authorized_keys
chmod 600 /root/.ssh/authorized_keys
log_info "Set permissions on authorized_keys (600)"

# Verify authorized_keys is not empty
if [ ! -s /root/.ssh/authorized_keys ]; then
    log_error "authorized_keys file is empty!"
    exit 1
fi

# Copy sshd_config if it exists in the ssh directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/sshd_config" ]; then
    log_info "Using custom sshd_config..."
    cp "$SCRIPT_DIR/sshd_config" /etc/ssh/sshd_config
    log_success "Copied custom sshd_config"
fi

# Create run directory for sshd
mkdir -p /run/sshd

# Test sshd configuration
log_info "Testing SSH daemon configuration..."
if /usr/sbin/sshd -t; then
    log_success "SSH daemon configuration is valid"
else
    log_error "SSH daemon configuration test failed!"
    exit 1
fi

# Start SSH daemon
log_info "Starting SSH daemon..."
/usr/sbin/sshd

# Check if sshd started successfully
if pgrep -x sshd > /dev/null; then
    log_success "SSH daemon started successfully"
    
    # Display access information
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "SSH Server is running on port 22"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Provide access instructions based on environment
    if [ -n "$RUNPOD_POD_ID" ]; then
        log_info "RunPod Environment Detected"
        log_info ""
        log_info "Access via RunPod SSH endpoint:"
        log_info "  Check RunPod dashboard for SSH connection details"
        log_info "  Typically: ssh root@<pod-id>.runpod.io -p <assigned-port>"
    else
        log_info "Local Environment Detected"
        log_info ""
        log_info "Access via localhost:"
        log_info "  ssh root@localhost -p 2222"
    fi
    
    log_info ""
    log_info "Network storage access:"
    if [ -d "/runpod-volume" ]; then
        log_info "  RunPod network volume: /runpod-volume/"
    fi
    if [ -d "/workspace" ]; then
        log_info "  Workspace: /workspace/"
    fi
    
    log_info ""
    log_info "Install Python packages to network storage:"
    log_info "  pip install --target=/runpod-volume/python-packages <package>"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
else
    log_error "Failed to start SSH daemon!"
    log_error "Check logs with: journalctl -u ssh"
    exit 1
fi

# Monitor SSH daemon (optional - runs in background)
monitor_sshd() {
    while true; do
        if ! pgrep -x sshd > /dev/null; then
            log_warning "SSH daemon stopped unexpectedly. Restarting..."
            /usr/sbin/sshd
            if pgrep -x sshd > /dev/null; then
                log_success "SSH daemon restarted successfully"
            else
                log_error "Failed to restart SSH daemon"
            fi
        fi
        sleep 30
    done
}

# Start monitoring in background if requested
if [ "$SSH_MONITOR" = "true" ]; then
    log_info "Starting SSH daemon monitor..."
    monitor_sshd &
    log_success "SSH daemon monitor started in background"
fi

log_success "SSH server setup complete!"
