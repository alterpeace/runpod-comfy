# Design Document: RunPod Serverless ComfyUI Deployment

## Overview

This design outlines a flexible ComfyUI deployment that supports both local development and RunPod Serverless production environments. The solution provides:

1. **Dual-Mode Operation**: Same Docker image runs locally (Docker Compose) or on RunPod Serverless
2. **Always-On ComfyUI WebUI**: WebUI is accessible and browsable in ALL modes for workflow development and debugging
3. **Serverless Handler**: Processes ComfyUI workflows on-demand in RunPod environment via API
4. **OpenZiti Integration**: Optional secure tunneling for HTTP and SSH access
5. **SSH Development Access**: Debug and customize environments with SSH access
6. **GitHub Container Registry**: Host images on ghcr.io for easy deployment

### Critical Design Principle: WebUI Accessibility

**The ComfyUI WebUI MUST be running and accessible in ALL operating modes.** This is a core requirement that enables:
- Interactive workflow development in local mode
- Manual testing and debugging in serverless mode
- Consistent user experience across environments
- Ability to browse and test workflows before automating them

### Operating Modes

**Local Mode (Development)**:
- Runs via Docker Compose on your machine
- ComfyUI WebUI accessible at http://localhost:8188 (or configured port)
- Direct port access to ComfyUI
- Local volume mounts for models and outputs
- Optional OpenZiti tunnel for remote access
- SSH access for debugging
- **Cost**: Free (uses your hardware)
- **Primary use**: Interactive workflow development via WebUI

**RunPod Serverless Mode (Pay-Per-Execution)**:
- Event-driven execution on RunPod infrastructure
- ComfyUI WebUI runs continuously and is accessible for browsing and debugging
- Starts on-demand when a job is received via API
- Processes ComfyUI workflows via handler API
- Returns results and shuts down automatically
- Scales automatically based on demand
- Optional OpenZiti tunnel for secure WebUI access
- Optional SSH for debugging and package installation
- **Cost**: Pay only for execution time (per second)
- **Primary use**: Automated batch processing, API-driven workflows
- **Dual interface**: WebUI for manual testing + Handler API for automated job processing

**RunPod Pods Mode (Persistent Server)**:
- Long-running container on RunPod infrastructure
- ComfyUI WebUI runs continuously, always accessible
- No serverless handler - direct WebUI access only
- Persistent until manually terminated
- Can be stopped (but still billed) or terminated (billing stops)
- Network storage persists across pod lifecycles
- Optional OpenZiti tunnel for secure access
- SSH access for debugging and customization
- **Cost**: Continuous billing while pod exists (even when stopped)
- **Cost optimization**: Use spot instances (cheaper but can be interrupted), terminate when not needed
- **Primary use**: Interactive development, long-running workflows, persistent workspace
- **Best for**: Heavy daily use, team collaboration, always-on access

## Deployment Mode Selection Guide

### When to Use Each Mode

| Use Case | Recommended Mode | Reason |
|----------|------------------|--------|
| Local development & testing | **Local** | Free, full control, no network latency |
| Occasional batch processing (< 1hr/day) | **Serverless** | Pay only for execution time |
| API-driven automation | **Serverless** | Auto-scaling, no management overhead |
| Heavy daily use (> 4hrs/day) | **Pods (Spot)** | More cost-effective than serverless for long sessions |
| Always-on workspace | **Pods (Spot)** | Persistent environment, but terminate when not needed |
| Team collaboration | **Pods (On-Demand)** | Reliable uptime, shared workspace |
| Production API (high availability) | **Serverless** | Auto-scaling, no single point of failure |

### Cost Comparison Example

**Scenario**: Running ComfyUI for 2 hours per day on RTX A4000

| Mode | Daily Cost | Monthly Cost | Notes |
|------|-----------|--------------|-------|
| **Local** | $0 | $0 | Uses your hardware |
| **Serverless** | ~$1.20 | ~$36 | $0.60/hr × 2hrs |
| **Pods (Spot)** | ~$0.80 | ~$24 | $0.40/hr × 2hrs (if terminated daily) |
| **Pods (Spot, Always On)** | ~$9.60 | ~$288 | $0.40/hr × 24hrs (not terminated) |
| **Pods (On-Demand)** | ~$1.60 | ~$48 | $0.80/hr × 2hrs (if terminated daily) |
| **Pods (On-Demand, Always On)** | ~$19.20 | ~$576 | $0.80/hr × 24hrs (not terminated) |

**Key Takeaway**: Always terminate pods when not in use! Stopping a pod doesn't stop billing.

### Lifecycle Management

**Serverless Endpoints**:
- **Create**: Deploy via RunPod UI or API
- **Invoke**: Send HTTP POST with workflow JSON
- **Scale**: Automatic based on queue depth
- **Delete**: Remove endpoint when no longer needed
- **Cost**: Only charged during execution

**Pods**:
- **Create**: Deploy via RunPod UI or API
- **Start**: Resume a stopped pod (billing resumes)
- **Stop**: Pause pod (billing continues!)
- **Terminate**: Delete pod (billing stops, network storage persists)
- **Cost**: Charged continuously while pod exists

## Architecture

### Multi-Mode Architecture Overview

The system supports three operating modes with shared components:

**Shared Components:**
- Same Docker image for all modes
- Same ComfyUI installation with WebUI
- Same models and custom nodes
- Same base configuration
- ComfyUI WebUI always accessible in all modes
- Same optional features (OpenZiti, SSH)

**Mode-Specific Behavior:**
- **Local Mode**: ComfyUI WebUI runs continuously, direct HTTP access, local volumes, no handler
- **Serverless Mode**: ComfyUI WebUI runs continuously + Handler processes jobs via API, ephemeral execution, auto-scaling
- **Pods Mode**: ComfyUI WebUI runs continuously, direct HTTP access, network volumes, no handler, persistent until terminated

