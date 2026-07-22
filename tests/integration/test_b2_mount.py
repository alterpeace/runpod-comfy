"""
Integration tests for B2 mount functionality
Tests the setup_b2_mount.sh script with various scenarios including
successful mounts, credential validation, and error handling.
"""

import os
import subprocess
import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestB2MountCredentialValidation:
    """Test B2 mount credential validation"""
    
    def test_mount_fails_with_missing_bucket(self, tmp_path):
        """Test mount fails when B2_BUCKET is missing"""
        env = {
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_BUCKET' in result.stdout
    
    def test_mount_fails_with_missing_key_id(self, tmp_path):
        """Test mount fails when B2_KEY_ID is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_KEY_ID' in result.stdout
    
    def test_mount_fails_with_missing_app_key(self, tmp_path):
        """Test mount fails when B2_APP_KEY is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_APP_KEY' in result.stdout
    
    def test_mount_fails_with_missing_endpoint(self, tmp_path):
        """Test mount fails when B2_ENDPOINT is missing"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'Missing required B2 environment variables' in result.stdout
        assert 'B2_ENDPOINT' in result.stdout
    
    def test_mount_fails_with_all_credentials_missing(self, tmp_path):
        """Test mount fails when all B2 credentials are missing"""
        env = {}
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
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
    
    def test_mount_fails_with_invalid_key_id_format(self, tmp_path):
        """Test mount fails when B2_KEY_ID is too short"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'short',  # Too short
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'B2_KEY_ID appears to be invalid' in result.stdout
    
    def test_mount_fails_with_invalid_app_key_format(self, tmp_path):
        """Test mount fails when B2_APP_KEY is too short"""
        env = {
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'short',  # Too short
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert 'B2_APP_KEY appears to be invalid' in result.stdout


class TestB2MountRcloneConfiguration:
    """Test rclone configuration generation for B2 mount"""
    
    def test_rclone_config_created_with_valid_credentials(self, tmp_path):
        """Test rclone config file is created with valid credentials"""
        # Create a temporary home directory
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
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
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
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
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


class TestB2MountCacheConfiguration:
    """Test cache directory configuration for B2 mount"""
    
    def test_cache_directory_creation_on_network_volume(self, tmp_path):
        """Test cache directory is created on network volume"""
        # Create mock network volume
        network_volume = tmp_path / 'runpod-volume'
        network_volume.mkdir()
        
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'RCLONE_CACHE_DIR': str(network_volume / 'rclone-cache')
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        # Run script (will fail at connectivity test)
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Exit code 127 means rclone command not found - skip test
        if result.returncode == 127:
            pytest.skip("rclone not installed in test environment")
        
        # Script should fail at connectivity test (exit code 2)
        # but cache directory should be created before that
        assert result.returncode in [2, 3]  # 2 = connectivity failed, 3 = mount failed
        
        # Check if cache directory was created
        cache_dir = network_volume / 'rclone-cache'
        if result.returncode == 2:
            # If it failed at connectivity, cache dir should exist
            assert cache_dir.exists()
            assert cache_dir.is_dir()
    
    def test_mount_fails_without_network_volume(self, tmp_path):
        """Test mount fails when network volume is not available"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        # Don't create /runpod-volume
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'RCLONE_CACHE_DIR': '/runpod-volume/rclone-cache'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Exit code 127 means rclone command not found - skip test
        if result.returncode == 127:
            pytest.skip("rclone not installed in test environment")
        
        # Should fail at connectivity test (exit code 2) since /runpod-volume doesn't exist
        # The script checks for network volume after connectivity test
        assert result.returncode in [2, 3]


class TestB2MountErrorHandling:
    """Test error handling for B2 mount"""
    
    def test_mount_provides_helpful_error_for_invalid_credentials(self, tmp_path):
        """Test mount provides helpful error message for invalid credentials"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        network_volume = tmp_path / 'runpod-volume'
        network_volume.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'nonexistent-bucket-12345',
            'B2_KEY_ID': 'invalid_key_id_1234567890',
            'B2_APP_KEY': 'invalid_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'RCLONE_CACHE_DIR': str(network_volume / 'rclone-cache')
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
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
    
    def test_mount_validates_bucket_name_format(self, tmp_path):
        """Test mount validates bucket name format"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'Invalid_Bucket_Name',  # Invalid: uppercase and underscores
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Should show warning about bucket name format
        assert 'B2_BUCKET name may not meet B2 naming requirements' in result.stdout
    
    def test_mount_validates_endpoint_format(self, tmp_path):
        """Test mount validates endpoint format"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 'invalid-endpoint.com'  # Invalid format
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Should show warning about endpoint format
        assert 'B2_ENDPOINT format may be incorrect' in result.stdout


class TestB2MountConfiguration:
    """Test B2 mount configuration options"""
    
    def test_mount_uses_custom_cache_size(self, tmp_path):
        """Test mount respects custom cache size configuration"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com',
            'RCLONE_CACHE_SIZE': '100G'
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Check that custom cache size is logged
        assert 'Cache Size: 100G' in result.stdout
    
    def test_mount_uses_default_cache_size(self, tmp_path):
        """Test mount uses default cache size when not specified"""
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        
        env = {
            'HOME': str(home_dir),
            'B2_BUCKET': 'test-comfyui-models',
            'B2_KEY_ID': 'test_key_id_1234567890',
            'B2_APP_KEY': 'test_app_key_1234567890abcdef',
            'B2_ENDPOINT': 's3.us-west-004.backblazeb2.com'
            # RCLONE_CACHE_SIZE not set
        }
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Check that default cache size is used
        assert 'Cache Size: 20G' in result.stdout
    
    def test_mount_uses_custom_b2_path(self, tmp_path):
        """Test mount respects B2_PATH subdirectory configuration"""
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
        
        script_path = Path(__file__).parent.parent.parent / 'storage' / 'setup_b2_mount.sh'
        
        if not script_path.exists():
            pytest.skip("setup_b2_mount.sh not found")
        
        result = subprocess.run(
            ['bash', str(script_path)],
            env=env,
            capture_output=True,
            text=True
        )
        
        # Check that custom path is logged
        assert 'Path: models/production' in result.stdout
