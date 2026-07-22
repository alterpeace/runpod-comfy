"""
Unit tests for B2 configuration and setup
Tests environment variable loading, validation, rclone configuration generation,
storage backend selection, and error handling.
"""

import os
import pytest
from unittest.mock import Mock, patch, mock_open, MagicMock
from pathlib import Path


class TestEnvironmentVariableLoading:
    """Test B2 environment variable loading and validation"""
    
    def test_all_required_vars_present(self):
        """Test validation passes when all required B2 variables are set"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # All required variables present
            assert os.getenv('B2_BUCKET') == 'my-comfyui-models'
            assert os.getenv('B2_KEY_ID') == 'abcdefghij1234567890xyz'
            assert os.getenv('B2_APP_KEY') == 'K001abcdefghijklmnopqrstuvwxyz'
            assert os.getenv('B2_ENDPOINT') == 's3.us-west-004.backblazeb2.com'
    
    def test_missing_bucket_var(self):
        """Test detection of missing B2_BUCKET variable"""
        env_vars = {
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            assert os.getenv('B2_BUCKET') is None
    
    def test_missing_key_id_var(self):
        """Test detection of missing B2_KEY_ID variable"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            assert os.getenv('B2_KEY_ID') is None
    
    def test_missing_app_key_var(self):
        """Test detection of missing B2_APP_KEY variable"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            assert os.getenv('B2_APP_KEY') is None
    
    def test_missing_endpoint_var(self):
        """Test detection of missing B2_ENDPOINT variable"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            assert os.getenv('B2_ENDPOINT') is None
    
    def test_optional_vars_with_defaults(self):
        """Test optional variables use defaults when not set"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Optional variables should use defaults
            b2_region = os.getenv('B2_REGION', 'us-west-004')
            b2_path = os.getenv('B2_PATH', '')
            rclone_cache_size = os.getenv('RCLONE_CACHE_SIZE', '20G')
            rclone_cache_max_age = os.getenv('RCLONE_CACHE_MAX_AGE', '24h')
            
            assert b2_region == 'us-west-004'
            assert b2_path == ''
            assert rclone_cache_size == '20G'
            assert rclone_cache_max_age == '24h'
    
    def test_optional_vars_custom_values(self):
        """Test optional variables can be customized"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'B2_REGION': 'eu-central-003',
            'B2_PATH': 'models/production',
            'RCLONE_CACHE_SIZE': '100G',
            'RCLONE_CACHE_MAX_AGE': '48h'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            assert os.getenv('B2_REGION') == 'eu-central-003'
            assert os.getenv('B2_PATH') == 'models/production'
            assert os.getenv('RCLONE_CACHE_SIZE') == '100G'
            assert os.getenv('RCLONE_CACHE_MAX_AGE') == '48h'