**Mode Detection:**
```
Entrypoint Script
    ↓
Check RUNPOD_POD_ID and MODE env var
    ↓
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Local Mode           │ Serverless Mode      │ Pods Mode            │
│ (MODE=local or       │ (RUNPOD_POD_ID set + │ (RUNPOD_POD_ID set + │
│  no RUNPOD_POD_ID)   │  MODE=serverless)    │  MODE=pods)          │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Start SSH (optional) │ Start SSH (optional) │ Start SSH (optional) │
│ Check .env           │ Check .env           │ Check .env           │
│ Init Ziti (optional) │ Init Ziti (optional) │ Init Ziti (optional) │
│ Start ComfyUI WebUI  │ Start ComfyUI WebUI  │ Start ComfyUI WebUI  │
│ (port 8188, --listen │ (port 8188, --listen │ (port 8188, --listen │
│  0.0.0.0 for access) │  0.0.0.0 for access) │  0.0.0.0 for access) │
│ Keep running (WebUI  │ Start handler (WebUI │ Keep running (WebUI  │
│ only, no handler)    │ + API processing)    │ only, no handler)    │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

### High-Level Architecture

**Serverless Mode:**
```
┌─────────────────┐
│   API Client    │
│  (User/Service) │
└────────┬────────┘
         │ HTTP POST (workflow JSON)
         ▼
┌─────────────────────────────────┐
│      RunPod Serverless API      │
│  (Job Queue & Orchestration)    │
└────────┬────────────────────────┘
         │ Triggers container
         ▼
┌──────────────────────────────────────────┐
│   Docker Container (ghcr.io)             │
│  ┌────────────────────────────────────┐  │
│  │   Entrypoint Script                │  │
│  │   - Detect serverless mode         │  │
│  │   - Check for .env in /runpod-volume│ │
│  │   - Init OpenZiti tunnel (optional)│  │
│  │   - Start SSH server (optional)    │  │
│  │   - Start ComfyUI                  │  │
│  │   - Launch handler                 │  │
│  └────────────┬───────────────────────┘  │
│               │                           │
│  ┌────────────▼───────────────────────┐  │
│  │   RunPod Handler (Python)          │  │
│  │   - Receives job payload           │  │
│  │   - Validates input                │  │
│  │   - Calls ComfyUI API              │  │
│  │   - Returns results                │  │
│  └────────────┬───────────────────────┘  │
│               │                           │
│  ┌────────────▼───────────────────────┐  │
│  │      ComfyUI Server                │  │
│  │   - Loads models from volume       │  │
│  │   - Executes workflow              │  │
│  │   - Generates outputs              │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   OpenZiti Tunnel (optional)       │  │
│  │   - Forward HTTP :8188             │  │
│  │   - Forward SSH :22                │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   SSH Server (optional)            │  │
│  │   - Access to /runpod-volume       │  │
│  │   - Install packages               │  │
│  │   - Debug and customize            │  │
│  └────────────────────────────────────┘  │
│                                           │
│  GPU: NVIDIA (CUDA enabled)               │
└───────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│   Storage                                 │
│  - RunPod Network Volume (/runpod-volume)│
│    - Models, custom nodes                │
│    - .env for OpenZiti config            │
│    - Python packages                     │
│  - S3/Cloud Storage for outputs          │
└──────────────────────────────────────────┘
         │
         ▼ (if OpenZiti enabled)
┌──────────────────────────────────────────┐
│   Your Local Network                      │
│  - Access ComfyUI via tunnel             │
│  - SSH access via tunnel                 │
└──────────────────────────────────────────┘
```

**Local Mode:**
```
┌─────────────────┐
│   Developer     │
│  (Local Access) │
└────────┬────────┘
         │ HTTP :8188 or SSH :2222
         ▼
┌──────────────────────────────────────────┐
│   Docker Container (local)               │
│  ┌────────────────────────────────────┐  │
│  │   Entrypoint Script                │  │
│  │   - Detect local mode              │  │
│  │   - Check for .env in /workspace   │  │
│  │   - Init OpenZiti tunnel (optional)│  │
│  │   - Start SSH server               │  │
│  │   - Start ComfyUI                  │  │
│  │   - Keep running                   │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │      ComfyUI Server                │  │
│  │   - Loads models from volume       │  │
│  │   - Accepts HTTP requests          │  │
│  │   - Generates outputs              │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   OpenZiti Tunnel (optional)       │  │
│  │   - Forward HTTP :8188             │  │
│  │   - Forward SSH :22                │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   SSH Server                       │  │
│  │   - Access to /workspace           │  │
│  │   - Install packages               │  │
│  │   - Debug and customize            │  │
│  └────────────────────────────────────┘  │
│                                           │
│  GPU: NVIDIA (CUDA enabled)               │
└───────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│   Local Storage (Docker volumes)         │
│  - ./models → /comfyui/models            │
│  - ./output → /comfyui/output            │
│  - ./custom_nodes → /comfyui/custom_nodes│
│  - ./.env → /workspace/.env              │
└──────────────────────────────────────────┘
```

**Pods Mode:**
```
┌─────────────────┐
│   Developer     │
│  (Remote Access)│
└────────┬────────┘
         │ HTTP via RunPod proxy, OpenZiti, or SSH tunnel
         ▼
┌──────────────────────────────────────────┐
│   RunPod Pod (Persistent Container)      │
│  ┌────────────────────────────────────┐  │
│  │   Entrypoint Script                │  │
│  │   - Detect pods mode               │  │
│  │   - Check for .env in /runpod-volume│ │
│  │   - Init OpenZiti tunnel (optional)│  │
│  │   - Start SSH server (optional)    │  │
│  │   - Start ComfyUI                  │  │
│  │   - Keep running indefinitely      │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │      ComfyUI Server                │  │
│  │   - Loads models from volume       │  │
│  │   - Accepts HTTP requests          │  │
│  │   - Generates outputs              │  │
│  │   - Always accessible              │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   OpenZiti Tunnel (optional)       │  │
│  │   - Forward HTTP :8188             │  │
│  │   - Forward SSH :22                │  │
│  └────────────────────────────────────┘  │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   SSH Server (optional)            │  │
│  │   - Access to /runpod-volume       │  │
│  │   - Install packages               │  │
│  │   - Debug and customize            │  │
│  └────────────────────────────────────┘  │
│                                           │
│  GPU: NVIDIA (CUDA enabled)               │
│  Status: Running continuously until       │
│          manually terminated              │
└───────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│   Storage                                 │
│  - RunPod Network Volume (/runpod-volume)│
│    - Models, custom nodes                │
│    - .env for OpenZiti config            │
│    - Python packages                     │
│    - Outputs (persistent)                │
│  - Persists across pod lifecycles        │
└──────────────────────────────────────────┘
         │
         ▼ (if OpenZiti enabled)
