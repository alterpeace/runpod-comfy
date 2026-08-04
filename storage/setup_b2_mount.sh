#!/bin/bash
set -e

# B2 Mount Setup Script
# Mounts Backblaze B2 bucket using rclone with optimized caching

echo "=== B2 Mount Setup ==="

# ============================================================================
# CREDENTIAL VALIDATION
# ============================================================================

# Validate required environment variables
REQUIRED_VARS=("B2_BUCKET" "B2_KEY_ID" "B2_APP_KEY" "B2_ENDPOINT")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "ERROR: Missing required B2 environment variables"
    echo ""
    echo "Missing variables: ${MISSING_VARS[*]}"
    echo ""
    echo "Required B2 configuration:"
    echo "  B2_BUCKET       - Your Backblaze B2 bucket name"
    echo "  B2_KEY_ID       - Your B2 application key ID"
    echo "  B2_APP_KEY      - Your B2 application key"
    echo "  B2_ENDPOINT     - B2 S3-compatible endpoint (e.g., s3.us-west-004.backblazeb2.com)"
    echo ""
    echo "Optional variables:"
    echo "  B2_REGION       - Bucket region (default: us-west-004)"
    echo "  B2_PATH         - Subdirectory within bucket (default: root)"
    echo "  RCLONE_CACHE_SIZE - Cache size (default: 20G)"
    echo ""
    echo "Please set these variables in your .env file or environment."
    exit 1
fi

