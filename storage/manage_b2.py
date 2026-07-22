#!/usr/bin/env python3
"""
B2 Bucket Management Tool

Manage Backblaze B2 bucket contents with commands for listing, sizing,
cleaning, and verifying model files.
"""

import argparse
import os
import sys
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta


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
        return True
    except Exception as e:
        print(f"ERROR: Failed to create rclone configuration: {e}")
        return False


def format_size(bytes_size: int) -> str:
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def get_remote_path(config: B2Config, subpath: str = "") -> str:
    """Construct full remote path"""
    if config.path and subpath:
        return f"b2:{config.bucket}/{config.path}/{subpath}"
    elif config.path:
        return f"b2:{config.bucket}/{config.path}"
    elif subpath:
        return f"b2:{config.bucket}/{subpath}"
    else:
        return f"b2:{config.bucket}"


def list_bucket_contents(config: B2Config, path: str = "", recursive: bool = True) -> bool:
    """
    List bucket contents with sizes
    
    Args:
        config: B2 configuration
        path: Subdirectory to list (optional)
        recursive: List recursively
    
    Returns:
        True if successful, False otherwise
    """
    print("=== B2 Bucket Contents ===")
    print(f"Bucket: {config.bucket}")
    print(f"Path: {config.path or '<root>'}")
    if path:
        print(f"Subpath: {path}")
    print()
    
    remote_path = get_remote_path(config, path)
    
    # Use rclone ls for file listing with sizes
    cmd = ['rclone', 'ls', remote_path]
    
    if not recursive:
        cmd.extend(['--max-depth', '1'])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"ERROR: Failed to list bucket contents")
            print(f"rclone output: {result.stderr}")
            return False
        
        # Parse and display results
        lines = result.stdout.strip().split('\n')
        if not lines or lines[0] == '':
            print("Bucket is empty")
            return True
        
        total_size = 0
        file_count = 0
        
        print(f"{'Size':<12} {'File'}")
        print("-" * 80)
        
        for line in lines:
            if not line.strip():
                continue
            
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                size_str, filename = parts
                try:
                    size = int(size_str)
                    total_size += size
                    file_count += 1
                    print(f"{format_size(size):<12} {filename}")
                except ValueError:
                    continue
        
        print("-" * 80)
        print(f"\nTotal: {file_count} files, {format_size(total_size)}")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("ERROR: List operation timed out")
        return False
    except Exception as e:
        print(f"ERROR: Failed to list bucket: {e}")
        return False


def calculate_bucket_size(config: B2Config, path: str = "") -> bool:
    """
    Calculate total storage size and estimated costs
    
    Args:
        config: B2 configuration
        path: Subdirectory to calculate (optional)
    
    Returns:
        True if successful, False otherwise
    """
    print("=== B2 Storage Analysis ===")
    print(f"Bucket: {config.bucket}")
    print(f"Path: {config.path or '<root>'}")
    if path:
        print(f"Subpath: {path}")
    print()
    print("Calculating storage size...")
    
    remote_path = get_remote_path(config, path)
    
    # Use rclone size to get total size
    cmd = ['rclone', 'size', remote_path, '--json']
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            print(f"ERROR: Failed to calculate bucket size")
            print(f"rclone output: {result.stderr}")
            return False
        
        # Parse JSON output
        data = json.loads(result.stdout)
        total_size = data.get('bytes', 0)
        file_count = data.get('count', 0)
        
        # Calculate costs (B2 pricing as of 2024)
        storage_cost_per_gb_month = 0.005  # $0.005 per GB per month
        size_gb = total_size / (1024 ** 3)
        monthly_cost = size_gb * storage_cost_per_gb_month
        yearly_cost = monthly_cost * 12
        
        # Display results
        print("\n=== Storage Statistics ===")
        print(f"Total files: {file_count:,}")
        print(f"Total size: {format_size(total_size)} ({size_gb:.2f} GB)")
        print()
        print("=== Estimated Costs ===")
        print(f"Storage (monthly): ${monthly_cost:.2f}")
        print(f"Storage (yearly): ${yearly_cost:.2f}")
        print()
        print("Note: Costs are estimates based on B2 storage pricing ($0.005/GB/month)")
        print("      Actual costs may vary. Egress fees not included (free via Cloudflare).")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("ERROR: Size calculation timed out")
        return False
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse rclone output: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to calculate size: {e}")
        return False


