#!/usr/bin/env python3
"""
Upload videos and files to RunPod network volume via a temporary pod.

This script:
  1. Creates a temporary RunPod pod with your network volume mounted
  2. Creates the folder structure (input/, output/, models/, etc.)
  3. Uploads your video files to /runpod-volume/input/
  4. Terminates the temporary pod

Usage:
  # Upload a single video
  .venv/bin/python scripts/upload_to_runpod.py video.mp4

  # Upload multiple files
  .venv/bin/python scripts/upload_to_runpod.py video1.mp4 video2.mp4 image.png

  # Upload to a subfolder
  .venv/bin/python scripts/upload_to_runpod.py video.mp4 --subfolder upscale_test

  # List files on the volume (no upload)
  .venv/bin/python scripts/upload_to_runpod.py --list

  # Specify GPU type for the temp pod (default: cheapest)
  .venv/bin/python scripts/upload_to_runpod.py video.mp4 --gpu "NVIDIA RTX A4000"

  # Keep the pod running after upload (for SSH access)
  .venv/bin/python scripts/upload_to_runpod.py video.mp4 --keep-pod

Prerequisites:
  - RUNPOD_API_KEY set in .env or environment
  - runpod SDK installed (uv sync)
  - SSH key registered with RunPod (for SCP upload)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List

# Load .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Run: uv sync")
    sys.exit(1)


# Colors
class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'


def log_info(msg): print(f"{C.BLUE}[INFO]{C.NC} {msg}")
def log_ok(msg): print(f"{C.GREEN}[OK]{C.NC} {msg}")
def log_warn(msg): print(f"{C.YELLOW}[WARN]{C.NC} {msg}")
def log_err(msg): print(f"{C.RED}[ERROR]{C.NC} {msg}")


def get_network_volume_id() -> Optional[str]:
    """Get the network volume ID from the first serverless endpoint."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    try:
        endpoints = runpod.get_endpoints()
        for ep in endpoints:
            vol = ep.get("networkVolume")
            if vol and vol.get("id"):
                log_info(f"Found network volume: {vol['id']} (from endpoint: {ep.get('name', '?')})")
                return vol["id"]
    except Exception as e:
        log_err(f"Failed to get endpoints: {e}")
    return None


def create_temp_pod(volume_id: str, gpu_type: str = "NVIDIA RTX A4000") -> dict:
    """Create a temporary pod with the network volume mounted."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    log_info(f"Creating temporary pod (GPU: {gpu_type})...")
    
    pod = runpod.create_pod(
        name="temp-upload-volume",
        image_name="ghcr.io/alterpeace/runpod-comfy:latest",
        gpu_type_id=gpu_type,
        network_volume_id=volume_id,
        volume_mount_path="/runpod-volume",
        container_disk_in_gb=50,
        ports="22/http",
        start_ssh=True,
    )
    
    if isinstance(pod, list):
        pod = pod[0] if pod else {}
    
    pod_id = pod.get("id")
    if not pod_id:
        log_err(f"Failed to create pod: {pod}")
        sys.exit(1)
    
    log_ok(f"Pod created: {pod_id}")
    return pod


def wait_for_pod_ready(pod_id: str, timeout: int = 120) -> dict:
    """Wait for pod to be running and get SSH connection info."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    log_info("Waiting for pod to start...")
    
    start = time.time()
    while time.time() - start < timeout:
        pods = runpod.get_pods()
        for p in pods:
            if p.get("id") == pod_id:
                status = p.get("status", "")
                if status == "RUNNING":
                    ports = p.get("ports", [])
                    ssh_port = None
                    ssh_host = None
                    for port_info in ports:
                        if port_info.get("privatePort") == 22:
                            ssh_port = port_info.get("publicPort")
                            ssh_host = port_info.get("ip")
                            break
                    
                    if ssh_port and ssh_host:
                        log_ok(f"Pod running! SSH: root@{ssh_host}:{ssh_port}")
                        return {
                            "host": ssh_host,
                            "port": ssh_port,
                            "pod_id": pod_id,
                        }
                    else:
                        log_warn(f"Pod running but no SSH port found: {ports}")
                elif status in ["FAILED", "ERROR"]:
                    log_err(f"Pod failed to start: {status}")
                    sys.exit(1)
                else:
                    log_info(f"Pod status: {status}...")
        time.sleep(5)
    
    log_err(f"Pod did not become ready within {timeout}s")
    runpod.terminate_pod(pod_id)
    sys.exit(1)


