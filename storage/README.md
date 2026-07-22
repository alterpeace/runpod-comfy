# Storage Backend Documentation

This directory contains scripts and tools for managing different storage backends for ComfyUI models and assets.

## Overview

The RunPod serverless ComfyUI deployment supports three storage backend options:

1. **Network Volume** (default) - RunPod network volumes
2. **B2 Mount** - Backblaze B2 mounted as filesystem via rclone
3. **B2 Sync** - Backblaze B2 synced to local storage on boot

## Storage Backend Comparison

| Backend | Cost | Performance | Use Case |
|---------|------|-------------|----------|
| **network-volume** | ~$100/TB/month | Fast (local network) | Small libraries (<50GB), maximum performance |
| **b2-mount** | ~$5/TB/month | Medium (network + cache) | Large libraries (100GB+), infrequent access |
| **b2-sync** | ~$5/TB/month + egress | Fast (local after sync) | Maximum performance with cost savings |

### Cost Examples

**50GB Model Library:**
- Network Volume: $5/month
- B2: $0.25/month
- **Savings: $4.75/month (95%)**

**200GB Model Library:**
- Network Volume: $20/month
- B2: $1/month
- **Savings: $19/month (95%)**

**1TB Model Library:**
- Network Volume: $100/month
- B2: $5/month
- **Savings: $95/month (95%)**

## Configuration

### Option 1: Network Volume (Default)

No additional configuration needed. This is the existing behavior.

```bash
STORAGE_BACKEND=network-volume
```

Models are stored in `/runpod-volume/models/` on the RunPod network volume.

### Option 2: B2 Mount with rclone

Mount Backblaze B2 storage as a filesystem with aggressive caching.

**Configuration:**

```bash
# Storage backend
STORAGE_BACKEND=b2-mount

# B2 credentials
B2_BUCKET=my-comfyui-models
B2_KEY_ID=your_key_id_here
B2_APP_KEY=your_app_key_here
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_PATH=models  # Optional subdirectory

# Cache configuration
RCLONE_CACHE_SIZE=20G  # Adjust based on needs
RCLONE_CACHE_MAX_AGE=24h
```

**Cache Size Recommendations:**
- SD 1.5 models: 20G
- SDXL models: 50G
- FLUX models: 100G+

**How it works:**
1. Container starts and validates B2 credentials
2. rclone mounts B2 bucket to `/comfyui/models`
3. Files are cached on network volume at `/runpod-volume/rclone-cache`
4. First access downloads from B2, subsequent access is instant (cached)
5. Cache persists across container restarts

**Performance:**
- Cold start (first access): 30-60s for 5GB model
- Warm start (cached): Instant, equivalent to local disk
- Cache hit rate: Typically >95% after initial warmup

### Option 3: B2 Sync on Boot

Sync B2 bucket contents to local storage on container startup.

**Configuration:**

```bash
# Storage backend
STORAGE_BACKEND=b2-sync

# B2 credentials
B2_BUCKET=my-comfyui-models
B2_KEY_ID=your_key_id_here
B2_APP_KEY=your_app_key_here
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_PATH=models  # Optional subdirectory
```

**How it works:**
1. Container starts and validates B2 credentials
2. rclone syncs B2 bucket to `/comfyui/models`
3. Only changed files are downloaded (checksum-based)
4. ComfyUI starts after sync completes
5. All model access is local (no network latency)

**Performance:**
- Initial sync time (depends on library size):
  - 10GB: 2-5 minutes
  - 50GB: 10-20 minutes
  - 100GB: 20-40 minutes
- Subsequent syncs: <1 minute (only changed files)
- Runtime: Equivalent to local disk

## Setting Up Backblaze B2

### 1. Create B2 Account

1. Go to https://www.backblaze.com/b2/cloud-storage.html
2. Sign up for a B2 account (free tier: 10GB storage, 1GB/day egress)
3. Verify your email and complete account setup

### 2. Create Bucket

1. Log in to B2 console
2. Click "Buckets" → "Create a Bucket"
3. Choose a unique bucket name (e.g., `my-comfyui-models`)
4. Select "Private" for bucket privacy
5. Choose a region close to your RunPod deployment
6. Click "Create a Bucket"

