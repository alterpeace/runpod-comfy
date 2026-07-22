# S3/Cloud Storage for ComfyUI Outputs

This document explains how to configure and use S3-compatible storage for ComfyUI generated outputs.

## Overview

The S3 storage module allows you to automatically upload ComfyUI generated images to:
- **AWS S3** - Amazon's object storage service
- **Cloudflare R2** - S3-compatible storage with zero egress fees
- **MinIO** - Self-hosted S3-compatible storage
- **Any S3-compatible service**

## Installation

The S3 storage functionality requires the `boto3` library:

```bash
# Add boto3 as an optional dependency
uv add boto3

# Or install in Docker image
pip install boto3
```

## Configuration

### Environment Variables

Configure S3 storage using environment variables in your `.env` file:

```bash
# Enable S3 storage
STORAGE_TYPE=s3

# Required: S3 bucket name
S3_BUCKET=my-comfyui-outputs

# Required: AWS credentials
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# Optional: AWS region (defaults to us-east-1)
S3_REGION=us-west-2

# Optional: Custom endpoint for S3-compatible services
# Leave unset for AWS S3
S3_ENDPOINT_URL=https://...

# Optional: Prefix for object keys (folder path in bucket)
S3_PREFIX=comfyui-outputs

# Optional: Make uploaded files publicly readable
S3_PUBLIC=false
```

### AWS S3 Configuration

For standard AWS S3:

```bash
STORAGE_TYPE=s3
S3_BUCKET=my-bucket
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_REGION=us-east-1
```

### Cloudflare R2 Configuration

For Cloudflare R2 (S3-compatible with zero egress fees):

```bash
STORAGE_TYPE=s3
S3_BUCKET=my-bucket
AWS_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_REGION=auto
```

### MinIO Configuration

For self-hosted MinIO:

```bash
STORAGE_TYPE=s3
S3_BUCKET=comfyui
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
S3_ENDPOINT_URL=http://minio:9000
S3_REGION=us-east-1
```

## Object Key Structure

Uploaded files are organized with the following structure:

```
{S3_PREFIX}/{YYYY}/{MM}/{DD}/{prompt_id}/node_{node_id}/{filename}
```

Example:
```
comfyui-outputs/2024/01/15/abc123def456/node_5/output_00001.png
```

This structure provides:
- **Date-based organization** - Easy to find outputs by date
- **Prompt ID grouping** - All outputs from one workflow together
- **Node identification** - Track which node generated each output

## Output Format

When using S3 storage, the handler returns URLs instead of base64-encoded images:

```json
{
  "status": "success",
  "output": {
    "images": [
      {
        "filename": "output_00001.png",
        "type": "output",
        "node_id": "5",
        "s3_key": "comfyui-outputs/2024/01/15/abc123/node_5/output_00001.png",
        "url": "https://my-bucket.s3.us-east-1.amazonaws.com/comfyui-outputs/2024/01/15/abc123/node_5/output_00001.png",
        "bucket": "my-bucket",
        "size": 1048576,
        "content_type": "image/png"
      }
    ],
    "prompt_id": "abc123"
  }
}
```

## Public vs Private Objects

### Private Objects (Default)

By default, uploaded objects are private and require AWS credentials to access:

```bash
S3_PUBLIC=false  # or omit this variable
```

The returned URL will be an S3 URI:
```
s3://my-bucket/comfyui-outputs/2024/01/15/abc123/output.png
```

To access private objects, use presigned URLs (see below).

### Public Objects

To make objects publicly readable:

```bash
S3_PUBLIC=true
```

The returned URL will be a public HTTPS URL:
```
https://my-bucket.s3.us-east-1.amazonaws.com/comfyui-outputs/2024/01/15/abc123/output.png
```

**Security Note**: Only enable public access if you want anyone to be able to view your generated images.

## Presigned URLs

For private objects, you can generate temporary presigned URLs:

```python
from storage_s3 import create_s3_client_from_env

# Initialize client
s3_client = create_s3_client_from_env()

# Generate presigned URL (valid for 1 hour)
url = s3_client.generate_presigned_url(
    key='comfyui-outputs/2024/01/15/abc123/output.png',
    expiration=3600
)

print(url)
# https://my-bucket.s3.amazonaws.com/...?X-Amz-Algorithm=...
```

