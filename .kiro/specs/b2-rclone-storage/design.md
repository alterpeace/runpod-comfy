# Design Document: B2/rclone Storage Integration

## Overview

This design adds Backblaze B2 (S3-compatible) storage as an optional alternative to RunPod network volumes for storing ComfyUI models and assets. The solution uses rclone to either mount B2 as a filesystem or sync B2 contents to local storage on boot. The VFS cache for rclone mount is stored on the RunPod network volume to support large cache sizes (100GB+) needed for models like FLUX.

### Key Design Decisions

1. **Optional Feature**: B2 storage is completely optional - existing network volume behavior remains default
2. **Two Strategies**: Support both mount (on-demand) and sync (pre-load) approaches
3. **Network Volume Cache**: Store rclone VFS cache on network volume for large cache support
4. **Environment-Driven**: All configuration via environment variables in .env file
5. **Backward Compatible**: No changes to existing code when B2 is not configured

### Storage Backend Options

| Backend | Description | Use Case | Cost | Performance |
|---------|-------------|----------|------|-------------|
| **network-volume** (default) | RunPod network volumes | Existing behavior | ~$100/TB/month | Fast (local network) |
| **b2-mount** | rclone mount B2 as filesystem | Large model library, infrequent access | ~$5/TB/month | Medium (network + cache) |
| **b2-sync** | Sync B2 to local on boot | Maximum performance needed | ~$5/TB/month + egress | Fast (local after sync) |

## Architecture

### High-Level Flow

```
Container Startup
    ↓
entrypoint.sh
    ↓
Check STORAGE_BACKEND env var
    ↓
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ network-volume       │ b2-mount             │ b2-sync              │
│ (default)            │                      │                      │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Use existing         │ 1. Validate B2 env   │ 1. Validate B2 env   │
│ /runpod-volume/models│    variables         │    variables         │
│ directory            │ 2. Configure rclone  │ 2. Configure rclone  │
│                      │ 3. Create cache dir  │ 3. Check local space │
│                      │    on network volume │ 4. Sync B2 → local   │
│                      │ 4. Mount B2 bucket   │ 5. Log sync stats    │
│                      │ 5. Verify mount      │                      │
└──────────────────────┴──────────────────────┴──────────────────────┘
    ↓                       ↓                       ↓
Start ComfyUI with appropriate model paths
    ↓
Handler/WebUI operates normally
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Docker Container                                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ entrypoint.sh (Enhanced)                               │ │
│  │ - Detect STORAGE_BACKEND                               │ │
│  │ - Call appropriate storage setup script                │ │
│  └────────────────┬───────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────────┐ │
│  │ storage/setup_b2_mount.sh                              │ │
│  │ - Validate B2 credentials                              │ │
│  │ - Generate rclone.conf from env vars                   │ │
│  │ - Create /runpod-volume/rclone-cache directory         │ │
│  │ - Mount B2 with optimized flags                        │ │
│  │ - Verify mount success                                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ storage/setup_b2_sync.sh                               │ │
│  │ - Validate B2 credentials                              │ │
│  │ - Generate rclone.conf from env vars                   │ │
│  │ - Check available disk space                           │ │
│  │ - Sync B2 bucket to /comfyui/models                    │ │
│  │ - Log sync statistics                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ComfyUI Server                                         │ │
│  │ - Loads models from configured path                    │ │
│  │ - Works transparently with any storage backend         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ rclone (when b2-mount)                                 │ │
│  │ - Runs as daemon process                               │ │
│  │ - Mounts B2 to /comfyui/models                         │ │
│  │ - Caches to /runpod-volume/rclone-cache                │ │
│  │ - Handles network errors and retries                   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Storage Layer                                                │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Network Volume   │  │ Backblaze B2     │                │
│  │ /runpod-volume/  │  │ (S3-compatible)  │                │
│  │ - models/        │  │ - models/        │                │
│  │ - rclone-cache/  │  │ - checkpoints/   │                │
│  │ - outputs/       │  │ - loras/         │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Storage Setup Scripts

**Location**: `runpod-serverless/storage/`

#### setup_b2_mount.sh

Mounts B2 bucket using rclone with optimized caching.

**Responsibilities**:
- Validate required environment variables (B2_BUCKET, B2_KEY_ID, B2_APP_KEY, B2_ENDPOINT)
- Generate rclone configuration from environment variables
- Create cache directory on network volume
- Mount B2 bucket with performance optimizations
- Verify mount is successful
- Handle errors gracefully

**Key rclone Flags**:
```bash
rclone mount b2:$B2_BUCKET/$B2_PATH /comfyui/models \
  --daemon \
  --vfs-cache-mode full \
  --vfs-cache-max-size ${RCLONE_CACHE_SIZE:-20G} \
  --cache-dir /runpod-volume/rclone-cache \
  --vfs-cache-max-age ${RCLONE_CACHE_MAX_AGE:-24h} \
  --buffer-size 256M \
  --vfs-read-ahead 256M \
  --dir-cache-time 1h \
  --poll-interval 0 \
  --read-only \
  --allow-other