### 3. Generate Application Keys

1. Go to "App Keys" in B2 console
2. Click "Add a New Application Key"
3. Name: `comfyui-readonly` (for production) or `comfyui-readwrite` (for development)
4. Bucket Access: Select your bucket
5. Permissions:
   - **Production**: Read-only (listBuckets, listFiles, readFiles)
   - **Development**: Read/Write (add writeFiles, deleteFiles)
6. Click "Create New Key"
7. **Important**: Copy the `keyID` and `applicationKey` immediately (shown only once)

### 4. Get S3 Endpoint

1. In B2 console, go to "Buckets"
2. Click on your bucket
3. Find "Endpoint" in bucket details
4. Format: `s3.<region>.backblazeb2.com`
5. Example: `s3.us-west-004.backblazeb2.com`

### 5. Configure Environment Variables

Add to your `.env` file:

```bash
STORAGE_BACKEND=b2-mount  # or b2-sync
B2_BUCKET=my-comfyui-models
B2_KEY_ID=<keyID from step 3>
B2_APP_KEY=<applicationKey from step 3>
B2_ENDPOINT=<endpoint from step 4>
B2_REGION=us-west-004
RCLONE_CACHE_SIZE=50G  # Adjust based on needs
```

## Uploading Models to B2

### Using rclone (Recommended)

```bash
# Install rclone
curl https://rclone.org/install.sh | bash

# Configure rclone with B2 credentials
rclone config

# Upload models directory
rclone sync ./models b2:my-comfyui-models/models --progress

# Upload specific subdirectory
rclone sync ./models/checkpoints b2:my-comfyui-models/models/checkpoints --progress
```

### Using B2 Web Interface

1. Log in to B2 console
2. Go to "Buckets" → Select your bucket
3. Click "Upload/Download"
4. Drag and drop files or click "Upload"
5. Wait for upload to complete

### Using upload_to_b2.py Script

```bash
# Upload all models
python storage/upload_to_b2.py --local ./models --bucket my-comfyui-models

# Upload specific subdirectory
python storage/upload_to_b2.py --local ./models/checkpoints --bucket my-comfyui-models --remote checkpoints

# Skip existing files
python storage/upload_to_b2.py --local ./models --bucket my-comfyui-models --skip-existing
```

## Managing B2 Storage

### List Bucket Contents

```bash
# Using rclone
rclone ls b2:my-comfyui-models

# Using manage_b2.py
python storage/manage_b2.py list --bucket my-comfyui-models
```

### Calculate Storage Costs

```bash
python storage/manage_b2.py size --bucket my-comfyui-models
```

### Clean Old Files

```bash
# Remove files older than 90 days
python storage/manage_b2.py clean --bucket my-comfyui-models --older-than 90d

# Remove files matching pattern
python storage/manage_b2.py clean --bucket my-comfyui-models --pattern "*.tmp"
```

### Verify Checksums

```bash
python storage/manage_b2.py verify --bucket my-comfyui-models --local ./models
```

## Performance Tuning

### Cache Size Optimization

The cache size determines how many models can be stored locally for instant access.

**Recommendations by model type:**
- **SD 1.5**: 20G (stores ~4-5 models)
- **SDXL**: 50G (stores ~8-10 models)
- **FLUX**: 100G+ (stores ~4-5 models)

**Setting cache size:**

```bash
RCLONE_CACHE_SIZE=100G  # For FLUX models
```

**Cache location:**
- Stored on network volume at `/runpod-volume/rclone-cache`
- Persists across container restarts
- Automatically managed by rclone (LRU eviction)

### Network Optimization

**For b2-mount:**
- Increase buffer size for faster downloads
- Increase read-ahead for sequential access
- Disable polling for static content

**For b2-sync:**
- Increase parallel transfers for faster sync
- Use fast-list for large directories
- Enable progress logging

### Hybrid Strategy

For optimal cost and performance, use a hybrid approach:

1. **Bake common models into Docker image**
   - Top 5-10 most-used models
   - Included in image build
   - Always available instantly

2. **Mount B2 for full library**
   - Less common models
   - On-demand access
   - Cost-effective storage