# Validate credential format
if [ ${#B2_KEY_ID} -lt 10 ]; then
    echo "ERROR: B2_KEY_ID appears to be invalid (too short)"
    echo "Expected format: A 25-character alphanumeric string"
    echo "Current value length: ${#B2_KEY_ID} characters"
    exit 1
fi

if [ ${#B2_APP_KEY} -lt 20 ]; then
    echo "ERROR: B2_APP_KEY appears to be invalid (too short)"
    echo "Expected format: A 31-character alphanumeric string"
    echo "Current value length: ${#B2_APP_KEY} characters"
    exit 1
fi

# Validate endpoint format
if [[ ! "$B2_ENDPOINT" =~ ^s3\.[a-z0-9-]+\.backblazeb2\.com$ ]]; then
    echo "WARNING: B2_ENDPOINT format may be incorrect"
    echo "Expected format: s3.<region>.backblazeb2.com"
    echo "Current value: $B2_ENDPOINT"
    echo "Continuing anyway..."
fi

# Validate bucket name format
if [[ ! "$B2_BUCKET" =~ ^[a-z0-9][a-z0-9-]{4,48}[a-z0-9]$ ]]; then
    echo "WARNING: B2_BUCKET name may not meet B2 naming requirements"
    echo "Bucket names must:"
    echo "  - Be 6-50 characters long"
    echo "  - Start and end with a letter or number"
    echo "  - Contain only lowercase letters, numbers, and hyphens"
    echo "Current value: $B2_BUCKET"
    echo "Continuing anyway..."
fi

echo "✓ Environment variables validated"

# Set optional variables with defaults
B2_REGION=${B2_REGION:-us-west-004}
B2_PATH=${B2_PATH:-}
RCLONE_CACHE_SIZE=${RCLONE_CACHE_SIZE:-20G}
RCLONE_CACHE_MAX_AGE=${RCLONE_CACHE_MAX_AGE:-24h}
RCLONE_CACHE_DIR=${RCLONE_CACHE_DIR:-/runpod-volume/rclone-cache}

# Log configuration
echo "Configuration:"
echo "  Bucket: $B2_BUCKET"
echo "  Region: $B2_REGION"
echo "  Path: ${B2_PATH:-<root>}"
echo "  Cache Size: $RCLONE_CACHE_SIZE"
echo "  Cache Max Age: $RCLONE_CACHE_MAX_AGE"
echo "  Cache Directory: $RCLONE_CACHE_DIR"

# Generate rclone configuration
echo "Generating rclone configuration..."
mkdir -p ~/.config/rclone

cat > ~/.config/rclone/rclone.conf <<EOF
[b2]
type = s3
provider = Other
env_auth = false
access_key_id = ${B2_KEY_ID}
secret_access_key = ${B2_APP_KEY}
endpoint = ${B2_ENDPOINT}
region = ${B2_REGION}
acl = private
EOF

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create rclone configuration"
    exit 2
fi

echo "✓ rclone configuration created"

# ============================================================================
# B2 CONNECTIVITY TESTING
# ============================================================================

echo "Testing B2 connectivity..."

# Test basic connectivity with detailed error handling
CONNECTIVITY_TEST_OUTPUT=$(rclone lsd b2:${B2_BUCKET} --max-depth 1 2>&1)
CONNECTIVITY_EXIT_CODE=$?

if [ $CONNECTIVITY_EXIT_CODE -ne 0 ]; then
    echo "ERROR: Failed to connect to B2 bucket"
    echo ""
    
    # Provide specific error messages based on common failure patterns
    if echo "$CONNECTIVITY_TEST_OUTPUT" | grep -q "NoSuchBucket"; then
        echo "Reason: Bucket does not exist"
        echo "  - Bucket name: $B2_BUCKET"
        echo "  - Verify the bucket exists in your B2 account"
        echo "  - Check for typos in the bucket name"
    elif echo "$CONNECTIVITY_TEST_OUTPUT" | grep -q "InvalidAccessKeyId"; then
        echo "Reason: Invalid access key ID"
        echo "  - Your B2_KEY_ID is not recognized"
        echo "  - Verify the key ID in your B2 account settings"
        echo "  - Ensure you're using an application key, not the master key"
    elif echo "$CONNECTIVITY_TEST_OUTPUT" | grep -q "SignatureDoesNotMatch"; then
        echo "Reason: Invalid application key"
        echo "  - Your B2_APP_KEY does not match the key ID"
        echo "  - Verify the application key in your B2 account settings"
        echo "  - Check for extra spaces or newlines in the key"
    elif echo "$CONNECTIVITY_TEST_OUTPUT" | grep -q "AccessDenied"; then
        echo "Reason: Access denied"
        echo "  - Your application key does not have permission to access this bucket"
        echo "  - Verify the key has 'listBuckets' and 'listFiles' permissions"
        echo "  - Check if the key is restricted to a different bucket"
    elif echo "$CONNECTIVITY_TEST_OUTPUT" | grep -q "connection refused\|network\|timeout"; then
        echo "Reason: Network connectivity issue"
        echo "  - Cannot reach B2 endpoint: $B2_ENDPOINT"
        echo "  - Check your internet connection"
        echo "  - Verify the endpoint URL is correct"
        echo "  - Check if a firewall is blocking outbound connections"
    else
        echo "Reason: Unknown error"
        echo ""
        echo "rclone output:"
        echo "$CONNECTIVITY_TEST_OUTPUT"
    fi
    
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Verify your B2 credentials in the B2 web console"
    echo "  2. Test credentials with: rclone lsd b2:$B2_BUCKET"
    echo "  3. Check rclone config: cat ~/.config/rclone/rclone.conf"
    echo "  4. Review B2 application key permissions"
    echo ""
    exit 2
fi

echo "✓ B2 connectivity verified"

# Verify bucket is accessible and not empty (warning only)
BUCKET_CONTENTS=$(rclone lsd b2:${B2_BUCKET} --max-depth 1 2>/dev/null | wc -l)
if [ "$BUCKET_CONTENTS" -eq 0 ]; then
    echo "WARNING: B2 bucket appears to be empty"
    echo "  - Bucket: $B2_BUCKET"
    echo "  - If this is unexpected, verify you're using the correct bucket"
    echo "  - ComfyUI may not find any models to load"
    echo ""
fi

# ============================================================================
# NETWORK VOLUME VERIFICATION
# ============================================================================

echo "Verifying network volume for cache storage..."

# Check if network volume is mounted
if [ ! -d "/runpod-volume" ]; then
    echo "ERROR: Network volume not found at /runpod-volume"
    echo ""
    echo "The rclone cache requires a network volume to be mounted."
    echo ""
    echo "Possible causes:"
    echo "  - Running in an environment without a network volume"
    echo "  - Network volume failed to mount"
    echo "  - Incorrect mount path configuration"
    echo ""
    echo "Solutions:"
    echo "  - Ensure your RunPod pod/serverless has a network volume attached"
    echo "  - Check RunPod dashboard for network volume status"
    echo "  - For local development, create a directory: mkdir -p /runpod-volume"
    echo ""
    exit 3
fi

# Verify network volume is writable
if [ ! -w "/runpod-volume" ]; then
    echo "ERROR: Network volume at /runpod-volume is not writable"
    echo ""
    echo "The rclone cache requires write access to the network volume."
    echo ""
    echo "Possible causes:"
    echo "  - Insufficient permissions"
    echo "  - Read-only mount"
    echo "  - Filesystem error"
    echo ""
    echo "Current permissions:"
    ls -ld /runpod-volume
    echo ""
    exit 3
fi

echo "✓ Network volume is accessible and writable"

# Create cache directory on network volume
echo "Creating cache directory at $RCLONE_CACHE_DIR..."
if ! mkdir -p "$RCLONE_CACHE_DIR"; then
    echo "ERROR: Failed to create cache directory at $RCLONE_CACHE_DIR"
    echo ""
    echo "Possible causes:"
    echo "  - Insufficient permissions"
    echo "  - Disk full"
    echo "  - Invalid path"
    echo ""
    exit 3
fi

# Verify cache directory is writable
if [ ! -w "$RCLONE_CACHE_DIR" ]; then
    echo "ERROR: Cache directory at $RCLONE_CACHE_DIR is not writable"
    echo ""
    echo "Current permissions:"
    ls -ld "$RCLONE_CACHE_DIR"
    echo ""
    exit 3
fi

echo "✓ Cache directory created and verified"

# Check network volume space
AVAILABLE_BYTES=$(df --output=avail -B1 /runpod-volume | tail -1)
AVAILABLE_GB=$((AVAILABLE_BYTES / 1024 / 1024 / 1024))
AVAILABLE_MB=$((AVAILABLE_BYTES / 1024 / 1024))

if [ $AVAILABLE_GB -gt 0 ]; then
    echo "Network volume available space: ${AVAILABLE_GB}GB"
else
    echo "Network volume available space: ${AVAILABLE_MB}MB"
fi

# Parse cache size to bytes for comparison
CACHE_SIZE_VALUE=$(echo "$RCLONE_CACHE_SIZE" | sed 's/[^0-9]//g')
CACHE_SIZE_UNIT=$(echo "$RCLONE_CACHE_SIZE" | sed 's/[0-9]//g' | tr '[:lower:]' '[:upper:]')

case "$CACHE_SIZE_UNIT" in
    "G"|"GB")
        CACHE_SIZE_BYTES=$((CACHE_SIZE_VALUE * 1024 * 1024 * 1024))
        ;;
    "M"|"MB")
        CACHE_SIZE_BYTES=$((CACHE_SIZE_VALUE * 1024 * 1024))
        ;;
    "T"|"TB")
        CACHE_SIZE_BYTES=$((CACHE_SIZE_VALUE * 1024 * 1024 * 1024 * 1024))
        ;;
    *)
        echo "WARNING: Could not parse cache size unit from: $RCLONE_CACHE_SIZE"
        echo "Assuming gigabytes..."
        CACHE_SIZE_BYTES=$((CACHE_SIZE_VALUE * 1024 * 1024 * 1024))
        ;;