def clean_old_files(
    config: B2Config,
    path: str = "",
    older_than_days: int = 90,
    pattern: str = "",
    dry_run: bool = True
) -> bool:
    """
    Delete old or unused models from B2
    
    Args:
        config: B2 configuration
        path: Subdirectory to clean (optional)
        older_than_days: Delete files older than this many days
        pattern: Only delete files matching this pattern (optional)
        dry_run: If True, only show what would be deleted
    
    Returns:
        True if successful, False otherwise
    """
    print("=== B2 Bucket Cleanup ===")
    print(f"Bucket: {config.bucket}")
    print(f"Path: {config.path or '<root>'}")
    if path:
        print(f"Subpath: {path}")
    print(f"Delete files older than: {older_than_days} days")
    if pattern:
        print(f"Pattern filter: {pattern}")
    print(f"Mode: {'DRY RUN (no files will be deleted)' if dry_run else 'LIVE (files will be deleted)'}")
    print()
    
    remote_path = get_remote_path(config, path)
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=older_than_days)
    
    # List files with modification times
    cmd = ['rclone', 'lsl', remote_path]
    if pattern:
        cmd.extend(['--include', pattern])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            print(f"ERROR: Failed to list files")
            print(f"rclone output: {result.stderr}")
            return False
        
        # Parse results and find old files
        lines = result.stdout.strip().split('\n')
        files_to_delete = []
        total_size_to_delete = 0
        
        for line in lines:
            if not line.strip():
                continue
            
            # Parse rclone lsl output: size date time filename
            parts = line.strip().split(None, 3)
            if len(parts) < 4:
                continue
            
            try:
                size = int(parts[0])
                date_str = parts[1]
                time_str = parts[2]
                filename = parts[3]
                
                # Parse modification time
                mod_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                
                # Check if file is older than cutoff
                if mod_time < cutoff_date:
                    files_to_delete.append((filename, size, mod_time))
                    total_size_to_delete += size
            except (ValueError, IndexError):
                continue
        
        if not files_to_delete:
            print("No files found matching criteria")
            return True
        
        # Display files to delete
        print(f"Found {len(files_to_delete)} files to delete:")
        print()
        print(f"{'Size':<12} {'Modified':<20} {'File'}")
        print("-" * 80)
        
        for filename, size, mod_time in files_to_delete:
            print(f"{format_size(size):<12} {mod_time.strftime('%Y-%m-%d %H:%M:%S'):<20} {filename}")
        
        print("-" * 80)
        print(f"\nTotal: {len(files_to_delete)} files, {format_size(total_size_to_delete)}")
        
        if dry_run:
            print("\nDRY RUN: No files were deleted")
            print("Run with --no-dry-run to actually delete these files")
            return True
        
        # Confirm deletion
        print("\nWARNING: This will permanently delete the files listed above!")
        response = input("Type 'DELETE' to confirm: ")
        
        if response != 'DELETE':
            print("Deletion cancelled")
            return True
        
        # Delete files
        print("\nDeleting files...")
        deleted_count = 0
        failed_count = 0
        
        for filename, size, mod_time in files_to_delete:
            file_path = f"{remote_path}/{filename}" if not remote_path.endswith(filename) else remote_path
            
            delete_cmd = ['rclone', 'deletefile', file_path]
            
            try:
                delete_result = subprocess.run(
                    delete_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if delete_result.returncode == 0:
                    deleted_count += 1
                    print(f"✓ Deleted: {filename}")
                else:
                    failed_count += 1
                    print(f"✗ Failed to delete: {filename}")
            except Exception as e:
                failed_count += 1
                print(f"✗ Error deleting {filename}: {e}")
        
        print(f"\nDeletion complete: {deleted_count} deleted, {failed_count} failed")
        return failed_count == 0
        
    except subprocess.TimeoutExpired:
        print("ERROR: Cleanup operation timed out")
        return False
    except Exception as e:
        print(f"ERROR: Cleanup failed: {e}")
        return False


def verify_checksums(config: B2Config, local_path: str, remote_path: str = "") -> bool:
    """
    Verify local files match B2 checksums
    
    Args:
        config: B2 configuration
        local_path: Local directory to verify
        remote_path: Remote path to compare against (optional)
    
    Returns:
        True if all files match, False otherwise
    """
    print("=== B2 Checksum Verification ===")
    print(f"Bucket: {config.bucket}")
    print(f"Local path: {local_path}")
    print(f"Remote path: {config.path or '<root>'}")
    if remote_path:
        print(f"Subpath: {remote_path}")
    print()
    
    local_dir = Path(local_path)
    if not local_dir.exists():
        print(f"ERROR: Local path does not exist: {local_path}")
        return False
    
    if not local_dir.is_dir():
        print(f"ERROR: Local path is not a directory: {local_path}")
        return False
    
    remote = get_remote_path(config, remote_path)
    
    print("Comparing local and remote files...")
    print("This may take a while for large directories...")
    print()
    
    # Use rclone check to compare checksums
    cmd = [
        'rclone', 'check',
        str(local_dir),
        remote,
        '--one-way',  # Only check files in local exist in remote
        '--checksum'  # Use checksums instead of size/modtime
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # rclone check returns 0 if all files match
        if result.returncode == 0:
            print("✓ All files verified successfully")
            print("Local files match remote checksums")
            return True
        else:
            print("✗ Verification failed - files do not match")
            print()
            
            # Parse output for details
            if result.stderr:
                print("Differences found:")
                print(result.stderr)
            
            return False
        
    except subprocess.TimeoutExpired:
        print("ERROR: Verification timed out")
        return False
    except Exception as e:
        print(f"ERROR: Verification failed: {e}")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Manage Backblaze B2 bucket contents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  list      List bucket contents with sizes
  size      Calculate total storage and estimated costs
  clean     Delete old or unused models
  verify    Verify local files match B2 checksums

Examples:
  # List all files in bucket
  python manage_b2.py list
  
  # List files in specific subdirectory
  python manage_b2.py list --path checkpoints
  
  # Calculate storage costs
  python manage_b2.py size
  
  # Clean files older than 90 days (dry run)
  python manage_b2.py clean --older-than 90
  
  # Actually delete old files
  python manage_b2.py clean --older-than 90 --no-dry-run
  
  # Clean specific file pattern
  python manage_b2.py clean --pattern "*.tmp" --no-dry-run
  
  # Verify local files match B2
  python manage_b2.py verify --local ./models

Environment Variables:
  B2_BUCKET      - B2 bucket name (required)
  B2_KEY_ID      - B2 access key ID (required)
  B2_APP_KEY     - B2 application key (required)
  B2_ENDPOINT    - B2 S3 endpoint URL (required)
  B2_REGION      - B2 region (optional, default: us-west-004)
  B2_PATH        - Base path within bucket (optional)
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List bucket contents')
    list_parser.add_argument(
        '--path',
        type=str,
        default='',
        help='Subdirectory to list (optional)'
    )
    list_parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Do not list recursively'
    )
    
    # Size command
    size_parser = subparsers.add_parser('size', help='Calculate storage size and costs')
    size_parser.add_argument(
        '--path',
        type=str,
        default='',
        help='Subdirectory to calculate (optional)'
    )
    
    # Clean command
    clean_parser = subparsers.add_parser('clean', help='Delete old or unused files')
    clean_parser.add_argument(
        '--path',
        type=str,
        default='',
        help='Subdirectory to clean (optional)'
    )
    clean_parser.add_argument(
        '--older-than',
        type=int,
        default=90,
        help='Delete files older than this many days (default: 90)'
    )
    clean_parser.add_argument(
        '--pattern',
        type=str,
        default='',
        help='Only delete files matching this pattern (optional)'
    )
    clean_parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Actually delete files (default is dry run)'
    )
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify local files match B2')
    verify_parser.add_argument(
        '--local',
        type=str,
        required=True,
        help='Local directory to verify'
    )
    verify_parser.add_argument(
        '--remote',
        type=str,
        default='',
        help='Remote path to compare against (optional)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Load B2 configuration
    config = B2Config.from_env()
    if not config:
        sys.exit(1)
    
    # Setup rclone configuration
    if not setup_rclone_config(config):
        sys.exit(2)
    
    # Execute command
    success = False
    
    try:
        if args.command == 'list':
            success = list_bucket_contents(
                config,
                path=args.path,
                recursive=not args.no_recursive
            )
        
        elif args.command == 'size':
            success = calculate_bucket_size(
                config,
                path=args.path
            )
        
        elif args.command == 'clean':
            success = clean_old_files(
                config,
                path=args.path,
                older_than_days=args.older_than,
                pattern=args.pattern,
                dry_run=not args.no_dry_run
            )
        
        elif args.command == 'verify':
            success = verify_checksums(
                config,
                local_path=args.local,
                remote_path=args.remote
            )
        
        else:
            print(f"ERROR: Unknown command: {args.command}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nERROR: Operation failed: {e}")
        sys.exit(3)
    
    # Exit with appropriate code
    sys.exit(0 if success else 3)


if __name__ == '__main__':
    main()