def run_ssh_command(host: str, port: int, command: str, timeout: int = 30) -> tuple:
    """Run a command on the remote pod via SSH."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-p", str(port),
        f"root@{host}",
        command
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def scp_upload(host: str, port: int, local_path: str, remote_path: str) -> bool:
    """Upload a file via SCP."""
    scp_cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-P", str(port),
        local_path,
        f"root@{host}:{remote_path}"
    ]
    log_info(f"Uploading {local_path} → {remote_path}...")
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        log_ok(f"Uploaded: {Path(local_path).name}")
        return True
    else:
        log_err(f"Upload failed: {result.stderr}")
        return False


def scp_upload_dir(host: str, port: int, local_dir: str, remote_dir: str) -> int:
    """Upload an entire directory via SCP (recursive). Returns count of files uploaded."""
    local_dir = os.path.expanduser(local_dir)
    if not os.path.isdir(local_dir):
        log_err(f"Not a directory: {local_dir}")
        return 0
    
    # Count files for progress
    file_count = sum(1 for f in Path(local_dir).rglob("*") if f.is_file())
    log_info(f"Uploading directory: {local_dir} ({file_count} files) → {remote_dir}/")
    
    # Create remote directory first
    run_ssh_command(host, port, f"mkdir -p {remote_dir}")
    
    # Use scp -r for recursive upload
    scp_cmd = [
        "scp", "-r",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-P", str(port),
        os.path.join(local_dir, "."),  # Upload contents, not the dir itself
        f"root@{host}:{remote_dir}/"
    ]
    
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode == 0:
        log_ok(f"Directory uploaded: {file_count} files → {remote_dir}/")
        return file_count
    else:
        log_err(f"Directory upload failed: {result.stderr[:500]}")
        return 0


def create_folder_structure(host: str, port: int):
    """Create the standard folder structure on the network volume."""
    log_info("Creating folder structure on network volume...")
    cmd = (
        "mkdir -p /runpod-volume/input "
        "/runpod-volume/output "
        "/runpod-volume/models/checkpoints "
        "/runpod-volume/models/loras "
        "/runpod-volume/models/vae "
        "/runpod-volume/models/SEEDVR2 "
        "/runpod-volume/custom_nodes "
        "/runpod-volume/user "
        "&& ls -la /runpod-volume/"
    )
    code, stdout, stderr = run_ssh_command(host, port, cmd)
    if code == 0:
        log_ok("Folder structure created:")
        print(stdout)
    else:
        log_err(f"Failed to create folders: {stderr}")


def list_files(host: str, port: int, path: str = "/runpod-volume/"):
    """List files on the network volume."""
    cmd = f"find {path} -type f -exec ls -lh {{}} \\; 2>/dev/null | head -50"
    code, stdout, stderr = run_ssh_command(host, port, cmd, timeout=30)
    if code == 0:
        print(stdout)
    else:
        log_err(f"Failed to list files: {stderr}")


def terminate_pod(pod_id: str):
    """Terminate the temporary pod."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    log_info(f"Terminating pod {pod_id}...")
    try:
        runpod.terminate_pod(pod_id)
        log_ok("Pod terminated")
    except Exception as e:
        log_err(f"Failed to terminate pod: {e}")
        log_warn(f"Terminate manually in RunPod dashboard: {pod_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload videos/files to RunPod network volume",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a single video
  %(prog)s video.mp4

  # Upload multiple files
  %(prog)s video1.mp4 video2.mp4 image.png

  # Upload an entire directory (recursive, preserves structure)
  %(prog)s /media/chiral/data/visuals/clips/al7/montked --subfolder montked

  # Upload to a subfolder under input/
  %(prog)s video.mp4 --subfolder upscale_test

  # List files on the volume
  %(prog)s --list

  # Keep the pod running after upload (for SSH/SCP access)
  %(prog)s video.mp4 --keep-pod
        """
    )
    parser.add_argument("files", nargs="*", help="Files to upload")
    parser.add_argument("--subfolder", default="", help="Subfolder under /runpod-volume/input/")
    parser.add_argument("--gpu", default="NVIDIA RTX A4000", help="GPU type for temp pod")
    parser.add_argument("--list", action="store_true", help="List files on volume and exit")
    parser.add_argument("--keep-pod", action="store_true", help="Keep temp pod running after upload")
    parser.add_argument("--volume-id", default=None, help="Network volume ID (auto-detected if omitted)")
    
    args = parser.parse_args()
    
    # Check API key
    if not os.environ.get("RUNPOD_API_KEY"):
        log_err("RUNPOD_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)
    
    # Get volume ID
    volume_id = args.volume_id or get_network_volume_id()
    if not volume_id:
        log_err("No network volume found. Create one in RunPod dashboard or specify --volume-id")
        sys.exit(1)
    
    # Create temp pod
    pod = create_temp_pod(volume_id, args.gpu)
    pod_id = pod["id"]
    
    try:
        # Wait for pod to be ready
        ssh_info = wait_for_pod_ready(pod_id)
        host = ssh_info["host"]
        port = ssh_info["port"]
        
        # Wait a bit for SSH to be fully ready
        time.sleep(3)
        
        # Create folder structure
        create_folder_structure(host, port)
        
        # List mode
        if args.list:
            log_info("Files on network volume:")
            list_files(host, port)
            if not args.keep_pod:
                terminate_pod(pod_id)
            return
        
        # Upload files
        if not args.files:
            log_warn("No files specified. Use --list to see existing files.")
            if not args.keep_pod:
                terminate_pod(pod_id)
            return
        
        # Determine remote path
        if args.subfolder:
            remote_dir = f"/runpod-volume/input/{args.subfolder}"
            # Create subfolder
            run_ssh_command(host, port, f"mkdir -p {remote_dir}")
        else:
            remote_dir = "/runpod-volume/input"
        
        uploaded = 0
        failed = 0
        for local_path in args.files:
            local_path = os.path.expanduser(local_path)
            if not os.path.exists(local_path):
                log_err(f"File not found: {local_path}")
                failed += 1
                continue
            
            # Handle directory upload (recursive)
            if os.path.isdir(local_path):
                dir_name = os.path.basename(os.path.normpath(local_path))
                if args.subfolder:
                    remote_subdir = f"{remote_dir}/{dir_name}"
                else:
                    remote_subdir = f"/runpod-volume/input/{dir_name}"
                
                count = scp_upload_dir(host, port, local_path, remote_subdir)
                uploaded += count
                continue
            
            # Single file upload
            filename = os.path.basename(local_path)
            remote_path = f"{remote_dir}/{filename}"
            
            if scp_upload(host, port, local_path, remote_path):
                uploaded += 1
            else:
                failed += 1
        
        log_info(f"Upload complete: {uploaded} files succeeded, {failed} failed")
        
        # List the uploaded files
        if uploaded > 0:
            log_info(f"Files in {remote_dir}:")
            list_files(host, port, remote_dir)
        
        # Print workflow reference
        log_info("To use these files in a ComfyUI workflow:")
        first_file = args.files[0] if args.files else ""
        first_file = os.path.expanduser(first_file)
        if os.path.isdir(first_file):
            dir_name = os.path.basename(os.path.normpath(first_file))
            if args.subfolder:
                print(f"  VHS_LoadVideo video: input/{args.subfolder}/{dir_name}/filename.mp4")
                print(f"  (resolves to: /runpod-volume/input/{args.subfolder}/{dir_name}/filename.mp4)")
            else:
                print(f"  VHS_LoadVideo video: input/{dir_name}/filename.mp4")
                print(f"  (resolves to: /runpod-volume/input/{dir_name}/filename.mp4)")
        elif first_file:
            if args.subfolder:
                print(f"  VHS_LoadVideo video: input/{args.subfolder}/{os.path.basename(first_file)}")
                print(f"  (resolves to: /runpod-volume/input/{args.subfolder}/{os.path.basename(first_file)})")
            else:
                print(f"  VHS_LoadVideo video: input/{os.path.basename(first_file)}")
                print(f"  (resolves to: /runpod-volume/input/{os.path.basename(first_file)})")
        
        if args.keep_pod:
            log_warn(f"Pod kept running for SSH access:")
            log_warn(f"  ssh root@{host} -p {port}")
            log_warn(f"  Volume mounted at: /runpod-volume/")
            log_warn(f"  Terminate with: .venv/bin/python scripts/upload_to_runpod.py --list  # then terminate manually")
            log_warn(f"  Or: runpod terminate-pod {pod_id}")
        else:
            terminate_pod(pod_id)
    
    except KeyboardInterrupt:
        log_warn("\nInterrupted by user")
        terminate_pod(pod_id)
    except Exception as e:
        log_err(f"Error: {e}")
        terminate_pod(pod_id)
        raise


if __name__ == "__main__":
    main()