esac

# Warn if cache size is larger than available space
if [ $CACHE_SIZE_BYTES -gt $AVAILABLE_BYTES ]; then
    CACHE_SIZE_GB=$((CACHE_SIZE_BYTES / 1024 / 1024 / 1024))
    echo "WARNING: Configured cache size (${CACHE_SIZE_GB}GB) exceeds available space (${AVAILABLE_GB}GB)"
    echo "  - rclone will use available space and manage cache automatically"
    echo "  - Consider reducing RCLONE_CACHE_SIZE or increasing network volume size"
    echo "  - Cache will still work but may not reach configured size"
    echo ""
elif [ $AVAILABLE_GB -lt 10 ]; then
    echo "WARNING: Low disk space on network volume (${AVAILABLE_GB}GB available)"
    echo "  - Cache may fill up quickly"
    echo "  - Consider increasing network volume size for better performance"
    echo ""
fi

# Create mount point
MOUNT_POINT="/comfyui/models"
echo "Creating mount point at $MOUNT_POINT..."
mkdir -p "$MOUNT_POINT"

# Construct remote path
if [ -n "$B2_PATH" ]; then
    REMOTE_PATH="b2:${B2_BUCKET}/${B2_PATH}"
else
    REMOTE_PATH="b2:${B2_BUCKET}"