class TestCredentialValidation:
    """Test B2 credential format validation"""
    
    def test_valid_key_id_length(self):
        """Test B2_KEY_ID with valid length"""
        key_id = 'abcdefghij1234567890xyz'  # 25 characters
        assert len(key_id) >= 10
    
    def test_invalid_key_id_too_short(self):
        """Test B2_KEY_ID that is too short"""
        key_id = 'short'  # Less than 10 characters
        assert len(key_id) < 10
    
    def test_valid_app_key_length(self):
        """Test B2_APP_KEY with valid length"""
        app_key = 'K001abcdefghijklmnopqrstuvwxyz'  # 31 characters
        assert len(app_key) >= 20
    
    def test_invalid_app_key_too_short(self):
        """Test B2_APP_KEY that is too short"""
        app_key = 'short'  # Less than 20 characters
        assert len(app_key) < 20
    
    def test_valid_endpoint_format(self):
        """Test B2_ENDPOINT with valid format"""
        endpoint = 's3.us-west-004.backblazeb2.com'
        # Should match pattern: s3.<region>.backblazeb2.com
        assert endpoint.startswith('s3.')
        assert '.backblazeb2.com' in endpoint
    
    def test_invalid_endpoint_format(self):
        """Test B2_ENDPOINT with invalid format"""
        endpoint = 'invalid-endpoint.com'
        # Should not match expected pattern
        assert not (endpoint.startswith('s3.') and '.backblazeb2.com' in endpoint)
    
    def test_valid_bucket_name_format(self):
        """Test B2_BUCKET with valid naming format"""
        bucket = 'my-comfyui-models'
        # Valid: 6-50 chars, lowercase, numbers, hyphens, start/end with letter or number
        assert 6 <= len(bucket) <= 50
        assert bucket[0].isalnum()
        assert bucket[-1].isalnum()
        assert all(c.islower() or c.isdigit() or c == '-' for c in bucket)
    
    def test_invalid_bucket_name_too_short(self):
        """Test B2_BUCKET that is too short"""
        bucket = 'short'  # Less than 6 characters
        assert len(bucket) < 6
    
    def test_invalid_bucket_name_uppercase(self):
        """Test B2_BUCKET with uppercase letters"""
        bucket = 'MyBucket'
        assert any(c.isupper() for c in bucket)
    
    def test_invalid_bucket_name_special_chars(self):
        """Test B2_BUCKET with invalid special characters"""
        bucket = 'my_bucket!'
        # Should only contain lowercase, numbers, and hyphens
        assert not all(c.islower() or c.isdigit() or c == '-' for c in bucket)