3. **ComfyUI checks local first**
   - Prefers baked-in models
   - Falls back to B2 mount
   - Transparent to users

## Troubleshooting

### Common Error Messages

The setup scripts provide detailed error messages to help diagnose issues. Below are common errors and their solutions.

#### Missing Environment Variables

**Error Message:**
```
ERROR: Missing required B2 environment variables
Missing variables: B2_BUCKET B2_KEY_ID
```

**Cause:** Required B2 configuration variables are not set.

**Solution:**
1. Check your `.env` file exists and contains all required variables
2. Verify `.env` is in the correct location (`/runpod-volume/.env` or `/workspace/.env`)
3. Ensure variables are exported: `source .env`
4. Required variables: `B2_BUCKET`, `B2_KEY_ID`, `B2_APP_KEY`, `B2_ENDPOINT`

#### Invalid Credentials

**Error Message:**
```
ERROR: Failed to connect to B2 bucket
Reason: Invalid access key ID
```

**Cause:** B2_KEY_ID is not recognized by Backblaze.

**Solution:**
1. Verify key ID in B2 console (App Keys section)
2. Ensure you copied the entire key ID (no spaces or newlines)
3. Check you're using an application key, not the master key
4. Regenerate key if necessary

**Error Message:**
```
ERROR: Failed to connect to B2 bucket
Reason: Invalid application key
```

**Cause:** B2_APP_KEY does not match the key ID.

**Solution:**
1. Verify application key in B2 console
2. Check for extra spaces or newlines in the key
3. Ensure key hasn't been deleted or rotated
4. Regenerate key pair if necessary

#### Bucket Not Found

**Error Message:**
```
ERROR: Failed to connect to B2 bucket
Reason: Bucket does not exist
```

**Cause:** Specified bucket doesn't exist in your B2 account.

**Solution:**
1. Verify bucket name in B2 console (Buckets section)
2. Check for typos in `B2_BUCKET` variable
3. Ensure bucket is in the correct B2 account
4. Create bucket if it doesn't exist

#### Access Denied

**Error Message:**
```
ERROR: Failed to connect to B2 bucket
Reason: Access denied
```

**Cause:** Application key doesn't have permission to access the bucket.

**Solution:**
1. Check application key permissions in B2 console
2. Ensure key has at least `listBuckets` and `listFiles` permissions
3. Verify key is not restricted to a different bucket
4. Create new key with correct permissions

#### Network Connectivity Issues

**Error Message:**
```
ERROR: Failed to connect to B2 bucket
Reason: Network connectivity issue
```

**Cause:** Cannot reach B2 endpoint.

**Solution:**
1. Check internet connection: `ping 8.8.8.8`
2. Verify endpoint URL: `ping s3.us-west-004.backblazeb2.com`
3. Check firewall rules (allow outbound HTTPS)
4. Verify DNS resolution: `nslookup s3.us-west-004.backblazeb2.com`
5. Check if B2 service is experiencing issues: https://status.backblaze.com

#### Network Volume Not Found

**Error Message:**
```
ERROR: Network volume not found at /runpod-volume
```

**Cause:** Network volume is not mounted or doesn't exist.

**Solution:**
1. Verify network volume is attached in RunPod dashboard
2. Check mount point: `ls -la /runpod-volume`
3. For local development: `mkdir -p /runpod-volume`
4. Restart container if volume was just attached
5. Check RunPod network volume status

#### Network Volume Not Writable

**Error Message:**
```
ERROR: Network volume at /runpod-volume is not writable
```

**Cause:** Insufficient permissions or read-only mount.

**Solution:**
1. Check permissions: `ls -ld /runpod-volume`
2. Verify mount is not read-only: `mount | grep runpod-volume`
3. Check filesystem errors: `dmesg | tail -50`
4. Contact RunPod support if issue persists

#### Insufficient Disk Space (Sync)

**Error Message:**
```
ERROR: Insufficient disk space for sync
Required: 50GB (with 10% buffer)
Available: 30GB
```

**Cause:** Not enough disk space to sync B2 bucket contents.

**Solution:**
1. Increase container disk size in RunPod dashboard
2. Use `b2-mount` instead (stores cache on network volume)
3. Reduce B2 bucket size (remove unused models)
4. Use `B2_PATH` to sync only a subdirectory
5. Clean up existing files: `docker system prune -a`