## Metadata

Each uploaded file includes metadata:

- `prompt_id` - ComfyUI workflow execution ID
- `node_id` - Node that generated the output
- `type` - Output type (usually "output")
- `generated_at` - ISO 8601 timestamp

View metadata using AWS CLI:
```bash
aws s3api head-object \
  --bucket my-bucket \
  --key comfyui-outputs/2024/01/15/abc123/output.png
```

## Content Types

The module automatically detects content types based on file extensions:

| Extension | Content Type |
|-----------|-------------|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.webp` | `image/webp` |
| `.gif` | `image/gif` |
| `.bmp` | `image/bmp` |
| `.tiff`, `.tif` | `image/tiff` |
| Other | `application/octet-stream` |

## Error Handling

The S3 module provides detailed error messages:

### Bucket Not Found
```
S3StorageError: Bucket 'my-bucket' does not exist
```

**Solution**: Create the bucket or check the bucket name.

### Access Denied
```
S3StorageError: Access denied to bucket 'my-bucket'. Check credentials and permissions.
```

**Solution**: Verify AWS credentials and IAM permissions.

### Connection Error
```
S3StorageError: S3 connection error: ...
```

**Solution**: Check network connectivity and endpoint URL.

### boto3 Not Installed
```
HandlerError: S3 storage not available. Install boto3: uv add boto3
```

**Solution**: Install boto3 library.

## IAM Permissions

Your AWS credentials need the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ]
    }
  ]
}
```

## Cost Considerations

### AWS S3
- **Storage**: ~$0.023/GB/month (Standard)
- **PUT requests**: $0.005 per 1,000 requests
- **GET requests**: $0.0004 per 1,000 requests
- **Data transfer out**: $0.09/GB (first 10TB)

### Cloudflare R2
- **Storage**: ~$0.015/GB/month
- **Operations**: $4.50 per million Class A operations (writes)
- **Data transfer out**: **FREE** (zero egress fees)

**Recommendation**: Use Cloudflare R2 for significant cost savings, especially if you download images frequently.

## Testing

Test S3 connectivity:

```python
from storage_s3 import create_s3_client_from_env

# Initialize and test
client = create_s3_client_from_env()
if client:
    client.test_connection()
    print("S3 connection successful!")
```

## Comparison with Other Storage Types

| Storage Type | Pros | Cons | Best For |
|-------------|------|------|----------|
| **Response** (base64) | Simple, no setup | Limited to ~10MB, slow | Small images, testing |
| **Volume** | Fast, persistent | Requires network volume | RunPod persistent storage |
| **S3** | Scalable, durable, accessible | Requires setup, costs | Production, sharing, archival |

## Example Usage

### Basic Workflow

1. Configure S3 in `.env`:
```bash
STORAGE_TYPE=s3
S3_BUCKET=my-comfyui-outputs
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

2. Submit workflow to handler:
```python
import requests

response = requests.post(
    'https://api.runpod.ai/v2/your-endpoint/run',
    json={
        'input': {
            'workflow': {...}  # Your ComfyUI workflow
        }
    }
)

result = response.json()
image_url = result['output']['images'][0]['url']
print(f"Image uploaded to: {image_url}")
```

3. Download the image:
```python
import requests

image_response = requests.get(image_url)
with open('output.png', 'wb') as f:
    f.write(image_response.content)
```

## Troubleshooting

### Images not uploading

1. Check boto3 is installed: `uv run python -c "import boto3; print(boto3.__version__)"`
2. Verify environment variables are set correctly
3. Test S3 connection using the test script above
4. Check handler logs for error messages

### Access denied errors

1. Verify AWS credentials are correct
2. Check IAM permissions include `s3:PutObject`
3. Ensure bucket exists and is in the correct region
4. For R2, verify account ID in endpoint URL

### Slow uploads

1. Choose a region close to your RunPod instance
2. Consider using Cloudflare R2 for better global performance
3. Check network connectivity and bandwidth

## Additional Resources

- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/)
- [MinIO Documentation](https://min.io/docs/)
- [boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
