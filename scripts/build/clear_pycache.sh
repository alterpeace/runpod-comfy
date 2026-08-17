#!/bin/bash
# Clear all __pycache__ directories from custom_nodes

# Allow passing a custom path as argument
if [ -n "$1" ]; then
    CUSTOM_NODES_DIR="$1"
elif [ -d "/comfyui/custom_nodes" ]; then
    CUSTOM_NODES_DIR="/comfyui/custom_nodes"
elif [ -d "/home/$USER/comfy/custom_nodes" ]; then
    CUSTOM_NODES_DIR="/home/$USER/comfy/custom_nodes"
elif [ -d "$HOME/comfy/custom_nodes" ]; then
    CUSTOM_NODES_DIR="$HOME/comfy/custom_nodes"
elif [ -d "./custom_nodes" ]; then
    CUSTOM_NODES_DIR="./custom_nodes"
elif [ -d "../custom_nodes" ]; then
    CUSTOM_NODES_DIR="../custom_nodes"
else
    echo "Could not find custom_nodes directory"
    echo "Usage: $0 [path_to_custom_nodes]"
    exit 1
fi

echo "Clearing __pycache__ from: $CUSTOM_NODES_DIR"

# Find and remove all __pycache__ directories
count=$(find "$CUSTOM_NODES_DIR" -type d -name "__pycache__" 2>/dev/null | wc -l)
find "$CUSTOM_NODES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Also remove .pyc files
pyc_count=$(find "$CUSTOM_NODES_DIR" -type f -name "*.pyc" 2>/dev/null | wc -l)
find "$CUSTOM_NODES_DIR" -type f -name "*.pyc" -delete 2>/dev/null

echo "Removed $count __pycache__ directories and $pyc_count .pyc files"
