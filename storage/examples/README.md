# Storage Backend Example Configurations

This directory contains example `.env` configurations for different storage backend scenarios. These examples help you choose and configure the right storage strategy for your use case.

## Available Examples

### 1. Small Model Library (< 20GB)
**File:** `.env.small-library`

Best for SD 1.5 models, testing, and development.

**Characteristics:**
- Storage: B2 mount with 20GB cache
- Cost: ~$0.10/month for B2 storage
- Performance: Medium (first access 30-60s, cached instant)
- Use case: Small collections, infrequent access

**When to use:**
- You have a small model collection (< 20GB)
- You're testing B2 integration
- You access models infrequently
- Cost savings are important

### 2. Large Model Library (100GB+)
**File:** `.env.large-library`

Best for FLUX models, large collections, and production deployments.

**Characteristics:**
- Storage: B2 mount with 100GB cache
- Cost: ~$0.50/month for B2 storage + $10/month for network volume
- Performance: Medium (first access 2-3 minutes, cached instant)
- Use case: Large collections, mixed model types

**When to use:**
- You have a large model library (100GB+)
- You use FLUX or multiple SDXL models
- You want significant cost savings (95% vs network volume)
- You can tolerate initial download times

### 3. Maximum Performance (B2 Sync)
**File:** `.env.maximum-performance`

Best for production workloads requiring low latency.

**Characteristics:**
- Storage: B2 synced to local disk on startup
- Cost: ~$0.50/month for B2 storage + egress costs
- Performance: Fast (local disk access, no network latency)
- Sync time: 20-40 minutes for 100GB initial sync

**When to use:**
- You need maximum performance (local disk access)
- You access models frequently
- You can tolerate startup sync time
- You have sufficient container disk space

### 4. Hybrid Approach
**File:** `.env.hybrid-approach`

Best for cost optimization with excellent performance for common models.

**Characteristics:**
- Storage: Frequently-used models baked into Docker image + B2 mount for full library
- Cost: ~$0.50/month for B2 storage
- Performance: Instant for common models, medium for rare models
- Complexity: Requires Docker image rebuilds

**When to use:**
- You have identifiable frequently-used models (80/20 rule)
- You want instant access to common models
- You want cost savings on full library
- You can rebuild Docker images periodically

## Quick Start

### 1. Choose Your Scenario

Review the characteristics above and choose the example that best matches your needs.

### 2. Copy Example Configuration

```bash
# Copy example to your .env file
cp storage/examples/.env.large-library .env

# Or append to existing .env
cat storage/examples/.env.large-library >> .env
```

### 3. Update Credentials

Edit the `.env` file and replace placeholder values:

```bash
# Edit .env file
nano .env

# Update these values:
B2_BUCKET=my-comfyui-models          # Your B2 bucket name
B2_KEY_ID=your_key_id_here           # Your B2 key ID
B2_APP_KEY=your_app_key_here         # Your B2 application key
B2_ENDPOINT=s3.us-west-004.backblazeb2.com  # Your B2 endpoint
B2_REGION=us-west-004                # Your B2 region
```

### 4. Upload Models to B2

```bash
# Install rclone (if not already installed)
curl https://rclone.org/install.sh | bash

# Configure rclone with your B2 credentials
rclone config

# Upload models to B2
rclone sync ./models b2:my-comfyui-models/models --progress
```

### 5. Start Container

```bash
# Start container with new configuration
docker-compose up -d

# Check logs
docker-compose logs -f comfyui
```

## Comparison Table

| Scenario | Storage Backend | Cache Size | Cost (100GB) | Performance | Startup Time | Complexity |
|----------|----------------|------------|--------------|-------------|--------------|------------|
| **Small Library** | b2-mount | 20G | $5.10/month | Medium | Instant | Low |
| **Large Library** | b2-mount | 100G | $15.50/month | Medium | Instant | Low |
| **Max Performance** | b2-sync | N/A | $11.50/month | Fast | 20-40 min | Low |
| **Hybrid** | b2-mount + baked | 50G | $10.50/month | Fast (common) | Instant | High |
| **Network Volume** | network-volume | N/A | $25/month | Fast | Instant | Low |

## Configuration Parameters

### Required Parameters (All B2 Scenarios)

```bash
STORAGE_BACKEND=b2-mount  # or b2-sync
B2_BUCKET=my-comfyui-models
B2_KEY_ID=your_key_id_here
B2_APP_KEY=your_app_key_here
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
```

### Optional Parameters

```bash
# Subdirectory within bucket (optional)
B2_PATH=models

# Cache configuration (b2-mount only)
RCLONE_CACHE_SIZE=50G      # Default: 20G
RCLONE_CACHE_MAX_AGE=24h   # Default: 24h
```

## Cache Size Recommendations

Choose cache size based on your model types:

| Model Type | Model Size | Recommended Cache | Models Cached |
|------------|------------|-------------------|---------------|
| **SD 1.5** | ~4GB | 20G | 4-5 models |
| **SDXL** | ~6GB | 50G | 8-10 models |
| **FLUX** | ~23GB | 100G | 4-5 models |
| **Mixed** | Varies | 50-100G | Varies |

**Formula:** Cache Size = (Number of frequently-used models × Average model size) × 1.2

**Example:**
- 3 FLUX models (23GB each) + 5 SDXL models (6GB each)
- = (3 × 23GB) + (5 × 6GB) = 69GB + 30GB = 99GB
- Recommended cache: 100G (with 20% buffer)

## Cost Calculator

### B2 Storage Costs