```


**Exit Codes**:
- 0: Success
- 1: Missing required environment variables
- 2: rclone configuration failed
- 3: Mount failed
- 4: Mount verification failed

#### setup_b2_sync.sh

Syncs B2 bucket contents to local storage on boot.

**Responsibilities**:
- Validate required environment variables
- Generate rclone configuration
- Check available disk space
- Sync B2 bucket to local directory
- Log sync progress and statistics
- Handle errors gracefully

**Key rclone Command**:
```bash
rclone sync b2:$B2_BUCKET/$B2_PATH /comfyui/models \
  --transfers 8 \
  --checkers 16 \
  --fast-list \
  --progress \
  --stats 10s \
  --stats-one-line
```

**Exit Codes**:
- 0: Success
- 1: Missing required environment variables
- 2: rclone configuration failed
- 3: Insufficient disk space
- 4: Sync failed

### 2. Enhanced Entrypoint Script

**File**: `runpod-serverless/entrypoint.sh`

**New Logic**:
```bash
# After existing initialization (OpenZiti, SSH)...

# Storage backend setup
STORAGE_BACKEND=${STORAGE_BACKEND:-network-volume}

case "$STORAGE_BACKEND" in
  "network-volume")
    echo "Using network volume storage (default)"
    # No additional setup needed
    ;;
  "b2-mount")
    echo "Setting up B2 mount with rclone..."
    ./storage/setup_b2_mount.sh
    if [ $? -ne 0 ]; then
      echo "ERROR: B2 mount setup failed"
      exit 1
    fi
    ;;
  "b2-sync")
    echo "Syncing models from B2..."
    ./storage/setup_b2_sync.sh
    if [ $? -ne 0 ]; then
      echo "ERROR: B2 sync failed"
      exit 1
    fi
    ;;
  *)
    echo "WARNING: Unknown STORAGE_BACKEND '$STORAGE_BACKEND', using network-volume"
    ;;
esac

# Continue with ComfyUI startup...
```

### 3. rclone Configuration

**Dynamic Configuration Generation**:

The setup scripts generate rclone configuration dynamically from environment variables rather than using a static config file.


**Configuration Template**:
```bash
# Generate rclone config
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf <<EOF
[b2]
type = s3
provider = Other
env_auth = false
access_key_id = ${B2_KEY_ID}
secret_access_key = ${B2_APP_KEY}
endpoint = ${B2_ENDPOINT}
region = ${B2_REGION:-us-west-004}
acl = private
EOF
```

**Environment Variables**:
- `B2_BUCKET`: Bucket name (required)
- `B2_KEY_ID`: Access key ID (required)
- `B2_APP_KEY`: Application key (required)
- `B2_ENDPOINT`: S3 endpoint URL (required, e.g., s3.us-west-004.backblazeb2.com)
- `B2_REGION`: Bucket region (optional, default: us-west-004)
- `B2_PATH`: Subdirectory within bucket (optional, default: empty/root)

### 4. Management Tools

**Location**: `runpod-serverless/storage/`

#### upload_to_b2.py

Upload local models to B2 bucket.

**Interface**:
```python
def upload_models(
    local_path: str,
    bucket: str,
    remote_path: str = "",
    skip_existing: bool = True,
    parallel: int = 8
) -> dict:
    """
    Upload models from local directory to B2.
    
    Args:
        local_path: Local models directory
        bucket: B2 bucket name
        remote_path: Remote path within bucket
        skip_existing: Skip files that already exist with matching checksums
        parallel: Number of parallel uploads
    
    Returns:
        Dictionary with upload statistics
    """
```

**Usage**:
```bash
# Upload all models
python storage/upload_to_b2.py --local ./models --bucket my-comfyui-models