┌──────────────────────────────────────────┐
│   Your Local Network                      │
│  - Access ComfyUI via tunnel             │
│  - SSH access via tunnel                 │
└──────────────────────────────────────────┘
```

### Component Interaction Flows

**Serverless Mode Flow:**
1. **Job Submission**: Client sends workflow JSON to RunPod API
2. **Container Initialization**: RunPod spins up container with GPU
3. **Handler Execution**: Python handler receives job payload
4. **ComfyUI Processing**: Handler submits workflow to ComfyUI API
5. **Result Collection**: Handler collects generated images/outputs
6. **Response**: Handler returns results to RunPod API
7. **Cleanup**: Container shuts down after job completion

**Pods Mode Flow:**
1. **Pod Creation**: User creates pod via RunPod UI/API
2. **Container Start**: RunPod starts container with GPU
3. **Initialization**: Entrypoint loads config, starts services
4. **Continuous Operation**: ComfyUI WebUI runs indefinitely
5. **User Access**: Direct HTTP, OpenZiti tunnel, or SSH
6. **Manual Termination**: User terminates pod to stop billing

**Local Mode Flow:**
1. **Docker Compose Up**: User starts container locally
2. **Initialization**: Entrypoint loads config, starts services
3. **Continuous Operation**: ComfyUI WebUI runs until stopped
4. **User Access**: Direct HTTP at localhost:8188
5. **Manual Stop**: User stops Docker Compose

## Project Structure

All files will be organized in a `runpod-serverless/` directory:

```
runpod-serverless/
├── Dockerfile                 # Docker image for all modes (local, serverless, pods)
├── docker-compose.yml         # Local development setup
├── handler.py                 # Main serverless handler (serverless mode only)
├── comfyui_client.py         # ComfyUI API wrapper
├── entrypoint.sh             # Entrypoint script for mode detection
├── openziti/
│   ├── tunnel_setup.sh       # OpenZiti tunnel initialization
│   └── ziti-config.json.example  # OpenZiti configuration template
├── ssh/
│   ├── setup_ssh.sh          # SSH server setup script
│   └── sshd_config           # SSH daemon configuration
├── lifecycle/
│   ├── runpod_pods.py        # Pod lifecycle management (create, start, stop, terminate, status)
│   ├── runpod_serverless.py  # Serverless endpoint management (create, invoke, delete, status)
│   └── README.md             # Lifecycle management documentation
├── requirements.txt          # Python dependencies
├── runpod-config-serverless.json  # RunPod serverless template configuration
├── runpod-config-pods.json        # RunPod pods template configuration
├── build.sh                  # Build and push script
├── deploy.sh                 # Deployment helper script (supports both modes)
├── test_local.sh             # Local testing script
├── test_runpod.py            # RunPod endpoint testing
├── .env.example              # Environment variables template
└── README.md                 # Comprehensive documentation for all modes

# Optional CI/CD
.github/
└── workflows/
    └── build-and-push.yml    # GitHub Actions workflow
```

## Components and Interfaces

### 1. RunPod Handler (`runpod-serverless/handler.py`)

The main serverless function that RunPod invokes.

**Interface:**
```python
def handler(job: dict) -> dict:
    """
    RunPod serverless handler function.
    
    Args:
        job: Dictionary containing:
            - id: Job ID from RunPod
            - input: User-provided input data
                - workflow: ComfyUI workflow JSON
                - images: Optional base64 encoded input images
                - return_outputs: Boolean to return generated images
    
    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - output: Generated images (base64) or URLs
            - message: Status message
            - metadata: Execution details
    """
