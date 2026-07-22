# Requirements Document

## Introduction

This feature adds Backblaze B2 (S3-compatible) storage integration using rclone as an optional alternative to RunPod network volumes for storing ComfyUI models, custom nodes, and other large assets. The solution provides a cost-effective storage option (~$5/TB/month vs ~$100/TB/month for network volumes) while maintaining compatibility with the existing network volume approach. Users can choose between network volumes, B2 with rclone mount, or B2 with sync-on-boot based on their performance and cost requirements.

## Requirements

### Requirement 1: rclone Installation and Configuration

**User Story:** As a developer, I want rclone installed in my Docker image with B2 configuration support, so that I can mount or sync Backblaze B2 storage at runtime.

#### Acceptance Criteria

1. WHEN building the Docker image THEN it SHALL install the latest stable version of rclone
2. WHEN configuring rclone THEN it SHALL support B2 S3-compatible endpoint configuration
3. WHEN configuring rclone THEN it SHALL load configuration from environment variables
4. WHEN configuring rclone THEN it SHALL support both rclone.conf file and environment-based configuration
5. IF B2 credentials are invalid THEN the system SHALL log an error and fall back to local storage
6. WHEN rclone is configured THEN it SHALL validate connectivity to B2 before mounting

### Requirement 2: B2 Mount with rclone

**User Story:** As a developer, I want to mount B2 storage as a filesystem using rclone, so that ComfyUI can access models directly from cloud storage without manual syncing.

#### Acceptance Criteria

1. WHEN STORAGE_BACKEND is set to "b2-mount" THEN the system SHALL mount B2 bucket using rclone mount
2. WHEN mounting B2 THEN it SHALL use aggressive caching for performance (vfs-cache-mode full)
3. WHEN mounting B2 THEN it SHALL configure appropriate cache size based on available disk space
4. WHEN mounting B2 THEN it SHALL mount to the standard ComfyUI models directory
5. WHEN the mount fails THEN the system SHALL log the error and exit with a clear error message
6. WHEN the container stops THEN it SHALL unmount B2 storage gracefully
7. WHEN mounting B2 THEN it SHALL run rclone mount as a daemon process

### Requirement 3: B2 Sync on Boot

**User Story:** As a developer, I want to sync models from B2 to local storage on container startup, so that I can achieve maximum performance while still using cost-effective B2 storage.

#### Acceptance Criteria

1. WHEN STORAGE_BACKEND is set to "b2-sync" THEN the system SHALL sync B2 bucket contents to local storage on startup
2. WHEN syncing from B2 THEN it SHALL use parallel transfers for faster sync times
3. WHEN syncing from B2 THEN it SHALL skip files that already exist locally with matching checksums
4. WHEN syncing from B2 THEN it SHALL log sync progress and completion time
5. WHEN sync fails THEN the system SHALL log the error and exit with a clear error message
6. WHEN sync completes THEN ComfyUI SHALL use the local synced files
7. IF local storage is insufficient THEN the system SHALL detect and report the error before syncing

### Requirement 4: Storage Backend Selection

**User Story:** As a developer, I want to choose between network volumes, B2 mount, or B2 sync using a configuration variable, so that I can optimize for cost or performance based on my needs.

#### Acceptance Criteria

1. WHEN STORAGE_BACKEND is set to "network-volume" THEN the system SHALL use RunPod network volumes (existing behavior)
2. WHEN STORAGE_BACKEND is set to "b2-mount" THEN the system SHALL mount B2 storage using rclone
3. WHEN STORAGE_BACKEND is set to "b2-sync" THEN the system SHALL sync B2 storage to local disk on boot
4. WHEN STORAGE_BACKEND is not set THEN the system SHALL default to "network-volume"
5. IF STORAGE_BACKEND has an invalid value THEN the system SHALL log an error and use the default
6. WHEN using B2 storage THEN the system SHALL validate required B2 environment variables are present

### Requirement 5: Environment Variable Configuration

**User Story:** As a developer, I want to configure B2 storage using environment variables, so that I can easily switch between storage backends without modifying code.