#### Mount Failed - FUSE Not Available

**Error Message:**
```
ERROR: Failed to mount B2 bucket
Reason: FUSE not available or not configured
```

**Cause:** FUSE kernel module is not available.

**Solution:**
1. Verify FUSE is installed: `which fusermount`
2. Check `/dev/fuse` exists: `ls -l /dev/fuse`
3. For Docker: Add `--device /dev/fuse` or `--privileged` flag
4. For RunPod: Contact support (should be available by default)
5. Rebuild image with FUSE: `apt-get install -y fuse`

#### Mount Failed - Permission Denied

**Error Message:**
```
ERROR: Failed to mount B2 bucket
Reason: Permission denied
```

**Cause:** Insufficient permissions to create mount.

**Solution:**
1. Check mount point permissions: `ls -ld /comfyui/models`
2. Verify user has mount permissions
3. Try with elevated privileges (if safe)
4. Check SELinux/AppArmor policies

#### Mount Failed - Already Mounted

**Error Message:**
```
ERROR: Failed to mount B2 bucket
Reason: Mount point already in use
```

**Cause:** Another process is using the mount point.

**Solution:**
1. Check existing mounts: `mount | grep rclone`
2. Unmount stale mount: `fusermount -u /comfyui/models`
3. Kill rclone processes: `pkill -f "rclone mount"`
4. Restart container

#### Mount Verification Failed

**Error Message:**
```
ERROR: Mount verification failed after 30s
Mount point is not accessible or not responding
```

**Cause:** Mount command succeeded but mount is not functional.

**Solution:**
1. Check rclone logs: `cat /tmp/rclone-mount.log`
2. Verify rclone process: `ps aux | grep rclone`
3. Test mount manually: `ls /comfyui/models`
4. Check system logs: `dmesg | tail -50`
5. Increase timeout if slow connection

#### Sync Failed - Disk Full

**Error Message:**
```
ERROR: Sync failed with exit code 4
Reason: Disk full during sync
```

**Cause:** Ran out of disk space while downloading files.