fi

echo "Mounting $REMOTE_PATH to $MOUNT_POINT..."

# ============================================================================
# B2 MOUNT EXECUTION
# ============================================================================

# Mount B2 bucket with optimized flags
echo "Executing rclone mount..."

MOUNT_OUTPUT=$(rclone mount "$REMOTE_PATH" "$MOUNT_POINT" \
    --daemon \
    --vfs-cache-mode full \
    --vfs-cache-max-size "$RCLONE_CACHE_SIZE" \
    --cache-dir "$RCLONE_CACHE_DIR" \
    --vfs-cache-max-age "$RCLONE_CACHE_MAX_AGE" \
    --buffer-size 256M \
    --vfs-read-ahead 256M \
    --dir-cache-time 1h \
    --poll-interval 0 \
    --read-only \
    --allow-other \
    --vfs-cache-poll-interval 1m \
    --log-level INFO \
    --log-file /tmp/rclone-mount.log 2>&1)

MOUNT_EXIT_CODE=$?

if [ $MOUNT_EXIT_CODE -ne 0 ]; then
    echo "ERROR: Failed to mount B2 bucket"
    echo ""
    echo "Exit code: $MOUNT_EXIT_CODE"
    
    # Provide specific error messages based on common failure patterns
    if echo "$MOUNT_OUTPUT" | grep -q "fusermount"; then
        echo "Reason: FUSE not available or not configured"
        echo "  - FUSE is required for rclone mount"
        echo "  - Ensure fuse package is installed"
        echo "  - Check if /dev/fuse exists and is accessible"
        echo "  - Container may need --device /dev/fuse or --privileged flag"
    elif echo "$MOUNT_OUTPUT" | grep -q "permission denied"; then
        echo "Reason: Permission denied"
        echo "  - Insufficient permissions to create mount"
        echo "  - Try running with elevated privileges"
        echo "  - Check mount point permissions"
    elif echo "$MOUNT_OUTPUT" | grep -q "already mounted\|busy"; then
        echo "Reason: Mount point already in use"
        echo "  - Another process may be using $MOUNT_POINT"
        echo "  - Try unmounting: fusermount -u $MOUNT_POINT"
        echo "  - Check for stale mounts: mount | grep rclone"
    elif echo "$MOUNT_OUTPUT" | grep -q "not empty"; then
        echo "Reason: Mount point directory is not empty"
        echo "  - $MOUNT_POINT contains files"
        echo "  - rclone requires an empty directory for mounting"
        echo "  - Clear the directory or use a different mount point"
    else
        echo "Reason: Unknown error"
        echo ""
        echo "Mount output:"
        echo "$MOUNT_OUTPUT"
    fi
    
    echo ""
    echo "Troubleshooting:"
    echo "  - Check rclone logs: tail -f /tmp/rclone-mount.log"
    echo "  - Test mount manually: rclone mount $REMOTE_PATH $MOUNT_POINT --vfs-cache-mode full"
    echo "  - Verify FUSE: ls -l /dev/fuse"
    echo ""
    exit 3
