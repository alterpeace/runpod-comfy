# Storage Backend Migration Guide

This guide provides step-by-step instructions for migrating between different storage backends.

## Table of Contents

- [Migration Overview](#migration-overview)
- [From Network Volume to B2](#from-network-volume-to-b2)
- [From B2 Back to Network Volume](#from-b2-back-to-network-volume)
- [Switching Between B2 Mount and B2 Sync](#switching-between-b2-mount-and-b2-sync)
- [Hybrid Approach Migration](#hybrid-approach-migration)
- [Rollback Procedures](#rollback-procedures)
- [Troubleshooting](#troubleshooting)

## Migration Overview

### Storage Backend Options

| Backend | Storage Location | Cost | Performance | Migration Complexity |
|---------|-----------------|------|-------------|---------------------|
| **network-volume** | RunPod network volume | High | Fast | Low (default) |
| **b2-mount** | B2 + cache on network volume | Low | Medium | Medium |
| **b2-sync** | B2 synced to container disk | Low | Fast | Medium |
| **hybrid** | Docker image + B2 mount | Low | Fast (common models) | High |

### Migration Checklist

Before migrating, ensure you have:

- [ ] Backup of all models (or ability to re-download)
- [ ] B2 account created (if migrating to B2)
- [ ] B2 bucket created and configured
- [ ] B2 application keys generated
- [ ] Sufficient disk space for migration
- [ ] Downtime window scheduled (if needed)
- [ ] Rollback plan prepared

### Estimated Migration Times

| Library Size | Upload to B2 | Download from B2 | Sync Time |
|--------------|--------------|------------------|-----------|
| 10GB | 5-10 minutes | 2-5 minutes | 2-5 minutes |
| 50GB | 20-40 minutes | 10-20 minutes | 10-20 minutes |
| 100GB | 40-80 minutes | 20-40 minutes | 20-40 minutes |
| 200GB | 80-160 minutes | 40-80 minutes | 40-80 minutes |

*Times vary based on network speed and B2 region*

---

## From Network Volume to B2

This migration moves your models from RunPod network volumes to Backblaze B2 storage.

### Prerequisites

1. **Create B2 Account**
   - Sign up at https://www.backblaze.com/b2/cloud-storage.html
   - Verify email and complete account setup

2. **Create B2 Bucket**
   ```bash
   # Via B2 console:
   # 1. Click "Buckets" → "Create a Bucket"
   # 2. Name: my-comfyui-models
   # 3. Privacy: Private
   # 4. Region: Choose closest to RunPod deployment
   ```

3. **Generate Application Keys**
   ```bash
   # Via B2 console:
   # 1. Go to "App Keys"
   # 2. Click "Add a New Application Key"
   # 3. Name: comfyui-readwrite
   # 4. Bucket Access: Select your bucket
   # 5. Permissions: Read/Write (for initial upload)
   # 6. Copy keyID and applicationKey (shown only once!)
   ```

### Step 1: Verify Current Models

```bash
# SSH into your RunPod instance
ssh root@<runpod-ip>

# Check current model location and size
ls -lh /runpod-volume/models/
du -sh /runpod-volume/models/

# List all model files
find /runpod-volume/models/ -type f -name "*.safetensors" -o -name "*.ckpt"
```

### Step 2: Install rclone (if not in container)

```bash
# Install rclone
curl https://rclone.org/install.sh | bash

# Verify installation
rclone version
```

### Step 3: Configure rclone for B2

```bash
# Create rclone config directory
mkdir -p ~/.config/rclone

# Create rclone configuration
cat > ~/.config/rclone/rclone.conf <<EOF
[b2]
type = s3
provider = Other
env_auth = false
access_key_id = <your_B2_KEY_ID>
secret_access_key = <your_B2_APP_KEY>
endpoint = <your_B2_ENDPOINT>
region = <your_B2_REGION>
acl = private
EOF

# Test configuration
rclone lsd b2:<your_bucket_name>
```

### Step 4: Upload Models to B2

```bash
# Dry run (preview what will be uploaded)
rclone sync /runpod-volume/models/ b2:<your_bucket_name>/models \
  --dry-run \
  --progress

# Actual upload (this may take 30-60 minutes for 100GB)
rclone sync /runpod-volume/models/ b2:<your_bucket_name>/models \
  --progress \
  --transfers 8 \
  --checkers 16 \
  --stats 10s

# Verify upload
rclone ls b2:<your_bucket_name>/models | wc -l
rclone size b2:<your_bucket_name>/models
```

### Step 5: Update Environment Variables

```bash
# Edit .env file
nano /runpod-volume/.env

# Add B2 configuration
STORAGE_BACKEND=b2-mount  # or b2-sync
B2_BUCKET=<your_bucket_name>
B2_KEY_ID=<your_key_id>
B2_APP_KEY=<your_app_key>
B2_ENDPOINT=<your_endpoint>
B2_REGION=<your_region>
B2_PATH=models
RCLONE_CACHE_SIZE=50G  # Adjust based on needs

# Save and exit (Ctrl+X, Y, Enter)
```

### Step 6: Restart Container

```bash
# Using Docker Compose
docker-compose down
docker-compose up -d

# Or using RunPod API
# Stop and start pod via RunPod dashboard
```

### Step 7: Verify B2 Mount/Sync

```bash
# Check logs
docker-compose logs comfyui | grep -i "b2\|rclone\|storage"

# For b2-mount: Verify mount point
docker-compose exec comfyui mountpoint /comfyui/models
docker-compose exec comfyui ls -la /comfyui/models/

# For b2-sync: Verify synced files
docker-compose exec comfyui ls -la /comfyui/models/
docker-compose exec comfyui du -sh /comfyui/models/

# Test model access
docker-compose exec comfyui ls -lh /comfyui/models/checkpoints/
```

### Step 8: Test ComfyUI

```bash
# Access ComfyUI WebUI
# Load a workflow and verify models are accessible
# First access may be slow (downloading from B2)
# Subsequent access should be fast (cached)
```

### Step 9: Clean Up Network Volume (Optional)

```bash
# ONLY after verifying B2 is working correctly!
# This frees up network volume space

# Backup first (just in case)
rclone sync /runpod-volume/models/ /runpod-volume/models-backup/ --progress

# Remove models from network volume
rm -rf /runpod-volume/models/*

# Keep cache directory (for b2-mount)
mkdir -p /runpod-volume/rclone-cache
```

### Step 10: Monitor Performance

```bash
# Monitor cache usage (for b2-mount)
watch -n 5 'du -sh /runpod-volume/rclone-cache'

# Monitor rclone logs
tail -f /tmp/rclone-mount.log  # for b2-mount
tail -f /tmp/rclone-sync.log   # for b2-sync

# Check model access times
time docker-compose exec comfyui ls /comfyui/models/checkpoints/
```

---

## From B2 Back to Network Volume

This migration moves your models from Backblaze B2 back to RunPod network volumes.

### When to Migrate Back

- B2 performance is insufficient for your workload
- Network volume costs are acceptable
- You need absolute minimum latency
- B2 connectivity issues

### Step 1: Verify Network Volume Space

```bash
# Check available space on network volume
df -h /runpod-volume/

# Calculate required space
rclone size b2:<your_bucket_name>/models

# Ensure you have enough space (model size + 10GB buffer)
```

### Step 2: Download Models from B2

```bash
# Create models directory on network volume
mkdir -p /runpod-volume/models

# Dry run (preview what will be downloaded)
rclone sync b2:<your_bucket_name>/models /runpod-volume/models \
  --dry-run \
  --progress

# Actual download (this may take 20-40 minutes for 100GB)
rclone sync b2:<your_bucket_name>/models /runpod-volume/models \
  --progress \
  --transfers 8 \
  --checkers 16 \
  --stats 10s

# Verify download
du -sh /runpod-volume/models/
find /runpod-volume/models/ -type f | wc -l
```

### Step 3: Update Environment Variables

```bash
# Edit .env file
nano /runpod-volume/.env

# Change storage backend to network-volume
STORAGE_BACKEND=network-volume

# Comment out or remove B2 configuration
# B2_BUCKET=...
# B2_KEY_ID=...
# B2_APP_KEY=...
# B2_ENDPOINT=...
# B2_REGION=...
# B2_PATH=...
# RCLONE_CACHE_SIZE=...

# Save and exit (Ctrl+X, Y, Enter)
```

### Step 4: Restart Container

```bash
# Using Docker Compose
docker-compose down
docker-compose up -d

# Or using RunPod API
# Stop and start pod via RunPod dashboard
```

### Step 5: Verify Network Volume Usage

```bash
# Check logs
docker-compose logs comfyui | grep -i "storage"

# Verify models are accessible
docker-compose exec comfyui ls -la /runpod-volume/models/
docker-compose exec comfyui ls -lh /runpod-volume/models/checkpoints/

# Test model access
time docker-compose exec comfyui ls /runpod-volume/models/checkpoints/
```

### Step 6: Test ComfyUI

```bash
# Access ComfyUI WebUI
# Load a workflow and verify models are accessible
# Access should be instant (local network volume)
```

### Step 7: Clean Up B2 (Optional)

```bash
# ONLY after verifying network volume is working correctly!
# This stops B2 storage costs

# Option 1: Delete all files but keep bucket
rclone delete b2:<your_bucket_name>/models --progress

# Option 2: Delete entire bucket (via B2 console)
# 1. Go to B2 console
# 2. Select bucket
# 3. Click "Delete Bucket"
# 4. Confirm deletion

# Option 3: Keep B2 as backup (recommended)
# Leave files in B2 for disaster recovery
```

### Step 8: Clean Up rclone Cache

```bash
# Remove rclone cache directory (frees up network volume space)
rm -rf /runpod-volume/rclone-cache

# Remove rclone config
rm -rf ~/.config/rclone/
```

---

## Switching Between B2 Mount and B2 Sync

This migration switches between b2-mount and b2-sync without re-uploading to B2.

### From B2 Mount to B2 Sync

**When to switch:**
- You need better performance (local disk access)
- You have sufficient container disk space
- You can tolerate startup sync time

**Steps:**

```bash
# 1. Check container disk space
df -h /comfyui/models/
rclone size b2:<your_bucket_name>/models

# 2. Ensure sufficient space (model size + 10GB buffer)

# 3. Update .env file
nano /runpod-volume/.env

# Change storage backend
STORAGE_BACKEND=b2-sync

# Remove mount-specific config
# RCLONE_CACHE_SIZE=...
# RCLONE_CACHE_MAX_AGE=...

# 4. Restart container
docker-compose down
docker-compose up -d

# 5. Monitor sync progress
docker-compose logs -f comfyui | grep -i "sync\|rclone"

# 6. Verify synced files
docker-compose exec comfyui ls -la /comfyui/models/
docker-compose exec comfyui du -sh /comfyui/models/

# 7. Optional: Clean up mount cache
rm -rf /runpod-volume/rclone-cache
```

### From B2 Sync to B2 Mount

**When to switch:**
- You need faster startup (no sync wait)
- You have limited container disk space
- You want to use network volume for cache

**Steps:**

```bash
# 1. Update .env file
nano /runpod-volume/.env

# Change storage backend
STORAGE_BACKEND=b2-mount

# Add mount-specific config
RCLONE_CACHE_SIZE=50G
RCLONE_CACHE_MAX_AGE=24h

# 2. Restart container
docker-compose down
docker-compose up -d

# 3. Verify mount
docker-compose exec comfyui mountpoint /comfyui/models
docker-compose exec comfyui ls -la /comfyui/models/

# 4. Optional: Remove synced files (frees container disk)
# ONLY after verifying mount is working!
docker-compose exec comfyui rm -rf /comfyui/models/*
# Note: Files will be re-downloaded on access (cached)
```

---

## Hybrid Approach Migration

This migration implements a hybrid strategy with baked models + B2 mount.

### Prerequisites

- Identify frequently-used models (top 5-10)
- Have models available locally for Docker build
- Can rebuild Docker image

### Step 1: Analyze Model Usage

```bash
# Check ComfyUI logs for model usage
docker-compose logs comfyui | grep -i "loading model" | sort | uniq -c | sort -rn

# Identify top 5-10 most-used models
# Example output:
#   45 Loading model: sd_xl_base_1.0.safetensors
#   32 Loading model: sd_v1-5-pruned.safetensors
#   18 Loading model: popular_lora_v1.safetensors
```

### Step 2: Prepare Models for Baking

```bash
# Create models directory in project
mkdir -p models/checkpoints
mkdir -p models/loras
mkdir -p models/vae

# Copy frequently-used models
cp /runpod-volume/models/checkpoints/sd_xl_base_1.0.safetensors \
   models/checkpoints/
cp /runpod-volume/models/checkpoints/sd_v1-5-pruned.safetensors \
   models/checkpoints/
cp /runpod-volume/models/loras/popular_lora_v1.safetensors \
   models/loras/

# Verify files
ls -lh models/checkpoints/
ls -lh models/loras/
```

### Step 3: Modify Dockerfile

```bash
# Edit Dockerfile
nano Dockerfile

# Add after ComfyUI installation, before entrypoint:
```

```dockerfile
# Bake frequently-used models into image
# This increases image size but provides instant access
COPY models/checkpoints/sd_xl_base_1.0.safetensors \
     /comfyui/models/checkpoints/
COPY models/checkpoints/sd_v1-5-pruned.safetensors \
     /comfyui/models/checkpoints/
COPY models/loras/popular_lora_v1.safetensors \
     /comfyui/models/loras/
```

### Step 4: Upload Full Library to B2

```bash
# Upload all models to B2 (if not already done)
rclone sync /runpod-volume/models/ b2:<your_bucket_name>/models \
  --progress \
  --transfers 8

# Verify upload
rclone size b2:<your_bucket_name>/models
```

### Step 5: Update Environment Variables

```bash
# Edit .env file
nano /runpod-volume/.env

# Configure B2 mount for remaining models
STORAGE_BACKEND=b2-mount
B2_BUCKET=<your_bucket_name>
B2_KEY_ID=<your_key_id>
B2_APP_KEY=<your_app_key>
B2_ENDPOINT=<your_endpoint>
B2_REGION=<your_region>
B2_PATH=models

# Smaller cache size (common models are baked)
RCLONE_CACHE_SIZE=50G
RCLONE_CACHE_MAX_AGE=24h
```

### Step 6: Rebuild Docker Image

```bash
# Build new image with baked models
docker-compose build

# Or using build script
./build.sh

# Verify image size
docker images | grep comfyui
# Note: Image will be 20-50GB larger
```

### Step 7: Deploy New Image

```bash
# Stop old container
docker-compose down

# Start new container with baked models
docker-compose up -d

# Check logs
docker-compose logs -f comfyui
```

### Step 8: Verify Hybrid Setup

```bash
# Check baked models (should be instant)
docker-compose exec comfyui ls -lh /comfyui/models/checkpoints/

# Check B2 mount (should show all models)
docker-compose exec comfyui ls -lh /comfyui/models/

# Test baked model access (instant)
time docker-compose exec comfyui cat /comfyui/models/checkpoints/sd_xl_base_1.0.safetensors > /dev/null

# Test B2-mounted model access (first time: slow, cached: fast)
time docker-compose exec comfyui cat /comfyui/models/checkpoints/rare_model.safetensors > /dev/null
```

### Step 9: Monitor Performance

```bash
# Monitor cache usage
watch -n 5 'du -sh /runpod-volume/rclone-cache'

# Check which models are accessed
docker-compose logs comfyui | grep -i "loading model"

# Verify baked models are used first
# (should not see download logs for baked models)
```

### Step 10: Update Baked Models Periodically

```bash
# Quarterly or when usage patterns change:
# 1. Analyze model usage again
# 2. Update models/ directory with new top models
# 3. Rebuild Docker image
# 4. Deploy new image
```

---

## Rollback Procedures

### Quick Rollback (Emergency)

If migration fails and you need to restore service immediately:

```bash
# 1. Revert .env changes
nano /runpod-volume/.env
# Change STORAGE_BACKEND back to previous value

# 2. Restart container
docker-compose down
docker-compose up -d

# 3. Verify service is restored
docker-compose logs comfyui
curl http://localhost:8188/
```

### Full Rollback (With Data Restore)

If you need to restore from backup:

```bash
# 1. Stop container
docker-compose down

# 2. Restore models from backup
rclone sync /runpod-volume/models-backup/ /runpod-volume/models/ --progress

# Or restore from B2
rclone sync b2:<your_bucket_name>/models /runpod-volume/models --progress

# 3. Revert .env changes
nano /runpod-volume/.env
STORAGE_BACKEND=network-volume

# 4. Restart container
docker-compose up -d

# 5. Verify restoration
docker-compose exec comfyui ls -la /runpod-volume/models/
```

### Rollback Docker Image (Hybrid)

If hybrid approach causes issues:

```bash
# 1. Revert Dockerfile changes
git checkout Dockerfile

# 2. Rebuild image
docker-compose build

# 3. Deploy reverted image
docker-compose down
docker-compose up -d

# 4. Or use previous image tag
docker-compose down
docker pull <your-registry>/comfyui:<previous-tag>
docker-compose up -d
```

---

## Troubleshooting

### Migration Fails: Upload to B2 Stalls

**Symptoms:**
- rclone sync hangs or stops progressing
- Upload speed drops to zero

**Solutions:**

```bash
# 1. Check network connectivity
ping 8.8.8.8
ping s3.us-west-004.backblazeb2.com

# 2. Reduce parallel transfers
rclone sync /runpod-volume/models/ b2:<bucket>/models \
  --progress \
  --transfers 4 \
  --checkers 8

# 3. Resume interrupted upload
# rclone automatically resumes from where it left off
rclone sync /runpod-volume/models/ b2:<bucket>/models --progress

# 4. Check B2 service status
# Visit https://status.backblaze.com
```

### Migration Fails: Insufficient Disk Space

**Symptoms:**
- "No space left on device" error
- Sync fails partway through

**Solutions:**

```bash
# 1. Check available space
df -h

# 2. Clean up temporary files
rm -rf /tmp/*
docker system prune -a

# 3. Increase container disk size (RunPod dashboard)

# 4. Use b2-mount instead of b2-sync
# (stores cache on network volume, not container disk)
STORAGE_BACKEND=b2-mount

# 5. Partial migration: sync only essential models
rclone sync /runpod-volume/models/checkpoints/ b2:<bucket>/models/checkpoints/ --progress
```

### Migration Fails: B2 Credentials Invalid

**Symptoms:**
- "Access denied" error
- "Invalid access key" error

**Solutions:**

```bash
# 1. Verify credentials in B2 console
# App Keys section

# 2. Check for extra spaces/newlines
echo "$B2_KEY_ID" | cat -A
echo "$B2_APP_KEY" | cat -A

# 3. Regenerate application keys
# B2 console → App Keys → Add New Key

# 4. Test credentials manually
rclone lsd b2:<bucket> -vv

# 5. Verify bucket permissions
# Ensure key has access to specified bucket
```

### Post-Migration: Models Not Accessible

**Symptoms:**
- ComfyUI can't find models
- Empty model list in WebUI

**Solutions:**

```bash
# 1. Check mount point (for b2-mount)
docker-compose exec comfyui mountpoint /comfyui/models
docker-compose exec comfyui ls -la /comfyui/models/

# 2. Check sync status (for b2-sync)
docker-compose logs comfyui | grep -i "sync"
docker-compose exec comfyui ls -la /comfyui/models/

# 3. Verify B2 configuration
docker-compose exec comfyui env | grep B2_

# 4. Check rclone logs
docker-compose exec comfyui cat /tmp/rclone-mount.log
docker-compose exec comfyui cat /tmp/rclone-sync.log

# 5. Restart container
docker-compose restart comfyui
```

### Post-Migration: Slow Performance

**Symptoms:**
- Models take minutes to load
- High latency on model access

**Solutions:**

```bash
# 1. Check cache size (for b2-mount)
du -sh /runpod-volume/rclone-cache
# Increase if too small:
RCLONE_CACHE_SIZE=100G

# 2. Pre-warm cache
docker-compose exec comfyui ls -R /comfyui/models/

# 3. Monitor cache hit rate
docker-compose exec comfyui rclone rc vfs/stats

# 4. Consider switching to b2-sync for better performance
STORAGE_BACKEND=b2-sync

# 5. Implement hybrid approach
# Bake frequently-used models into Docker image
```

### Post-Migration: High B2 Costs

**Symptoms:**
- Unexpected egress charges
- Higher than expected monthly bill

**Solutions:**

```bash
# 1. Check egress usage in B2 console
# Billing → Usage

# 2. Configure Cloudflare for free egress
# B2 console → Buckets → Cloudflare Settings

# 3. Reduce container restarts (for b2-sync)
# Each restart triggers full sync

# 4. Use b2-mount instead of b2-sync
# Only downloads files on first access

# 5. Implement caching strategy
# Increase RCLONE_CACHE_SIZE to reduce re-downloads
```

---

## Best Practices

### Before Migration

1. **Backup everything**
   - Models on network volume
   - Environment configuration
   - Docker images

2. **Test in development first**
   - Use separate B2 bucket for testing
   - Verify performance with test workloads

3. **Schedule downtime**
   - Inform users of maintenance window
   - Plan for migration duration

4. **Document current state**
   - Model inventory
   - Disk usage
   - Performance baselines

### During Migration

1. **Monitor progress**
   - Watch rclone logs
   - Check disk space
   - Verify upload/download speeds

2. **Validate each step**
   - Don't skip verification steps
   - Test before proceeding

3. **Keep rollback option ready**
   - Don't delete old data immediately
   - Keep previous configuration

### After Migration

1. **Monitor performance**
   - Model load times
   - Cache hit rates
   - User experience

2. **Optimize configuration**
   - Adjust cache sizes
   - Tune rclone parameters

3. **Document changes**
   - Update runbooks
   - Share learnings with team

4. **Clean up after verification**
   - Remove old data (after 1-2 weeks)
   - Delete unused resources

---

## Support

For migration assistance:

1. **Check logs first**
   ```bash
   docker-compose logs comfyui
   cat /tmp/rclone-mount.log
   cat /tmp/rclone-sync.log
   ```

2. **Review troubleshooting section**
   - Common issues and solutions above

3. **Test B2 connectivity**
   ```bash
   rclone lsd b2:<bucket> -vv
   ```

4. **Open an issue**
   - Include error messages (redact credentials)
   - Include relevant logs
   - Describe migration steps taken

5. **Contact support**
   - RunPod support for infrastructure
   - Backblaze support for B2 issues
   - rclone forum for rclone issues
