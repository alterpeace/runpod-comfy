# Implementation Plan

- [x] 1. Set up storage directory structure and configuration
  - Create `runpod-serverless/storage/` directory
  - Update `.env.example` with B2 configuration variables (STORAGE_BACKEND, B2_BUCKET, B2_KEY_ID, B2_APP_KEY, B2_ENDPOINT, B2_REGION, B2_PATH, RCLONE_CACHE_SIZE, RCLONE_CACHE_MAX_AGE)
  - Create `storage/README.md` with storage backend documentation
  - _Requirements: 4.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [x] 2. Implement B2 mount setup script
  - Create `storage/setup_b2_mount.sh` script
  - Implement environment variable validation for required B2 credentials
  - Implement rclone configuration generation from environment variables
  - Implement network volume cache directory creation at /runpod-volume/rclone-cache
  - Implement B2 bucket mount with optimized rclone flags (vfs-cache-mode full, cache-dir, buffer-size, read-ahead, etc.)
  - Implement mount verification with timeout
  - Add error handling with specific exit codes (1: missing vars, 2: config failed, 3: mount failed, 4: verification failed)
  - Add logging for mount status and cache configuration
  - Make script executable
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 7.1, 7.2, 7.3, 7.7, 7.8_

- [x] 3. Implement B2 sync setup script
  - Create `storage/setup_b2_sync.sh` script
  - Implement environment variable validation for required B2 credentials
  - Implement rclone configuration generation from environment variables
  - Implement disk space checking before sync
  - Implement B2 to local sync with parallel transfers and progress logging
  - Implement sync statistics logging (files transferred, size, duration)
  - Add error handling with specific exit codes (1: missing vars, 2: config failed, 3: insufficient space, 4: sync failed)
  - Add logging for sync progress and completion
  - Make script executable
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Update entrypoint script for storage backend selection
  - Add STORAGE_BACKEND environment variable detection in entrypoint.sh
  - Implement storage backend case statement (network-volume, b2-mount, b2-sync)
  - Add call to setup_b2_mount.sh when STORAGE_BACKEND=b2-mount
  - Add call to setup_b2_sync.sh when STORAGE_BACKEND=b2-sync
  - Add default behavior for network-volume (no additional setup)
  - Add warning for unknown STORAGE_BACKEND values
  - Add error handling to exit if B2 setup fails
  - Add logging for which storage backend is being used
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 11.1, 11.2, 11.3, 11.4_

- [x] 5. Update Dockerfile for rclone support
  - Add rclone installation to Dockerfile using official install script
  - Add fuse package installation for rclone mount support
  - Copy storage/ directory to container
  - Set executable permissions for storage scripts
  - _Requirements: 1.1, 2.7_

- [x] 6. Implement B2 upload management tool
  - Create `storage/upload_to_b2.py` script
  - Implement B2 configuration loading from environment variables
  - Implement local directory scanning for models
  - Implement parallel upload to B2 with progress tracking
  - Implement skip logic for existing files with matching checksums
  - Add command-line argument parsing (--local, --bucket, --remote, --parallel)
  - Add upload statistics logging (files uploaded, size, duration)
  - Add error handling for upload failures
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 7. Implement B2 bucket management tool
  - Create `storage/manage_b2.py` script
  - Implement 'list' command to show bucket contents with sizes
  - Implement 'size' command to calculate total storage and estimated costs
  - Implement 'clean' command to delete old or unused models
  - Implement 'verify' command to check local vs B2 checksums
  - Add command-line argument parsing for subcommands
  - Add B2 configuration loading from environment variables
  - Add error handling for B2 API operations
  - _Requirements: 9.5, 9.6, 9.7_

- [x] 8. Add comprehensive error handling and validation
  - Implement B2 credential validation in setup scripts
  - Implement B2 connectivity testing before mount/sync
  - Implement network volume mount verification for cache directory
  - Add detailed error messages for common failure scenarios
  - Add logging for all error conditions
  - _Requirements: 1.5, 1.6, 5.9, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 9. Create unit tests for B2 configuration and setup
  - Create `tests/test_b2_config.py` for configuration parsing tests
  - Test environment variable loading and validation
  - Test rclone configuration generation
  - Test storage backend selection logic
  - Test error handling for missing/invalid credentials
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 10. Create integration tests for B2 storage
  - Create `tests/integration/test_b2_mount.py` for mount testing
  - Create `tests/integration/test_b2_sync.py` for sync testing
  - Test successful B2 mount with valid credentials
  - Test successful B2 sync with valid credentials
  - Test error handling for invalid credentials
  - Test cache directory creation on network volume
  - Test fallback to network volume when B2 not configured
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2_

- [x] 11. Update documentation with B2 storage guide
  - Add "Storage Backend Options" section to README with comparison table
  - Document when to use each storage option (network-volume, b2-mount, b2-sync)
  - Add cost analysis and comparison examples
  - Add "B2 Setup Guide" section with account creation and configuration steps
  - Document B2 application key creation and permissions
  - Add "Uploading Models to B2" section with upload_to_b2.py usage
  - Add "Performance Tuning" section with cache size recommendations
  - Document cache size recommendations for different model types (SD 1.5: 20GB, SDXL: 50GB, FLUX: 100GB+)
  - Add "Troubleshooting" section for common B2 issues
  - Add example configurations for different scenarios
  - Document security best practices for B2 credentials
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 12. Add storage backend examples and templates
  - Create example .env configurations for small model library (< 20GB)
  - Create example .env configurations for large model library (100GB+)
  - Create example .env configurations for maximum performance (b2-sync)
  - Create example .env configurations for hybrid approach
  - Document migration path from network volume to B2
  - Document migration path from B2 back to network volume
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.6_