fi

echo "✓ B2 mount command executed"

# ============================================================================
# MOUNT VERIFICATION
# ============================================================================

echo "Verifying mount..."
TIMEOUT=30
ELAPSED=0
VERIFICATION_FAILED=false

while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check if mount point is actually mounted
    if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        echo "✓ Mount point verified"
        
        # Additional verification: try to list directory
        if timeout 5 ls "$MOUNT_POINT" > /dev/null 2>&1; then
            echo "✓ Mount is accessible and responsive"
            
            # Check if rclone process is running
            if pgrep -f "rclone mount.*$MOUNT_POINT" > /dev/null; then
                echo "✓ rclone daemon is running"
            else
                echo "WARNING: Mount exists but rclone process not found"
                echo "  - This may indicate an issue with the mount"
                echo "  - Check /tmp/rclone-mount.log for details"
            fi
            
            echo ""
            echo "=== B2 Mount Setup Complete ==="
            echo "Models directory: $MOUNT_POINT"
            echo "Cache directory: $RCLONE_CACHE_DIR"
            echo "Cache size: $RCLONE_CACHE_SIZE"
            echo "Mount logs: /tmp/rclone-mount.log"
            echo ""
            echo "Performance tips:"
            echo "  - First access to files will be slow (downloading from B2)"
            echo "  - Subsequent access will be fast (served from cache)"
            echo "  - Monitor cache usage: du -sh $RCLONE_CACHE_DIR"
            echo "  - Monitor mount logs: tail -f /tmp/rclone-mount.log"
            echo ""
            exit 0
        else
            echo "WARNING: Mount point exists but is not responsive"
            echo "  - Waiting for mount to become ready..."
        fi
    fi
    
    # Check if rclone process died
    if [ $ELAPSED -gt 5 ] && ! pgrep -f "rclone mount.*$MOUNT_POINT" > /dev/null; then
        echo "ERROR: rclone process is not running"
        VERIFICATION_FAILED=true
        break
    fi
    
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    
    if [ $((ELAPSED % 5)) -eq 0 ]; then
        echo "  Still waiting... (${ELAPSED}/${TIMEOUT}s)"
    fi
done

# Mount verification failed
echo ""
echo "ERROR: Mount verification failed after ${TIMEOUT}s"
echo ""

if [ "$VERIFICATION_FAILED" = true ]; then
    echo "Reason: rclone process died unexpectedly"
else
    echo "Reason: Mount point is not accessible or not responding"
fi

echo ""
echo "Diagnostic information:"
echo ""

# Check mount point status
echo "Mount point status:"
if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    echo "  ✓ Mount point exists"
else
    echo "  ✗ Mount point does not exist"
fi

# Check rclone process
echo ""
echo "rclone process status:"
if pgrep -f "rclone mount" > /dev/null; then
    echo "  ✓ rclone process is running:"
    pgrep -af "rclone mount" | head -5
else
    echo "  ✗ No rclone process found"
fi

# Show recent log entries
echo ""
echo "Recent rclone logs (last 20 lines):"
if [ -f /tmp/rclone-mount.log ]; then
    tail -20 /tmp/rclone-mount.log
else
    echo "  Log file not found at /tmp/rclone-mount.log"
fi

echo ""
echo "Troubleshooting steps:"
echo "  1. Check full logs: cat /tmp/rclone-mount.log"
echo "  2. Verify B2 connectivity: rclone lsd $REMOTE_PATH"
echo "  3. Check FUSE availability: ls -l /dev/fuse"
echo "  4. Try manual mount: rclone mount $REMOTE_PATH $MOUNT_POINT --vfs-cache-mode full -vv"
echo "  5. Check system logs: dmesg | tail -50"
echo ""

exit 4
