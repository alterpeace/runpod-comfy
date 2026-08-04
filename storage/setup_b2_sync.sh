#!/bin/bash
set -e

# B2 Sync Setup Script
# Syncs Backblaze B2 bucket contents to local storage on container startup

echo "=== B2 Sync Setup ==="

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
    echo "  SYNC_TARGET     - Local sync destination (default: /comfyui/models)"
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
SYNC_TARGET=${SYNC_TARGET:-/comfyui/models}

# Log configuration
echo "Configuration:"
echo "  Bucket: $B2_BUCKET"
echo "  Region: $B2_REGION"
echo "  Path: ${B2_PATH:-<root>}"
echo "  Sync Target: $SYNC_TARGET"

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

# Construct remote path
if [ -n "$B2_PATH" ]; then
    REMOTE_PATH="b2:${B2_BUCKET}/${B2_PATH}"
else
    REMOTE_PATH="b2:${B2_BUCKET}"
fi

# ============================================================================
# DISK SPACE VERIFICATION
# ============================================================================

echo "Checking disk space..."

# Get remote size with timeout and error handling
echo "Calculating remote bucket size..."
REMOTE_SIZE_OUTPUT=$(timeout 60 rclone size "$REMOTE_PATH" --json 2>&1)
REMOTE_SIZE_EXIT_CODE=$?

if [ $REMOTE_SIZE_EXIT_CODE -eq 124 ]; then
    echo "WARNING: Remote size calculation timed out after 60 seconds"
    echo "  - This may indicate a very large bucket or slow connection"
    echo "  - Continuing with sync, but disk space check may be inaccurate"
    echo ""
    REMOTE_SIZE_BYTES=0
elif [ $REMOTE_SIZE_EXIT_CODE -ne 0 ]; then
    echo "WARNING: Could not calculate remote bucket size"
    echo "  - Error: $REMOTE_SIZE_OUTPUT"
    echo "  - Continuing with sync, but disk space check may be inaccurate"
    echo ""
    REMOTE_SIZE_BYTES=0
else
    REMOTE_SIZE_BYTES=$(echo "$REMOTE_SIZE_OUTPUT" | grep -o '"bytes":[0-9]*' | cut -d':' -f2)
    
    if [ -z "$REMOTE_SIZE_BYTES" ]; then
        echo "WARNING: Could not parse remote size from rclone output"
        REMOTE_SIZE_BYTES=0
    fi
fi

REMOTE_SIZE_GB=$((REMOTE_SIZE_BYTES / 1024 / 1024 / 1024))
REMOTE_SIZE_MB=$((REMOTE_SIZE_BYTES / 1024 / 1024))

if [ $REMOTE_SIZE_BYTES -eq 0 ]; then
    echo "Remote bucket size: Unknown or empty"
elif [ $REMOTE_SIZE_GB -gt 0 ]; then
    echo "Remote bucket size: ${REMOTE_SIZE_GB}GB (${REMOTE_SIZE_BYTES} bytes)"
else
    echo "Remote bucket size: ${REMOTE_SIZE_MB}MB (${REMOTE_SIZE_BYTES} bytes)"
fi

# Get available disk space
SYNC_TARGET_DIR=$(dirname "$SYNC_TARGET")

# Create target directory if it doesn't exist
if ! mkdir -p "$SYNC_TARGET_DIR" 2>/dev/null; then
    echo "ERROR: Failed to create sync target directory"
    echo "  - Path: $SYNC_TARGET_DIR"
    echo "  - Check permissions and available disk space"
    exit 3
fi

# Verify target directory is writable
if [ ! -w "$SYNC_TARGET_DIR" ]; then
    echo "ERROR: Sync target directory is not writable"
    echo "  - Path: $SYNC_TARGET_DIR"
    echo "  - Current permissions:"
    ls -ld "$SYNC_TARGET_DIR"
    exit 3
fi

# Get available disk space
AVAILABLE_BYTES=$(df --output=avail -B1 "$SYNC_TARGET_DIR" 2>/dev/null | tail -1)

if [ -z "$AVAILABLE_BYTES" ]; then
    echo "ERROR: Could not determine available disk space"
    echo "  - Target directory: $SYNC_TARGET_DIR"
    echo "  - Check if filesystem is mounted correctly"
    exit 3
fi

AVAILABLE_GB=$((AVAILABLE_BYTES / 1024 / 1024 / 1024))
AVAILABLE_MB=$((AVAILABLE_BYTES / 1024 / 1024))

if [ $AVAILABLE_GB -gt 0 ]; then
    echo "Available disk space: ${AVAILABLE_GB}GB (${AVAILABLE_BYTES} bytes)"
else
    echo "Available disk space: ${AVAILABLE_MB}MB (${AVAILABLE_BYTES} bytes)"
fi

