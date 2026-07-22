#!/usr/bin/env python3
"""
B2 Upload Management Tool

Uploads local models to Backblaze B2 bucket using rclone with parallel transfers,
progress tracking, and checksum verification.
"""

import argparse
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class B2Config:
    """B2 storage configuration loaded from environment variables"""
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
        missing = [var for var in required if not os.getenv(var)]
        
        if missing:
            print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
            print("Required variables: B2_BUCKET, B2_KEY_ID, B2_APP_KEY, B2_ENDPOINT")
            return None
        
        return cls(
            bucket=os.getenv('B2_BUCKET'),
            key_id=os.getenv('B2_KEY_ID'),
            app_key=os.getenv('B2_APP_KEY'),
            endpoint=os.getenv('B2_ENDPOINT'),
            region=os.getenv('B2_REGION', 'us-west-004'),
            path=os.getenv('B2_PATH', '')
        )


def setup_rclone_config(config: B2Config) -> bool:
    """Generate rclone configuration from B2 config"""
    print("Setting up rclone configuration...")
    
    rclone_dir = Path.home() / '.config' / 'rclone'
    rclone_dir.mkdir(parents=True, exist_ok=True)
    
    config_content = f"""[b2]
type = s3
provider = Other
env_auth = false
access_key_id = {config.key_id}
secret_access_key = {config.app_key}
endpoint = {config.endpoint}
region = {config.region}
acl = private
"""
    
    config_file = rclone_dir / 'rclone.conf'
    try:
        config_file.write_text(config_content)
        print("✓ rclone configuration created")
        return True
    except Exception as e:
        print(f"ERROR: Failed to create rclone configuration: {e}")
        return False


