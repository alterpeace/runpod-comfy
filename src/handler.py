"""
RunPod Serverless Handler for ComfyUI

This module provides the main serverless handler function for processing
ComfyUI workflows on RunPod. It handles workflow validation, execution,
output retrieval, and cleanup.

It also supports a "download_models" action for downloading LTX-2.5 (or
LTX-2.3) models to the network volume via the RunPod serverless API,
without needing SSH access to the worker.
"""

import os
import sys
import json
import base64
import logging
import subprocess
import time
import tempfile
import shutil
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

import runpod

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import ComfyUI client
from comfyui_client import ComfyUIClient, ComfyUIError, ComfyUIConnectionError, ComfyUIWorkflowError

# Import S3 storage (optional)
try:
    from storage_s3 import S3StorageClient, S3StorageError, create_s3_client_from_env
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("S3 storage module not available (boto3 not installed)")

# Environment variable configuration with defaults and validation
def get_env_int(key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    """Get integer environment variable with validation."""
    try:
        value = int(os.environ.get(key, str(default)))
        if min_val is not None and value < min_val:
            logger.warning(f"{key}={value} is below minimum {min_val}, using minimum")
            return min_val
        if max_val is not None and value > max_val:
            logger.warning(f"{key}={value} is above maximum {max_val}, using maximum")
            return max_val
        return value
    except (ValueError, TypeError):
        logger.warning(f"Invalid {key} value, using default: {default}")
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.environ.get(key, '').lower()
    if value in ('true', '1', 'yes', 'on'):
        return True
    elif value in ('false', '0', 'no', 'off', ''):
        return False if not value else default
    return default


def validate_storage_type(storage_type: str) -> str:
    """Validate storage type configuration."""
    valid_types = ['response', 'volume', 's3']
    if storage_type not in valid_types:
        logger.warning(
            f"Invalid STORAGE_TYPE '{storage_type}', must be one of {valid_types}. "
            f"Using default: 'response'"
        )
        return 'response'
    return storage_type


def validate_mode(mode: str) -> str:
    """Validate operating mode configuration."""
    valid_modes = ['local', 'serverless', 'pods']
    if mode not in valid_modes:
        logger.warning(
            f"Invalid MODE '{mode}', must be one of {valid_modes}. "
            f"Using default: 'serverless'"
        )
        return 'serverless'
    return mode


# Configuration with defaults and validation
# Operating Mode
MODE = validate_mode(os.environ.get('MODE', 'serverless'))

# ComfyUI Configuration
COMFYUI_URL = os.environ.get('COMFYUI_URL', 'http://127.0.0.1:8188')
COMFYUI_PORT = os.environ.get('COMFYUI_PORT', '8188')
COMFYUI_ARGS = os.environ.get('COMFYUI_ARGS', '--lowvram')
COMFYUI_PATH = os.environ.get('COMFYUI_PATH', '/comfyui')

# Timeout Configuration (5 seconds to 1 hour)
TIMEOUT = get_env_int('TIMEOUT', default=300, min_val=5, max_val=3600)

# Storage Configuration
STORAGE_TYPE = validate_storage_type(os.environ.get('STORAGE_TYPE', 'response'))
VOLUME_OUTPUT_PATH = os.environ.get('VOLUME_OUTPUT_PATH', '/runpod-volume/outputs')

# S3 Configuration (only used when STORAGE_TYPE='s3')
S3_BUCKET = os.environ.get('S3_BUCKET', '')
S3_REGION = os.environ.get('S3_REGION', 'us-east-1')
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL', '')  # For S3-compatible services
S3_PREFIX = os.environ.get('S3_PREFIX', 'comfyui-outputs')
S3_PUBLIC = get_env_bool('S3_PUBLIC', default=False)

# AWS Credentials (for S3)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

# SSH Configuration
ENABLE_SSH = get_env_bool('ENABLE_SSH', default=False)
SSH_PUBLIC_KEY = os.environ.get('SSH_PUBLIC_KEY', '')
SSH_AUTHORIZED_KEYS_PATH = os.environ.get('SSH_AUTHORIZED_KEYS_PATH', '')

# Cloudflare Tunnel Configuration (userspace reverse tunnel for WebUI access)
# Works on serverless workers — no CAP_NET_ADMIN or TUN interface needed.
# Requires a pre-created named tunnel + credentials file on the network volume.
CLOUDFLARED_TUNNEL_ID = os.environ.get('CLOUDFLARED_TUNNEL_ID', '')
CLOUDFLARED_CREDENTIALS_PATH = os.environ.get('CLOUDFLARED_CREDENTIALS_PATH', '')
CLOUDFLARED_CONFIG_PATH = os.environ.get('CLOUDFLARED_CONFIG_PATH', '')
CLOUDFLARED_HOSTNAME = os.environ.get('CLOUDFLARED_HOSTNAME', '')
CLOUDFLARED_ENABLED = bool(CLOUDFLARED_TUNNEL_ID and CLOUDFLARED_CREDENTIALS_PATH)

# Log configuration on startup
logger.info(f"Configuration loaded:")
logger.info(f"  MODE: {MODE}")
logger.info(f"  COMFYUI_URL: {COMFYUI_URL}")
logger.info(f"  COMFYUI_PORT: {COMFYUI_PORT}")
logger.info(f"  TIMEOUT: {TIMEOUT}s")
logger.info(f"  STORAGE_TYPE: {STORAGE_TYPE}")
if STORAGE_TYPE == 'volume':
    logger.info(f"  VOLUME_OUTPUT_PATH: {VOLUME_OUTPUT_PATH}")
elif STORAGE_TYPE == 's3':
    logger.info(f"  S3_BUCKET: {S3_BUCKET}")
    logger.info(f"  S3_REGION: {S3_REGION}")
    logger.info(f"  S3_PREFIX: {S3_PREFIX}")
    if S3_ENDPOINT_URL:
        logger.info(f"  S3_ENDPOINT_URL: {S3_ENDPOINT_URL}")
logger.info(f"  ENABLE_SSH: {ENABLE_SSH}")
logger.info(f"  Cloudflare Tunnel: {'enabled' if CLOUDFLARED_ENABLED else 'disabled'}")
if CLOUDFLARED_ENABLED:
    logger.info(f"  CLOUDFLARED_TUNNEL_ID: {CLOUDFLARED_TUNNEL_ID}")
    logger.info(f"  CLOUDFLARED_HOSTNAME: {CLOUDFLARED_HOSTNAME or '(not set)'}")

# Global ComfyUI process and clients
comfyui_process = None
comfyui_client = None
s3_client = None

# Default model manifest paths (relative to /workspace inside the container)
LTX25_MANIFEST = "/workspace/config/ltx-2.5-models.json"
LTX23_MANIFEST = "/workspace/config/ltx-2.3-models.json"

# Default output directory on the network volume — models downloaded here
# are symlinked into /comfyui/models/ by entrypoint.sh on the next boot.
DEFAULT_MODELS_OUTPUT_DIR = "/runpod-volume/models"


class HandlerError(Exception):
    """Base exception for handler errors"""
    pass


class ValidationError(HandlerError):
    """Raised when input validation fails"""
    pass


def initialize_comfyui() -> bool:
    """
    Start ComfyUI server in background if not already running.
    
    Returns:
        True if ComfyUI is running and healthy
        
    Raises:
        HandlerError: If ComfyUI fails to start
    """
    global comfyui_process, comfyui_client, s3_client
    
    # Initialize ComfyUI client
    if comfyui_client is None:
        comfyui_client = ComfyUIClient(
            base_url=COMFYUI_URL,
            timeout=TIMEOUT
        )
    
    # Initialize S3 client if storage type is S3
    if STORAGE_TYPE == 's3' and s3_client is None and S3_AVAILABLE:
        try:
            s3_client = create_s3_client_from_env()
            if s3_client:
                logger.info("S3 storage client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise HandlerError(f"S3 storage configuration error: {e}")
    
    # Check if already running
    if comfyui_client.health_check():
        logger.info("ComfyUI server is already running")
        return True
    
    logger.info("Starting ComfyUI server...")
    
    # Build command
    cmd = [
        sys.executable,
        'main.py',
        '--listen',
        '0.0.0.0',
        '--port',
        COMFYUI_PORT
    ]
    
    # Add additional arguments
    if COMFYUI_ARGS:
        cmd.extend(COMFYUI_ARGS.split())
    
    try:
        # Start ComfyUI process
        comfyui_process = subprocess.Popen(
            cmd,
            cwd=COMFYUI_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for server to be ready
        max_wait = 60  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if comfyui_client.health_check():
                logger.info("ComfyUI server started successfully")
                return True
            
            # Check if process died
            if comfyui_process.poll() is not None:
                stdout, stderr = comfyui_process.communicate()
                raise HandlerError(
                    f"ComfyUI process died during startup. "
                    f"stdout: {stdout}, stderr: {stderr}"
                )
            
            time.sleep(2)
        
        raise HandlerError(
            f"ComfyUI server failed to start within {max_wait} seconds"
        )
        
    except Exception as e:
        logger.error(f"Failed to start ComfyUI: {e}")
        raise HandlerError(f"Failed to start ComfyUI: {e}")


def validate_workflow(workflow: Any) -> Dict[str, Any]:
    """
    Validate workflow input structure.
    
    Args:
        workflow: Workflow data to validate
        
    Returns:
        Validated workflow dictionary
        
    Raises:
        ValidationError: If workflow is invalid
    """
    if workflow is None:
        raise ValidationError("Workflow is required")
    
    if not isinstance(workflow, dict):
        raise ValidationError(
            f"Workflow must be a dictionary, got {type(workflow).__name__}"
        )
    
    if not workflow:
        raise ValidationError("Workflow cannot be empty")
    
    # Check for at least one node
    if not any(key for key in workflow.keys() if key.isdigit() or isinstance(key, int)):
        raise ValidationError(
            "Workflow must contain at least one node (numeric keys)"
        )
    
    # Validate node structure
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            raise ValidationError(
                f"Node {node_id} must be a dictionary, got {type(node_data).__name__}"
            )
        
        if 'class_type' not in node_data:
            raise ValidationError(
                f"Node {node_id} missing required field 'class_type'"
            )
        
        if 'inputs' not in node_data:
            raise ValidationError(
                f"Node {node_id} missing required field 'inputs'"
            )
    
    logger.info(f"Workflow validation passed: {len(workflow)} nodes")
    return workflow


def upload_files(files: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Upload input files to ComfyUI.

    Works with any file type — images, videos, audio, etc. Files are
    base64-encoded in the job input and uploaded via ComfyUI's /upload/image
    endpoint, which saves them as real files in /comfyui/input/.

    Args:
        files: Dictionary mapping filenames to base64 encoded file data

    Returns:
        Dictionary mapping original filenames to uploaded filenames

    Raises:
        HandlerError: If file upload fails
    """
    if not files:
        logger.info("No input files to upload")
        return {}

    if not isinstance(files, dict):
        raise ValidationError(
            f"Files must be a dictionary, got {type(files).__name__}"
        )

    uploaded = {}

    for filename, file_data in files.items():
        try:
            # Decode base64 data
            if isinstance(file_data, str):
                # Remove data URL prefix if present
                if file_data.startswith('data:'):
                    file_data = file_data.split(',', 1)[1]

                file_bytes = base64.b64decode(file_data)
            else:
                raise ValidationError(
                    f"File data for {filename} must be base64 string"
                )

            # Upload to ComfyUI (uses upload_file which derives content type)
            result = comfyui_client.upload_file(
                file_data=file_bytes,
                filename=filename,
                overwrite=True
            )

            uploaded[filename] = result.get('name', filename)
            logger.info(f"Uploaded file: {filename} ({len(file_bytes)} bytes)")

        except Exception as e:
            logger.error(f"Failed to upload file {filename}: {e}")
            raise HandlerError(f"Failed to upload file {filename}: {e}")

    return uploaded


# Backward-compatible alias
def upload_images(images: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Backward-compatible alias for upload_files."""
    return upload_files(images)


def execute_workflow(
    workflow: Dict[str, Any],
    timeout: Optional[int] = None,
    clear_cache: bool = True
) -> str:
    """
    Submit workflow to ComfyUI and monitor execution.
    
    Args:
        workflow: Validated workflow dictionary
        timeout: Maximum execution time in seconds (None = use default)
        clear_cache: If True, clear cached latents before execution to prevent
                    corrupted outputs from stale tensor data (default: True)
        
    Returns:
        prompt_id: Unique identifier for the executed workflow
        
    Raises:
        HandlerError: If workflow execution fails
    """
    if timeout is None:
        timeout = TIMEOUT
    
    try:
        # Clear cached latents and intermediate tensors before execution
        # This prevents corrupted outputs from stale cached data on subsequent runs
        if clear_cache:
            cache_cleared = comfyui_client.clear_cache()
            if cache_cleared:
                logger.info("Cleared cached latents before workflow execution")
            else:
                logger.warning(
                    "Could not clear cache (ComfyUI may not support /free endpoint). "
                    "Proceeding with execution."
                )
        
        # Submit workflow
        prompt_id = comfyui_client.queue_prompt(workflow)
        logger.info(f"Workflow submitted with prompt_id: {prompt_id}")
        
        # Wait for completion
        history = comfyui_client.wait_for_completion(
            prompt_id=prompt_id,
            poll_interval=1,
            max_wait_time=timeout
        )
        
        logger.info(f"Workflow {prompt_id} completed successfully")
        return prompt_id
        
    except ComfyUIWorkflowError as e:
        logger.error(f"Workflow execution failed: {e}")
        raise HandlerError(f"Workflow execution failed: {e}")
    except ComfyUIConnectionError as e:
        logger.error(f"Connection to ComfyUI failed: {e}")
        raise HandlerError(f"Connection to ComfyUI failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during workflow execution: {e}")
        raise HandlerError(f"Unexpected error during workflow execution: {e}")


def get_outputs(prompt_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve generated images from completed workflow.
    
    Args:
        prompt_id: Unique identifier of the workflow
        
    Returns:
        List of output dictionaries containing:
        - filename: Name of the output file
        - data: Image data as bytes
        - type: Output type
        - node_id: Source node ID
        
    Raises:
        HandlerError: If output retrieval fails
    """
    try:
        outputs = comfyui_client.get_outputs(prompt_id)
        logger.info(f"Retrieved {len(outputs)} outputs for prompt {prompt_id}")
        return outputs
        
    except ComfyUIWorkflowError as e:
        logger.error(f"Failed to retrieve outputs: {e}")
        raise HandlerError(f"Failed to retrieve outputs: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving outputs: {e}")
        raise HandlerError(f"Unexpected error retrieving outputs: {e}")


def cleanup_temp_files() -> None:
    """
    Clean up temporary files after execution.
    
    This function removes temporary files created during workflow execution
    to prevent disk space issues.
    """
    try:
        # Clean up ComfyUI temp directory
        temp_dir = Path(COMFYUI_PATH) / 'temp'
        if temp_dir.exists():
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning(f"Failed to delete {item}: {e}")
        
        logger.info("Temporary files cleaned up")
        
    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")


def process_outputs(
    outputs: List[Dict[str, Any]],
    prompt_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Process outputs based on storage configuration.
    
    Args:
        outputs: List of output dictionaries from get_outputs()
        prompt_id: ComfyUI prompt ID for S3 organization
        
    Returns:
        List of processed outputs with appropriate data format
        
    Raises:
        HandlerError: If output processing fails
    """
    processed = []
    
    for output in outputs:
        result = {
            'filename': output['filename'],
            'type': output.get('type', 'output'),
            'node_id': output.get('node_id')
        }
        
        if STORAGE_TYPE == 'volume':
            # Save to volume storage
            try:
                output_path = Path(VOLUME_OUTPUT_PATH)
                output_path.mkdir(parents=True, exist_ok=True)
                
                file_path = output_path / output['filename']
                file_path.write_bytes(output['data'])
                
                result['path'] = str(file_path)
                logger.info(f"Saved output to volume: {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to save to volume: {e}")
                raise HandlerError(f"Failed to save to volume: {e}")
        
        elif STORAGE_TYPE == 's3':
            # Upload to S3-compatible storage
            if not S3_AVAILABLE:
                logger.error("S3 storage requested but boto3 not installed")
                raise HandlerError(
                    "S3 storage not available. Install boto3: uv add boto3"
                )
            
            if s3_client is None:
                logger.error("S3 storage requested but client not initialized")
                raise HandlerError(
                    "S3 client not initialized. Check S3 configuration."
                )
            
            try:
                # Prepare metadata
                metadata = {
                    'prompt_id': prompt_id or 'unknown',
                    'node_id': str(output.get('node_id', 'unknown')),
                    'type': output.get('type', 'output'),
                    'generated_at': datetime.now().isoformat()
                }
                
                # Upload to S3
                upload_result = s3_client.upload_file(
                    file_data=output['data'],
                    filename=output['filename'],
                    prompt_id=prompt_id,
                    node_id=output.get('node_id'),
                    metadata=metadata,
                    public=os.environ.get('S3_PUBLIC', 'false').lower() == 'true'
                )
                
                # Add S3 information to result
                result['s3_key'] = upload_result['key']
                result['url'] = upload_result['url']
                result['bucket'] = upload_result['bucket']
                result['size'] = upload_result['size']
                result['content_type'] = upload_result['content_type']
                
                logger.info(
                    f"Uploaded {output['filename']} to S3: {upload_result['url']}"
                )
                
            except S3StorageError as e:
                logger.error(f"S3 upload failed: {e}")
                raise HandlerError(f"S3 upload failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during S3 upload: {e}")
                raise HandlerError(f"Unexpected error during S3 upload: {e}")
        
        else:  # response (default)
            # Return as base64 in response
            result['data'] = base64.b64encode(output['data']).decode('utf-8')
            result['encoding'] = 'base64'
        
        processed.append(result)
    
    return processed


def download_models(job_input: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """
    Download LTX-2.5 (or LTX-2.3) models to the network volume.

    This action does NOT start ComfyUI — it runs the download script directly,
    making it fast and lightweight. Models are saved to /runpod-volume/models/
    so they persist across worker restarts and are shared by all workers
    attached to the same network volume.

    Expected job_input keys:
        - action: "download_models" (required, checked by caller)
        - manifest: "ltx-2.5" (default) or "ltx-2.3"
        - profile: Named profile from the manifest (e.g. "low_vram_8gb",
                   "mid_vram_24gb", "full"). Mutually exclusive with "ids".
        - ids: List of explicit model IDs to download. Mutually exclusive
               with "profile".
        - output_dir: Override the output directory (default: /runpod-volume/models)
        - force: Re-download even if the file already exists (default: false)
        - dry_run: Show what would be downloaded without downloading (default: false)
        - hf_token: Override HF_TOKEN env var for gated repos

    Returns:
        Dictionary with download results, including per-model status.
    """
    start_time = time.time()

    manifest_choice = job_input.get("manifest", "ltx-2.5")

    # Support inline manifest: if the job input contains "inline_manifest",
    # write it to a temp file and use that as the manifest path.
    inline_manifest = job_input.get("inline_manifest")
    if inline_manifest:
        if not isinstance(inline_manifest, dict):
            raise ValidationError("inline_manifest must be a JSON object")
        import tempfile
        fd, manifest_path = tempfile.mkstemp(suffix=".json", prefix="manifest_")
        with os.fdopen(fd, "w") as f:
            json.dump(inline_manifest, f)
        logger.info(f"[download_models] Using inline manifest from job input")
    elif manifest_choice == "ltx-2.3":
        manifest_path = LTX23_MANIFEST
    elif manifest_choice == "ltx-2.5":
        manifest_path = LTX25_MANIFEST
    else:
        # Allow passing a custom manifest path
        manifest_path = job_input.get("manifest_path", LTX25_MANIFEST)

    if not os.path.isfile(manifest_path):
        raise HandlerError(
            f"Model manifest not found at {manifest_path}. "
            f"Ensure config/ is copied into the Docker image."
        )

    output_dir = job_input.get("output_dir", DEFAULT_MODELS_OUTPUT_DIR)
    force = job_input.get("force", False)
    dry_run = job_input.get("dry_run", False)
    profile = job_input.get("profile")
    ids = job_input.get("ids")

    if not profile and not ids:
        raise ValidationError(
            "Either 'profile' or 'ids' must be specified for download_models action"
        )
    if profile and ids:
        raise ValidationError(
            "'profile' and 'ids' are mutually exclusive — specify one or the other"
        )

    # Resolve HF token: job input > env var
    hf_token = job_input.get("hf_token") or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not hf_token:
        logger.warning(
            "HF_TOKEN not set — gated LTX-2.5 repos will fail. "
            "Visit https://huggingface.co/Lightricks/LTX-2.5 and click 'Agree and Access', "
            "then set HF_TOKEN in the endpoint environment or pass hf_token in the job input."
        )

    # Build the download script command
    download_script = "/workspace/scripts/models/download_ltx25_models.py"
    if not os.path.isfile(download_script):
        raise HandlerError(
            f"Download script not found at {download_script}. "
            f"Ensure scripts/ is copied into the Docker image."
        )

    cmd = [
        sys.executable,
        download_script,
        "--manifest", manifest_path,
        "--output-dir", output_dir,
        "--copy",  # Copy (not symlink) so files persist on the network volume
    ]

    if ids:
        if isinstance(ids, str):
            ids = [ids]
        cmd.extend(["--ids"] + ids)
    else:
        cmd.extend(["--profile", profile])

    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")

    # Pass HF token via environment
    env = os.environ.copy()
    if hf_token:
        env["HF_TOKEN"] = hf_token
        env["HUGGING_FACE_HUB_TOKEN"] = hf_token

    logger.info(f"[download_models] Running: {' '.join(cmd)}")
    logger.info(f"[download_models] Output dir: {output_dir}")
    logger.info(f"[download_models] Manifest: {manifest_path}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=3300,  # 55 min max (RunPod serverless max is ~60 min)
        )
    except subprocess.TimeoutExpired:
        raise HandlerError(
            "Model download timed out after 55 minutes. "
            "Try a smaller profile or fewer model IDs."
        )

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # Log output for debugging
    for line in stdout.strip().splitlines():
        logger.info(f"[download_models] {line}")
    if stderr.strip():
        for line in stderr.strip().splitlines():
            logger.warning(f"[download_models] {line}")

    if result.returncode != 0:
        raise HandlerError(
            f"Download script exited with code {result.returncode}. "
            f"stdout: {stdout[:1000]} | stderr: {stderr[:1000]}"
        )

    # Parse the stdout to count successes/failures
    ok_count = stdout.count("[ok]")
    skip_count = stdout.count("[skip]")
    fail_count = stdout.count("[FAIL]")
    dry_run_count = stdout.count("[dry-run]")

    execution_time = time.time() - start_time

    return {
        "status": "success" if fail_count == 0 else "partial",
        "output": {
            "downloaded": ok_count,
            "skipped": skip_count,
            "failed": fail_count,
            "dry_run": dry_run_count,
            "output_dir": output_dir,
            "manifest": manifest_choice,
            "profile": profile,
            "ids": ids,
            "stdout": stdout,
        },
        "metadata": {
            "job_id": job_id,
            "execution_time": round(execution_time, 2),
            "action": "download_models",
        },
    }


def run_diagnostic(job_input: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """
    Run diagnostic commands on the worker for debugging.

    Executes one or more shell commands and returns their output.
    Useful for checking file paths, verifying mounts, and inspecting
    the worker environment without SSH access.

    Expected job_input keys:
        - action: "diagnostic" (required, checked by caller)
        - commands: List of shell commands to run (default: basic filesystem checks)
        - timeout: Max seconds per command (default: 30)

    Returns:
        Dictionary with command outputs.
    """
    start_time = time.time()

    commands = job_input.get("commands")
    cmd_timeout = job_input.get("timeout", 30)

    if not commands:
        # Default diagnostics: check input paths, volume mount, custom nodes
        commands = [
            "ls -la /runpod-volume/ 2>&1 | head -30",
            "ls -la /runpod-volume/input/ 2>&1 | head -30",
            "find /runpod-volume/input -type f 2>&1 | head -50",
            "ls -la /comfyui/input/ 2>&1 | head -30",
            "find /comfyui/input -type f 2>&1 | head -50",
            "ls -la /comfyui/custom_nodes/ 2>&1 | head -30",
            "cd /comfyui/custom_nodes/ComfyUI-LTXVideo && git log --oneline -5 2>&1",
            "cat /comfyui/custom_nodes/ComfyUI-LTXVideo/gemma_encoder.py 2>&1 | head -10",
            "ls -la /runpod-volume/models/ 2>&1 | head -20",
            "df -h /runpod-volume 2>&1",
        ]

    if not isinstance(commands, list):
        commands = [commands]

    results = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=cmd_timeout,
            )
            results.append({
                "command": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": f"TIMEOUT after {cmd_timeout}s",
                "returncode": -1,
            })
        except Exception as e:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
            })

    execution_time = time.time() - start_time

    return {
        "status": "success",
        "output": {
            "results": results,
        },
        "metadata": {
            "job_id": job_id,
            "execution_time": round(execution_time, 2),
            "action": "diagnostic",
        },
    }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main RunPod serverless handler function.
    
    Args:
        job: Dictionary containing:
            - id: Job ID from RunPod
            - input: User-provided input data
                - action: Optional. "download_models" to download LTX models
                          instead of running a workflow. If omitted, defaults
                          to workflow execution.
                - workflow: ComfyUI workflow JSON (required when action is
                            omitted or is "run_workflow")
                - input_images: Optional dict of base64 encoded images
                - timeout: Optional custom timeout in seconds
                - clear_cache: Optional bool to clear latent cache before execution
                              (default: True, prevents corrupted outputs)
                - config: Optional configuration overrides
    
    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - output: Generated images or error details
            - metadata: Execution details
    """
    job_id = job.get('id', 'unknown')
    start_time = time.time()
    prompt_id = None
    
    logger.info(f"Processing job {job_id}")
    
    try:
        # Get input data
        job_input = job.get('input', {})
        
        if not isinstance(job_input, dict):
            raise ValidationError("Job input must be a dictionary")

        # ---- Action routing ----
        action = job_input.get("action", "run_workflow")

        if action == "download_models":
            logger.info(f"Job {job_id}: action=download_models")
            return download_models(job_input, job_id)

        if action == "diagnostic":
            logger.info(f"Job {job_id}: action=diagnostic")
            return run_diagnostic(job_input, job_id)

        if action != "run_workflow":
            raise ValidationError(
                f"Unknown action '{action}'. Supported: 'run_workflow' (default), 'download_models', 'diagnostic'"
            )

        # ---- Default: workflow execution ----
        
        # Initialize ComfyUI
        initialize_comfyui()
        
        # Extract and validate workflow
        workflow = job_input.get('workflow')
        workflow = validate_workflow(workflow)
        
        # Upload input files if provided (supports both input_images and input_files)
        input_files = job_input.get('input_files') or job_input.get('input_images')
        uploaded_images = upload_files(input_files)
        
        # Get custom timeout if provided
        custom_timeout = job_input.get('timeout')
        if custom_timeout:
            try:
                custom_timeout = int(custom_timeout)
            except (ValueError, TypeError):
                logger.warning(f"Invalid timeout value: {custom_timeout}, using default")
                custom_timeout = None
        
        # Get clear_cache option (default True to prevent corrupted outputs)
        clear_cache = job_input.get('clear_cache', True)
        if isinstance(clear_cache, str):
            clear_cache = clear_cache.lower() in ('true', '1', 'yes')
        
        # Execute workflow
        prompt_id = execute_workflow(
            workflow,
            timeout=custom_timeout,
            clear_cache=clear_cache
        )
        
        # Get outputs
        outputs = get_outputs(prompt_id)
        
        # Process outputs based on storage type
        processed_outputs = process_outputs(outputs, prompt_id=prompt_id)
        
        # Clear history for this prompt to free memory
        if comfyui_client:
            comfyui_client.clear_history(prompt_id)
        
        # Clean up temporary files
        cleanup_temp_files()
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Build response
        response = {
            'status': 'success',
            'output': {
                'images': processed_outputs,
                'prompt_id': prompt_id
            },
            'metadata': {
                'job_id': job_id,
                'prompt_id': prompt_id,
                'execution_time': round(execution_time, 2),
                'node_count': len(workflow),
                'output_count': len(processed_outputs),
                'storage_type': STORAGE_TYPE
            }
        }
        
        logger.info(
            f"Job {job_id} completed successfully in {execution_time:.2f}s"
        )
        
        return response
        
    except ValidationError as e:
        logger.error(f"Validation error in job {job_id}: {e}")
        return {
            'status': 'error',
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': str(e),
                'type': 'ValidationError'
            },
            'metadata': {
                'job_id': job_id,
                'execution_time': round(time.time() - start_time, 2),
                'error_code': 'VALIDATION_ERROR',
                'error_message': str(e),
                'error_type': 'ValidationError'
            }
        }
    
    except HandlerError as e:
        logger.error(f"Handler error in job {job_id}: {e}")
        return {
            'status': 'error',
            'error': {
                'code': 'HANDLER_ERROR',
                'message': str(e),
                'type': 'HandlerError'
            },
            'metadata': {
                'job_id': job_id,
                'execution_time': round(time.time() - start_time, 2),
                'error_code': 'HANDLER_ERROR',
                'error_message': str(e),
                'error_type': 'HandlerError'
            }
        }
    
    except Exception as e:
        logger.error(f"Unexpected error in job {job_id}: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': f"An unexpected error occurred: {str(e)}",
                'type': type(e).__name__
            },
            'metadata': {
                'job_id': job_id,
                'execution_time': round(time.time() - start_time, 2),
                'error_code': 'INTERNAL_ERROR',
                'error_message': f"An unexpected error occurred: {str(e)}",
                'error_type': type(e).__name__
            }
        }
    
    finally:
        # Always attempt cleanup
        try:
            cleanup_temp_files()
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


# RunPod serverless entry point
if __name__ == "__main__":
    logger.info("Starting RunPod serverless handler")
    runpod.serverless.start({"handler": handler})