# Check if we have enough space (with 10% buffer)
if [ $REMOTE_SIZE_BYTES -gt 0 ]; then
    REQUIRED_BYTES=$((REMOTE_SIZE_BYTES + REMOTE_SIZE_BYTES / 10))
    REQUIRED_GB=$((REQUIRED_BYTES / 1024 / 1024 / 1024))
    REQUIRED_MB=$((REQUIRED_BYTES / 1024 / 1024))
    
    if [ $AVAILABLE_BYTES -lt $REQUIRED_BYTES ]; then
        echo ""
        echo "ERROR: Insufficient disk space for sync"
        echo ""
        if [ $REQUIRED_GB -gt 0 ]; then
            echo "Required: ${REQUIRED_GB}GB (with 10% buffer)"
        else
            echo "Required: ${REQUIRED_MB}MB (with 10% buffer)"
        fi
        echo "Available: ${AVAILABLE_GB}GB"
        echo "Shortfall: $(( (REQUIRED_BYTES - AVAILABLE_BYTES) / 1024 / 1024 / 1024 ))GB"
        echo ""
        echo "Solutions:"
        echo "  1. Increase container disk size"
        echo "  2. Use b2-mount instead of b2-sync (stores cache on network volume)"
        echo "  3. Reduce the size of your B2 bucket"
        echo "  4. Use B2_PATH to sync only a subdirectory"
        echo ""
        exit 3
    fi
    
    echo "✓ Sufficient disk space available"
    
    # Warn if space is tight (less than 20% free after sync)
    SPACE_AFTER_SYNC=$((AVAILABLE_BYTES - REMOTE_SIZE_BYTES))
    SPACE_AFTER_SYNC_PERCENT=$((SPACE_AFTER_SYNC * 100 / AVAILABLE_BYTES))
    
    if [ $SPACE_AFTER_SYNC_PERCENT -lt 20 ]; then
        echo "WARNING: Disk space will be tight after sync (${SPACE_AFTER_SYNC_PERCENT}% free)"
        echo "  - Consider increasing disk size for better performance"
        echo "  - ComfyUI outputs and temporary files also need space"
        echo ""
    fi
else
    echo "✓ Skipping disk space check (remote size unknown)"
fi

# Create sync target directory
echo "Creating sync target directory at $SYNC_TARGET..."
mkdir -p "$SYNC_TARGET"

# ============================================================================
# SYNC EXECUTION
# ============================================================================

# Start sync with progress logging
echo ""
echo "Starting sync from $REMOTE_PATH to $SYNC_TARGET..."
echo "This may take several minutes depending on the size of your model library."
echo ""

START_TIME=$(date +%s)

# Sync with parallel transfers and progress logging
SYNC_OUTPUT=$(rclone sync "$REMOTE_PATH" "$SYNC_TARGET" \
    --transfers 8 \
    --checkers 16 \
    --fast-list \
    --progress \
    --stats 10s \
    --stats-one-line \
    --log-level INFO \
    --log-file /tmp/rclone-sync.log 2>&1)

SYNC_EXIT_CODE=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

