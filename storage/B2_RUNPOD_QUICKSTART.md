# Backblaze B2 + RunPod Quick Setup Guide

A practical guide to set up Backblaze B2 storage with RunPod for cost-effective model storage.

## Why B2 + RunPod?

**Cost Savings:** 60-95% cheaper than RunPod network volumes alone
- 100GB on B2: ~$0.50/month
- 100GB on RunPod network volume: ~$10/month
- Combined (B2 + smaller cache volume): ~$5-10/month vs $25/month

**Performance:** Near-instant access after initial cache warmup

## Prerequisites

- RunPod account with API key
- Credit card for Backblaze B2 (free tier available)
- Basic command line knowledge

## Step 1: Create Backblaze B2 Account

1. Go to https://www.backblaze.com/b2/sign-up.html
2. Sign up (free tier: 10GB storage, 1GB daily download)
3. Verify your email

## Step 2: Create B2 Bucket

1. Log into B2 console: https://secure.backblaze.com/b2_buckets.htm
2. Click **"Create a Bucket"**
3. Configure:
   - **Bucket Name:** `my-comfyui-models` (must be globally unique)
   - **Files in Bucket:** Private
   - **Default Encryption:** Disable (optional)
   - **Object Lock:** Disable
4. Click **"Create a Bucket"**
5. Note your bucket name

## Step 3: Generate B2 Application Keys

1. Go to **App Keys**: https://secure.backblaze.com/app_keys.htm
2. Click **"Add a New Application Key"**
3. Configure:
   - **Name:** `comfyui-readwrite`
   - **Allow access to Bucket(s):** Select your bucket
   - **Type of Access:** Read and Write
   - **Allow List All Bucket Names:** Yes (optional)
4. Click **"Create New Key"**
5. **IMPORTANT:** Copy and save immediately:
   - **keyID** (starts with `004...`)
   - **applicationKey** (long random string, shown only once!)

## Step 4: Get B2 S3 Endpoint

Your endpoint depends on your bucket's region:

1. Go to your bucket details
2. Find **"Endpoint"** section
3. Copy the S3 Compatible endpoint

**Common endpoints:**
- US West: `s3.us-west-004.backblazeb2.com`
- US East: `s3.us-east-005.backblazeb2.com`
- EU Central: `s3.eu-central-003.backblazeb2.com`

**Region codes:**
- US West: `us-west-004`
- US East: `us-east-005`
- EU Central: `eu-central-003`

## Step 5: Upload Models to B2

### Option A: Using rclone (Recommended)

```bash
# Install rclone
curl https://rclone.org/install.sh | bash

# Configure rclone
cat > ~/.config/rclone/rclone.conf <<EOF
[b2]
type = s3
provider = Other
env_auth = false
access_key_id = YOUR_KEY_ID_HERE
secret_access_key = YOUR_APP_KEY_HERE
endpoint = s3.us-west-004.backblazeb2.com
region = us-west-004
acl = private
EOF

# Test connection
rclone lsd b2:my-comfyui-models

# Upload models (adjust paths as needed)
rclone sync ./models b2:my-comfyui-models/models --progress

# Verify upload
rclone size b2:my-comfyui-models/models
```

### Option B: Using B2 Web Interface

1. Go to your bucket in B2 console
2. Click **"Upload/Download"**
3. Drag and drop model files
4. Wait for upload to complete

**Note:** Web upload is slower and less reliable for large files. Use rclone for 10GB+.

## Step 6: Configure RunPod Environment

### For Serverless Endpoints

1. Go to RunPod dashboard → **Serverless**
2. Select your endpoint (or create new)
3. Click **"Edit"** → **"Environment Variables"**
4. Add these variables:

```bash
STORAGE_BACKEND=b2-mount
B2_BUCKET=my-comfyui-models
B2_KEY_ID=004abc123def456...
B2_APP_KEY=K004abc123def456...
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_PATH=models
RCLONE_CACHE_SIZE=50G
```

5. Click **"Save"**
6. Restart endpoint

### For Pods

1. Go to RunPod dashboard → **Pods**
2. Select your pod (or create new)
3. Click **"Edit"** → **"Environment Variables"**
4. Add the same variables as above
5. Click **"Save"**
6. Restart pod

### Using .env File (Alternative)

Create `.env` file in your project:

```bash
# Storage Backend Configuration
STORAGE_BACKEND=b2-mount

# B2 Credentials
B2_BUCKET=my-comfyui-models
B2_KEY_ID=004abc123def456...
B2_APP_KEY=K004abc123def456...
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004

# B2 Path Configuration
B2_PATH=models

# Cache Configuration
RCLONE_CACHE_SIZE=50G
RCLONE_CACHE_MAX_AGE=24h
```

Upload to RunPod network volume:
```bash
scp -P <port> .env root@<pod-ip>:/runpod-volume/.env
```

## Step 7: Verify Setup

### Check Logs

```bash
# For Docker Compose
docker-compose logs comfyui | grep -i "b2\|rclone\|storage"

# For RunPod (via SSH)
ssh root@<pod-ip> -p <port>
tail -f /var/log/comfyui.log | grep -i "b2\|rclone"
```

### Test Model Access