#### Acceptance Criteria

1. WHEN configuring B2 THEN it SHALL support B2_BUCKET environment variable for bucket name
2. WHEN configuring B2 THEN it SHALL support B2_KEY_ID for access key ID
3. WHEN configuring B2 THEN it SHALL support B2_APP_KEY for application key
4. WHEN configuring B2 THEN it SHALL support B2_ENDPOINT for S3 endpoint URL
5. WHEN configuring B2 THEN it SHALL support B2_REGION for bucket region
6. WHEN configuring B2 THEN it SHALL support B2_PATH for subdirectory within bucket (optional)
7. WHEN configuring rclone mount THEN it SHALL support RCLONE_CACHE_SIZE for cache size configuration (e.g., "20G", "100G", "150G")
8. WHEN configuring rclone mount THEN it SHALL support RCLONE_CACHE_MAX_AGE for cache expiration (default 24h)
9. WHEN configuring rclone mount THEN it SHALL default to using /runpod-volume/rclone-cache for cache directory
10. IF required B2 variables are missing THEN the system SHALL log which variables are required

### Requirement 6: Performance Optimization for rclone Mount

**User Story:** As a developer, I want rclone mount to be optimized for ComfyUI model loading with configurable cache sizes up to 100GB+, so that I can achieve acceptable performance when using B2 storage with large models.

#### Acceptance Criteria

1. WHEN mounting B2 THEN it SHALL use --vfs-cache-mode full for complete file caching
2. WHEN mounting B2 THEN it SHALL configure --buffer-size for optimal read performance
3. WHEN mounting B2 THEN it SHALL use --vfs-read-ahead for prefetching data
4. WHEN mounting B2 THEN it SHALL disable polling with --poll-interval 0 for static content
5. WHEN mounting B2 THEN it SHALL use --dir-cache-time to cache directory listings
6. WHEN mounting B2 THEN it SHALL support RCLONE_CACHE_SIZE environment variable to configure cache size (default 20GB, support up to network volume capacity)
7. WHEN mounting B2 THEN it SHALL use --cache-dir=/runpod-volume/rclone-cache to store cache on network volume
8. WHEN mounting B2 THEN it SHALL use --read-only flag to prevent accidental writes to B2
9. WHEN using large cache sizes THEN it SHALL configure --vfs-cache-poll-interval to manage cache efficiently
10. WHEN mounting B2 THEN it SHALL check network volume space and log available capacity

### Requirement 7: VFS Cache on Network Volume

**User Story:** As a developer, I want to store the rclone VFS cache on the RunPod network volume, so that I can use large cache sizes (100GB+) without worrying about container disk space limits.

#### Acceptance Criteria

1. WHEN mounting B2 with rclone THEN it SHALL place the VFS cache directory on the network volume at /runpod-volume/rclone-cache
2. WHEN using network volume for cache THEN it SHALL create the cache directory structure automatically if it doesn't exist
3. WHEN using network volume for cache THEN the cache SHALL persist across container restarts
4. WHEN configuring cache size THEN it SHALL support sizes up to the network volume capacity (typically 100GB-1TB+)
5. WHEN starting the container THEN it SHALL check network volume space and log available capacity
6. WHEN documenting cache configuration THEN it SHALL recommend cache sizes based on model types (SD 1.5: 20GB, SDXL: 50GB, FLUX: 100GB+)
7. WHEN using network volume cache THEN it SHALL configure rclone with --cache-dir=/runpod-volume/rclone-cache
8. IF network volume space is low THEN it SHALL log a warning but continue operation
9. WHEN cache grows large THEN rclone SHALL automatically manage cache based on --vfs-cache-max-age and LRU policy

### Requirement 8: Hybrid Storage Strategy

**User Story:** As a developer, I want to use a hybrid approach with frequently-used models in the Docker image and less common models on B2, so that I can optimize both cost and performance.

#### Acceptance Criteria