# Upload specific subdirectory
python storage/upload_to_b2.py --local ./models/checkpoints --bucket my-comfyui-models --remote checkpoints
```

#### manage_b2.py

Manage B2 bucket contents and costs.

**Commands**:
- `list`: List bucket contents with sizes
- `size`: Calculate total storage size and estimated costs
- `clean`: Remove unused models based on age or pattern
- `verify`: Verify local files match B2 checksums

**Usage**:
```bash
# List bucket contents
python storage/manage_b2.py list --bucket my-comfyui-models

# Calculate costs
python storage/manage_b2.py size --bucket my-comfyui-models

# Clean old files
python storage/manage_b2.py clean --bucket my-comfyui-models --older-than 90d
```


## Data Models

### Environment Configuration

```python
@dataclass
class B2Config:
    """B2 storage configuration"""
    bucket: str
    key_id: str
    app_key: str
    endpoint: str
    region: str = "us-west-004"
    path: str = ""
    
    @classmethod
    def from_env(cls) -> Optional['B2Config']:
        """Load configuration from environment variables"""
        required = ['B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY', 'B2_ENDPOINT']
        if not all(os.getenv(var) for var in required):
            return None
        
        return cls(
            bucket=os.getenv('B2_BUCKET'),
            key_id=os.getenv('B2_KEY_ID'),
            app_key=os.getenv('B2_APP_KEY'),
            endpoint=os.getenv('B2_ENDPOINT'),
            region=os.getenv('B2_REGION', 'us-west-004'),
            path=os.getenv('B2_PATH', '')
        )

@dataclass
class RcloneMountConfig:
    """rclone mount configuration"""
    cache_size: str = "20G"
    cache_max_age: str = "24h"
    cache_dir: str = "/runpod-volume/rclone-cache"
    buffer_size: str = "256M"
    read_ahead: str = "256M"
    
    @classmethod
    def from_env(cls) -> 'RcloneMountConfig':
        """Load configuration from environment variables"""
        return cls(
            cache_size=os.getenv('RCLONE_CACHE_SIZE', '20G'),
            cache_max_age=os.getenv('RCLONE_CACHE_MAX_AGE', '24h'),
            cache_dir=os.getenv('RCLONE_CACHE_DIR', '/runpod-volume/rclone-cache')
        )
```

### Storage Backend Enum

```python
from enum import Enum

class StorageBackend(Enum):
    """Available storage backends"""
    NETWORK_VOLUME = "network-volume"
    B2_MOUNT = "b2-mount"
    B2_SYNC = "b2-sync"
    
    @classmethod
    def from_env(cls) -> 'StorageBackend':
        """Get storage backend from environment"""
        backend = os.getenv('STORAGE_BACKEND', 'network-volume')
        try:
            return cls(backend)
        except ValueError:
            logger.warning(f"Unknown STORAGE_BACKEND '{backend}', using network-volume")
            return cls.NETWORK_VOLUME