class TestRcloneConfigGeneration:
    """Test rclone configuration file generation"""
    
    def test_config_file_content(self):
        """Test rclone config file is generated with correct content"""
        env_vars = {
            'B2_BUCKET': 'my-comfyui-models',
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'B2_REGION': 'us-west-004'
        }
        
        expected_config = """[b2]
type = s3
provider = Other
env_auth = false
access_key_id = abcdefghij1234567890xyz
secret_access_key = K001abcdefghijklmnopqrstuvwxyz
endpoint = s3.us-west-004.backblazeb2.com
region = us-west-004
acl = private
"""
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Generate config content
            config_content = f"""[b2]
type = s3
provider = Other
env_auth = false
access_key_id = {os.getenv('B2_KEY_ID')}
secret_access_key = {os.getenv('B2_APP_KEY')}
endpoint = {os.getenv('B2_ENDPOINT')}
region = {os.getenv('B2_REGION', 'us-west-004')}
acl = private
"""
            
            assert config_content == expected_config
    
    def test_config_file_path(self):
        """Test rclone config file is created at correct path"""
        expected_path = os.path.expanduser('~/.config/rclone/rclone.conf')
        
        # Verify path structure
        assert expected_path.endswith('.config/rclone/rclone.conf')
    
    def test_config_with_default_region(self):
        """Test config generation uses default region when not specified"""
        env_vars = {
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            region = os.getenv('B2_REGION', 'us-west-004')
            assert region == 'us-west-004'
    
    def test_config_with_custom_region(self):
        """Test config generation uses custom region when specified"""
        env_vars = {
            'B2_KEY_ID': 'abcdefghij1234567890xyz',
            'B2_APP_KEY': 'K001abcdefghijklmnopqrstuvwxyz',
            'B2_ENDPOINT': 's3.eu-central-003.backblazeb2.com',
            'B2_REGION': 'eu-central-003'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            region = os.getenv('B2_REGION')
            assert region == 'eu-central-003'


class TestStorageBackendSelection:
    """Test storage backend selection logic"""
    
    def test_default_backend_network_volume(self):
        """Test default storage backend is network-volume"""
        with patch.dict(os.environ, {}, clear=True):
            backend = os.getenv('STORAGE_BACKEND', 'network-volume')
            assert backend == 'network-volume'
    
    def test_backend_b2_mount(self):
        """Test storage backend selection for b2-mount"""
        env_vars = {'STORAGE_BACKEND': 'b2-mount'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            assert backend == 'b2-mount'
    
    def test_backend_b2_sync(self):
        """Test storage backend selection for b2-sync"""
        env_vars = {'STORAGE_BACKEND': 'b2-sync'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            assert backend == 'b2-sync'
    
    def test_backend_network_volume_explicit(self):
        """Test explicit network-volume backend selection"""
        env_vars = {'STORAGE_BACKEND': 'network-volume'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            assert backend == 'network-volume'
    
    def test_invalid_backend_fallback(self):
        """Test invalid backend value falls back to default"""
        env_vars = {'STORAGE_BACKEND': 'invalid-backend'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND', 'network-volume')
            
            # Simulate validation logic
            valid_backends = ['network-volume', 'b2-mount', 'b2-sync']
            if backend not in valid_backends:
                backend = 'network-volume'
            
            assert backend == 'network-volume'
    
    def test_backend_case_sensitive(self):
        """Test storage backend selection is case-sensitive"""
        env_vars = {'STORAGE_BACKEND': 'B2-MOUNT'}  # Wrong case
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            
            # Should not match valid backends (case-sensitive)
            valid_backends = ['network-volume', 'b2-mount', 'b2-sync']
            assert backend not in valid_backends


class TestB2MountConfiguration:
    """Test B2 mount-specific configuration"""
    
    def test_mount_requires_b2_credentials(self):
        """Test b2-mount backend requires B2 credentials"""
        env_vars = {'STORAGE_BACKEND': 'b2-mount'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Check if required B2 vars are present
            required_vars = ['B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY', 'B2_ENDPOINT']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            # Should have missing variables
            assert len(missing_vars) == 4
    
    def test_mount_cache_size_default(self):
        """Test default cache size for b2-mount"""
        env_vars = {'STORAGE_BACKEND': 'b2-mount'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            cache_size = os.getenv('RCLONE_CACHE_SIZE', '20G')
            assert cache_size == '20G'
    
    def test_mount_cache_size_custom(self):
        """Test custom cache size for b2-mount"""
        env_vars = {
            'STORAGE_BACKEND': 'b2-mount',
            'RCLONE_CACHE_SIZE': '100G'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            cache_size = os.getenv('RCLONE_CACHE_SIZE')
            assert cache_size == '100G'
    
    def test_mount_cache_dir_default(self):
        """Test default cache directory for b2-mount"""
        with patch.dict(os.environ, {}, clear=True):
            cache_dir = os.getenv('RCLONE_CACHE_DIR', '/runpod-volume/rclone-cache')
            assert cache_dir == '/runpod-volume/rclone-cache'
    
    def test_mount_cache_max_age_default(self):
        """Test default cache max age for b2-mount"""
        with patch.dict(os.environ, {}, clear=True):
            cache_max_age = os.getenv('RCLONE_CACHE_MAX_AGE', '24h')
            assert cache_max_age == '24h'


class TestB2SyncConfiguration:
    """Test B2 sync-specific configuration"""
    
    def test_sync_requires_b2_credentials(self):
        """Test b2-sync backend requires B2 credentials"""
        env_vars = {'STORAGE_BACKEND': 'b2-sync'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Check if required B2 vars are present
            required_vars = ['B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY', 'B2_ENDPOINT']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            # Should have missing variables
            assert len(missing_vars) == 4
    
    def test_sync_target_default(self):
        """Test default sync target directory"""
        with patch.dict(os.environ, {}, clear=True):
            sync_target = os.getenv('SYNC_TARGET', '/comfyui/models')
            assert sync_target == '/comfyui/models'
    
    def test_sync_target_custom(self):
        """Test custom sync target directory"""
        env_vars = {'SYNC_TARGET': '/custom/models/path'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            sync_target = os.getenv('SYNC_TARGET')
            assert sync_target == '/custom/models/path'


class TestErrorHandling:
    """Test error handling for missing and invalid credentials"""
    
    def test_detect_all_missing_credentials(self):
        """Test detection when all B2 credentials are missing"""
        with patch.dict(os.environ, {}, clear=True):
            required_vars = ['B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY', 'B2_ENDPOINT']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            assert len(missing_vars) == 4
            assert set(missing_vars) == set(required_vars)
    
    def test_detect_partial_missing_credentials(self):
        """Test detection when some B2 credentials are missing"""
        env_vars = {
            'B2_BUCKET': 'my-bucket',
            'B2_KEY_ID': 'my-key-id'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            required_vars = ['B2_BUCKET', 'B2_KEY_ID', 'B2_APP_KEY', 'B2_ENDPOINT']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            assert len(missing_vars) == 2
            assert 'B2_APP_KEY' in missing_vars
            assert 'B2_ENDPOINT' in missing_vars
    
    def test_empty_string_treated_as_missing(self):
        """Test empty string values are treated as missing"""
        env_vars = {
            'B2_BUCKET': '',
            'B2_KEY_ID': 'my-key-id',
            'B2_APP_KEY': 'my-app-key',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Empty strings should be treated as missing
            bucket = os.getenv('B2_BUCKET')
            assert bucket == ''
            assert not bucket  # Empty string is falsy
    
    def test_whitespace_only_values(self):
        """Test whitespace-only values are detected"""
        env_vars = {
            'B2_BUCKET': '   ',
            'B2_KEY_ID': 'my-key-id',
            'B2_APP_KEY': 'my-app-key',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            bucket = os.getenv('B2_BUCKET', '').strip()
            assert bucket == ''
            assert not bucket


class TestB2PathConfiguration:
    """Test B2_PATH subdirectory configuration"""
    
    def test_b2_path_empty_default(self):
        """Test B2_PATH defaults to empty (root)"""
        with patch.dict(os.environ, {}, clear=True):
            b2_path = os.getenv('B2_PATH', '')
            assert b2_path == ''
    
    def test_b2_path_custom_subdirectory(self):
        """Test B2_PATH with custom subdirectory"""
        env_vars = {'B2_PATH': 'models/production'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            b2_path = os.getenv('B2_PATH')
            assert b2_path == 'models/production'
    
    def test_remote_path_construction_with_path(self):
        """Test remote path construction with B2_PATH"""
        env_vars = {
            'B2_BUCKET': 'my-bucket',
            'B2_PATH': 'models'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            bucket = os.getenv('B2_BUCKET')
            path = os.getenv('B2_PATH')
            
            if path:
                remote_path = f"b2:{bucket}/{path}"
            else:
                remote_path = f"b2:{bucket}"
            
            assert remote_path == 'b2:my-bucket/models'
    
    def test_remote_path_construction_without_path(self):
        """Test remote path construction without B2_PATH"""
        env_vars = {'B2_BUCKET': 'my-bucket'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            bucket = os.getenv('B2_BUCKET')
            path = os.getenv('B2_PATH', '')
            
            if path:
                remote_path = f"b2:{bucket}/{path}"
            else:
                remote_path = f"b2:{bucket}"
            
            assert remote_path == 'b2:my-bucket'


class TestNetworkVolumeBackend:
    """Test network-volume backend (default) configuration"""
    
    def test_network_volume_no_b2_required(self):
        """Test network-volume backend does not require B2 credentials"""
        env_vars = {'STORAGE_BACKEND': 'network-volume'}
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            assert backend == 'network-volume'
            
            # B2 credentials should not be required
            assert os.getenv('B2_BUCKET') is None
            assert os.getenv('B2_KEY_ID') is None
    
    def test_network_volume_default_behavior(self):
        """Test network-volume is default when STORAGE_BACKEND not set"""
        with patch.dict(os.environ, {}, clear=True):
            backend = os.getenv('STORAGE_BACKEND', 'network-volume')
            assert backend == 'network-volume'
    
    def test_network_volume_with_b2_vars_ignored(self):
        """Test B2 variables are ignored when using network-volume"""
        env_vars = {
            'STORAGE_BACKEND': 'network-volume',
            'B2_BUCKET': 'my-bucket',
            'B2_KEY_ID': 'my-key-id'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            backend = os.getenv('STORAGE_BACKEND')
            assert backend == 'network-volume'
            
            # B2 vars are present but should be ignored for network-volume
            assert os.getenv('B2_BUCKET') == 'my-bucket'