1. WHEN building the Docker image THEN it SHALL support baking frequently-used models into the image
2. WHEN using B2 storage THEN it SHALL support mounting B2 to a secondary models directory
3. WHEN ComfyUI loads models THEN it SHALL check both local and B2-mounted directories
4. WHEN configuring hybrid storage THEN it SHALL support MODEL_PATHS environment variable with multiple paths
5. IF a model exists in multiple locations THEN ComfyUI SHALL prefer the local version

### Requirement 9: Cost and Performance Documentation

**User Story:** As a developer, I want clear documentation comparing storage options, so that I can make informed decisions about which storage backend to use.

#### Acceptance Criteria

1. WHEN reading documentation THEN it SHALL include a cost comparison table for network volumes vs B2
2. WHEN reading documentation THEN it SHALL include performance benchmarks for each storage backend
3. WHEN reading documentation THEN it SHALL explain when to use each storage option
4. WHEN reading documentation THEN it SHALL document cold start times for each approach
5. WHEN reading documentation THEN it SHALL explain the trade-offs between mount and sync approaches
6. WHEN reading documentation THEN it SHALL provide example configurations for common scenarios
7. WHEN reading documentation THEN it SHALL explain how to upload models to B2

### Requirement 10: B2 Upload and Management Tools

**User Story:** As a developer, I want helper scripts to upload models to B2 and manage B2 storage, so that I can easily populate and maintain my B2 bucket.

#### Acceptance Criteria

1. WHEN using the upload script THEN it SHALL upload local models directory to B2
2. WHEN uploading to B2 THEN it SHALL skip files that already exist with matching checksums
3. WHEN uploading to B2 THEN it SHALL use parallel uploads for faster transfer
4. WHEN uploading to B2 THEN it SHALL log upload progress and completion
5. WHEN using the management script THEN it SHALL list contents of B2 bucket
6. WHEN using the management script THEN it SHALL calculate total storage size and estimated costs
7. WHEN using the management script THEN it SHALL support deleting unused models from B2

### Requirement 11: Fallback and Error Handling

**User Story:** As a developer, I want robust error handling for B2 storage failures, so that my system can gracefully handle network issues or configuration problems.

#### Acceptance Criteria

1. WHEN B2 mount fails THEN the system SHALL log detailed error information
2. WHEN B2 sync fails THEN the system SHALL log detailed error information
3. WHEN B2 credentials are invalid THEN the system SHALL provide clear error messages
4. WHEN B2 bucket is not accessible THEN the system SHALL detect and report the issue
5. IF B2 storage fails during operation THEN the system SHALL log the error and continue with available models
6. WHEN network connectivity is lost THEN rclone SHALL attempt to reconnect automatically

### Requirement 12: Integration with Existing System

**User Story:** As a developer, I want B2 storage to integrate seamlessly with the existing RunPod serverless system, so that I can use it without breaking existing functionality.

#### Acceptance Criteria

1. WHEN B2 storage is not configured THEN the system SHALL work exactly as before with network volumes
2. WHEN using B2 storage THEN all existing features SHALL continue to work (OpenZiti, SSH, multi-mode)
3. WHEN switching between storage backends THEN it SHALL not require code changes
4. WHEN using B2 storage THEN the entrypoint script SHALL handle initialization before starting ComfyUI
5. WHEN using B2 storage THEN the handler SHALL work without modifications
6. WHEN using B2 storage in local mode THEN it SHALL work with Docker Compose

### Requirement 13: Security Best Practices

**User Story:** As a developer, I want B2 credentials to be handled securely, so that my storage access keys are not exposed.

#### Acceptance Criteria

1. WHEN configuring B2 THEN credentials SHALL be loaded from environment variables or .env file
2. WHEN configuring B2 THEN credentials SHALL NOT be committed to Git
3. WHEN configuring B2 THEN credentials SHALL NOT be baked into Docker images
4. WHEN documenting B2 setup THEN it SHALL include security warnings about credential handling
5. WHEN using B2 THEN it SHALL support read-only access for production deployments
6. WHEN logging B2 operations THEN it SHALL NOT log credentials or sensitive information