**Solution:**
1. Check disk space: `df -h`
2. Increase container disk size
3. Clean up temporary files: `rm -rf /tmp/*`
4. Use `b2-mount` instead (doesn't require full sync)
5. Partial sync may have succeeded - check `/comfyui/models`

#### Sync Failed - Network Error

**Error Message:**
```
ERROR: Sync failed with exit code 4
Reason: Network error during sync
```

**Cause:** Connection to B2 was interrupted.

**Solution:**
1. Check network connectivity: `ping 8.8.8.8`
2. Retry sync (rclone will resume from where it left off)
3. Check B2 service status: https://status.backblaze.com
4. Reduce parallel transfers: `--transfers 4`
5. Check firewall/proxy settings

### Performance Issues

#### Slow Model Loading (Mount)

**Symptom:** Models take 30+ seconds to load with b2-mount.

**Possible causes:**
1. First access (downloading from B2)
2. Cache size too small
3. Network latency
4. Cache not on network volume

**Solutions:**
```bash
# Increase cache size
RCLONE_CACHE_SIZE=100G

# Verify cache location (should be on network volume)
ls -la /runpod-volume/rclone-cache

# Check cache usage
du -sh /runpod-volume/rclone-cache

# Monitor rclone logs
tail -f /tmp/rclone-mount.log

# Pre-warm cache by accessing models
ls -R /comfyui/models
```

#### Slow Sync Times

**Symptom:** Sync takes longer than expected.

**Possible causes:**
1. Large model library
2. Slow network connection
3. B2 rate limiting

**Solutions:**
```bash
# Check sync progress
tail -f /tmp/rclone-sync.log

# Increase parallel transfers (if network allows)
# Edit setup_b2_sync.sh: --transfers 16

# Use fast-list for large directories (already enabled)

# Check network speed
curl -o /dev/null http://speedtest.tele2.net/100MB.zip
```

#### Cache Not Working

**Symptom:** Every model access downloads from B2.

**Possible causes:**
1. Cache directory not on network volume
2. Cache size too small
3. Cache being evicted too quickly

**Solutions:**
```bash
# Verify cache location
echo $RCLONE_CACHE_DIR
ls -la /runpod-volume/rclone-cache

# Check cache size
du -sh /runpod-volume/rclone-cache

# Increase cache size
RCLONE_CACHE_SIZE=100G

# Increase cache max age
RCLONE_CACHE_MAX_AGE=72h

# Check rclone cache stats
rclone rc vfs/stats
```

### Diagnostic Commands

#### Check B2 Connectivity

```bash
# Test basic connectivity
rclone lsd b2:my-comfyui-models

# List bucket contents
rclone ls b2:my-comfyui-models

# Check bucket size
rclone size b2:my-comfyui-models

# Test download speed
rclone copy b2:my-comfyui-models/test.txt /tmp/ -P
```

#### Check Mount Status

```bash
# Verify mount point
mountpoint /comfyui/models

# List mounted filesystems
mount | grep rclone

# Check rclone process
ps aux | grep rclone

# View rclone logs
tail -f /tmp/rclone-mount.log

# Test mount access
ls -la /comfyui/models
```

#### Check Disk Space

```bash
# Check all filesystems
df -h

# Check specific directory
df -h /comfyui/models

# Check network volume
df -h /runpod-volume

# Check cache usage
du -sh /runpod-volume/rclone-cache

# Find large files
find /comfyui/models -type f -size +1G -exec ls -lh {} \;
```

#### Check Network

```bash
# Test internet connectivity
ping -c 4 8.8.8.8

# Test B2 endpoint
ping -c 4 s3.us-west-004.backblazeb2.com

# Test DNS resolution
nslookup s3.us-west-004.backblazeb2.com

# Check network speed
curl -o /dev/null http://speedtest.tele2.net/100MB.zip

# Check firewall rules
iptables -L -n
```

#### View Logs

```bash
# rclone mount logs
cat /tmp/rclone-mount.log
tail -f /tmp/rclone-mount.log

# rclone sync logs
cat /tmp/rclone-sync.log
tail -f /tmp/rclone-sync.log

# Container logs
docker-compose logs comfyui
docker-compose logs -f comfyui

# System logs
dmesg | tail -50
journalctl -xe
```

### Getting Help

If you're still experiencing issues after trying the above solutions:

1. **Gather diagnostic information:**
   ```bash
   # Save logs
   cat /tmp/rclone-mount.log > rclone-debug.log
   cat /tmp/rclone-sync.log >> rclone-debug.log
   
   # Save configuration (redact credentials!)
   env | grep B2_ | sed 's/=.*/=REDACTED/' > config-debug.txt
   
   # Save system info
   df -h > system-debug.txt
   mount >> system-debug.txt
   ps aux | grep rclone >> system-debug.txt
   ```

2. **Test B2 connectivity manually:**
   ```bash
   rclone lsd b2:my-comfyui-models -vv
   ```

3. **Check B2 service status:**
   - Visit https://status.backblaze.com

4. **Open an issue:**
   - Include error messages (redact credentials)
   - Include relevant logs
   - Include system information
   - Describe what you've already tried

5. **Contact support:**
   - RunPod support for infrastructure issues
   - Backblaze support for B2 issues
   - rclone forum for rclone issues

## Security Best Practices

### Credential Management

1. **Never commit credentials to Git**
   - Use `.env` file (in `.gitignore`)
   - Use environment variables in RunPod console

2. **Use read-only keys for production**
   - Create separate keys for prod/dev
   - Limit permissions to minimum required

3. **Rotate keys periodically**
   - Generate new keys every 90 days
   - Update environment variables

4. **Use separate keys per environment**
   - Development: Read/write access
   - Production: Read-only access
   - Testing: Separate bucket

### Network Security

1. **All traffic over HTTPS**
   - B2 uses TLS 1.2+
   - No plaintext credentials

2. **Private buckets**
   - Never make buckets public
   - Use signed URLs if needed

3. **Restrict bucket access**
   - Use application keys (not master key)
   - Limit to specific buckets

## Migration Guide

For comprehensive migration instructions, see the [Migration Guide](MIGRATION.md).

### Quick Migration Overview

**From Network Volume to B2:**
1. Upload models to B2 using rclone
2. Update `.env` with B2 configuration
3. Restart container
4. Verify models accessible

**From B2 Back to Network Volume:**
1. Sync models from B2 to network volume
2. Update `.env` to use network-volume
3. Restart container
4. Verify models accessible

**Between B2 Mount and B2 Sync:**
1. Update `STORAGE_BACKEND` in `.env`
2. Restart container
3. Monitor sync/mount progress

**To Hybrid Approach:**
1. Identify frequently-used models
2. Modify Dockerfile to bake models
3. Rebuild Docker image
4. Configure B2 mount for remaining models

For detailed step-by-step instructions, troubleshooting, and rollback procedures, see the [Migration Guide](MIGRATION.md).

## Example Configurations

We provide ready-to-use example configurations for common scenarios. See the [examples directory](examples/) for detailed configurations.

### Quick Reference

| Scenario | File | Best For | Cost (100GB) |
|----------|------|----------|--------------|
| Small Library | [.env.small-library](examples/.env.small-library) | SD 1.5, testing | $5.10/month |
| Large Library | [.env.large-library](examples/.env.large-library) | FLUX, production | $15.50/month |
| Max Performance | [.env.maximum-performance](examples/.env.maximum-performance) | Low latency | $12.50/month |
| Hybrid | [.env.hybrid-approach](examples/.env.hybrid-approach) | Cost + performance | $11/month |

### Using Example Configurations

```bash
# Copy example to your .env file
cp storage/examples/.env.large-library .env

# Update credentials
nano .env

# Start container
docker-compose up -d
```

For detailed configuration options and guidance, see:
- [Example Configurations README](examples/README.md) - Detailed guide for each scenario
- [Migration Guide](MIGRATION.md) - Step-by-step migration instructions

## Scripts Reference

### setup_b2_mount.sh

Mounts B2 bucket using rclone with optimized caching.

**Usage:**
```bash
./storage/setup_b2_mount.sh
```

**Exit codes:**
- 0: Success
- 1: Missing required environment variables
- 2: rclone configuration failed
- 3: Mount failed
- 4: Mount verification failed

### setup_b2_sync.sh

Syncs B2 bucket contents to local storage on boot.

**Usage:**
```bash
./storage/setup_b2_sync.sh
```

**Exit codes:**
- 0: Success
- 1: Missing required environment variables
- 2: rclone configuration failed
- 3: Insufficient disk space
- 4: Sync failed

### upload_to_b2.py

Upload local models to B2 bucket.

**Usage:**
```bash
python storage/upload_to_b2.py --local ./models --bucket my-comfyui-models
```

**Options:**
- `--local`: Local models directory
- `--bucket`: B2 bucket name
- `--remote`: Remote path within bucket (optional)
- `--skip-existing`: Skip files that already exist (default: true)
- `--parallel`: Number of parallel uploads (default: 8)

### manage_b2.py

Manage B2 bucket contents and costs.

**Commands:**
- `list`: List bucket contents with sizes
- `size`: Calculate total storage size and estimated costs
- `clean`: Remove unused models based on age or pattern
- `verify`: Verify local files match B2 checksums

**Usage:**
```bash
# List contents
python storage/manage_b2.py list --bucket my-comfyui-models

# Calculate costs
python storage/manage_b2.py size --bucket my-comfyui-models

# Clean old files
python storage/manage_b2.py clean --bucket my-comfyui-models --older-than 90d

# Verify checksums
python storage/manage_b2.py verify --bucket my-comfyui-models --local ./models
```

## Additional Resources

- [Backblaze B2 Documentation](https://www.backblaze.com/b2/docs/)
- [rclone Documentation](https://rclone.org/docs/)
- [rclone B2 Configuration](https://rclone.org/b2/)
- [rclone Mount Documentation](https://rclone.org/commands/rclone_mount/)
- [rclone VFS Cache](https://rclone.org/commands/rclone_mount/#vfs-cache-mode)

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review rclone logs: `docker-compose logs comfyui`
3. Test B2 connectivity: `rclone lsd b2:my-comfyui-models`
4. Open an issue on GitHub with logs and configuration (redact credentials)
