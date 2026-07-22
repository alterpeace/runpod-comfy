"""
Integration tests for S3 storage with handler
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock boto3 availability
with patch('storage_s3.BOTO3_AVAILABLE', True):
    from handler import process_outputs, HandlerError
    from storage_s3 import S3StorageClient, S3StorageError


class TestS3Integration:
    """Test S3 storage integration with handler"""
    
    @patch('handler.S3_AVAILABLE', True)
    @patch('handler.s3_client')
    @patch('handler.STORAGE_TYPE', 's3')
    def test_process_outputs_s3_success(self, mock_s3_client):
        """Test successful S3 upload through process_outputs"""
        # Mock S3 client upload
        mock_s3_client.upload_file.return_value = {
            'key': 'comfyui-outputs/2024/01/15/abc123/output.png',
            'url': 'https://bucket.s3.amazonaws.com/comfyui-outputs/2024/01/15/abc123/output.png',
            'bucket': 'test-bucket',
            'size': 1024,
            'content_type': 'image/png'
        }
        
        # Test outputs
        outputs = [
            {
                'filename': 'output.png',
                'data': b'fake image data',
                'type': 'output',
                'node_id': '5'
            }
        ]
        
        # Process outputs
        result = process_outputs(outputs, prompt_id='abc123')
        
        # Verify S3 upload was called
        mock_s3_client.upload_file.assert_called_once()
        call_kwargs = mock_s3_client.upload_file.call_args[1]
        
        assert call_kwargs['filename'] == 'output.png'
        assert call_kwargs['file_data'] == b'fake image data'
        assert call_kwargs['prompt_id'] == 'abc123'
        assert call_kwargs['node_id'] == '5'
        
        # Verify result
        assert len(result) == 1
        assert result[0]['filename'] == 'output.png'
        assert result[0]['s3_key'] == 'comfyui-outputs/2024/01/15/abc123/output.png'
        assert result[0]['url'].startswith('https://')
        assert result[0]['bucket'] == 'test-bucket'
        assert result[0]['size'] == 1024
        assert 'data' not in result[0]  # Should not include base64 data
    
    @patch('handler.S3_AVAILABLE', True)
    @patch('handler.s3_client')
    @patch('handler.STORAGE_TYPE', 's3')
    def test_process_outputs_s3_multiple_files(self, mock_s3_client):
        """Test S3 upload with multiple output files"""
        # Mock S3 client upload
        def mock_upload(file_data, filename, **kwargs):
            return {
                'key': f'comfyui-outputs/2024/01/15/{filename}',
                'url': f'https://bucket.s3.amazonaws.com/{filename}',
                'bucket': 'test-bucket',
                'size': len(file_data),
                'content_type': 'image/png'
            }
        
        mock_s3_client.upload_file.side_effect = mock_upload
        
        # Test outputs
        outputs = [
            {
                'filename': 'output1.png',
                'data': b'image1',
                'type': 'output',
                'node_id': '5'
            },
            {
                'filename': 'output2.png',
                'data': b'image2',
                'type': 'output',
                'node_id': '6'
            }
        ]
        
        # Process outputs
        result = process_outputs(outputs, prompt_id='abc123')
        
        # Verify both uploads
        assert mock_s3_client.upload_file.call_count == 2
        assert len(result) == 2
        assert result[0]['filename'] == 'output1.png'
        assert result[1]['filename'] == 'output2.png'
    
    @patch('handler.S3_AVAILABLE', False)
    @patch('handler.STORAGE_TYPE', 's3')
    def test_process_outputs_s3_not_available(self):
        """Test error when S3 requested but boto3 not installed"""
        outputs = [
            {
                'filename': 'output.png',
                'data': b'fake image data',
                'type': 'output'
            }
        ]
        
        with pytest.raises(HandlerError, match="S3 storage not available"):
            process_outputs(outputs, prompt_id='abc123')
    
    @patch('handler.S3_AVAILABLE', True)
    @patch('handler.s3_client', None)
    @patch('handler.STORAGE_TYPE', 's3')
    def test_process_outputs_s3_client_not_initialized(self):
        """Test error when S3 client not initialized"""
        outputs = [
            {
                'filename': 'output.png',
                'data': b'fake image data',
                'type': 'output'
            }
        ]
        
        with pytest.raises(HandlerError, match="S3 client not initialized"):
            process_outputs(outputs, prompt_id='abc123')
    
    @patch('handler.S3_AVAILABLE', True)
    @patch('handler.s3_client')
    @patch('handler.STORAGE_TYPE', 's3')
    @patch('handler.S3StorageError', S3StorageError)
    def test_process_outputs_s3_upload_failure(self, mock_s3_client):
        """Test error handling when S3 upload fails"""
        # Mock S3 upload failure
        mock_s3_client.upload_file.side_effect = S3StorageError("Upload failed")
        
        outputs = [
            {
                'filename': 'output.png',
                'data': b'fake image data',
                'type': 'output'
            }
        ]
        
        with pytest.raises(HandlerError, match="S3 upload failed"):
            process_outputs(outputs, prompt_id='abc123')


class TestS3ClientCreation:
    """Test S3 client creation from environment"""
    
    @patch('storage_s3.BOTO3_AVAILABLE', True)
    @patch('storage_s3.boto3')
    def test_create_s3_client_from_env(self, mock_boto3):
        """Test S3 client creation from environment variables"""
        from storage_s3 import create_s3_client_from_env
        
        mock_s3_client = Mock()
        mock_s3_client.head_bucket.return_value = {}
        mock_boto3.client.return_value = mock_s3_client
        
        env_vars = {
            'S3_BUCKET': 'my-bucket',
            'S3_REGION': 'us-west-2',
            'S3_ENDPOINT_URL': 'https://s3.example.com',
            'AWS_ACCESS_KEY_ID': 'test-key',
            'AWS_SECRET_ACCESS_KEY': 'test-secret',
            'S3_PREFIX': 'my-outputs'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            client = create_s3_client_from_env()
        
        assert client is not None
        assert client.bucket == 'my-bucket'
        assert client.region == 'us-west-2'
        assert client.endpoint_url == 'https://s3.example.com'
        assert client.prefix == 'my-outputs'
    
    @patch('storage_s3.BOTO3_AVAILABLE', True)
    def test_create_s3_client_no_bucket(self):
        """Test returns None when S3_BUCKET not set"""
        from storage_s3 import create_s3_client_from_env
        
        with patch.dict(os.environ, {}, clear=True):
            client = create_s3_client_from_env()
        
        assert client is None