```bash
# SSH into container
ssh root@<pod-ip> -p <port>

# Check mount point (for b2-mount)
mountpoint /comfyui/models
ls -la /comfyui/models/

# Test model access (first time will download)
time ls /comfyui/models/checkpoints/

# Second access should be instant (cached)
time ls /comfyui/models/checkpoints/
```

### Access ComfyUI WebUI

1. Open ComfyUI WebUI (via RunPod proxy or OpenZiti)
2. Check model dropdown - should show your models
3. Load a workflow and generate an image
4. First generation may be slow (downloading model)
5. Subsequent generations should be fast (cached)

## Step 8: Monitor and Optimize

### Check Storage Costs

```bash
# Set environment variables
export B2_BUCKET=my-comfyui-models
export B2_KEY_ID=004abc123def456...
export B2_APP_KEY=K004abc123def456...
export B2_ENDPOINT=s3.us-west-004.backblazeb2.com
export B2_REGION=us-west-004

# Calculate storage size and costs
uv run python storage/manage_b2.py size
```

### Monitor Cache Usage

```bash
# Check cache size
du -sh /runpod-volume/rclone-cache

# Monitor cache in real-time
watch -n 5 'du -sh /runpod-volume/rclone-cache'
```

### Adjust Cache Size

If models are frequently re-downloading:

```bash
# Increase cache size in .env
RCLONE_CACHE_SIZE=100G

# Restart container
docker-compose restart comfyui
```

## Configuration Options

### Storage Backend Modes

**b2-mount** (Recommended for most users)
```bash
STORAGE_BACKEND=b2-mount
RCLONE_CACHE_SIZE=50G
```
- Models cached on network volume
- Instant startup
- Medium performance (first access slow, cached fast)
- Best for: General use, cost optimization

**b2-sync** (For maximum performance)
```bash
STORAGE_BACKEND=b2-sync
```
- Full library synced to container disk on startup
- 20-40 minute startup for 100GB
- Fast performance (local disk access)
- Best for: Production workloads, frequent access

### Cache Size Recommendations

| Model Type | Model Size | Recommended Cache | Models Cached |
|------------|------------|-------------------|---------------|
| SD 1.5 | ~4GB | 20G | 4-5 models |
| SDXL | ~6GB | 50G | 8-10 models |
| FLUX | ~23GB | 100G | 4-5 models |

**Formula:** Cache Size = (Frequently-used models × Average size) × 1.2

## Troubleshooting

### Models Not Showing in ComfyUI

```bash
# Check mount status
mountpoint /comfyui/models

# Check rclone logs
cat /tmp/rclone-mount.log

# Verify B2 credentials
rclone lsd b2:my-comfyui-models

# Restart container
docker-compose restart comfyui
```

### Slow Model Loading

```bash
# Check cache size
du -sh /runpod-volume/rclone-cache

# Increase cache size
RCLONE_CACHE_SIZE=100G

# Or switch to b2-sync for better performance
STORAGE_BACKEND=b2-sync
```

### "Access Denied" Errors

```bash
# Verify credentials are correct
echo $B2_KEY_ID
echo $B2_APP_KEY

# Check for extra spaces/newlines
echo "$B2_KEY_ID" | cat -A

# Regenerate keys in B2 console if needed
```

### High B2 Costs

```bash
# Check egress usage in B2 console
# Billing → Usage

# Configure Cloudflare for free egress
# B2 console → Buckets → Cloudflare Settings

# Use b2-mount instead of b2-sync
# (only downloads accessed models)
STORAGE_BACKEND=b2-mount
```

## Cost Optimization Tips

1. **Use Cloudflare for free egress**
   - B2 console → Buckets → Cloudflare Settings
   - Eliminates download fees

2. **Choose right cache size**
   - Too small: Frequent re-downloads
   - Too large: Wasted network volume space
   - Sweet spot: 80% of frequently-used models

3. **Use b2-mount for occasional access**
   - Only downloads models you actually use
   - Minimal egress costs

4. **Use b2-sync for heavy usage**
   - One-time download
   - No ongoing egress costs

5. **Clean up old models**
   ```bash
   # List old files (dry run)
   uv run python storage/manage_b2.py clean --older-than 90
   
   # Actually delete
   uv run python storage/manage_b2.py clean --older-than 90 --no-dry-run
   ```

## Next Steps

- **Hybrid Approach:** Bake frequently-used models into Docker image for instant access
- **Multiple Buckets:** Separate buckets for different model types
- **Automated Backups:** Use rclone to backup outputs to B2
- **Team Sharing:** Share B2 bucket across multiple RunPod instances

## Additional Resources

- [Full Storage Documentation](README.md)
- [Migration Guide](MIGRATION.md)
- [Example Configurations](examples/README.md)
- [B2 Documentation](https://www.backblaze.com/b2/docs/)
- [rclone Documentation](https://rclone.org/docs/)

## Support

Having issues? Check:

1. **Logs:** `docker-compose logs comfyui | grep -i b2`
2. **B2 Connectivity:** `rclone lsd b2:your-bucket`
3. **Cache Status:** `du -sh /runpod-volume/rclone-cache`
4. **Full Documentation:** [Storage README](README.md)