```

**Responsibilities:**
- Initialize ComfyUI server if not running
- Validate input payload structure
- Upload input images to ComfyUI if provided
- Submit workflow to ComfyUI API
- Poll for workflow completion
- Retrieve generated outputs
- Encode outputs as base64 or upload to storage
- Handle errors and timeouts gracefully

**Key Functions:**
- `initialize_comfyui()`: Start ComfyUI server in background
- `validate_workflow(workflow_json)`: Validate workflow structure
- `upload_images(images_dict)`: Upload input images to ComfyUI
- `execute_workflow(workflow)`: Submit and monitor workflow execution
- `get_outputs(prompt_id)`: Retrieve generated images
- `cleanup_temp_files()`: Remove temporary files after execution

### 2. Dockerfile (`runpod-serverless/Dockerfile`)

Multi-stage Docker image optimized for RunPod Serverless. This will be located at `runpod-serverless/Dockerfile`.

**Base Image Strategy:**
```dockerfile
FROM ghcr.io/radiatingreverberations/comfyui-base:latest
```

**Key Additions:**
- RunPod Python SDK (`runpod`)
- Handler script and dependencies
- Optimized layer caching for faster cold starts
- Health check endpoint
- Proper signal handling for graceful shutdown

**Build Stages:**
1. **Base**: Start from existing ComfyUI image
2. **Dependencies**: Install RunPod SDK and additional requirements
3. **Handler**: Copy handler code and configuration
4. **Models** (optional): Pre-download common models to reduce cold start time

### 3. ComfyUI API Client

Wrapper around ComfyUI's HTTP API for workflow execution.

**Key Endpoints Used:**
- `POST /prompt`: Submit workflow for execution
- `GET /history/{prompt_id}`: Check execution status
- `GET /view`: Retrieve generated images
- `POST /upload/image`: Upload input images

**Implementation:**
```python
class ComfyUIClient:
    def __init__(self, base_url="http://127.0.0.1:8188"):
        self.base_url = base_url
        self.client_id = str(uuid.uuid4())
    
    def queue_prompt(self, workflow: dict) -> str:
        """Submit workflow and return prompt_id"""
    
    def get_history(self, prompt_id: str) -> dict:
        """Get execution status and outputs"""
    
    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Download generated image"""
    
    def upload_image(self, image_data: bytes, filename: str) -> dict:
        """Upload input image"""
```

### 4. Build and Deployment Scripts

All scripts will be in the `runpod-serverless/` directory.

**`runpod-serverless/build.sh`**: Build and push Docker image
```bash
#!/bin/bash
# Build Docker image
# Tag for ghcr.io
# Push to GitHub Container Registry
# Validate image was pushed successfully
```

**`deploy.sh`**: Deploy to RunPod (optional helper)
```bash
#!/bin/bash
# Configure RunPod template via API or CLI
# Set environment variables
# Configure GPU requirements
# Set timeout and scaling parameters
```

**`test_local.sh`**: Test handler locally before deployment
```bash
#!/bin/bash
# Run container locally
# Send test workflow
# Verify outputs
```

### 5. Entrypoint Script (`runpod-serverless/entrypoint.sh`)

Detects operating mode and initializes appropriate services.

**Responsibilities:**
- Detect if running in serverless mode (RunPod) or local mode
- Check for OpenZiti configuration in network storage or local path
- Initialize OpenZiti tunnel if configured
- Start SSH server if enabled
- **Start ComfyUI server with WebUI (ALWAYS, in ALL modes)**
- Ensure ComfyUI is accessible via --listen 0.0.0.0 on configured port
- Wait for ComfyUI to be ready before proceeding
- Launch serverless handler (RunPod mode) or keep ComfyUI running (local mode)
- Log WebUI access information for user

**Mode Detection Logic:**
```bash
if [ -n "$RUNPOD_POD_ID" ]; then
    MODE="serverless"
else
    MODE="local"
fi
```

**Configuration Loading Logic:**
```bash
# Check network storage first (RunPod), then local workspace
if [ -f "/runpod-volume/.env" ]; then
    echo "Loading config from network storage..."
    source /runpod-volume/.env
elif [ -f "/workspace/.env" ]; then
    echo "Loading config from local workspace..."
    source /workspace/.env
else
    echo "No .env file found - using defaults"
fi

# Enable OpenZiti if configured
if [ -n "$OPENZITI_IDENTITY" ] || [ -n "$OPENZITI_IDENTITY_JSON" ]; then
    echo "OpenZiti config detected - initializing tunnel..."
    ./openziti/tunnel_setup.sh
fi

# Enable SSH if configured
if [ "$ENABLE_SSH" = "true" ] && [ -n "$SSH_PUBLIC_KEY" ]; then
    echo "SSH config detected - starting SSH server..."
    ./ssh/setup_ssh.sh
fi
```

### 6. OpenZiti Tunnel Integration

**Components:**

**`openziti/tunnel_setup.sh`**: Initialize OpenZiti tunnel
```bash
#!/bin/bash
# Load OpenZiti identity from .env
# Initialize ziti-edge-tunnel
# Forward ComfyUI HTTP (port 8188)
# Forward SSH (port 22)
# Monitor tunnel health
```

**Environment Variables Required:**
- `OPENZITI_IDENTITY`: Path to OpenZiti identity file or identity JSON
- `OPENZITI_CONTROLLER`: OpenZiti controller URL
- `OPENZITI_SERVICE_HTTP`: Service name for HTTP forwarding
- `OPENZITI_SERVICE_SSH`: Service name for SSH forwarding

**Configuration File (`.env` in network storage or local):**
```bash
# OpenZiti Configuration (SECRETS - Never commit to Git!)
OPENZITI_IDENTITY=/runpod-volume/ziti-identity.json
OPENZITI_CONTROLLER=https://controller.example.com:443
OPENZITI_SERVICE_HTTP=comfyui-http
OPENZITI_SERVICE_SSH=comfyui-ssh

# Or embed identity JSON directly (for easier deployment)
OPENZITI_IDENTITY_JSON='{"zt":"...","id":"..."}'
```

**Tunnel Behavior:**
- If `.env` exists with OpenZiti config: Initialize tunnel
- If initialization fails: Log error, continue without tunnel
- If no `.env` or no OpenZiti config: Skip tunnel setup
- Tunnel runs in background, monitored by entrypoint script

**Security Pattern:**
- `.env` file is **NEVER** committed to Git (in `.gitignore`)
- `.env` file is **NEVER** baked into Docker image
- `.env` file is placed manually in:
  - Local: `./runpod-serverless/.env` (for local development)
  - RunPod: `/runpod-volume/.env` (uploaded to network storage)
- `.env.example` is committed (template without secrets)

### 7. SSH Server Setup

**Components:**

**`ssh/setup_ssh.sh`**: Configure and start SSH server
```bash
#!/bin/bash
# Generate host keys if not present
# Configure SSH for key-based auth
# Set up authorized_keys from environment or network storage
# Start SSH daemon
# Monitor SSH process
```

**`ssh/sshd_config`**: SSH daemon configuration
```
Port 22
PermitRootLogin yes
PubkeyAuthentication yes
PasswordAuthentication no
AuthorizedKeysFile /root/.ssh/authorized_keys
Subsystem sftp /usr/lib/openssh/sftp-server
```

**Environment Variables:**
- `ENABLE_SSH`: Set to "true" to enable SSH server (default: false in serverless, true in local)
- `SSH_PUBLIC_KEY`: Public key for authentication (can be multiline, loaded from .env)
- `SSH_AUTHORIZED_KEYS_PATH`: Path to authorized_keys file in network storage

**SSH Key Management:**
- SSH public keys stored in `.env` file (never committed)
- Example in `.env`:
  ```bash
  SSH_PUBLIC_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... user@host"
  ```
- Or reference a file in network storage:
  ```bash
  SSH_AUTHORIZED_KEYS_PATH=/runpod-volume/authorized_keys
  ```
- Private keys stay on your local machine, never uploaded

**SSH Access Patterns:**

1. **With OpenZiti Tunnel**:
   ```bash
   # SSH via OpenZiti service
   ssh root@comfyui-ssh.ziti
   ```

2. **Without OpenZiti (RunPod)**:
   ```bash
   # Use RunPod's SSH endpoint
   ssh root@<pod-id>.runpod.io -p <assigned-port>
   ```

3. **Local Development**:
   ```bash
   # Direct SSH to localhost
   ssh root@localhost -p 2222
   ```

**Network Storage Access:**
- SSH session provides access to `/runpod-volume/` (network storage)
- Can install Python packages: `pip install --target=/runpod-volume/python-packages <package>`
- Can modify models, custom nodes, configurations
- Changes persist across container restarts

### 8. Docker Compose for Local Development

**`docker-compose.yml`**: Local development setup
```yaml
version: '3.8'

services:
  comfyui:
    build: .
    image: ghcr.io/${GITHUB_USERNAME}/comfyui-serverless:latest
    ports:
      - "8188:8188"  # ComfyUI HTTP
      - "2222:22"    # SSH
    volumes:
      - ./models:/comfyui/models
      - ./output:/comfyui/output
      - ./input:/comfyui/input
      - ./custom_nodes:/comfyui/custom_nodes
      - ./.env:/workspace/.env:ro  # OpenZiti config
    environment:
      - MODE=local
      - ENABLE_SSH=true
      - SSH_PUBLIC_KEY=${SSH_PUBLIC_KEY}
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### 9. RunPod Lifecycle Management Tools

**Purpose**: Provide CLI tools for managing RunPod Serverless endpoints and Pods without using the web UI.

**Components:**

**`lifecycle/runpod_pods.py`**: Pod lifecycle management CLI
```python
# Commands:
# - create: Create a new pod with specified GPU and configuration
# - start: Start a stopped pod
# - stop: Stop a running pod (WARNING: billing continues!)
# - terminate: Delete a pod (stops billing, network storage persists)
# - status: Show pod status, uptime, and current costs
# - list: List all pods with their status

# Example usage:
python runpod_pods.py create --name comfyui-dev --gpu "RTX A4000" --spot
python runpod_pods.py status --pod-id abc123
python runpod_pods.py terminate --pod-id abc123
```

**`lifecycle/runpod_serverless.py`**: Serverless endpoint management CLI
```python
# Commands:
# - create: Create a new serverless endpoint
# - update: Update endpoint configuration
# - delete: Remove a serverless endpoint
# - invoke: Send a workflow to the endpoint
# - status: Show endpoint status and metrics
# - list: List all endpoints

# Example usage:
python runpod_serverless.py create --name comfyui-api --gpu "RTX A4000"
python runpod_serverless.py invoke --endpoint-id xyz789 --workflow workflow.json
python runpod_serverless.py delete --endpoint-id xyz789
```

**Authentication:**
- Uses `RUNPOD_API_KEY` environment variable
- Can be set in `.env` file or passed as argument
- API key obtained from RunPod dashboard

**Features:**
- Interactive prompts for missing parameters
- Cost estimation before creating resources
- Automatic network volume attachment
- Template-based configuration
- JSON output for scripting

**Cost Warnings:**
- Pods: Clearly warn that stopping doesn't stop billing
- Pods: Show estimated daily/monthly costs
- Serverless: Show per-execution costs
- Both: Recommend spot instances for cost savings

### 10. Unified Configuration Strategy

**Single `.env` File Controls Everything:**

The system uses **one `.env` file** to control all optional features (OpenZiti, SSH, storage, etc.) in both local and production environments.

**File Locations (checked in order):**
1. `/runpod-volume/.env` - RunPod network storage (production)
2. `/workspace/.env` - Local workspace (development)
3. If neither exists: Use defaults (no OpenZiti, no SSH)

**Feature Enablement:**
- **OpenZiti Tunnel**: Enabled if `OPENZITI_IDENTITY` or `OPENZITI_IDENTITY_JSON` is set
- **SSH Server**: Enabled if `ENABLE_SSH=true` AND `SSH_PUBLIC_KEY` is set
- **S3 Storage**: Enabled if `S3_BUCKET` and credentials are set

**Security Model:**
- `.env` file contains secrets (never committed to Git, in `.gitignore`)
- `.env.example` is a template (committed, no secrets)
- Docker image does NOT include `.env` file
- `.env` is loaded at runtime from storage or local mount
- Same `.env` file works in local and production

**Feature Matrix (based on .env contents):**

| .env Variable | Feature Enabled | Works In |
|---------------|----------------|----------|
| `OPENZITI_IDENTITY` or `OPENZITI_IDENTITY_JSON` | OpenZiti tunnel | Local + Production |
| `ENABLE_SSH=true` + `SSH_PUBLIC_KEY` | SSH server | Local + Production |
| `S3_BUCKET` + credentials | S3 output storage | Production |
| None of the above | Basic operation only | Local + Production |

**Deployment Workflow:**

**Local Development:**
```bash
# Create .env with your secrets
cp .env.example .env
# Edit .env with your actual keys
nano .env
# Add to .gitignore (already there)
echo ".env" >> .gitignore
# Run locally
docker-compose up
```

**RunPod Production:**
```bash
# Upload .env to network storage
# Option 1: Via RunPod web UI (upload to network volume)
# Option 2: Via SSH (if already running)
scp .env root@pod:/runpod-volume/.env
# Option 3: Via RunPod API
# The container will automatically load it on startup
```

### 11. Configuration Files

**`runpod-config-serverless.json`**: RunPod serverless template configuration
```json
{
  "name": "comfyui-serverless",
  "image": "ghcr.io/[username]/comfyui-serverless:latest",
  "gpu_type_id": "NVIDIA RTX A4000",
  "container_disk_in_gb": 50,
  "volume_in_gb": 100,
  "volume_mount_path": "/runpod-volume",
  "env": {
    "MODE": "serverless",
    "COMFYUI_PORT": "8188",
    "COMFYUI_ARGS": "--use-sage-attention --lowvram"
  }
}
```

**`runpod-config-pods.json`**: RunPod pods template configuration
```json
{
  "name": "comfyui-serverless",
  "image": "ghcr.io/[username]/comfyui-serverless:latest",
  "gpu_type_id": "NVIDIA RTX A4000",
  "container_disk_in_gb": 50,
  "volume_in_gb": 100,
  "volume_mount_path": "/runpod-volume",
  "env": {
    "MODE": "serverless",
    "COMFYUI_PORT": "8188",
    "COMFYUI_ARGS": "--use-sage-attention --lowvram",
    "ENABLE_SSH": "true",
    "SSH_PUBLIC_KEY": "ssh-rsa AAAA..."
  },
  "docker_args": "",
  "start_ssh": false
}
```

**`.env.example`**: Environment variables template (commit this)
```bash
# Operating Mode (auto-detected if not set)
# MODE=local  # or "serverless"

# ComfyUI Configuration
COMFYUI_PORT=8188
COMFYUI_ARGS=--use-sage-attention --lowvram

# SSH Configuration (optional - enables SSH if present)
# ENABLE_SSH=true
# SSH_PUBLIC_KEY=ssh-rsa AAAA...your-public-key-here

# OpenZiti Configuration (optional - enables tunnel if present)
# OPENZITI_IDENTITY=/runpod-volume/ziti-identity.json
# OPENZITI_CONTROLLER=https://controller.example.com:443
# OPENZITI_SERVICE_HTTP=comfyui-http
# OPENZITI_SERVICE_SSH=comfyui-ssh
# Or embed identity directly:
# OPENZITI_IDENTITY_JSON='{"zt":"...","id":"..."}'

# Output Storage Configuration (optional)
# Choose one of the following storage methods for generated outputs:

# Option 1: Network Volume Storage (recommended for RunPod)
# Stores outputs to /runpod-volume/outputs - persists across runs
# STORAGE_TYPE=volume
# VOLUME_OUTPUT_PATH=/runpod-volume/outputs

# Option 2: S3/Cloud Storage
# Uploads outputs to S3-compatible storage and returns URLs
# STORAGE_TYPE=s3
# S3_BUCKET=my-comfyui-outputs
# S3_ACCESS_KEY=...
# S3_SECRET_KEY=...
# S3_REGION=us-east-1
# S3_ENDPOINT_URL=https://...  # Optional: for S3-compatible services (R2, MinIO, etc.)

# Option 3: Return in Response (default if not configured)
# Base64 encodes images in API response - limited to ~10MB total

# GitHub Container Registry (for building only)
# GITHUB_USERNAME=your-username
# GITHUB_TOKEN=ghp_...
```

**Actual `.env` file (NEVER commit - add to .gitignore):**
```bash
# This file contains SECRETS - keep it secure!
# Place in: ./runpod-serverless/.env (local) or /runpod-volume/.env (RunPod)

# SSH Configuration - Uncomment to enable SSH in production
ENABLE_SSH=true
SSH_PUBLIC_KEY=ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC... your-actual-key

# OpenZiti Configuration - Uncomment to enable tunnel in production
OPENZITI_IDENTITY_JSON='{"zt":"actual-token","id":"actual-id",...}'
OPENZITI_CONTROLLER=https://your-controller.example.com:443
OPENZITI_SERVICE_HTTP=comfyui-http-prod
OPENZITI_SERVICE_SSH=comfyui-ssh-prod
```

**`.github/workflows/build-and-push.yml`**: GitHub Actions for CI/CD (optional)
```yaml
# Automated build and push on git push
# Build Docker image
# Authenticate with ghcr.io
# Push image with tags (latest, commit SHA)
```

## Data Models

### Job Input Schema

```python
{
    "workflow": {
        # ComfyUI workflow JSON structure
        "1": {
            "inputs": {...},
            "class_type": "CheckpointLoaderSimple",
            "_meta": {...}
        },
        # ... more nodes
    },
    "input_images": {
        # Optional: base64 encoded images
        "image1.png": "base64_encoded_data...",
    },
    "config": {
        "return_outputs": true,  # Return images in response vs upload to storage
        "output_format": "png",  # Output image format
        "timeout": 300,  # Max execution time in seconds
    }
}
```

### Job Output Schema

```python
{
    "status": "success",  # or "error"
    "output": {
        "images": [
            {
                "filename": "ComfyUI_00001_.png",
                "data": "base64_encoded_image...",  # if return_outputs=true
                "url": "https://storage.../image.png",  # if uploaded to storage
                "type": "output"
            }
        ]
    },
    "metadata": {
        "prompt_id": "uuid-here",
        "execution_time": 45.2,
        "node_count": 12,
        "gpu_used": "NVIDIA RTX A4000"
    },
    "message": "Workflow executed successfully"
}
```

## Error Handling

### Error Categories

1. **Validation Errors** (HTTP 400 equivalent)
   - Invalid workflow JSON structure
   - Missing required nodes
   - Invalid node parameters
   - Unsupported node types

2. **Execution Errors** (HTTP 500 equivalent)
   - ComfyUI server failed to start
   - Workflow execution failed
   - Out of memory errors
   - Model loading failures

3. **Timeout Errors** (HTTP 408 equivalent)
   - Workflow execution exceeded timeout
   - Model download timeout

4. **Resource Errors** (HTTP 507 equivalent)
   - Insufficient GPU memory
   - Disk space exhausted

### Error Response Format

```python
{
    "status": "error",
    "error": {
        "code": "WORKFLOW_EXECUTION_FAILED",
        "message": "Node 'KSampler' failed: CUDA out of memory",
        "details": {
            "node_id": "3",
            "node_type": "KSampler",
            "traceback": "..."
        }
    },
    "metadata": {
        "execution_time": 12.5,
        "failed_at": "2025-10-08T21:45:00Z"
    }
}
```

### Error Handling Strategy

- **Retry Logic**: Implement exponential backoff for transient failures
- **Graceful Degradation**: Return partial results if some outputs succeeded
- **Detailed Logging**: Log all errors to RunPod logs for debugging
- **User-Friendly Messages**: Translate technical errors to actionable messages

## Storage Strategy

### Model Storage

**Option 1: Baked into Image** (Recommended for small models)
- Pre-download models during Docker build
- Faster cold starts
- Larger image size
- Best for: Essential models under 10GB total

**Option 2: RunPod Network Volume** (Recommended for large model libraries)
- Mount persistent volume at `/comfyui/models`
- Shared across all serverless instances
- Slower first cold start, fast subsequent starts
- Best for: Large model collections (>10GB)

**Option 3: Download on Demand**
- Download models from HuggingFace/CivitAI on first use
- Slowest cold start
- Most flexible
- Best for: Testing or rarely-used models

### Output Storage

The system supports three output storage strategies, configured via `STORAGE_TYPE` environment variable:

**Option 1: Network Volume Storage** (Recommended for RunPod)
- Save outputs to `/runpod-volume/outputs` or custom path
- Outputs persist across serverless runs
- No external service dependencies
- Access via SSH or subsequent jobs
- No size limits (within volume capacity)
- Configuration:
  ```bash
  STORAGE_TYPE=volume
  VOLUME_OUTPUT_PATH=/runpod-volume/outputs
  ```
- Best for: Persistent storage, batch processing, debugging, building output galleries

**Option 2: S3/Cloud Storage**
- Upload outputs to S3, R2, or S3-compatible storage
- Return public URLs in response
- Supports large outputs and CDN integration
- Requires storage credentials
- Configuration:
  ```bash
  STORAGE_TYPE=s3
  S3_BUCKET=my-comfyui-outputs
  S3_ACCESS_KEY=...
  S3_SECRET_KEY=...
  S3_REGION=us-east-1
  S3_ENDPOINT_URL=https://...  # Optional for R2, MinIO, etc.
  ```
- Best for: Public sharing, long-term archival, integration with other services

**Option 3: Return in Response** (Default)
- Base64 encode images in JSON response
- Simple implementation, no configuration needed
- Limited by response size (typically 10MB max)
- Best for: Single images or small outputs, immediate results

## Testing Strategy

### Unit Tests

Test individual components in isolation:

1. **Handler Function Tests**
   - Test input validation
   - Test error handling
   - Mock ComfyUI API responses

2. **ComfyUI Client Tests**
   - Test API communication
   - Test image upload/download
   - Test workflow submission

3. **Utility Function Tests**
   - Test base64 encoding/decoding
   - Test file cleanup
   - Test configuration parsing

### Integration Tests

Test component interactions:

1. **Local Container Tests**
   - Run container locally with test workflows
   - Verify outputs match expected results
   - Test error scenarios

2. **ComfyUI Integration Tests**
   - Test with real ComfyUI server
   - Test various workflow types
   - Test with different models

### End-to-End Tests

Test complete serverless deployment:

1. **RunPod Deployment Tests**
   - Deploy to RunPod test environment
   - Submit test jobs via API
   - Verify results and timing
   - Test concurrent job handling

2. **Performance Tests**
   - Measure cold start time
   - Measure warm start time
   - Measure execution time for various workflows
   - Test GPU utilization

### Test Workflows

Create sample workflows for testing:

1. **Simple Text-to-Image**: Basic checkpoint + KSampler
2. **Image-to-Image**: With ControlNet
3. **Multi-Output**: Generate multiple images
4. **Complex Pipeline**: LoRA + ControlNet + Upscaling
5. **Error Cases**: Invalid nodes, missing models

## GitHub Container Registry Setup

### Authentication

**Personal Access Token (PAT)**:
1. Create GitHub PAT with `write:packages` and `read:packages` scopes
2. Store as environment variable: `GITHUB_TOKEN`
3. Login: `echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin`

**GitHub Actions**:
- Use `GITHUB_TOKEN` secret (automatically available)
- No manual authentication needed

### Image Naming Convention

```
ghcr.io/[github-username]/comfyui-serverless:[tag]
```

**Tags:**
- `latest`: Most recent build
- `v1.0.0`: Semantic version tags
- `sha-abc123`: Git commit SHA for traceability

### Visibility

- **Public**: Free, no authentication needed to pull
- **Private**: Requires authentication, use for proprietary setups

**RunPod Configuration for Private Images:**
```json
{
  "registry_auth": {
    "username": "github-username",
    "password": "github-pat-token"
  }
}
```

## ComfyUI WebUI Access in All Modes

### WebUI Availability Requirement

**The ComfyUI WebUI MUST be running and accessible in ALL modes.** This is enforced by:

1. **Entrypoint Script**: Always starts ComfyUI with `--listen 0.0.0.0`
2. **Health Check**: Waits for WebUI to be ready before proceeding
3. **Background Process**: Runs in background so it doesn't block other services
4. **Port Configuration**: Uses COMFYUI_PORT (default: 8188)

### Access Methods by Mode

**Local Mode:**
```bash
# Direct HTTP access
http://localhost:8188

# Or via OpenZiti tunnel (if configured)
http://comfyui-http.ziti
```

**Serverless Mode (RunPod):**
```bash
# Option 1: RunPod HTTP Proxy (automatic)
https://<pod-id>-8188.proxy.runpod.net

# Option 2: OpenZiti Tunnel (if configured in .env)
http://comfyui-http.ziti

# Option 3: SSH Tunnel
ssh -L 8188:localhost:8188 root@<pod-id>.runpod.io
# Then browse: http://localhost:8188

# Option 4: Direct access (if RunPod exposes port)
http://<pod-ip>:8188
```

### WebUI + Handler Coexistence (Serverless Mode)

In serverless mode, both the WebUI and handler run simultaneously:

```
┌─────────────────────────────────────┐
│  ComfyUI Server (port 8188)         │
│  ├─ WebUI (browser access)          │
│  └─ API (handler access)            │
└─────────────────────────────────────┘
         ↓                    ↓
    User Browser         RunPod Handler
    (manual testing)     (automated jobs)
```

**Benefits:**
- Test workflows manually via WebUI before automating
- Debug handler issues by watching WebUI in real-time
- Develop workflows in serverless environment
- Monitor job execution visually

### Implementation Details

**Entrypoint Script Ensures:**
```bash
# Start ComfyUI with external access
python /comfyui/main.py --listen 0.0.0.0 --port $COMFYUI_PORT &

# Wait for WebUI to be ready
while ! curl -s http://127.0.0.1:$COMFYUI_PORT/ > /dev/null; do
    sleep 1
done

# Log access information
log_success "ComfyUI WebUI is running at http://0.0.0.0:$COMFYUI_PORT"
```

**Docker Configuration Ensures:**
- Port 8188 is exposed in Dockerfile
- Port mapping in docker-compose.yml (local mode)
- RunPod automatically proxies exposed ports (serverless mode)

## Performance Optimizations

### Cold Start Optimization

1. **Layer Caching**: Order Dockerfile to maximize layer reuse
2. **Model Pre-loading**: Bake common models into image
3. **Minimal Base Image**: Remove unnecessary dependencies
4. **Parallel Downloads**: Download models concurrently during build

### Execution Optimization

1. **Keep-Warm Strategy**: Configure RunPod to keep 1+ instances warm
2. **GPU Selection**: Choose appropriate GPU for workload
3. **Memory Management**: Use `--lowvram` or `--use-sage-attention` flags
4. **Batch Processing**: Process multiple prompts in single job when possible

### Cost Optimization

1. **Timeout Configuration**: Set appropriate timeouts to avoid runaway costs
2. **Auto-Scaling**: Configure max concurrent instances
3. **Spot Instances**: Use spot pricing when available
4. **Model Sharing**: Use network volumes to share models across instances

## Deployment Workflow

### Development Cycle

1. **Local Development**
   ```bash
   # Build image locally
   ./build.sh --local
   
   # Test locally
   ./test_local.sh
   ```

2. **Push to Registry**
   ```bash
   # Build and push to ghcr.io
   ./build.sh --push
   ```

3. **Deploy to RunPod**
   ```bash
   # Update RunPod template
   ./deploy.sh --template-id YOUR_TEMPLATE_ID
   ```

4. **Test in Production**
   ```bash
   # Submit test job
   python test_runpod.py --endpoint YOUR_ENDPOINT_ID
   ```

### CI/CD Pipeline (Optional)

```
Git Push → GitHub Actions → Build Image → Push to ghcr.io → Update RunPod Template
```

## Migration from Docker Compose

### Key Differences

| Aspect | Docker Compose | RunPod Serverless |
|--------|----------------|-------------------|
| **Lifecycle** | Always running | On-demand |
| **Scaling** | Manual | Automatic |
| **Cost** | Fixed (24/7) | Pay-per-use |
| **State** | Persistent | Ephemeral |
| **Volumes** | Local mounts | Network volumes or baked-in |
| **Access** | Direct port access | API endpoint |

### Migration Checklist

- [ ] Convert persistent volumes to network volumes or baked-in models
- [ ] Replace direct API access with job submission pattern
- [ ] Handle stateless execution (no persistent data between jobs)
- [ ] Update client code to use RunPod API instead of direct ComfyUI API
- [ ] Configure appropriate timeouts for workflows
- [ ] Set up monitoring and logging
- [ ] Test cold start performance
- [ ] Validate cost projections

## SSH Server Best Practices for RunPod

### When to Use SSH

**Development and Debugging:**
- Installing additional Python packages to network storage
- Debugging workflow execution issues
- Inspecting model files and custom nodes
- Testing configurations before deployment
- Modifying files in network storage

**Not Recommended For:**
- Production serverless execution (adds overhead)
- Public-facing deployments (security risk)
- Automated workflows (use API instead)

### SSH Access Patterns

**1. Development Mode (Recommended)**
- Enable SSH in local Docker Compose for development
- Use SSH to install packages: `pip install --target=/runpod-volume/python-packages <package>`
- Test configurations before deploying to RunPod
- Disable SSH for production serverless deployments

**2. RunPod Debugging Mode**
- Enable SSH temporarily for debugging specific issues
- Use OpenZiti tunnel for secure access without exposing ports
- Disable SSH after debugging is complete

**3. Network Storage Management**
- SSH into RunPod instance to manage network storage
- Install packages that persist across container restarts
- Organize models and custom nodes
- Clean up temporary files

### Installing Python Packages via SSH

**To Network Storage (Persists):**
```bash
# SSH into container
ssh root@<endpoint>

# Install to network storage
pip install --target=/runpod-volume/python-packages <package>

# Add to Python path in entrypoint.sh
export PYTHONPATH="/runpod-volume/python-packages:$PYTHONPATH"
```

**To Container (Ephemeral):**
```bash
# SSH into container
ssh root@<endpoint>

# Install normally (lost on container restart)
pip install <package>
```

### SSH Security Recommendations

1. **Always use public key authentication** - Never enable password auth
2. **Use OpenZiti tunnel when possible** - Avoid exposing SSH publicly
3. **Rotate SSH keys regularly** - Update authorized_keys periodically
4. **Disable SSH in production** - Only enable for debugging
5. **Use RunPod's built-in SSH** - For quick access without custom setup
6. **Limit SSH access** - Use firewall rules or VPN when not using OpenZiti

## Security Considerations

1. **API Authentication**: Use RunPod API keys, never expose publicly
2. **Input Validation**: Sanitize all user inputs to prevent injection attacks
3. **Resource Limits**: Set memory and timeout limits to prevent abuse
4. **Registry Access**: Use private registry for proprietary models/code
5. **Secrets Management**: Use environment variables for sensitive data, store OpenZiti identities in network storage
6. **Network Isolation**: RunPod containers are isolated by default
7. **SSH Security**: Use public key auth only, disable password authentication
8. **OpenZiti Security**: Use OpenZiti for secure tunneling instead of exposing ports publicly

## Monitoring and Logging

### Metrics to Track

- Cold start time
- Warm start time
- Execution time per workflow
- Success/failure rate
- GPU utilization
- Memory usage
- Cost per job

### Logging Strategy

- Use Python `logging` module
- Log to stdout (captured by RunPod)
- Include job ID in all log messages
- Log key events: start, workflow submission, completion, errors
- Structured logging (JSON) for easier parsing

### Example Log Format

```json
{
  "timestamp": "2025-10-08T21:45:00Z",
  "job_id": "uuid-here",
  "level": "INFO",
  "message": "Workflow execution started",
  "metadata": {
    "node_count": 12,
    "gpu": "NVIDIA RTX A4000"
  }
}
```

## Future Enhancements

1. **Webhook Support**: Notify external services on job completion
2. **Batch Processing**: Process multiple workflows in single job
3. **Streaming Outputs**: Stream intermediate results during generation
4. **Model Caching**: Intelligent model loading/unloading
5. **Multi-GPU Support**: Distribute workflow across multiple GPUs
6. **Custom Node Support**: Dynamic custom node installation
7. **Workflow Validation**: Pre-validate workflows before execution
8. **Cost Estimation**: Estimate cost before job submission
