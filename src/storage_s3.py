"""
S3/Cloud Storage Module for ComfyUI Outputs

This module provides S3-compatible storage functionality for uploading
ComfyUI generated images to S3, R2, MinIO, or other S3-compatible services.
"""

import os
import logging
import mimetypes
from typing import Dict, Optional, Any
from pathlib import Path
from datetime import datetime

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class S3StorageError(Exception):
    """Base exception for S3 storage errors"""
    pass


class S3StorageClient:
    """
    S3-compatible storage client for uploading ComfyUI outputs.
    
    Supports AWS S3, Cloudflare R2, MinIO, and other S3-compatible services.
    """
    
    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        prefix: str = "comfyui-outputs"
    ):
        """
        Initialize S3 storage client.
        
        Args:
            bucket: S3 bucket name
            region: AWS region (optional, defaults to us-east-1)
            endpoint_url: Custom endpoint URL for S3-compatible services
            access_key: AWS access key ID (defaults to env var)
            secret_key: AWS secret access key (defaults to env var)
            prefix: Prefix for object keys (folder path)
            
        Raises:
            S3StorageError: If boto3 is not installed or configuration is invalid
        """
        if not BOTO3_AVAILABLE:
            raise S3StorageError(
                "boto3 is not installed. Install with: uv add boto3"
            )
        
        if not bucket:
            raise S3StorageError("S3 bucket name is required")
        
        self.bucket = bucket
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.endpoint_url = endpoint_url
        self.prefix = prefix.strip('/')
        
        # Get credentials from parameters or environment
        self.access_key = access_key or os.environ.get('AWS_ACCESS_KEY_ID')
        self.secret_key = secret_key or os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        if not self.access_key or not self.secret_key:
            raise S3StorageError(
                "AWS credentials not found. Set AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY environment variables or pass them "
                "as parameters."
            )
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            
            logger.info(
                f"S3 client initialized: bucket={bucket}, "
                f"region={self.region}, endpoint={endpoint_url or 'AWS'}"
            )
            
        except Exception as e:
            raise S3StorageError(f"Failed to initialize S3 client: {e}")
    
    def _get_content_type(self, filename: str) -> str:
        """
        Determine content type from filename.
        
        Args:
            filename: Name of the file
            
        Returns:
            MIME type string
        """
        content_type, _ = mimetypes.guess_type(filename)
        
        if content_type:
            return content_type
        
        # Default content types for common image formats
        ext = Path(filename).suffix.lower()
        default_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
        }
        
        return default_types.get(ext, 'application/octet-stream')
    
    def _generate_object_key(
        self,
        filename: str,
        prompt_id: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> str:
        """
        Generate S3 object key with organized structure.
        
        Args:
            filename: Original filename
            prompt_id: ComfyUI prompt ID
            node_id: ComfyUI node ID
            
        Returns:
            S3 object key (path)
        """
        # Use timestamp for organization
        timestamp = datetime.now().strftime('%Y/%m/%d')
        
        # Build path components
        parts = [self.prefix, timestamp]
        
        if prompt_id:
            parts.append(prompt_id)
        
        if node_id:
            parts.append(f"node_{node_id}")
        
        parts.append(filename)
        
        # Join with forward slashes
        key = '/'.join(parts)
        
        return key
    
    def upload_file(
        self,
        file_data: bytes,
        filename: str,
        prompt_id: Optional[str] = None,
        node_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        public: bool = False
    ) -> Dict[str, str]:
        """
        Upload file to S3.
        
        Args:
            file_data: File content as bytes
            filename: Name of the file
            prompt_id: ComfyUI prompt ID (for organization)
            node_id: ComfyUI node ID (for organization)
            metadata: Additional metadata to store with object
            public: Whether to make object publicly readable
            
        Returns:
            Dictionary containing:
            - key: S3 object key
            - url: Public URL (if public=True) or S3 URI
            - bucket: Bucket name
            - size: File size in bytes
            
        Raises:
            S3StorageError: If upload fails
        """
        try:
            # Generate object key
            key = self._generate_object_key(filename, prompt_id, node_id)
            
            # Determine content type
            content_type = self._get_content_type(filename)
            
            # Prepare upload parameters
            extra_args = {
                'ContentType': content_type,
            }
            
            # Add metadata if provided
            if metadata:
                # S3 metadata keys must be lowercase
                extra_args['Metadata'] = {
                    k.lower(): str(v) for k, v in metadata.items()
                }
            
            # Set ACL if public
            if public:
                extra_args['ACL'] = 'public-read'
            
            # Upload file
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_data,
                **extra_args
            )
            
            # Generate URL
            if public and not self.endpoint_url:
                # AWS S3 public URL
                url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
            elif public and self.endpoint_url:
                # Custom endpoint public URL
                base_url = self.endpoint_url.rstrip('/')
                url = f"{base_url}/{self.bucket}/{key}"
            else:
                # S3 URI for private objects
                url = f"s3://{self.bucket}/{key}"
            
            result = {
                'key': key,
                'url': url,
                'bucket': self.bucket,
                'size': len(file_data),
                'content_type': content_type
            }
            
            logger.info(
                f"Uploaded {filename} to S3: {key} ({len(file_data)} bytes)"
            )
            
            return result
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            raise S3StorageError(
                f"S3 upload failed ({error_code}): {error_msg}"
            )
        except BotoCoreError as e:
            raise S3StorageError(f"S3 connection error: {e}")
        except Exception as e:
            raise S3StorageError(f"Unexpected error during S3 upload: {e}")
    
    def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for temporary access to a private object.
        
        Args:
            key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL string
            
        Raises:
            S3StorageError: If URL generation fails
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': key
                },
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned URL for {key} (expires in {expiration}s)")
            return url
            
        except ClientError as e:
            raise S3StorageError(f"Failed to generate presigned URL: {e}")
    
    def test_connection(self) -> bool:
        """
        Test S3 connection and bucket access.
        
        Returns:
            True if connection is successful
            
        Raises:
            S3StorageError: If connection test fails
        """
        try:
            # Try to head the bucket
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.info(f"S3 connection test successful: bucket={self.bucket}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                raise S3StorageError(f"Bucket '{self.bucket}' does not exist")
            elif error_code == '403':
                raise S3StorageError(
                    f"Access denied to bucket '{self.bucket}'. "
                    "Check credentials and permissions."
                )
            else:
                raise S3StorageError(f"S3 connection test failed: {e}")
        except Exception as e:
            raise S3StorageError(f"S3 connection test failed: {e}")


def create_s3_client_from_env() -> Optional[S3StorageClient]:
    """
    Create S3 storage client from environment variables.
    
    Environment variables:
    - S3_BUCKET: Bucket name (required)
    - S3_REGION: AWS region (optional)
    - S3_ENDPOINT_URL: Custom endpoint for S3-compatible services (optional)
    - AWS_ACCESS_KEY_ID: Access key (required)
    - AWS_SECRET_ACCESS_KEY: Secret key (required)
    - S3_PREFIX: Object key prefix (optional, default: comfyui-outputs)
    
    Returns:
        S3StorageClient instance or None if not configured
    """
    bucket = os.environ.get('S3_BUCKET')
    
    if not bucket:
        logger.info("S3_BUCKET not set, S3 storage disabled")
        return None
    
    try:
        client = S3StorageClient(
            bucket=bucket,
            region=os.environ.get('S3_REGION'),
            endpoint_url=os.environ.get('S3_ENDPOINT_URL'),
            prefix=os.environ.get('S3_PREFIX', 'comfyui-outputs')
        )
        
        # Test connection
        client.test_connection()
        
        return client
        
    except S3StorageError as e:
        logger.error(f"Failed to initialize S3 client: {e}")
        raise