if [ $SYNC_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "ERROR: Sync failed with exit code $SYNC_EXIT_CODE"
    echo ""
    
    # Provide specific error messages based on common failure patterns
    if echo "$SYNC_OUTPUT" | grep -q "no space left"; then
        echo "Reason: Disk full during sync"
        echo "  - Ran out of disk space while downloading files"
        echo "  - Initial space check may have been inaccurate"
        echo "  - Some files may have been synced successfully"
        echo ""
        echo "Solutions:"
        echo "  1. Increase container disk size"
        echo "  2. Use b2-mount instead (doesn't require full sync)"
        echo "  3. Clean up existing files to free space"
    elif echo "$SYNC_OUTPUT" | grep -q "permission denied"; then
        echo "Reason: Permission denied"
        echo "  - Cannot write to sync target directory"
        echo "  - Check directory permissions"
        echo ""
        echo "Target directory permissions:"
        ls -ld "$SYNC_TARGET" 2>/dev/null || echo "  Directory does not exist"
    elif echo "$SYNC_OUTPUT" | grep -q "connection\|network\|timeout"; then
        echo "Reason: Network error during sync"
        echo "  - Connection to B2 was interrupted"
        echo "  - Some files may have been synced successfully"
        echo ""
        echo "Solutions:"
        echo "  1. Check network connectivity"
        echo "  2. Retry the sync (rclone will resume from where it left off)"
        echo "  3. Check if B2 service is experiencing issues"
    elif echo "$SYNC_OUTPUT" | grep -q "AccessDenied"; then
        echo "Reason: Access denied to some files"
        echo "  - Application key may not have permission to read all files"
        echo "  - Check B2 application key permissions"
    else
        echo "Reason: Unknown error"
        echo ""
        echo "Sync output:"
        echo "$SYNC_OUTPUT"
    fi
    
    echo ""
    echo "Diagnostic information:"
    echo "  - Sync duration: ${DURATION_MIN}m ${DURATION_SEC}s"
    echo "  - Full logs: /tmp/rclone-sync.log"
    echo ""
    echo "Recent log entries (last 30 lines):"
    if [ -f /tmp/rclone-sync.log ]; then
        tail -30 /tmp/rclone-sync.log
    else
        echo "  Log file not found"
    fi
    echo ""
    exit 4
fi

echo ""
echo "✓ Sync completed successfully"

# ============================================================================
# SYNC VERIFICATION AND STATISTICS
# ============================================================================

echo ""
echo "=== Sync Statistics ==="

# Verify sync target exists and is accessible
if [ ! -d "$SYNC_TARGET" ]; then
    echo "ERROR: Sync target directory does not exist after sync"
    echo "  - Expected: $SYNC_TARGET"
    echo "  - This should not happen - sync may have failed silently"
    exit 4
fi

# Count files in target directory
echo "Counting synced files..."
FILE_COUNT=$(find "$SYNC_TARGET" -type f 2>/dev/null | wc -l)

if [ $FILE_COUNT -eq 0 ]; then
    echo "WARNING: No files found in sync target directory"
    echo "  - Directory: $SYNC_TARGET"
    echo "  - This may indicate:"
    echo "    - B2 bucket is empty"
    echo "    - B2_PATH points to an empty subdirectory"
    echo "    - Sync completed but no files were transferred"
    echo ""
    echo "Checking B2 bucket contents..."
    REMOTE_FILE_COUNT=$(rclone lsf "$REMOTE_PATH" --recursive 2>/dev/null | wc -l)
    echo "  - Files in B2 bucket: $REMOTE_FILE_COUNT"
    
    if [ $REMOTE_FILE_COUNT -eq 0 ]; then
        echo "  - Bucket is empty - this is expected"
    else
        echo "  - WARNING: Bucket has files but none were synced"
        echo "  - Check /tmp/rclone-sync.log for details"
    fi
    echo ""
fi

echo "Files synced: $FILE_COUNT"

# Get total size of synced files
echo "Calculating total size..."
SYNCED_SIZE_BYTES=$(du -sb "$SYNC_TARGET" 2>/dev/null | cut -f1)

if [ -z "$SYNCED_SIZE_BYTES" ]; then
    echo "WARNING: Could not calculate synced size"
    SYNCED_SIZE_BYTES=0
fi

SYNCED_SIZE_GB=$((SYNCED_SIZE_BYTES / 1024 / 1024 / 1024))
SYNCED_SIZE_MB=$((SYNCED_SIZE_BYTES / 1024 / 1024))

if [ $SYNCED_SIZE_GB -gt 0 ]; then
    echo "Total size: ${SYNCED_SIZE_GB}GB (${SYNCED_SIZE_BYTES} bytes)"
else
    echo "Total size: ${SYNCED_SIZE_MB}MB (${SYNCED_SIZE_BYTES} bytes)"
fi

echo "Duration: ${DURATION_MIN}m ${DURATION_SEC}s"

# Calculate transfer speed
if [ $DURATION -gt 0 ] && [ $SYNCED_SIZE_BYTES -gt 0 ]; then
    SPEED_MBPS=$((SYNCED_SIZE_BYTES / DURATION / 1024 / 1024))
    echo "Average speed: ${SPEED_MBPS}MB/s"
fi

# Verify against expected size if we calculated it earlier
if [ $REMOTE_SIZE_BYTES -gt 0 ] && [ $SYNCED_SIZE_BYTES -gt 0 ]; then
    SIZE_DIFF=$((REMOTE_SIZE_BYTES - SYNCED_SIZE_BYTES))
    SIZE_DIFF_ABS=${SIZE_DIFF#-}  # Absolute value
    SIZE_DIFF_PERCENT=$((SIZE_DIFF_ABS * 100 / REMOTE_SIZE_BYTES))
    
    if [ $SIZE_DIFF_PERCENT -gt 5 ]; then
        echo ""
        echo "WARNING: Synced size differs from remote size by ${SIZE_DIFF_PERCENT}%"
        echo "  - Remote: ${REMOTE_SIZE_GB}GB"
        echo "  - Local: ${SYNCED_SIZE_GB}GB"
        echo "  - This may indicate an incomplete sync"
        echo "  - Check /tmp/rclone-sync.log for errors"
    fi
fi

# Check remaining disk space
REMAINING_BYTES=$(df --output=avail -B1 "$SYNC_TARGET" 2>/dev/null | tail -1)
REMAINING_GB=$((REMAINING_BYTES / 1024 / 1024 / 1024))

echo ""
echo "Remaining disk space: ${REMAINING_GB}GB"

if [ $REMAINING_GB -lt 5 ]; then
    echo "WARNING: Low disk space remaining (${REMAINING_GB}GB)"
    echo "  - ComfyUI needs space for outputs and temporary files"
    echo "  - Consider increasing disk size"
fi

echo ""
echo "=== B2 Sync Setup Complete ==="
echo "Models directory: $SYNC_TARGET"
echo "Sync logs: /tmp/rclone-sync.log"
echo ""

if [ $FILE_COUNT -gt 0 ]; then
    echo "✓ Sync successful - $FILE_COUNT files ready for use"
else
    echo "⚠ Sync completed but no files were transferred"
fi

echo ""

exit 0
