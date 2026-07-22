#!/bin/bash
# Update all ComfyUI custom nodes by pulling latest from git
# Works in Docker container or locally
#
# Usage:
#   ./update_custom_nodes.sh [options]
#
# Options:
#   --force            Reset local changes before pulling (git checkout .)
#   --fix-permissions  Fix ownership issues (requires sudo/root)
#   --help             Show this help message

# Don't use set -e - we want to continue even if individual updates fail

# Parse command line arguments
FORCE_UPDATE=false
FIX_PERMISSIONS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_UPDATE=true
            shift
            ;;
        --fix-permissions)
            FIX_PERMISSIONS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --force            Reset local changes before pulling (git checkout .)"
            echo "  --fix-permissions  Fix ownership issues (requires sudo/root)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Determine custom_nodes directory (check in order of priority)
find_custom_nodes_dir() {
    # 1. Check if explicitly set via environment variable
    if [ -n "$CUSTOM_NODES_DIR" ] && [ -d "$CUSTOM_NODES_DIR" ]; then
        echo "$CUSTOM_NODES_DIR"
        return
    fi
    
    # 2. Check Docker container path
    if [ -d "/comfyui/custom_nodes" ]; then
        echo "/comfyui/custom_nodes"
        return
    fi
    
    # 3. Check relative to script location (../custom_nodes)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -d "$SCRIPT_DIR/../custom_nodes" ]; then
        echo "$(cd "$SCRIPT_DIR/../custom_nodes" && pwd)"
        return
    fi
    
    # 4. Check $HOME/comfy/custom_nodes
    if [ -d "$HOME/comfy/custom_nodes" ]; then
        echo "$HOME/comfy/custom_nodes"
        return
    fi
    
    # 5. Check $HOME/ComfyUI/custom_nodes (common install location)
    if [ -d "$HOME/ComfyUI/custom_nodes" ]; then
        echo "$HOME/ComfyUI/custom_nodes"
        return
    fi
    
    # Not found
    echo ""
}

CUSTOM_NODES_DIR="$(find_custom_nodes_dir)"
LOG_FILE="/tmp/custom_nodes_update.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "ComfyUI Custom Nodes Updater"
echo "=========================================="
echo "Custom nodes directory: $CUSTOM_NODES_DIR"
echo "Log file: $LOG_FILE"
if [ "$FORCE_UPDATE" = true ]; then
    echo -e "${YELLOW}Force mode: ON (will reset local changes)${NC}"
fi
if [ "$FIX_PERMISSIONS" = true ]; then
    echo -e "${YELLOW}Fix permissions: ON${NC}"
fi
echo ""

# Initialize counters
updated=0
failed=0
skipped=0

# Clear log file
> "$LOG_FILE"

# Check if directory exists
if [ -z "$CUSTOM_NODES_DIR" ] || [ ! -d "$CUSTOM_NODES_DIR" ]; then
    echo -e "${RED}Error: Could not find custom_nodes directory${NC}"
    echo "Searched in:"
    echo "  - \$CUSTOM_NODES_DIR (if set)"
    echo "  - /comfyui/custom_nodes (Docker)"
    echo "  - ../custom_nodes (relative to script)"
    echo "  - \$HOME/comfy/custom_nodes"
    echo "  - \$HOME/ComfyUI/custom_nodes"
    echo ""
    echo "Set CUSTOM_NODES_DIR environment variable to specify location:"
    echo "  CUSTOM_NODES_DIR=/path/to/custom_nodes $0"
    exit 1
fi

cd "$CUSTOM_NODES_DIR"

# Get list of directories
for node_dir in */; do
    # Remove trailing slash
    node_name="${node_dir%/}"
    
    # Skip if not a directory
    [ ! -d "$node_name" ] && continue
    
    # Skip disabled nodes
    if [[ "$node_name" == *.disabled ]]; then
        echo -e "${YELLOW}[SKIP]${NC} $node_name (disabled)"
        ((skipped++))
        continue
    fi
    
    # Skip non-git directories
    if [ ! -d "$node_name/.git" ]; then
        echo -e "${YELLOW}[SKIP]${NC} $node_name (not a git repo)"
        ((skipped++))
        continue
    fi
    
    echo -n "Updating $node_name... "
    
    cd "$node_name"
    
    # Fix permissions if requested
    if [ "$FIX_PERMISSIONS" = true ]; then
        if [ "$(id -u)" = "0" ]; then
            # Running as root
            chown -R root:root . 2>/dev/null || true
            chmod -R u+rw .git 2>/dev/null || true
        else
            # Try with sudo
            sudo chown -R "$(whoami)" . 2>/dev/null || true
            chmod -R u+rw .git 2>/dev/null || true
        fi
    fi
    
    # Get current commit for comparison
    old_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # Reset local changes if force mode is enabled
    if [ "$FORCE_UPDATE" = true ]; then
        git checkout . >> "$LOG_FILE" 2>&1 || true
        git clean -fd >> "$LOG_FILE" 2>&1 || true
        # Also update submodules if they exist
        if [ -f ".gitmodules" ]; then
            git submodule update --init --recursive >> "$LOG_FILE" 2>&1 || true
        fi
    fi
    
    # Try to update
    if git pull --ff-only >> "$LOG_FILE" 2>&1; then
        new_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        
        if [ "$old_commit" != "$new_commit" ]; then
            echo -e "${GREEN}[UPDATED]${NC} $old_commit -> $new_commit"
            ((updated++))
            
            # Check for requirements.txt and install if exists
            if [ -f "requirements.txt" ]; then
                echo "  Installing requirements..."
                if [ -f "/comfyui/venv/bin/activate" ]; then
                    . /comfyui/venv/bin/activate
                    pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || true
                fi
            fi
        else
            echo -e "${GREEN}[OK]${NC} already up to date"
        fi
    else
        echo -e "${RED}[FAILED]${NC} check $LOG_FILE for details"
        echo "=== $node_name ===" >> "$LOG_FILE"
        ((failed++))
        
        # If force mode and still failed, try harder
        if [ "$FORCE_UPDATE" = true ]; then
            echo "  Retrying with git reset --hard..."
            git fetch origin >> "$LOG_FILE" 2>&1 || true
            default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
            if git reset --hard "origin/$default_branch" >> "$LOG_FILE" 2>&1; then
                new_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
                echo -e "  ${GREEN}[RECOVERED]${NC} reset to $new_commit"
                ((failed--))
                ((updated++))
            fi
        fi
    fi
    
    cd "$CUSTOM_NODES_DIR"
done

echo ""
echo "=========================================="
echo "Summary:"
echo "  Updated: $updated"
echo "  Failed:  $failed"
echo "  Skipped: $skipped"
echo "=========================================="

if [ $failed -gt 0 ]; then
    echo ""
    echo "Some updates failed. Check $LOG_FILE for details."
    echo "Common issues:"
    echo "  - Local changes conflict with upstream"
    echo "  - Network issues"
    echo "  - Repository moved or deleted"
fi

if [ $updated -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Restart ComfyUI to load updated nodes.${NC}"
fi
