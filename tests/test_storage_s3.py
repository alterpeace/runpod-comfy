"""
Unit tests for S3 storage module
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Import the module - boto3 is optional so tests work without it
from storage_s3 import (
    S3StorageClient,
    S3StorageError,
    create_s3_client_from_env
)


class TestS3StorageClient:
    """Test S3StorageClient functionality"""
    
    @patch('storage_s3.BOTO3_AVAILABLE', True)
    @patch('storage_s3.boto3')
    def test_init_success(self, mock_boto3):
        """Test successful S3 client initialization"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            region='us-west-2',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        assert client.bucket == 'test-bucket'
        assert client.region == 'us-west-2'
        assert client.prefix == 'comfyui-outputs'
        
        mock_boto3.client.assert_called_once_with(
            's3',
            region_name='us-west-2',
            endpoint_url=None,
            aws_access_key_id='test-key',
            aws_secret_access_key='test-secret'
        )
    
    @patch('storage_s3.boto3')
    def test_init_with_endpoint(self, mock_boto3):
        """Test initialization with custom endpoint (R2, MinIO)"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            endpoint_url='https://s3.example.com',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        assert client.endpoint_url == 'https://s3.example.com'
        
        mock_boto3.client.assert_called_once()
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs['endpoint_url'] == 'https://s3.example.com'
    
    def test_init_missing_bucket(self):
        """Test initialization fails without bucket"""
        with pytest.raises(S3StorageError, match="bucket name is required"):
            S3StorageClient(
                bucket='',
                access_key='test-key',
                secret_key='test-secret'
            )
    
    @patch('storage_s3.boto3')
    def test_init_missing_credentials(self, mock_boto3):
        """Test initialization fails without credentials"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(S3StorageError, match="credentials not found"):
                S3StorageClient(bucket='test-bucket')
    
    @patch('storage_s3.boto3')
    def test_get_content_type(self, mock_boto3):
        """Test content type detection"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        assert client._get_content_type('image.png') == 'image/png'
        assert client._get_content_type('photo.jpg') == 'image/jpeg'
        assert client._get_content_type('photo.jpeg') == 'image/jpeg'
        assert client._get_content_type('image.webp') == 'image/webp'
        # Test unknown extension falls back to default
        assert client._get_content_type('unknown.unknownext') == 'application/octet-stream'
    
    @patch('storage_s3.boto3')
    def test_generate_object_key(self, mock_boto3):
        """Test S3 object key generation"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret',
            prefix='outputs'
        )
        
        # Test basic key
        key = client._generate_object_key('test.png')
        assert key.startswith('outputs/')
        assert key.endswith('/test.png')
        
        # Test with prompt_id
        key = client._generate_object_key('test.png', prompt_id='abc123')
        assert 'abc123' in key
        assert key.endswith('/test.png')
        
        # Test with node_id
        key = client._generate_object_key('test.png', node_id='5')
        assert 'node_5' in key
        assert key.endswith('/test.png')
        
        # Test with both
        key = client._generate_object_key(
            'test.png',
            prompt_id='abc123',
            node_id='5'
        )
        assert 'abc123' in key
        assert 'node_5' in key
        assert key.endswith('/test.png')
    
    @patch('storage_s3.boto3')
    def test_upload_file_success(self, mock_boto3):
        """Test successful file upload"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            region='us-east-1',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        file_data = b'fake image data'
        result = client.upload_file(
            file_data=file_data,
            filename='test.png',
            prompt_id='abc123'
        )
        
        # Verify upload was called
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]
        
        assert call_kwargs['Bucket'] == 'test-bucket'
        assert call_kwargs['Body'] == file_data
        assert call_kwargs['ContentType'] == 'image/png'
        assert 'test.png' in call_kwargs['Key']
        
        # Verify result
        assert result['bucket'] == 'test-bucket'
        assert result['size'] == len(file_data)
        assert result['content_type'] == 'image/png'
        assert 'key' in result
        assert 'url' in result
    
    @patch('storage_s3.boto3')
    def test_upload_file_with_metadata(self, mock_boto3):
        """Test file upload with metadata"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        metadata = {
            'prompt_id': 'abc123',
            'node_id': '5',
            'type': 'output'
        }
        
        client.upload_file(
            file_data=b'test',
            filename='test.png',
            metadata=metadata
        )
        
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert 'Metadata' in call_kwargs
        assert call_kwargs['Metadata']['prompt_id'] == 'abc123'
    
    @patch('storage_s3.boto3')
    def test_upload_file_public(self, mock_boto3):
        """Test public file upload"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            region='us-east-1',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        result = client.upload_file(
            file_data=b'test',
            filename='test.png',
            public=True
        )
        
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs['ACL'] == 'public-read'
        
        # Public URL should be HTTPS
        assert result['url'].startswith('https://')
        assert 'test-bucket' in result['url']
    
    @patch('storage_s3.boto3')
    def test_upload_file_error(self, mock_boto3):
        """Test upload error handling"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        # Mock ClientError
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': 'NoSuchBucket',
                'Message': 'The specified bucket does not exist'
            }
        }
        mock_s3_client.put_object.side_effect = ClientError(
            error_response,
            'PutObject'
        )
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        with pytest.raises(S3StorageError, match="S3 upload failed"):
            client.upload_file(
                file_data=b'test',
                filename='test.png'
            )
    
    @patch('storage_s3.boto3')
    def test_generate_presigned_url(self, mock_boto3):
        """Test presigned URL generation"""
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = 'https://presigned-url.com'
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        url = client.generate_presigned_url('path/to/file.png', expiration=7200)
        
        assert url == 'https://presigned-url.com'
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            'get_object',
            Params={'Bucket': 'test-bucket', 'Key': 'path/to/file.png'},
            ExpiresIn=7200
        )
    
    @patch('storage_s3.boto3')
    def test_test_connection_success(self, mock_boto3):
        """Test successful connection test"""
        mock_s3_client = Mock()
        mock_s3_client.head_bucket.return_value = {}
        mock_boto3.client.return_value = mock_s3_client
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        assert client.test_connection() is True
        mock_s3_client.head_bucket.assert_called_once_with(Bucket='test-bucket')
    
    @patch('storage_s3.boto3')
    def test_test_connection_bucket_not_found(self, mock_boto3):
        """Test connection test with non-existent bucket"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client
        
        from botocore.exceptions import ClientError
        error_response = {'Error': {'Code': '404'}}
        mock_s3_client.head_bucket.side_effect = ClientError(
            error_response,
            'HeadBucket'
        )
        
        client = S3StorageClient(
            bucket='test-bucket',
            access_key='test-key',
            secret_key='test-secret'
        )
        
        with pytest.raises(S3StorageError, match="does not exist"):
            client.test_connection()


class TestCreateS3ClientFromEnv:
    """Test environment-based S3 client creation"""
    
    @patch('storage_s3.S3StorageClient')
    def test_create_from_env_success(self, mock_client_class):
        """Test successful client creation from environment"""
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance
        
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
        
        assert client == mock_instance
        mock_client_class.assert_called_once_with(
            bucket='my-bucket',
            region='us-west-2',
            endpoint_url='https://s3.example.com',
            prefix='my-outputs'
        )
    
    def test_create_from_env_no_bucket(self):
        """Test returns None when S3_BUCKET not set"""
        with patch.dict(os.environ, {}, clear=True):
            client = create_s3_client_from_env()
        
        assert client is None
    
    @patch('storage_s3.S3StorageClient')
    def test_create_from_env_default_prefix(self, mock_client_class):
        """Test default prefix when not specified"""
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance
        
        env_vars = {
            'S3_BUCKET': 'my-bucket',
            'AWS_ACCESS_KEY_ID': 'test-key',
            'AWS_SECRET_ACCESS_KEY': 'test-secret'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            client = create_s3_client_from_env()
        
        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs['prefix'] == 'comfyui-outputs'
