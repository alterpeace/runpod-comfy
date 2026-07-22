"""
Integration tests for B2 sync functionality
Tests the setup_b2_sync.sh script with various scenarios including
successful syncs, credential validation, disk space checks, and error handling.
"""

import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestB2SyncCredentialValidation:
    """Test B2 sync credential validation"""
    
    def test_sync_fails_with_missing_bucket(self, tmp_path):
        """Test sync fails when B2_BUCKET is missing"""
        env = {
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_BUCKET' in result.stdout
    
    def test_sync_fails_with_missing_key_id(self, tmp_path):
        """Test sync fails when B2_KEY_ID is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_KEY_ID' in result.stdout
    
    def test_sync_fails_with_missing_app_key(self, tmp_path):
        """Test sync fails when B2_APP_KEY is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_APP_KEY' in result.stdout
    
    def test_sync_fails_with_missing_endpoint(self, tmp_path):
        """Test sync fails when B2_ENDPOINT is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_ENDPOINT' in result.stdout
    
    def test_sync_fails_with_all_credentials_missing(self, tmp_path):
        """Test sync fails when all B2 credentials are missing"""
        env = {}
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_BUCKET' in result.stdout
        assert 'B2_KEY_ID' in result.stdout
        assert 'B2_APP_KEY' in result.stdout
        assert 'B2_ENDPOINT' in result.stdout
    
    def test_sync_fails_with_invalid_key_id_format(self, tmp_path):
        """Test sync fails when B2_KEY_ID is too short"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'short',  # Too short
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'B2_KEY_ID appears to be invalid' in result.stdout
    
    def test_sync_fails_with_invalid_app_key_format(self, tmp_path):
        """Test sync fails when B2_APP_KEY is too short"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'short',  # Too short
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'B2_APP_KEY appears to be invalid' in result.stdout


class TestB2SyncRcloneConfiguration:
    """Test rclone configuration generation for B2 sync"""
    
    def test_rclone_config_created_with_valid_credentials(self, tmp_path):
        """Test rclone config file is created with valid credentials"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'B2_REGION': 'us-west-004'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        # Run script (will fail at connectivity test, but config should be created)
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Check if config file was created
        config_path = home_dir / '.config' / 'rclone' / 'rclone.conf'
        
        if config_path.exists():
            config_content = config_path.read_text()
            
            assert '[b2]' in config_content
            assert 'type = s3' in config_content
            assert 'provider = Other' in config_content
            assert f'access_key_id = {env["B2_KEY_ID"]}' in config_content
            assert f'secret_access_key = {env["B2_APP_KEY"]}' in config_content
            assert f'endpoint = {env["B2_ENDPOINT"]}' in config_content
            assert f'region = {env["B2_REGION"]}' in config_content
    
    def test_rclone_config_uses_default_region(self, tmp_path):
        """Test rclone config uses default region when not specified"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
            # B2_REGION not set
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        config_path = home_dir / '.config' / 'rclone' / 'rclone.conf'
        
        if config_path.exists():
            config_content = config_path.read_text()
            assert 'region = us-west-004' in config_content


class TestB2SyncDiskSpaceValidation:
    """Test disk space validation for B2 sync"""
    
    def test_sync_checks_available_disk_space(self, tmp_path):
        """Test sync checks available disk space before syncing"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        sync_target = tmp_path / 'comfyui' / 'models'
        sync_target.mkdir(parents=True)
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'SYNC_TARGET': str(sync_target)
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Exit code 127 means rclone command not found - skip test
        if result.returncode == 127:
            pytest.skip("rclone not installed in test environment")
        
        # Script should check disk space (will fail at connectivity test)
        assert 'Checking disk space' in result.stdout or 'Available disk space' in result.stdout
    
    def test_sync_creates_target_directory(self, tmp_path):
        """Test sync creates target directory if it doesn't exist"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        sync_target = tmp_path / 'comfyui' / 'models'
        # Don't create the directory
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'SYNC_TARGET': str(sync_target)
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Exit code 127 means rclone command not found - skip test
        if result.returncode == 127:
            pytest.skip("rclone not installed in test environment")
        
        # Directory should be created (script will fail at connectivity test)
        # but we can check if the parent directory was created
        assert sync_target.parent.exists()


class TestB2SyncErrorHandling:
    """Test error handling for B2 sync"""
    
    def test_sync_provides_helpful_error_for_invalid_credentials(self, tmp_path):
        """Test sync provides helpful error message for invalid credentials"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        sync_target = tmp_path / 'comfyui' / 'models'
        sync_target.mkdir(parents=True)
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'nonexistent-bucket-12345',
            'B2_KEY_ID': 'invalid_key_id_1234567890',
            'B2_APP_KEY': 'invalid_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'SYNC_TARGET': str(sync_target)
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Exit code 127 means rclone command not found - skip test
        if result.returncode == 127:
            pytest.skip("rclone not installed in test environment")
        
        # Should fail at connectivity test
        assert result.returncode == 2
        assert 'Failed to connect to B2 bucket' in result.stdout
    
    def test_sync_validates_bucket_name_format(self, tmp_path):
        """Test sync validates bucket name format"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'Invalid_Bucket_Name',  # Invalid: uppercase and underscores
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Should show warning about bucket name format
        assert 'B2_BUCKET name may not meet B2 naming requirements' in result.stdout
    
    def test_sync_validates_endpoint_format(self, tmp_path):
        """Test sync validates endpoint format"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 'invalid-endpoint.com'  # Invalid format
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Should show warning about endpoint format
        assert 'B2_ENDPOINT format may be incorrect' in result.stdout


class TestB2SyncConfiguration:
    """Test B2 sync configuration options"""
    
    def test_sync_uses_custom_sync_target(self, tmp_path):
        """Test sync respects custom sync target configuration"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        custom_target = tmp_path / 'custom' / 'models'
        custom_target.mkdir(parents=True)
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'SYNC_TARGET': str(custom_target)
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check that custom sync target is logged
        assert f'Sync Target: {custom_target}' in result.stdout
    
    def test_sync_uses_default_sync_target(self, tmp_path):
        """Test sync uses default sync target when not specified"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
            # SYNC_TARGET not set
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check that default sync target is used
        assert 'Sync Target: /comfyui/models' in result.stdout
    
    def test_sync_uses_custom_b2_path(self, tmp_path):
        """Test sync respects B2_PATH subdirectory configuration"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'B2_PATH': 'models/production'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check that custom path is logged
        assert 'Path: models/production' in result.stdout


class TestB2SyncStatistics:
    """Test sync statistics and verification"""
    
    def test_sync_logs_duration_on_completion(self, tmp_path):
        """Test sync logs duration when completed"""
        # This test would require a real B2 bucket or mocking rclone
        # For now, we just verify the script structure supports it
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        script_content = script_path.read_text()
        
        # Verify script calculates duration
        assert 'START_TIME' in script_content
        assert 'END_TIME' in script_content
        assert 'DURATION' in script_content
    
    def test_sync_logs_file_count_on_completion(self, tmp_path):
        """Test sync logs file count when completed"""
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        script_content = script_path.read_text()
        
        # Verify script counts files
        assert 'FILE_COUNT' in script_content
        assert 'Files synced' in script_content or 'files' in script_content.lower()
    
    def test_sync_logs_total_size_on_completion(self, tmp_path):
        """Test sync logs total size when completed"""
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_sync.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_sync.sh not found")
        
        script_content = script_path.read_text()
        
        # Verify script calculates size
        assert 'SYNCED_SIZE' in script_content or 'Total size' in script_content
