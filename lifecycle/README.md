# RunPod Lifecycle Management Tools

Command-line tools for managing RunPod Pods (persistent servers) and Serverless endpoints without using the web UI.

## Prerequisites

1. **RunPod API Key**: Get your API key from [RunPod Settings](https://www.runpod.io/console/user/settings)
2. **Set Environment Variable**:
   ```bash
   export RUNPOD_API_KEY=your_api_key_here
   ```
   Or add to your `.env` file:
   ```bash
   RUNPOD_API_KEY=your_api_key_here
   ```

3. **Install Dependencies**:
   ```bash
   cd runpod-comfy
   uv sync
   ```

## RunPod Pods Management

Manage persistent RunPod servers (Pods). **WARNING: Stopping a pod does NOT stop billing! You must TERMINATE to stop charges.**

### Commands

#### Create a Pod

Create a new persistent server:

```bash
# Create a spot instance (cheaper, can be interrupted)
uv run python lifecycle/runpod_pods.py create \
  --name comfyui-dev \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --spot

# Create with network volume attached
uv run python lifecycle/runpod_pods.py create \
  --name comfyui-dev \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --spot \
  --volume-id abc123xyz \
  --volume-mount /runpod-volume

# Create with environment variables
uv run python lifecycle/runpod_pods.py create \
  --name comfyui-dev \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --spot \
  --env MODE=pods \
  --env ENABLE_SSH=true

# Create with exposed ports
uv run python lifecycle/runpod_pods.py create \
  --name comfyui-dev \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --spot \
  --ports "8188/http,22/tcp"
```

**Options:**
- `--name`: Pod name (required)
- `--gpu`: GPU type (required) - e.g., "RTX A4000", "RTX 4090", "A100 40GB"
- `--image`: Docker image URL (required)
- `--spot`: Use spot instance (cheaper but can be interrupted)
- `--volume-id`: Network volume ID to attach
- `--volume-mount`: Volume mount path (default: /runpod-volume)
- `--env`: Environment variables (can be used multiple times)
- `--ports`: Ports to expose (e.g., "8188/http,22/tcp")

#### List All Pods

```bash
uv run python lifecycle/runpod_pods.py list

# JSON output for scripting
uv run python lifecycle/runpod_pods.py list --json
```

#### Get Pod Status

```bash
uv run python lifecycle/runpod_pods.py status --pod-id xyz789

# JSON output
uv run python lifecycle/runpod_pods.py status --pod-id xyz789 --json
```

#### Start a Stopped Pod

Resume a stopped pod (billing resumes):

```bash
uv run python lifecycle/runpod_pods.py start --pod-id xyz789
```

#### Stop a Pod

**⚠️ WARNING: Stopping does NOT stop billing!**

```bash
uv run python lifecycle/runpod_pods.py stop --pod-id xyz789
```

The tool will warn you that billing continues. Use `terminate` instead to stop charges.

#### Terminate a Pod

Delete the pod and stop billing (network volumes remain intact):

```bash
uv run python lifecycle/runpod_pods.py terminate --pod-id xyz789
```

### Cost Estimates

The tool provides cost estimates when creating pods:

```
Estimated Cost: $0.40/hour
Daily (24h): $9.60
Monthly (30d): $288.00

⚠️  WARNING: Stopping a pod does NOT stop billing!
⚠️  You must TERMINATE the pod to stop charges.
```

### Spot vs On-Demand

- **Spot Instances**: ~50% cheaper but can be interrupted
- **On-Demand**: More expensive but guaranteed availability

Use `--spot` flag for spot instances (recommended for development).

## RunPod Serverless Management

Manage serverless endpoints (pay-per-execution).

### Commands

#### Create an Endpoint

```bash
# Create a serverless endpoint
uv run python lifecycle/runpod_serverless.py create \
  --name comfyui-api \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest

# Create with custom scaling
uv run python lifecycle/runpod_serverless.py create \
  --name comfyui-api \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --min-workers 0 \
  --max-workers 5 \
  --idle-timeout 10

# Create with network volume
uv run python lifecycle/runpod_serverless.py create \
  --name comfyui-api \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --volume-id abc123xyz \
  --volume-mount /runpod-volume

# Create with environment variables
uv run python lifecycle/runpod_serverless.py create \
  --name comfyui-api \
  --gpu "RTX A4000" \
  --image ghcr.io/username/comfyui-serverless:latest \
  --env MODE=serverless \
  --env STORAGE_TYPE=s3
```

**Options:**
- `--name`: Endpoint name (required)
- `--gpu`: GPU type (required)
- `--image`: Docker image URL (required)
- `--min-workers`: Minimum workers (default: 0 = scale to zero)
- `--max-workers`: Maximum workers (default: 3)
- `--idle-timeout`: Minutes before scaling down (default: 5)
- `--volume-id`: Network volume ID to attach
- `--volume-mount`: Volume mount path (default: /runpod-volume)
- `--env`: Environment variables (can be used multiple times)

#### List All Endpoints

```bash
uv run python lifecycle/runpod_serverless.py list

# JSON output
uv run python lifecycle/runpod_serverless.py list --json
```

#### Get Endpoint Status

```bash
uv run python lifecycle/runpod_serverless.py status --endpoint-id xyz789

# JSON output
uv run python lifecycle/runpod_serverless.py status --endpoint-id xyz789 --json
```

#### Invoke an Endpoint

Submit a workflow to the endpoint:

```bash
# Invoke with workflow file
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id xyz789 \
  --workflow examples/text_to_image_simple.json

# Invoke and wait for completion
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id xyz789 \
  --workflow examples/text_to_image_simple.json \
  --wait

# Invoke with custom timeout
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id xyz789 \
  --workflow workflow.json \
  --wait \
  --timeout 600

# Invoke with inline JSON
uv run python lifecycle/runpod_serverless.py invoke \
  --endpoint-id xyz789 \
  --workflow-json '{"prompt": "a cat"}'
```

**Options:**
- `--endpoint-id`: Endpoint ID (required)
- `--workflow`: Path to workflow JSON file
- `--workflow-json`: Workflow JSON string
- `--wait`: Wait for job completion
- `--timeout`: Timeout in seconds (default: 300)

#### Update an Endpoint

```bash
uv run python lifecycle/runpod_serverless.py update \
  --endpoint-id xyz789 \
  --min-workers 1 \
  --max-workers 5 \
  --idle-timeout 10
```

#### Delete an Endpoint

```bash
uv run python lifecycle/runpod_serverless.py delete --endpoint-id xyz789
```

### Cost Estimates

The tool provides cost estimates when creating endpoints:

```
Estimated Cost:
  Per execution (1 min): ~$0.0100
  Per hour (60 exec): ~$0.60
  Per day (1440 exec): ~$14.40

💡 Serverless = Pay only for execution time
```

## JSON Output Mode

All commands support `--json` flag for scripting:

```bash
# Get pod list as JSON
uv run python lifecycle/runpod_pods.py list --json | jq '.[] | {id, name, status}'

# Get endpoint status as JSON
uv run python lifecycle/runpod_serverless.py status --endpoint-id xyz789 --json
```

## Common Workflows

### Development Workflow (Pods)

1. **Create a spot instance pod for development**:
   ```bash
   uv run python lifecycle/runpod_pods.py create \
     --name dev-pod \
     --gpu "RTX A4000" \
     --image ghcr.io/username/comfyui-serverless:latest \
     --spot \
     --volume-id abc123 \
     --env MODE=pods \
     --env ENABLE_SSH=true
   ```

2. **Work on your pod** (access via RunPod UI or SSH)

3. **Terminate when done** (stops billing):
   ```bash
   uv run python lifecycle/runpod_pods.py terminate --pod-id xyz789
   ```

4. **Create a new pod later** (reattach same volume):
   ```bash
   uv run python lifecycle/runpod_pods.py create \
     --name dev-pod-2 \
     --gpu "RTX A4000" \
     --image ghcr.io/username/comfyui-serverless:latest \
     --spot \
     --volume-id abc123
   ```

### Production Workflow (Serverless)

1. **Create a serverless endpoint**:
   ```bash
   uv run python lifecycle/runpod_serverless.py create \
     --name prod-api \
     --gpu "RTX A4000" \
     --image ghcr.io/username/comfyui-serverless:latest \
     --volume-id abc123
   ```

2. **Test the endpoint**:
   ```bash
   uv run python lifecycle/runpod_serverless.py invoke \
     --endpoint-id xyz789 \
     --workflow examples/text_to_image_simple.json \
     --wait
   ```

3. **Monitor status**:
   ```bash
   uv run python lifecycle/runpod_serverless.py status --endpoint-id xyz789
   ```

4. **Scale up for production**:
   ```bash
   uv run python lifecycle/runpod_serverless.py update \
     --endpoint-id xyz789 \
     --min-workers 1 \
     --max-workers 10
   ```

## Cost Optimization Tips

### For Pods

1. **Always terminate when not in use** - Stopping doesn't stop billing!
2. **Use spot instances** - 50% cheaper than on-demand
3. **Attach network volumes** - Persist data across pod lifecycles
4. **Monitor uptime** - Check status regularly to avoid forgotten pods

### For Serverless

1. **Set min-workers to 0** - Scale to zero when idle (no charges)
2. **Optimize cold start** - Pre-download models to network volume
3. **Batch requests** - Process multiple workflows per execution
4. **Set appropriate idle timeout** - Balance between cold starts and idle costs

## Troubleshooting

### Authentication Errors

```bash
ERROR: RUNPOD_API_KEY not found in environment or arguments
```

**Solution**: Set your API key:
```bash
export RUNPOD_API_KEY=your_key_here
```

### Pod Creation Fails

**Check**:
- GPU type is valid (use RunPod UI to see available GPUs)
- Image URL is correct and accessible
- Network volume ID exists (if specified)

### Endpoint Invocation Fails

**Check**:
- Endpoint is in "RUNNING" state
- Workflow JSON is valid
- Image has the handler code installed

## API Key Security

**Never commit your API key to Git!**

Add to `.gitignore`:
```
.env
*.key
```

Store in `.env` file:
```bash
RUNPOD_API_KEY=your_key_here
```

Or use environment variable:
```bash
export RUNPOD_API_KEY=your_key_here
```

## Additional Resources

- [RunPod Documentation](https://docs.runpod.io/)
- [RunPod API Reference](https://docs.runpod.io/reference/api)
- [RunPod Pricing](https://www.runpod.io/pricing)
- [GPU Comparison](https://www.runpod.io/console/gpu-cloud)

## Support

For issues with these tools, check:
1. RunPod API status
2. Your API key permissions
3. Network connectivity
4. Docker image availability

For RunPod platform issues, contact [RunPod Support](https://www.runpod.io/support).