def test_b2_connectivity(config: B2Config) -> bool:
    """Test connectivity to B2 bucket"""
    print("Testing B2 connectivity...")
    
    try:
        result = subprocess.run(
            ['rclone', 'lsd', f'b2:{config.bucket}', '--max-depth', '1'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✓ B2 connectivity verified")
            return True
        else:
            print(f"ERROR: Failed to connect to B2 bucket")
            print(f"rclone output: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("ERROR: Connection test timed out")
        return False
    except Exception as e:
        print(f"ERROR: Connection test failed: {e}")
        return False


def scan_local_directory(local_path: Path) -> List[Path]:
    """Scan local directory for files to upload"""
    print(f"Scanning local directory: {local_path}")
    
    if not local_path.exists():
        print(f"ERROR: Local path does not exist: {local_path}")
        return []
    
    if not local_path.is_dir():
        print(f"ERROR: Local path is not a directory: {local_path}")
        return []
    
    files = []
    for item in local_path.rglob('*'):
        if item.is_file():
            files.append(item)
    
    print(f"✓ Found {len(files)} files to process")
    return files


def get_directory_size(path: Path) -> int:
    """Calculate total size of directory in bytes"""
    total_size = 0
    for item in path.rglob('*'):
        if item.is_file():
            total_size += item.stat().st_size
    return total_size


def format_size(bytes_size: int) -> str:
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def upload_to_b2(
    local_path: Path,
    config: B2Config,
    remote_path: str = "",
    parallel: int = 8,
    skip_existing: bool = True
) -> Dict[str, any]:
    """
    Upload local directory to B2 bucket using rclone
    
    Args:
        local_path: Local directory to upload
        config: B2 configuration
        remote_path: Remote path within bucket (optional)
        parallel: Number of parallel transfers
        skip_existing: Skip files that already exist with matching checksums
    
    Returns:
        Dictionary with upload statistics
    """
    print("\n=== Starting B2 Upload ===")
    print(f"Local path: {local_path}")
    print(f"Bucket: {config.bucket}")
    print(f"Remote path: {remote_path or '<root>'}")
    print(f"Parallel transfers: {parallel}")
    print(f"Skip existing: {skip_existing}")
    print()
    
    # Calculate total size
    total_size = get_directory_size(local_path)
    print(f"Total size to upload: {format_size(total_size)}")
    print()
    
    # Construct remote destination
    if config.path and remote_path:
        remote_dest = f"b2:{config.bucket}/{config.path}/{remote_path}"
    elif config.path:
        remote_dest = f"b2:{config.bucket}/{config.path}"
    elif remote_path:
        remote_dest = f"b2:{config.bucket}/{remote_path}"
    else:
        remote_dest = f"b2:{config.bucket}"
    
    # Build rclone command
    cmd = [
        'rclone',
        'copy' if skip_existing else 'copyto',
        str(local_path),
        remote_dest,
        '--transfers', str(parallel),
        '--checkers', str(parallel * 2),
        '--progress',
        '--stats', '5s',
        '--stats-one-line',
        '--log-level', 'INFO'
    ]
    
    if skip_existing:
        cmd.extend(['--checksum'])
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    # Execute upload
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=False
        )
        
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print("\n✓ Upload completed successfully")
            
            stats = {
                'success': True,
                'duration': duration,
                'total_size': total_size,
                'error': None
            }
            
            print(f"\n=== Upload Statistics ===")
            print(f"Duration: {duration:.2f} seconds")
            print(f"Total size: {format_size(total_size)}")
            print(f"Average speed: {format_size(total_size / duration)}/s")
            
            return stats
        else:
            print(f"\nERROR: Upload failed with exit code {result.returncode}")
            return {
                'success': False,
                'duration': duration,
                'total_size': total_size,
                'error': f'rclone exited with code {result.returncode}'
            }
    
    except KeyboardInterrupt:
        print("\n\nUpload interrupted by user")
        return {
            'success': False,
            'duration': time.time() - start_time,
            'total_size': total_size,
            'error': 'Interrupted by user'
        }
    except Exception as e:
        print(f"\nERROR: Upload failed: {e}")
        return {
            'success': False,
            'duration': time.time() - start_time,
            'total_size': total_size,
            'error': str(e)
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Upload models to Backblaze B2 bucket',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload all models from local directory
  python upload_to_b2.py --local ./models
  
  # Upload to specific remote path
  python upload_to_b2.py --local ./models/checkpoints --remote checkpoints
  
  # Use custom bucket and parallel transfers
  python upload_to_b2.py --local ./models --bucket my-bucket --parallel 16
  
  # Force re-upload all files (don't skip existing)
  python upload_to_b2.py --local ./models --no-skip-existing

Environment Variables:
  B2_BUCKET      - B2 bucket name (required)
  B2_KEY_ID      - B2 access key ID (required)
  B2_APP_KEY     - B2 application key (required)
  B2_ENDPOINT    - B2 S3 endpoint URL (required)
  B2_REGION      - B2 region (optional, default: us-west-004)
  B2_PATH        - Base path within bucket (optional)
        """
    )
    
    parser.add_argument(
        '--local',
        type=str,
        required=True,
        help='Local directory to upload'
    )
    
    parser.add_argument(
        '--bucket',
        type=str,
        help='B2 bucket name (overrides B2_BUCKET env var)'
    )
    
    parser.add_argument(
        '--remote',
        type=str,
        default='',
        help='Remote path within bucket (optional)'
    )
    
    parser.add_argument(
        '--parallel',
        type=int,
        default=8,
        help='Number of parallel transfers (default: 8)'
    )
    
    parser.add_argument(
        '--no-skip-existing',
        action='store_true',
        help='Re-upload all files (don\'t skip existing files with matching checksums)'
    )
    
    args = parser.parse_args()
    
    # Load B2 configuration
    config = B2Config.from_env()
    if not config:
        sys.exit(1)
    
    # Override bucket if provided
    if args.bucket:
        config.bucket = args.bucket
    
    # Setup rclone configuration
    if not setup_rclone_config(config):
        sys.exit(2)
    
    # Test B2 connectivity
    if not test_b2_connectivity(config):
        sys.exit(2)
    
    # Validate local path
    local_path = Path(args.local).resolve()
    if not local_path.exists():
        print(f"ERROR: Local path does not exist: {local_path}")
        sys.exit(1)
    
    # Perform upload
    stats = upload_to_b2(
        local_path=local_path,
        config=config,
        remote_path=args.remote,
        parallel=args.parallel,
        skip_existing=not args.no_skip_existing
    )
    
    # Exit with appropriate code
    sys.exit(0 if stats['success'] else 3)


if __name__ == '__main__':
    main()