```
Monthly Storage Cost = Library Size (GB) × $0.005/GB/month
```

**Examples:**
- 20GB: $0.10/month
- 50GB: $0.25/month
- 100GB: $0.50/month
- 200GB: $1.00/month

### B2 Egress Costs

```
Egress Cost = Downloaded Data (GB) × $0.01/GB
```

**Notes:**
- Free via Cloudflare (recommended)
- Only charged on first download (cached after)
- b2-mount: Minimal egress (only accessed models)
- b2-sync: Full library egress on each sync

### Network Volume Costs

```
Monthly Volume Cost = Volume Size (GB) × $0.10/GB/month
```

**Examples:**
- 50GB: $5/month
- 100GB: $10/month
- 150GB: $15/month
- 200GB: $20/month

### Total Cost Comparison (100GB Library)

| Scenario | B2 Storage | Egress | Network Volume | Total |
|----------|------------|--------|----------------|-------|
| **Network Volume Only** | $0 | $0 | $25/month | **$25/month** |
| **B2 Mount** | $0.50/month | $1 (one-time) | $15/month | **$15.50/month** |
| **B2 Sync** | $0.50/month | $1/month | $11/month | **$12.50/month** |
| **Hybrid** | $0.50/month | $0.50/month | $10/month | **$11/month** |

**Savings with B2:** 38-56% cost reduction

## Performance Expectations

### B2 Mount (b2-mount)

**Cold Start (First Access):**
- SD 1.5 model (4GB): 20-30 seconds
- SDXL model (6GB): 30-60 seconds
- FLUX model (23GB): 2-3 minutes

**Warm Start (Cached):**
- All models: Instant (< 1 second)
- Equivalent to local disk access
- Cache persists across container restarts

**Cache Hit Rate:**
- Typical: 95%+ after initial warmup
- Depends on cache size and model usage patterns

### B2 Sync (b2-sync)

**Initial Sync:**
- 10GB: 2-5 minutes
- 50GB: 10-20 minutes
- 100GB: 20-40 minutes
- 200GB: 40-80 minutes

**Subsequent Syncs:**
- No changes: < 10 seconds (checksum verification)
- Few changes: < 1 minute
- Many changes: Proportional to changed data

**Runtime Performance:**
- All models: Instant (local disk)
- No network latency
- Equivalent to network volume

### Hybrid Approach

**Baked Models:**
- Access time: Instant (< 1 second)
- Always available
- No download needed

**B2-Mounted Models:**
- First access: 30-60 seconds (download + cache)
- Subsequent access: Instant (cached)

## Troubleshooting

### Example Configuration Not Working

**Check credentials:**
```bash
# Verify B2 credentials are correct
rclone lsd b2:my-comfyui-models

# Test B2 connectivity
rclone ls b2:my-comfyui-models/models
```

**Check logs:**
```bash
# View container logs
docker-compose logs comfyui | grep -i "b2\|rclone\|storage"

# View rclone logs
docker-compose exec comfyui cat /tmp/rclone-mount.log
docker-compose exec comfyui cat /tmp/rclone-sync.log
```

**Verify configuration:**
```bash
# Check environment variables
docker-compose exec comfyui env | grep B2_
docker-compose exec comfyui env | grep STORAGE_BACKEND
```

### Performance Issues

**Slow model loading:**
```bash
# Check cache size
du -sh /runpod-volume/rclone-cache

# Increase cache size in .env
RCLONE_CACHE_SIZE=100G

# Restart container
docker-compose restart comfyui
```

**High B2 costs:**
```bash
# Configure Cloudflare for free egress
# B2 console → Buckets → Cloudflare Settings

# Switch to b2-mount (less egress than b2-sync)
STORAGE_BACKEND=b2-mount
```

## Migration Between Examples

### From Small to Large Library

```bash
# 1. Update .env with larger cache size
RCLONE_CACHE_SIZE=100G

# 2. Restart container
docker-compose restart comfyui

# 3. Upload additional models to B2
rclone sync ./models b2:my-comfyui-models/models --progress
```

### From B2 Mount to B2 Sync

```bash
# 1. Check container disk space
df -h

# 2. Update .env
STORAGE_BACKEND=b2-sync

# 3. Restart container (will trigger sync)
docker-compose down
docker-compose up -d

# 4. Monitor sync progress
docker-compose logs -f comfyui
```

### From Any B2 to Hybrid

```bash
# 1. Identify frequently-used models
docker-compose logs comfyui | grep -i "loading model" | sort | uniq -c | sort -rn

# 2. Copy models to project directory
mkdir -p models/checkpoints
cp /runpod-volume/models/checkpoints/sd_xl_base_1.0.safetensors models/checkpoints/

# 3. Update Dockerfile (see .env.hybrid-approach for example)

# 4. Rebuild image
docker-compose build

# 5. Deploy new image
docker-compose down
docker-compose up -d
```

## Additional Resources

- [Storage Backend Documentation](../README.md) - Comprehensive guide
- [Migration Guide](../MIGRATION.md) - Step-by-step migration instructions
- [Backblaze B2 Documentation](https://www.backblaze.com/b2/docs/)
- [rclone Documentation](https://rclone.org/docs/)

## Support

For help with example configurations:

1. Review the [Storage Backend Documentation](../README.md)
2. Check the [Troubleshooting section](../README.md#troubleshooting)
3. Review [Migration Guide](../MIGRATION.md) for detailed steps
4. Open an issue with:
   - Which example you're using
   - Error messages (redact credentials)
   - Relevant logs
   - What you've already tried