```

## Error Handling

### Error Scenarios and Responses

| Scenario | Detection | Response | User Impact |
|----------|-----------|----------|-------------|
| Missing B2 credentials | Startup validation | Log error, exit with code 1 | Container fails to start |
| Invalid B2 credentials | rclone config test | Log error, exit with code 2 | Container fails to start |
| B2 bucket not accessible | Mount/sync attempt | Log error, exit with code 3 | Container fails to start |
| Network volume not mounted | Cache dir creation | Log error, exit with code 4 | Container fails to start |
| Insufficient disk space (sync) | Pre-sync check | Log error, exit with code 3 | Container fails to start |
| Mount fails | Mount verification | Log error, exit with code 3 | Container fails to start |
| Network interruption (mount) | rclone auto-retry | Automatic reconnection | Temporary slowdown |
| Cache full | rclone LRU eviction | Automatic cleanup | Transparent |


### Validation Strategy

**Startup Validation**:
1. Check STORAGE_BACKEND value
2. If B2 backend selected:
   - Validate all required environment variables present
   - Test B2 credentials with `rclone lsd`
   - Check network volume is mounted (for cache directory)
   - For sync: Check sufficient disk space
3. Fail fast with clear error messages

**Runtime Monitoring**:
- For mount: rclone daemon monitors connection health
- For mount: Automatic reconnection on network issues
- Log warnings for cache space issues
- Monitor mount point health

## Testing Strategy

### Unit Tests

**Test Coverage**:
- Environment variable parsing and validation
- rclone configuration generation
- Error handling for missing/invalid credentials
- Storage backend selection logic

**Test Files**:
- `tests/test_b2_config.py`: Configuration parsing
- `tests/test_storage_setup.py`: Setup script logic

### Integration Tests

**Test Scenarios**:
1. **B2 Mount Success**: Mount B2 bucket, verify files accessible
2. **B2 Sync Success**: Sync B2 bucket, verify files copied
3. **Invalid Credentials**: Verify proper error handling
4. **Network Volume Cache**: Verify cache directory creation
5. **Fallback to Network Volume**: Verify default behavior when B2 not configured

**Test Files**:
- `tests/integration/test_b2_mount.py`
- `tests/integration/test_b2_sync.py`

### Manual Testing

**Test Checklist**:
- [ ] Mount B2 with small cache (5GB), load model
- [ ] Mount B2 with large cache (100GB), load FLUX model
- [ ] Sync B2 to local, verify all files present
- [ ] Test with invalid credentials, verify error message
- [ ] Test without B2 config, verify network volume used
- [ ] Test cache persistence across container restarts
- [ ] Test network interruption recovery (mount mode)

## Performance Considerations

### B2 Mount Performance

**Cold Start (First Access)**:
- Model download from B2: ~30-60s for 5GB model
- Subsequent access: Instant (cached)

**Cache Hit Performance**:
- Equivalent to local disk access
- No network latency

**Cache Miss Performance**:
- Network latency: ~50-200ms
- Download speed: Depends on B2 → RunPod bandwidth


### B2 Sync Performance

**Initial Sync Time** (depends on model library size):
- 10GB: ~2-5 minutes
- 50GB: ~10-20 minutes
- 100GB: ~20-40 minutes

**Subsequent Syncs**:
- Only changed files downloaded
- Typically < 1 minute if no changes

**Runtime Performance**:
- Equivalent to local disk (files are local)
- No network latency

### Optimization Recommendations

**For Frequent Access (Daily Use)**:
- Use `b2-sync` for best performance
- Sync on boot, use local files

**For Infrequent Access (Occasional Use)**:
- Use `b2-mount` to save sync time
- Set large cache size (50-100GB)

**For Large Model Libraries (100GB+)**:
- Use `b2-mount` with 100GB+ cache
- Store cache on network volume
- Consider hybrid approach (common models in image)

**Hybrid Strategy**:
1. Bake top 5-10 most-used models into Docker image
2. Mount B2 for full model library
3. ComfyUI checks local first, then B2 mount

## Cost Analysis

### Storage Costs Comparison

**Network Volume** (RunPod):
- Cost: ~$0.10/GB/month = ~$100/TB/month
- Performance: Fast (local network)
- Persistence: Tied to RunPod account

**Backblaze B2**:
- Storage: $0.005/GB/month = ~$5/TB/month
- Egress: Free via Cloudflare
- Performance: Network-dependent
- Persistence: Independent of compute

### Example Cost Scenarios

**Scenario 1: 50GB Model Library**
- Network Volume: $5/month
- B2: $0.25/month
- **Savings: $4.75/month (95%)**

**Scenario 2: 200GB Model Library**
- Network Volume: $20/month
- B2: $1/month
- **Savings: $19/month (95%)**

**Scenario 3: 1TB Model Library**
- Network Volume: $100/month
- B2: $5/month
- **Savings: $95/month (95%)**

### Break-Even Analysis

B2 is cost-effective when:
- Model library > 10GB
- Models accessed infrequently
- Multiple projects share same models

Network volumes are better when:
- Model library < 10GB
- Models accessed constantly
- Absolute minimum latency required


## Security Considerations

### Credential Management

**Best Practices**:
1. Store B2 credentials in `.env` file (never commit to Git)
2. Use application keys with restricted permissions
3. Create read-only keys for production deployments
4. Rotate keys periodically
5. Use separate keys for different environments

**B2 Application Key Permissions**:
- Production: Read-only access to specific bucket
- Development: Read/write access for uploading models
- Never use master application key

### Network Security

**B2 Access**:
- All traffic over HTTPS
- S3-compatible API with authentication
- No public bucket access required

**rclone Security**:
- Credentials stored in config file (not in process list)
- Read-only mount prevents accidental writes
- Cache directory permissions restricted to root user

## Deployment Considerations

### Docker Image Changes

**Dockerfile Additions**:
```dockerfile
# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Create storage scripts directory
COPY storage/ /comfyui/storage/
RUN chmod +x /comfyui/storage/*.sh

# Install fuse for rclone mount
RUN apt-get update && apt-get install -y fuse && rm -rf /var/lib/apt/lists/*
```

### Environment Variables in .env.example

```bash
# Storage Backend Selection
STORAGE_BACKEND=network-volume  # Options: network-volume, b2-mount, b2-sync

# Backblaze B2 Configuration (required for b2-mount or b2-sync)
B2_BUCKET=my-comfyui-models
B2_KEY_ID=your_key_id_here
B2_APP_KEY=your_app_key_here
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_PATH=models  # Optional: subdirectory within bucket

# rclone Mount Configuration (for b2-mount only)
RCLONE_CACHE_SIZE=20G  # Adjust based on needs: 20G, 50G, 100G, etc.
RCLONE_CACHE_MAX_AGE=24h  # How long to keep cached files
```

### RunPod Configuration

**Network Volume Requirements**:
- Minimum size: 50GB (for cache + outputs)
- Recommended: 100GB+ (for large model caches)
- Mount point: `/runpod-volume`

**Container Disk**:
- For b2-mount: Minimal (cache on network volume)
- For b2-sync: Must fit entire model library + 10GB buffer

### Migration Path

**From Network Volume to B2**:
1. Upload models to B2 using `upload_to_b2.py`
2. Update `.env` with B2 credentials
3. Set `STORAGE_BACKEND=b2-mount` or `b2-sync`
4. Restart container
5. Verify models accessible
6. Optionally remove models from network volume

**From B2 Back to Network Volume**:
1. Set `STORAGE_BACKEND=network-volume`
2. Restart container
3. System uses network volume automatically


## Implementation Notes

### File Structure

```
runpod-serverless/
├── storage/                      # New directory for storage backends
│   ├── setup_b2_mount.sh        # Mount B2 with rclone
│   ├── setup_b2_sync.sh         # Sync B2 to local
│   ├── upload_to_b2.py          # Upload models to B2
│   ├── manage_b2.py             # Manage B2 bucket
│   └── README.md                # Storage backend documentation
├── entrypoint.sh                # Enhanced with storage backend logic
├── Dockerfile                   # Enhanced with rclone installation
├── .env.example                 # Updated with B2 variables
└── README.md                    # Updated with B2 documentation
```

### Integration Points

**Entrypoint Script**:
- Add storage backend detection after SSH/OpenZiti setup
- Call appropriate setup script based on STORAGE_BACKEND
- Fail fast if setup fails

**Handler**:
- No changes required
- Works transparently with any storage backend

**ComfyUI**:
- No changes required
- Loads models from configured path regardless of backend

### Backward Compatibility

**Guarantees**:
1. If STORAGE_BACKEND not set → use network-volume (existing behavior)
2. If B2 variables not set → use network-volume (existing behavior)
3. No changes to existing code paths
4. Existing deployments continue working without modification

### Future Enhancements

**Potential Additions**:
1. Support for other S3-compatible storage (AWS S3, Cloudflare R2, MinIO)
2. Automatic model download from HuggingFace to B2
3. Model versioning and rollback
4. Multi-region B2 support for global deployments
5. Intelligent caching based on model usage patterns
6. Compression for model storage

## Documentation Requirements

### README Sections to Add

1. **Storage Backend Options**
   - Comparison table
   - When to use each option
   - Cost analysis

2. **B2 Setup Guide**
   - Creating B2 account
   - Creating bucket
   - Generating application keys
   - Configuring environment variables

3. **Uploading Models to B2**
   - Using upload_to_b2.py script
   - Using rclone directly
   - Using B2 web interface

4. **Performance Tuning**
   - Cache size recommendations
   - Network optimization
   - Hybrid strategies

5. **Troubleshooting**
   - Common errors and solutions
   - Debugging mount issues
   - Verifying B2 connectivity

6. **Cost Optimization**
   - Storage cost calculator
   - Cache size vs performance trade-offs
   - When to use sync vs mount

### Example Configurations

**Example 1: Small Model Library (< 20GB)**
```bash
STORAGE_BACKEND=b2-mount
RCLONE_CACHE_SIZE=20G
```

**Example 2: Large Model Library (100GB+)**
```bash
STORAGE_BACKEND=b2-mount
RCLONE_CACHE_SIZE=100G
```

**Example 3: Maximum Performance**
```bash
STORAGE_BACKEND=b2-sync
# Syncs all models to local disk on boot
```

**Example 4: Hybrid Approach**
```bash
# Bake common models in Docker image
# Mount B2 for full library
STORAGE_BACKEND=b2-mount
RCLONE_CACHE_SIZE=50G
```
